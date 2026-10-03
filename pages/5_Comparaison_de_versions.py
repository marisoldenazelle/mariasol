"""
Suivi d'un texte à travers ses versions.

Ce que cette page sert à faire : suivre un texte de la proposition de la
Commission jusqu'au dernier compromis, savoir ce qui a bougé, où, et si le
changement porte à conséquence.

L'appariement des articles et le calcul des écarts sont déterministes ; le
modèle n'intervient qu'ensuite, pour qualifier la portée d'un écart déjà
constaté — jamais pour dire s'il y a eu changement.

Trois entrées, dans l'ordre où on s'en sert :

1. **Le fil du texte** — toutes les versions chargées d'un même dossier, dans
   l'ordre, et l'évolution d'un article donné à travers toutes ces versions.
   C'est ce qui manquait : un omnibus ne se suit pas deux versions à la fois.
2. **Les changements majeurs** — ce qui a bougé entre deux versions, trié par
   ce qui compte, avec accès direct au texte modifié.
3. **Les cartes** et le **détail article par article**, pour aller au mot près.
"""

from __future__ import annotations

import io
import time

import pandas as pd
import streamlit as st

from core import modificatif, store
from core.config import CORPUS_DIR, __version__
from core.diff import (CHANGE_LABEL, compare, ecart_hors_champ, ecart_mots,
                       evolution_article, qualify, rendu_mot_a_mot,
                       summary_table)
from core.ingest import read_pages
from core.duree import CADENCE_QUALIFICATION, avancement, duree_estimee
from core.ingest import VERSION_KINDS
from core.labels import label_fragment
from core.llm import get_client
from core.fiabilite import versions as alertes_versions
from core.report import note_omnibus_docx
from core.ui import (carte_modificatif, comment_ca_marche, entete_module,
                     panneau_fiabilite, pour_aller_plus_loin)
from core.viz import (STATUS, change_bars, change_scatter, change_treemap)


def _article_clique(evenement, connus: set[str]) -> str:
    """Retrouve l'article cliqué dans un événement de sélection Plotly.

    La forme de l'événement dépend du type de trace : une tuile de treemap
    porte l'intitulé dans `label`, une barre dans `y`, un point de nuage dans
    `customdata`. Plutôt que de coder une lecture par type de graphique — qui
    casse au premier changement de figure — on ratisse les champs plausibles
    et on ne retient que ce qui correspond à un article connu.
    """
    selection = getattr(evenement, "selection", None)
    if selection is None and hasattr(evenement, "get"):
        selection = evenement.get("selection")
    points = (selection or {}).get("points", []) if selection else []

    for point in points:
        candidats: list = []
        for champ in ("label", "y", "text", "hovertext", "x"):
            candidats.append(point.get(champ) if hasattr(point, "get") else None)
        donnees = point.get("customdata") if hasattr(point, "get") else None
        if isinstance(donnees, (list, tuple)):
            candidats.extend(donnees)
        elif donnees is not None:
            candidats.append(donnees)
        for valeur in candidats:
            if isinstance(valeur, str) and valeur in connus:
                return valeur
    return ""


def _repere(row) -> str:
    """Repère de version lisible : nature, date, intitulé libre."""
    morceaux = []
    kind = row.get("version_kind") or ""
    if kind and kind in VERSION_KINDS and kind != "autre":
        morceaux.append(VERSION_KINDS[kind])
    date = row.get("version_date") or ""
    if date:
        morceaux.append(date)
    libre = row.get("version_label") or ""
    if libre:
        morceaux.append(str(libre))
    return " · ".join(morceaux) if morceaux else "repère de version non renseigné"


entete_module(
    "Comment ce texte a-t-il évolué ?",
    "L'appariement des articles et le calcul des écarts sont déterministes. Le "
    "modèle n'intervient qu'ensuite, pour qualifier la portée d'un écart déjà "
    "constaté, jamais pour dire s'il y a eu changement.")

docs = store.list_documents()
if len(docs) < 2:
    st.info(
        "Il faut au moins deux documents au corpus pour suivre un texte. "
        "Chargez-les depuis la **Bibliothèque**, en renseignant leur nature "
        "(proposition de la Commission, compromis de la présidence…) et leur "
        "date, qui servent à les ordonner."
    )
    st.stop()

# Le type de document oriente le tri mais n'exclut plus rien : un texte mal
# classé au chargement restait invisible ici, alors qu'il était dans la base.
kinds = docs.get("kind", pd.Series(dtype=str))
docs = docs.assign(
    _prio=(kinds != "legal_text").astype(int),
    _date=docs.get("version_date", pd.Series([""] * len(docs))).fillna(""))
ordre = docs.sort_values(["_prio", "_date", "name"])
index_docs = docs.set_index("id")


def etiquette(i: str) -> str:
    row = index_docs.loc[i]
    marque = "" if row.get("kind") == "legal_text" else "  ·  autre type"
    return f"{row['name'][:60]} · {_repere(row)}{marque}"


# --------------------------------------------------------------------- dossier
# Le dossier est un CONFORT d'affichage, pas un filtre bloquant : un omnibus
# modifie plusieurs textes à la fois, et le texte de départ et le texte
# d'arrivée n'appartiennent pas toujours au même dossier. Les deux listes de
# sélection portent donc toujours sur l'ensemble du corpus.
dossiers = sorted({d for d in docs["dossier"].fillna("") if d})
dossier = st.selectbox(
    "Dossier mis en avant (facultatif)", ["— tous les documents —"] + dossiers,
    help="Sert à trier le fil du texte et à remonter ces documents en tête "
         "des listes. Vous pouvez toujours comparer deux documents de "
         "dossiers différents.")

pool = ordre                       # toujours tout le corpus
if not dossier.startswith("—"):
    # Les documents du dossier passent devant, les autres restent accessibles.
    pool = ordre.assign(_du_dossier=(ordre["dossier"] != dossier).astype(int)) \
                .sort_values(["_du_dossier", "_prio", "_date", "name"])
    if (pool["_du_dossier"] == 0).sum() < 2:
        st.caption(
            "Ce dossier ne contient pas deux versions : les listes ci-dessous "
            "restent ouvertes à tout le corpus.")

# ================================================= choix du couple à comparer
# Aucune paire par défaut, volontairement. Une comparaison lancée d'office sur
# les deux premiers documents du corpus produit un écran plein de chiffres qui
# ne répondent à aucune question posée — et rien ne le signale à l'écran.
st.markdown("### Quels textes comparer ?")
st.caption(
    "N'importe quels deux documents du corpus, quel que soit leur dossier ou "
    "leur type : proposition de la Commission, compromis de présidence non "
    "publié, texte du Journal officiel, ou document de travail interne.")

VIDE = ""
c1, c2 = st.columns(2)
old_id = c1.selectbox(
    "Version de départ (la plus ancienne)", options=[VIDE] + list(pool["id"]),
    index=0,
    format_func=lambda i: "— choisir un texte —" if i == VIDE else etiquette(i))
new_id = c2.selectbox(
    "Version d'arrivée (celle qu'on examine)", options=[VIDE] + list(pool["id"]),
    index=0,
    format_func=lambda i: "— choisir un texte —" if i == VIDE else etiquette(i))

# Le piège que cette page doit signaler : comparer un acte modificatif à
# l'un des textes qu'il modifie. L'omnibus ne récrit pas le Data Act, il dit
# ce qu'il faut y changer ; apparier son article 1 à l'article 1 du Data Act
# produit un résultat qui ressemble à une comparaison et n'en est pas une.
@st.cache_data(show_spinner=False)
def _est_acte_modificatif(doc_id: str) -> bool:
    segs = store.load_segments(doc_id)
    if segs is None or segs.empty:
        return False
    return modificatif.est_acte_modificatif(
        "\n".join(str(x) for x in segs["text"]))


pret = bool(old_id) and bool(new_id) and old_id != new_id
if old_id and new_id and old_id == new_id:
    st.warning("Les deux listes désignent le même document.")
elif pret:
    modificatifs = [i for i in (old_id, new_id) if _est_acte_modificatif(i)]
    if len(modificatifs) == 1:
        st.warning(
            "**L'un de ces deux documents est un acte modificatif**, un "
            "omnibus, ou un règlement « portant modification de… ». Il ne "
            "contient pas le texte modifié : il contient les instructions "
            "pour le modifier. Comparer ses articles à ceux d'un autre texte "
            "apparie l'article 1 de l'un avec l'article 1 de l'autre, qui ne "
            "traitent pas du même sujet, le résultat n'a pas de sens.\n\n"
            "**Allez plutôt à l'onglet « Omnibus et actes modificatifs »** : "
            "il lit ces instructions et montre, texte par texte et article "
            "par article, ce que l'omnibus change.",
            icon=":material/rule_settings:")
elif not pret:
    st.caption(
        "Le premier onglet, le fil du texte, fonctionne sans ce choix : il "
        "montre toutes les versions chargées et l'évolution d'un article à "
        "travers chacune. Les autres onglets attendent les deux textes.")

st.divider()

t0, tm, t1, t2, t3, t4 = st.tabs(
    ["Fil du texte", "Omnibus et actes modificatifs", "Changements majeurs",
     "Cartes interactives", "Article par article", "Export"])

# ============================================================== fil du texte
with t0:
    st.info(
        "**Toute la trajectoire du texte, pas seulement le dernier écart.** "
        "En haut, les versions chargées dans l'ordre ; en bas, un article "
        "suivi d'une version à l'autre, avec ce qui a été ajouté et retiré à "
        "chaque étape.", icon=":material/timeline:")

    fil = pool if dossier.startswith("—") else pool[pool["dossier"] == dossier]
    if len(fil) < 2:
        fil = pool
    fil = fil.sort_values(["_date", "imported_at"])
    frise = pd.DataFrame({
        "Version": [r["name"][:52] for _, r in fil.iterrows()],
        "Nature": [VERSION_KINDS.get(r.get("version_kind") or "autre", "—")
                   for _, r in fil.iterrows()],
        "Date": [r.get("version_date") or "—" for _, r in fil.iterrows()],
        "Repère libre": [r.get("version_label") or "—" for _, r in fil.iterrows()],
        "Articles": [int(r.get("n_segments") or 0) for _, r in fil.iterrows()],
    })
    st.dataframe(frise, width="stretch", hide_index=True)
    if (frise["Date"] == "—").all():
        st.caption(
            "Aucune date de version renseignée : l'ordre affiché est celui de "
            "l'import. Renseignez la date dans **Bibliothèque → Corpus**, "
            "elle est détectée automatiquement à l'import, et modifiable.")

    st.divider()
    versions = []
    for _, r in fil.iterrows():
        versions.append({
            "id": r["id"], "name": r["name"],
            "version_kind": r.get("version_kind") or "",
            "version_date": r.get("version_date") or "",
            "segments": store.load_segments(r["id"]),
        })

    sections: dict[str, str] = {}
    for v in versions:
        seg = v["segments"]
        if seg is None or seg.empty:
            continue
        for sid, label in zip(seg["section_id"], seg["section_label"]):
            sections.setdefault(str(sid), str(label))

    if not sections:
        st.warning("Aucun article indexé dans ces versions.")
    else:
        choix = st.selectbox(
            "Article suivi", options=list(sections),
            format_func=lambda s: sections[s])
        etapes = evolution_article(versions, choix)

        chiffres = pd.DataFrame({
            "Version": [e.document_name[:40] for e in etapes],
            "Présent": ["oui" if e.present else "non" for e in etapes],
            "Similarité avec la version précédente": [
                e.similarite if e.similarite is not None else float("nan")
                for e in etapes],
            "Mots ajoutés": [e.mots_ajoutes for e in etapes],
            "Mots retirés": [e.mots_retires for e in etapes],
        })
        st.dataframe(
            chiffres, width="stretch", hide_index=True,
            column_config={
                "Similarité avec la version précédente":
                    st.column_config.ProgressColumn(
                        "Similarité", min_value=0.0, max_value=1.0,
                        format="%.2f")})

        bouges = [e for e in etapes if e.inline_html]
        if not bouges:
            st.success("Cet article n'a pas changé d'une version à l'autre.")
        for e in bouges:
            with st.expander(
                    f"{e.document_name[:52]} · +{e.mots_ajoutes} / "
                    f"−{e.mots_retires} mots", expanded=len(bouges) == 1):
                st.markdown(
                    f"<div style='font-size:0.92rem;line-height:1.6;"
                    f"background:#fcfcfb;border:1px solid rgba(11,11,11,0.10);"
                    f"border-radius:8px;padding:1rem;'>{e.inline_html}</div>",
                    unsafe_allow_html=True)
                st.caption("Barré : retiré · souligné : ajouté, aux couleurs de la palette active.")

# ================================================ omnibus / acte modificatif
@st.cache_data(show_spinner="Lecture de l'acte modificatif…")
def _lire_modificatif(doc_id: str, fichier: str):
    """Lit les instructions de modification d'un document du corpus.

    On repart du **fichier d'origine**, pas du nom d'usage du document : les
    deux diffèrent dès qu'un document a été renommé, et les numéros de page
    affichés doivent être ceux du document, pas ceux d'une reconstitution. À
    défaut de fichier, les segments indexés servent de repli.
    """
    pages: list[str] = []
    for candidat in (fichier, ""):
        if not candidat:
            continue
        chemin = CORPUS_DIR / candidat
        if chemin.exists():
            try:
                pages = read_pages(chemin)
                break
            except Exception:
                pages = []
    if not pages:
        segs = store.load_segments(doc_id)
        if segs is not None and not segs.empty:
            pages = [str(x) for x in segs["text"]]
    return modificatif.lire(pages)


def _fichier_de(doc_id: str) -> str:
    """Nom du fichier d'origine d'un document, quand il est connu."""
    ligne = index_docs.loc[doc_id]
    return str(ligne.get("fichier") or ligne.get("name") or "")


VUES_OMNIBUS = ("Vue d'ensemble", "Texte par texte", "Comparer deux versions")


def _court(texte: str, limite: int) -> str:
    """Début d'un texte, coupé sur un mot entier.

    Une troncature brute donne « notamment l'enregistrement vol », qui se lit
    comme une faute de frappe plutôt que comme un résumé abrégé.
    """
    texte = " ".join((texte or "").split())
    if len(texte) <= limite:
        return texte
    coupe = texte[:limite].rsplit(" ", 1)[0].rstrip(" ,;:·")
    return f"{coupe}…"


def _caracterisation_de(doc_omni: str) -> dict:
    """Ce que le modèle a déjà dit de cet omnibus, tous textes cibles confondus.

    La caractérisation est mémorisée par (omnibus, texte cible) au fil de la
    session. La relire ici permet à la vue d'ensemble, à la note Word et au
    classeur de porter tout ce qui a été qualifié, et pas seulement le texte
    affiché à l'écran.
    """
    trouve = {}
    for cle, valeurs in st.session_state.items():
        if not str(cle).startswith(f"qualif_modif::{doc_omni}::"):
            continue
        acte = str(cle).split("::")[-1]
        for article, triplet in (valeurs or {}).items():
            trouve[(acte, article)] = triplet
    return trouve


def _caracteriser_tout(doc_omni: str, lecture) -> None:
    """Une seule passe du modèle sur l'omnibus entier, tous textes cibles.

    Sans cela, il fallait ouvrir les dix textes l'un après l'autre et cliquer
    dix fois : la vue d'ensemble restait grise, et c'est justement elle qui
    dit par où commencer.
    """
    a_faire: list[tuple[str, str, object]] = []
    reconstitutions: dict[str, list] = {}
    deja = _caracterisation_de(doc_omni)
    for bloc in lecture.blocs:
        candidats = modificatif.documents_candidats(bloc, docs)
        segments = store.load_segments(candidats[0]) if candidats else None
        articles = modificatif.appliquer(bloc, segments)
        reconstitutions[bloc.acte_cible] = articles
        for art in articles:
            if art.touche and (bloc.acte_cible, art.article) not in deja:
                a_faire.append((bloc.acte_cible, art.article, art))

    if not a_faire:
        st.success("Tous les articles touchés sont déjà caractérisés.")
        return

    barre = st.progress(0.0)
    etat = st.empty()
    depart = time.time()
    for i, (acte, article, art) in enumerate(a_faire, start=1):
        modificatif.qualifier(art, acte)
        cle = f"qualif_modif::{doc_omni}::{acte}"
        memoire = st.session_state.get(cle, {})
        memoire[article] = (art.resume, art.impact, art.concepts)
        st.session_state[cle] = memoire
        barre.progress(i / len(a_faire), text=avancement(i, len(a_faire), depart))
        etat.caption(f"{acte} · {article}")
    barre.empty()
    etat.empty()


def _vue_ensemble(doc_omni: str, lecture) -> None:
    """Ce que l'omnibus fait, vu de haut : où il frappe, et à quel endroit fort."""
    syn = modificatif.synthese(lecture, _caracterisation_de(doc_omni))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Textes modifiés", syn.nb_textes)
    k2.metric("Articles touchés", syn.nb_articles)
    k3.metric("Instructions", syn.nb_instructions)
    k4.metric("De portée majeure",
              len(syn.points_durs) if syn.caracterises else "—")

    disponible = get_client().available
    reste = syn.nb_articles - syn.caracterises
    c1, c2 = st.columns([3, 1])
    if not disponible:
        c1.caption(
            "Aucun modèle configuré : la carte suit les opérations écrites "
            "dans l'acte, ce qui se lit sans aide. La portée, elle, demande "
            "le modèle.")
    elif reste:
        c1.caption(duree_estimee(
            reste, CADENCE_QUALIFICATION,
            f"{reste} article(s) dont la portée reste à caractériser"))
    else:
        c1.caption("Tous les articles touchés sont caractérisés.")
    if c2.button("Caractériser tout l'omnibus", type="primary",
                 width="stretch", disabled=not reste or not disponible):
        _caracteriser_tout(doc_omni, lecture)
        st.rerun()

    # --- la carte ----------------------------------------------------------
    st.markdown("#### Où l'omnibus frappe")
    par_impact = st.toggle(
        "Colorer par portée", value=bool(syn.caracterises),
        help="Décoché, la couleur suit l'opération écrite dans l'acte "
             "(supprimé, remplacé, inséré), qui ne demande aucun modèle.")
    st.markdown(carte_modificatif(syn, par_impact=par_impact),
                unsafe_allow_html=True)
    st.caption(
        "Une ligne par texte modifié, une case par article touché. L'exposant "
        "indique le nombre d'instructions portant sur cet article. Passez la "
        "souris sur une case pour lire l'opération, la page et le résumé.")

    # --- ce que l'acte fait, en nombre -------------------------------------
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Ce que l'acte fait")
        ops = pd.DataFrame(
            sorted(syn.par_operation.items(), key=lambda kv: -kv[1]),
            columns=["Opération", "Instructions"])
        st.dataframe(ops, width="stretch", hide_index=True)
    with g2:
        st.markdown("##### Charge par texte")
        charge = pd.DataFrame([
            {"Texte": (lignes[0].nom_cible or lignes[0].acte_cible),
             "Articles": len(lignes),
             "Instructions": sum(l.nb_modifications for l in lignes),
             "Majeurs": sum(1 for l in lignes if l.impact == "majeur")}
            for lignes in syn.par_texte.values()])
        st.dataframe(
            charge.sort_values("Instructions", ascending=False),
            width="stretch", hide_index=True,
            # Sans largeur explicite, « Règlement protection des données des
            # institutions de l'UE » se coupe au milieu d'un mot.
            column_config={"Texte": st.column_config.TextColumn(width="large")})

    # --- les points durs ---------------------------------------------------
    if syn.points_durs:
        st.markdown("#### Par où commencer")
        st.caption(
            "Les articles dont la modification crée, supprime ou déplace une "
            "obligation, un droit, un champ d'application, un seuil, une "
            "compétence, une sanction ou un délai. C'est la liste à porter "
            "dans une note.")
        # Une liste de points durs qui reprend presque tous les articles ne
        # hiérarchise plus rien : il faut le dire plutôt que de laisser croire
        # à un tri.
        if len(syn.points_durs) > 0.6 * max(syn.caracterises, 1):
            st.warning(
                f"**{len(syn.points_durs)} articles sur {syn.caracterises} "
                "caractérisés sont classés majeurs.** À ce niveau, la "
                "qualification ne hiérarchise plus : soit l'acte est "
                "effectivement lourd de bout en bout, soit le modèle "
                "sur-qualifie. Lisez les instructions verbatim avant de "
                "reprendre ce tri dans une note.",
                icon=":material/priority_high:")
        for ligne in syn.points_durs:
            with st.expander(
                    f"{ligne.libelle_cible} · {ligne.article}"
                    + (f"  ·  {_court(ligne.resume, 110)}" if ligne.resume
                       else "")):
                st.markdown(f"**{ligne.resume}**" if ligne.resume else "")
                # L'instruction et le texte qu'elle introduit sont indissociables :
                # « au paragraphe 1, les points suivants sont ajoutés: » ne dit
                # rien sans les points en question. L'instruction seule se
                # terminait par deux points suivis de rien.
                for instruction, nouveau in zip(ligne.instructions,
                                                ligne.textes_nouveaux):
                    st.markdown(
                        f"<div style='border-left:3px solid #e1000f;"
                        f"padding:0.2rem 0 0.2rem 0.8rem;margin-bottom:0.2rem;"
                        f"font-size:0.92rem'>{instruction}"
                        + (f"<div style='color:#3a3a3a;background:#f7f7fa;"
                           f"border-radius:4px;padding:0.4rem 0.6rem;"
                           f"margin-top:0.35rem;font-size:0.88rem'>« "
                           f"{_court(nouveau, 700)} »</div>"
                           if nouveau else "")
                        + "</div>",
                        unsafe_allow_html=True)
                if ligne.concepts:
                    st.caption("Notions touchées : " + ", ".join(ligne.concepts))
                st.caption(
                    f"{ligne.article_omnibus} de l'acte · page "
                    f"{ligne.page_min or '—'} · pour le détail et le texte "
                    "avant/après, vue « Texte par texte ».")
    elif syn.caracterises:
        st.info("Aucune modification de portée majeure sur les articles "
                "caractérisés.", icon=":material/check_circle:")

    # --- lecture horizontale ----------------------------------------------
    if syn.notions:
        st.markdown("#### Ce qui revient d'un texte à l'autre")
        st.caption(
            "Notions modifiées dans plusieurs textes à la fois. C'est la "
            "lecture propre à un omnibus : elle dit quels dossiers, tenus par "
            "des bureaux différents, sont touchés par la même idée.")
        st.dataframe(
            pd.DataFrame([
                {"Notion": notion, "Textes": len({l.acte_cible for l in lignes}),
                 "Articles concernés": " · ".join(
                     f"{l.nom_cible or l.acte_cible} {l.article}"
                     for l in lignes[:8])}
                for notion, lignes in syn.notions[:25]]),
            width="stretch", hide_index=True)

    # --- toutes les instructions, filtrables -------------------------------
    st.markdown("#### Toutes les modifications")
    f1, f2, f3 = st.columns([2, 2, 3])
    textes = f1.multiselect(
        "Textes", options=[(l[0].nom_cible or l[0].acte_cible)
                           for l in syn.par_texte.values()])
    portees = f2.multiselect(
        "Portée", options=["majeur", "mineur", "redactionnel",
                           "non caractérisé"])
    recherche = f3.text_input(
        "Chercher dans les instructions", placeholder="délai, notification…")

    lignes_vue = syn.lignes
    if textes:
        lignes_vue = [l for l in lignes_vue
                      if (l.nom_cible or l.acte_cible) in textes]
    if portees:
        lignes_vue = [l for l in lignes_vue
                      if (l.impact or "non caractérisé") in portees]
    if recherche.strip():
        besoin = recherche.strip().lower()
        lignes_vue = [l for l in lignes_vue
                      if besoin in " ".join(l.instructions).lower()
                      or besoin in (l.resume or "").lower()
                      or besoin in l.article.lower()]

    if lignes_vue:
        st.dataframe(
            pd.DataFrame([
                {"Texte": l.nom_cible or l.acte_cible, "Article": l.article,
                 "Opérations": ", ".join(l.operations),
                 "Instructions": l.nb_modifications,
                 "Portée": l.impact or "—",
                 "Ce que ça change": l.resume or "—",
                 "Page": l.page_min or "—"} for l in lignes_vue]),
            width="stretch", hide_index=True, height=380)
    else:
        st.caption("Aucune modification ne correspond à ces filtres.")

    # --- livrables ---------------------------------------------------------
    st.divider()
    st.markdown("#### Emporter le dossier")
    nom_acte = etiquette(doc_omni)
    d1, d2 = st.columns(2)
    try:
        note = note_omnibus_docx(nom_acte, syn, __version__)
        d1.download_button(
            "Note de synthèse (.docx)", data=note,
            file_name="omnibus_note_de_synthese.docx", width="stretch",
            mime="application/vnd.openxmlformats-officedocument."
                 "wordprocessingml.document")
    except Exception as exc:
        d1.warning(f"Note indisponible : {type(exc).__name__}")

    recap = pd.DataFrame([
        {"Texte modifié": b.nom_cible or "—", "Référence": b.acte_cible,
         "Article de l'omnibus": b.article_omnibus, "CELEX": b.celex or "—",
         "Articles touchés": len(b.articles_touches),
         "Modifications": len(b.modifications)} for b in lecture.blocs])
    carac = _caracterisation_de(doc_omni)
    lignes_export = [
        {"Texte modifié": b.nom_cible or b.acte_cible,
         "Référence": b.acte_cible, "CELEX": b.celex,
         "Article de l'omnibus": b.article_omnibus,
         "Article visé": m.article_cible, "Numéro": m.numero,
         "Opération": m.libelle_operation, "Précision visée": m.portee,
         "Instruction": m.instruction, "Texte nouveau": m.texte_nouveau[:30000],
         "Page": m.page,
         "Portée": (carac.get((b.acte_cible, m.article_cible)) or ("", ""))[1],
         "Ce que ça change": (carac.get((b.acte_cible, m.article_cible))
                              or ("", ""))[0]}
        for b in lecture.blocs for m in b.modifications]
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as writer:
        pd.DataFrame(lignes_export).to_excel(
            writer, sheet_name="Modifications", index=False)
        recap.to_excel(writer, sheet_name="Textes modifiés", index=False)
    d2.download_button(
        "Toutes les modifications (.xlsx)", data=tampon.getvalue(),
        file_name="omnibus_modifications.xlsx", width="stretch",
        mime="application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet")
    st.caption(
        f"La note reprend les {len(syn.points_durs)} point(s) dur(s), les "
        "notions transverses et le détail article par article, en tableaux "
        "Word modifiables. Le classeur porte les "
        f"{len(lignes_export)} instructions verbatim avec leur page.")


# Le corps de l'onglet est une fonction : il comporte des sorties
# anticipées, et `st.stop()` arrêterait le script entier — donc aussi
# les onglets de comparaison classique, rendus plus bas.
def _onglet_omnibus() -> None:
    st.info(
        "**Un omnibus ne se compare pas comme deux versions d'un même "
        "texte.** Il ne récrit pas le Data Act : il dit ce qu'il faut y "
        "changer · « à l'article 5 du règlement (UE) 2023/2854, le paragraphe "
        "2 est remplacé par… ». Son article premier ne correspond à rien dans "
        "le Data Act. Cet onglet lit ces instructions et les range par texte "
        "modifié, puis par article.", icon=":material/rule_settings:")

    doc_omni = st.selectbox(
        "Acte modificatif à lire", options=[VIDE] + list(pool["id"]), index=0,
        format_func=lambda i: "— choisir le texte omnibus —" if i == VIDE
        else etiquette(i),
        help="La proposition de la Commission, ou un compromis de présidence "
             "portant sur elle.")

    if not doc_omni:
        st.caption(
            "Choisissez l'acte modificatif. La lecture est déterministe : "
            "aucune instruction n'est résumée ni interprétée par un modèle, "
            "chacune est affichée telle qu'elle est écrite, avec sa page.")
        return

    lecture = _lire_modificatif(doc_omni, _fichier_de(doc_omni))
    for remarque in lecture.remarques:
        st.warning(remarque)

    if not lecture.est_modificatif or not lecture.blocs:
        st.warning(
            "Ce document ne se présente pas comme un acte modificatif : la "
            "formule « est modifié comme suit » n'y a pas été trouvée. S'il "
            "s'agit bien d'un omnibus, c'est que son extraction a échoué, "
            "vérifiez le nombre de segments dans la Bibliothèque. Pour deux "
            "versions d'un même texte, servez-vous des autres onglets.")
        return

    vue = st.radio(
        "Comment lire cet acte", VUES_OMNIBUS, horizontal=True, index=0,
        label_visibility="collapsed",
        help="La vue d'ensemble répond à « qu'est-ce que ce texte nous fait, "
             "et par où commencer ». Le texte par texte est la lecture de "
             "travail, article par article.")

    if vue == VUES_OMNIBUS[0]:
        _vue_ensemble(doc_omni, lecture)
        return
    if vue == VUES_OMNIBUS[2]:
        _vue_deux_versions(doc_omni, lecture)
        return

    choix_bloc = st.selectbox(
        "Texte à examiner", options=list(range(len(lecture.blocs))),
        format_func=lambda i: (
            f"{lecture.blocs[i].libelle} · "
            f"{len(lecture.blocs[i].articles_touches)} article(s) touché(s), "
            f"{len(lecture.blocs[i].modifications)} modification(s)"),
        help="Un omnibus modifie plusieurs textes ; on les examine l'un après "
             "l'autre. Le nom d'usage, RGPD, Data Act, est celui du "
             "catalogue interne ; la référence entre parenthèses est celle "
             "que porte l'omnibus.")
    bloc = lecture.blocs[choix_bloc]

    # Le texte cible, s'il est chargé : sans lui on montre les instructions,
    # avec lui on montre l'article avant et après.
    candidats = modificatif.documents_candidats(bloc, docs)
    options = [VIDE] + candidats + [
        i for i in pool["id"] if i not in candidats and i != doc_omni]
    cible_id = st.selectbox(
        f"Texte de référence · {bloc.libelle}",
        options=options, index=1 if candidats else 0,
        format_func=lambda i: ("— non chargé : afficher seulement les "
                               "modifications —") if i == VIDE else etiquette(i),
        help="Chargez le texte consolidé en vigueur depuis la Bibliothèque "
             "pour voir chaque article avant et après l'omnibus.")

    segments_cible = store.load_segments(cible_id) if cible_id else None
    articles = modificatif.appliquer(bloc, segments_cible)

    touches = [a for a in articles if a.touche]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Articles du texte", len(articles) if cible_id else "—")
    k2.metric("Articles touchés", len(touches))
    k3.metric("Modifications", len(bloc.modifications))
    k4.metric("Reconstitutions exactes",
              sum(1 for a in touches if a.fiabilite == "exacte"))

    if not cible_id:
        st.caption(
            "Texte de référence non chargé : seules les instructions sont "
            "affichées. Chargez le texte consolidé pour obtenir la colonne "
            "« tel que modifié ».")

    # --- caractérisation de la portée --------------------------------------
    # Mémorisée par (omnibus, texte cible) : changer d'onglet ne doit pas
    # relancer trente appels au modèle.
    cle_qualif = f"qualif_modif::{doc_omni}::{bloc.acte_cible}"
    deja = st.session_state.get(cle_qualif, {})
    for art in articles:
        if art.article in deja:
            art.resume, art.impact, art.concepts = deja[art.article]

    with st.expander("Caractériser la portée des modifications", expanded=False):
        st.markdown(
            "Pour chaque article touché, le modèle dit **ce que la "
            "modification change** et si elle pèse, majeure (obligation, "
            "champ d'application, seuil, compétence, sanction, délai), "
            "mineure, ou rédactionnelle.\n\n"
            "Ce qu'il qualifie ici est une modification **écrite par le "
            "législateur** : « l'article 33 est modifié comme suit », pas "
            "un rapprochement calculé entre deux textes. C'est toute la "
            "différence avec une comparaison d'articles qui ne se "
            "correspondent pas : là, le modèle décrivait fidèlement un écart "
            "qui n'existait pas.")
        a_faire = [a for a in articles if a.touche and not a.impact]
        disponible = get_client().available
        if not disponible:
            st.caption("Aucun modèle configuré : les instructions verbatim "
                       "restent affichées, elles se lisent sans aide.")
        elif not a_faire:
            st.caption("Tous les articles touchés sont caractérisés.")
        else:
            st.caption(duree_estimee(
                len(a_faire), CADENCE_QUALIFICATION,
                f"{len(a_faire)} article(s) à caractériser"))
        if st.button("Caractériser", type="primary", width="stretch",
                     disabled=not a_faire or not disponible,
                     key=f"btn_{cle_qualif}"):
            barre = st.progress(0.0)
            etat = st.empty()
            depart = time.time()
            for i, art in enumerate(a_faire, start=1):
                modificatif.qualifier(art, bloc.acte_cible)
                deja[art.article] = (art.resume, art.impact, art.concepts)
                barre.progress(i / len(a_faire),
                               text=avancement(i, len(a_faire), depart))
                etat.caption(art.article)
            st.session_state[cle_qualif] = deja
            barre.empty()
            etat.empty()
            st.rerun()

    caracterises = [a for a in touches if a.resume]
    if caracterises:
        st.markdown("#### Ce que l'omnibus change, article par article")
        st.dataframe(
            pd.DataFrame([
                {"Article": a.article, "Statut": a.statut,
                 "Portée": a.impact or "—", "Ce que ça change": a.resume,
                 "Notions touchées": ", ".join(a.concepts)}
                for a in sorted(
                    caracterises,
                    key=lambda x: (modificatif.IMPACT_ORDRE.get(x.impact, 4),
                                   x.article))]),
            width="stretch", hide_index=True)

    f1, f2 = st.columns([2, 1])
    filtre = f1.radio(
        "Afficher", ["Les articles touchés", "Tout le texte, inchangés compris"],
        horizontal=True, index=0,
        help="La liste complète évite de croire qu'un article a été oublié : "
             "un article sans modification y figure, marqué « inchangé ».")
    ouvrir = f2.toggle("Déplier tous les articles", value=False)

    vue = articles if filtre.startswith("Tout") else touches
    if caracterises:
        portees = st.multiselect(
            "N'afficher que les modifications de portée",
            ["majeur", "mineur", "redactionnel", "non caractérisé"],
            help="La caractérisation doit avoir été lancée ci-dessus.")
        if portees:
            vue = [a for a in vue
                   if (a.impact or "non caractérisé") in portees]
    if not vue:
        st.info("Aucun article à afficher pour ce texte.")
        return

    COULEUR_STATUT = {"Modifié": "#000091", "Inséré": "#0ca30c",
                      "Supprimé": "#e1000f", "Inchangé": "#898781"}
    FIABILITE = {
        "exacte": ("Reconstitution exacte", ":material/check_circle:"),
        "approchee": ("Reconstitution partielle", ":material/error:"),
        "non_appliquee": ("Modification non appliquée au texte",
                          ":material/warning:"),
        "inchange": ("", ""),
    }

    for art in vue:
        etat = art.statut
        titre = f"{art.article} · {etat}"
        if art.modifications:
            titre += f"  ·  {len(art.modifications)} modification(s)"
        with st.expander(titre, expanded=ouvrir and art.touche):
            if not art.modifications:
                st.caption("Cet article n'est pas modifié par l'omnibus.")
                if art.texte_avant:
                    st.text(art.texte_avant[:3000])
                continue

            libelle, icone = FIABILITE.get(art.fiabilite, ("", ""))
            if libelle:
                st.caption(f"{icone} {libelle}")
            if art.cible_chargee and not art.texte_avant and etat != "Inséré":
                st.caption(
                    ":material/help: Cet article ne figure pas dans le texte "
                    "de référence chargé. Soit la version chargée n'est pas la "
                    "version consolidée en vigueur, soit son découpage l'a "
                    "manqué, la modification, elle, est bien écrite dans "
                    "l'omnibus.")
            if art.note:
                st.warning(art.note)

            if art.resume:
                couleur_impact = {"majeur": "#e1000f", "mineur": "#f0a202",
                                  "redactionnel": "#898781"}.get(
                                      art.impact, "#000091")
                st.markdown(
                    f"<div style='border-left:4px solid {couleur_impact};"
                    f"background:#f5f5fa;padding:0.6rem 0.9rem;"
                    f"border-radius:0 6px 6px 0;margin-bottom:0.8rem'>"
                    f"<b>Portée : {art.impact}</b><br>{art.resume}</div>",
                    unsafe_allow_html=True)
                if art.concepts:
                    st.caption("Notions touchées : " + ", ".join(art.concepts))

            st.markdown("**Ce que dit l'omnibus**")
            for mod in art.modifications:
                # Dire, instruction par instruction, si elle se retrouve dans
                # le « avant / après » affiché plus bas : une modification
                # qu'on ne sait pas localiser n'y apparaît pas, et il ne faut
                # pas que le silence passe pour une absence de changement.
                if mod.appliquee is False:
                    marque = ("<span style='color:#b34000'> · non reportée "
                              "dans le texte ci-dessous</span>")
                elif mod.appliquee and art.texte_avant:
                    marque = ("<span style='color:#18753c'> · reportée dans "
                              "le texte ci-dessous</span>")
                else:
                    marque = ""
                st.markdown(
                    f"<div style='border-left:3px solid "
                    f"{COULEUR_STATUT.get(etat, '#000091')};padding:0.2rem 0 "
                    f"0.2rem 0.8rem;margin-bottom:0.5rem'>"
                    f"<b>{mod.numero} · {mod.libelle_operation}</b>"
                    f"<span style='color:#898781'> · page {mod.page}</span>"
                    f"{marque}"
                    f"<br>{mod.instruction}</div>",
                    unsafe_allow_html=True)
                if mod.texte_nouveau:
                    with st.popover(f"Texte nouveau · {mod.numero}"):
                        st.write(mod.texte_nouveau)

            if art.texte_avant or art.texte_apres:
                ajoutes, retires = ecart_mots(art.texte_avant, art.texte_apres)
                long_article = ecart_hors_champ(
                    art.texte_avant, art.texte_apres, 900)

                t1, t2 = st.columns([3, 2])
                t1.markdown("**Le texte, avant et après**")
                # Un article de dix mille mots dont trois passages changent se
                # lit comme un mur : les passages modifiés y sont invisibles.
                # On resserre par défaut dès que l'article est long.
                condense = t2.toggle(
                    "Ne montrer que les passages modifiés",
                    value=long_article, key=f"condense::{art.section_id}",
                    help="Remplace les longs passages inchangés par « […] ». "
                         "Décochez pour lire l'article entier.")
                rendu = rendu_mot_a_mot(
                    art.texte_avant, art.texte_apres,
                    # Aucun plafond : le plafond de 900 mots coupait la fin
                    # d'un article long, et les modifications ajoutées en fin
                    # d'article disparaissaient sans que rien ne le signale.
                    max_mots=None, contexte=25 if condense else 0)
                st.markdown(
                    f"<div style='font-size:0.92rem;line-height:1.6;"
                    f"background:#fcfcfb;border:1px solid rgba(11,11,11,0.10);"
                    f"border-radius:8px;padding:1rem;'>{rendu}</div>",
                    unsafe_allow_html=True)
                manquantes = [m for m in art.modifications
                              if m.appliquee is False]
                st.caption(
                    f"**+{ajoutes} mot(s) ajouté(s) · −{retires} mot(s) "
                    "retiré(s).** Barré : texte actuel retiré · souligné : "
                    "texte ajouté par l'omnibus, aux couleurs de la palette "
                    "active."
                    + (f" **{len(manquantes)} instruction(s) ne figurent pas "
                       "dans ce rendu** (voir ci-dessus) : le texte « après » "
                       "est donc incomplet." if manquantes else ""))
                if art.texte_avant == art.texte_apres and art.touche:
                    st.info(
                        "Rien n'apparaît barré ni souligné : aucune des "
                        "instructions de cet article n'a pu être reportée "
                        "automatiquement dans le texte. Elles sont écrites "
                        "au-dessus, verbatim, c'est la lecture qui fait foi.",
                        icon=":material/info:")

    st.divider()
    st.caption(
        "L'export de toutes les instructions et la note de synthèse Word sont "
        "dans la vue d'ensemble, en haut de cet onglet.")


# ------------------------------------------------- deux versions d'un omnibus
def _vue_deux_versions(doc_omni: str, lecture) -> None:
    st.markdown("### Comparer avec une autre version de cet omnibus")
    st.caption(
        "Un compromis de présidence ressemble à la proposition, avec des "
        "passages changés, et il ne dit pas lesquels. La comparaison porte "
        "ici sur les **instructions de modification**, article visé par "
        "article visé : la question de négociation n'est pas « qu'est-ce qui "
        "a bougé dans le texte » mais « sur quels articles du Data Act la "
        "présidence a-t-elle changé ce que la Commission proposait ».")

    autre_id = st.selectbox(
        "Autre version (compromis de présidence, version révisée…)",
        options=[VIDE] + [i for i in pool["id"] if i != doc_omni], index=0,
        format_func=lambda i: "— aucune —" if i == VIDE else etiquette(i))
    if not autre_id:
        return

    autre = _lire_modificatif(autre_id, _fichier_de(autre_id))
    if not autre.est_modificatif or not autre.blocs:
        st.warning(
            "Cette autre version ne se lit pas comme un acte modificatif : "
            "ses instructions n'ont pas pu être extraites.")
        return

    ecarts = modificatif.comparer(lecture, autre)
    bouges = [e for e in ecarts if e.statut != "identique"]

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Modifications comparées", len(ecarts))
    e2.metric("Changées", sum(1 for e in ecarts if e.statut == "modifiee"))
    e3.metric("Nouvelles", sum(1 for e in ecarts if e.statut == "ajoutee"))
    e4.metric("Abandonnées", sum(1 for e in ecarts if e.statut == "retiree"))

    if not bouges:
        st.success(
            "Les deux versions demandent exactement les mêmes modifications.")
        return

    st.dataframe(
        pd.DataFrame([
            {"Texte modifié": e.acte_cible, "Article visé": e.article,
             "Ce qui a changé": modificatif.STATUT_ECART[e.statut],
             "Similarité": round(e.similarite, 2)} for e in bouges]),
        width="stretch", hide_index=True)

    for e in bouges:
        with st.expander(
                f"{e.acte_cible} · {e.article} · "
                f"{modificatif.STATUT_ECART[e.statut]}"):
            if e.statut == "modifiee":
                st.markdown(
                    f"<div style='font-size:0.92rem;line-height:1.6;"
                    f"background:#fcfcfb;border:1px solid rgba(11,11,11,0.10);"
                    f"border-radius:8px;padding:1rem;'>"
                    f"{rendu_mot_a_mot(e.avant, e.apres)}</div>",
                    unsafe_allow_html=True)
                st.caption("Barré : ce que demandait la première version · "
                           "souligné : ce que demande la seconde.")
            elif e.statut == "ajoutee":
                st.markdown("**Instruction absente de la première version**")
                st.write(e.apres[:4000])
            else:
                st.markdown("**Instruction abandonnée dans la seconde version**")
                st.write(e.avant[:4000])



with tm:
    _onglet_omnibus()

# ============================== rien ne se compare tant que rien n'est choisi
if not pret:
    for onglet in (t1, t2, t3, t4):
        with onglet:
            st.info(
                "**Choisissez d'abord les deux textes à comparer**, en haut de "
                "la page. Tant qu'ils ne sont pas désignés, il n'y a rien à "
                "montrer ici : comparer deux documents pris au hasard dans le "
                "corpus ne veut rien dire.", icon=":material/rule:")
    st.stop()

old_seg = store.load_segments(old_id)
new_seg = store.load_segments(new_id)

key = f"deltas::{old_id}::{new_id}"
if key not in st.session_state:
    st.session_state[key] = compare(old_seg, new_seg)
deltas = st.session_state[key]

# Les intitulés produits par le découpage automatique — « Article 24 (2/12) » —
# ne renvoient à rien dans le texte officiel : on les remplace par la première
# disposition réellement contenue dans le fragment.
for d in deltas:
    d.section_label = label_fragment(d.section_label, d.new_text or d.old_text)

changed = [d for d in deltas if d.status != "inchange"]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Articles comparés", len(deltas))
k2.metric("Modifiés", sum(1 for d in deltas if d.status == "reformulation"))
k3.metric("Ajoutés", sum(1 for d in deltas if d.status == "ajout"))
k4.metric("Supprimés", sum(1 for d in deltas if d.status == "suppression"))

table = summary_table(deltas)

comment_ca_marche("versions")
panneau_fiabilite(alertes_versions(deltas))

# ======================================================= changements majeurs
with t1:
    st.info(
        "**Ce qui a bougé, trié par ce qui compte.** Le modèle qualifie "
        "chaque changement, majeur s'il touche une obligation, un champ "
        "d'application, un seuil, une compétence ou un délai ; mineur s'il "
        "précise sans déplacer l'équilibre ; rédactionnel sinon.",
        icon=":material/priority_high:")

    todo = [d for d in changed if not d.impact]
    disponible = get_client().available

    a1, a2 = st.columns([2, 1])
    a1.markdown(
        f"**{len(changed)} articles modifiés**, dont **{len(todo)}** restent à "
        "qualifier." if changed else "Aucun article modifié entre ces deux versions.")
    if todo:
        a1.caption(duree_estimee(len(todo), CADENCE_QUALIFICATION,
                                 f"{len(todo)} article(s) à qualifier"))
    if not disponible:
        a1.caption("Aucun modèle configuré : les écarts bruts restent "
                   "disponibles, la qualification non.")

    if a2.button("Tout qualifier", type="primary", width="stretch",
                 disabled=not todo or not disponible):
        bar = st.progress(0.0)
        etat = st.empty()
        depart = time.time()
        for i, d in enumerate(todo, start=1):
            qualify(d)
            bar.progress(i / len(todo), text=avancement(i, len(todo), depart))
            etat.caption(d.section_label)
        bar.empty()
        etat.empty()
        st.session_state[key] = deltas
        st.rerun()

    if changed:
        ORDRE_IMPACT = {"majeur": 0, "mineur": 1, "redactionnel": 2, "": 3,
                        "nul": 4}
        filtre = st.multiselect(
            "N'afficher que", ["majeur", "mineur", "redactionnel", "non qualifié"],
            default=["majeur", "non qualifié"] if todo else ["majeur"])

        def retenu(d) -> bool:
            impact = d.impact or "non qualifié"
            return not filtre or impact in filtre

        vus = sorted([d for d in changed if retenu(d)],
                     key=lambda d: (ORDRE_IMPACT.get(d.impact, 3), -d.churn))
        st.caption(f"{len(vus)} article(s) affiché(s), du plus lourd au plus léger.")

        for d in vus[:60]:
            couleur = {"majeur": STATUS["interdit"], "mineur": STATUS["restreint"],
                       "redactionnel": "#9db8dc"}.get(d.impact, "#c3c2b7")
            with st.expander(
                    f"{d.section_label} · {CHANGE_LABEL.get(d.status, d.status)}"
                    f"  ·  +{d.words_added} / −{d.words_removed} mots"
                    + (f"  ·  impact {d.impact}" if d.impact else
                       "  ·  non qualifié")):
                if d.summary_fr:
                    st.markdown(
                        f"<div style='border-left:4px solid {couleur};"
                        f"padding:0.4rem 0 0.4rem 0.9rem;margin-bottom:0.6rem;'>"
                        f"{d.summary_fr}</div>", unsafe_allow_html=True)
                if d.concepts:
                    st.caption("Notions touchées : " + ", ".join(d.concepts))
                if d.inline_html:
                    st.markdown(
                        f"<div style='font-size:0.92rem;line-height:1.6;"
                        f"background:#fcfcfb;border:1px solid rgba(11,11,11,0.10);"
                        f"border-radius:8px;padding:1rem;'>{d.inline_html}</div>",
                        unsafe_allow_html=True)
                    st.caption("Barré : retiré · souligné : ajouté, aux couleurs de la palette active.")

# ======================================================= cartes interactives
with t2:
    st.info(
        "**Par où commencer, sur un texte de cent articles.** Une seule carte, "
        "grande : chaque tuile est un article, sa surface le nombre de mots "
        "touchés. Cliquez une tuile, l'article s'ouvre juste en dessous avec "
        "ses différences mot à mot.", icon=":material/map:")

    # Une carte lisible plutôt que trois illisibles. Trois vues côte à côte
    # obligeaient à choisir avant d'avoir compris ; et cent tuiles dans une
    # figure de 400 px ne portent aucune étiquette lisible. On montre donc les
    # changements les plus lourds, en grand, et on dit combien restent dehors.
    o1, o2, o3 = st.columns([1, 1, 1])
    grouper = o1.radio(
        "Grouper par", ["Statut", "Impact"], horizontal=True,
        help="« Impact » n'est renseigné qu'après la qualification par le "
             "modèle, dans l'onglet précédent.")
    combien = o2.slider(
        "Articles affichés", min_value=10, max_value=80, value=30, step=5,
        help="Les articles les plus lourdement modifiés d'abord. Monter le "
             "curseur ajoute des tuiles, et les rend plus petites.")
    inclure = o3.toggle("Inclure les articles inchangés", value=False)

    cartographiables = [d for d in deltas
                        if inclure or d.status != "inchange"]
    fig = change_treemap(
        table, par=grouper, inclure_inchanges=inclure, top=combien,
        title="Chaque tuile est un article ; sa surface, le nombre de mots touchés")

    evenement = st.plotly_chart(fig, width="stretch", on_select="rerun",
                                key=f"carte_{grouper}_{combien}_{inclure}_{key}")
    choisi = _article_clique(evenement, set(table["Article"]))

    reste = max(0, len(cartographiables) - combien)
    if reste:
        st.caption(
            f"{combien} article(s) affiché(s), du plus lourdement modifié au "
            f"plus léger. **{reste} de plus ne sont pas sur la carte** : ils "
            "figurent tous dans l'onglet « Changements majeurs » et dans le "
            "classeur exporté.")

    with st.expander("Deux autres façons de lire les mêmes chiffres"):
        st.caption(
            "Utiles pour une note : les barres montrent la balance ajouts / "
            "retraits article par article, le nuage isole les articles "
            "réécrits, beaucoup de mots touchés et faible similarité.")
        st.plotly_chart(
            change_bars(table, inclure_inchanges=inclure,
                        title="Ce qui a été retiré, ce qui a été ajouté"),
            width="stretch")
        st.plotly_chart(
            change_scatter(table, inclure_inchanges=inclure,
                           title="En bas à droite : les articles réécrits"),
            width="stretch")

    if choisi:
        d = next((x for x in deltas if x.section_label == choisi), None)
        if d is not None:
            st.divider()
            st.markdown(f"### {d.section_label}")
            st.markdown(
                f"{CHANGE_LABEL.get(d.status, d.status)}  ·  "
                f"similarité {d.similarity:.0%}  ·  "
                f"+{d.words_added} / −{d.words_removed} mots"
                + (f"  ·  impact {d.impact}" if d.impact else ""))
            if d.summary_fr:
                st.info(d.summary_fr)
            if d.inline_html:
                st.markdown(
                    f"<div style='font-size:0.92rem;line-height:1.6;"
                    f"background:#fcfcfb;border:1px solid rgba(11,11,11,0.10);"
                    f"border-radius:8px;padding:1rem;'>{d.inline_html}</div>",
                    unsafe_allow_html=True)
                st.caption("Barré : retiré · souligné : ajouté, aux couleurs de la palette active.")
    else:
        st.caption(
            "Aucune tuile sélectionnée : cliquez un article sur la carte pour "
            "en voir le texte modifié ici même.")

# ====================================================== article par article
with t3:
    st.info(
        "**Le mot près.** Un article, son texte dans les deux versions, et "
        "les différences soulignées.", icon=":material/text_snippet:")
    sel = st.selectbox(
        "Article", options=[d.section_id for d in deltas],
        format_func=lambda s: next(
            f"{d.section_label} · {CHANGE_LABEL.get(d.status, d.status)}"
            for d in deltas if d.section_id == s))
    d = next(x for x in deltas if x.section_id == sel)

    st.markdown(f"**{d.section_label}** · {CHANGE_LABEL.get(d.status, d.status)}  ·  "
                f"similarité {d.similarity:.0%}  ·  "
                f"+{d.words_added} / −{d.words_removed} mots"
                + (f"  ·  impact {d.impact}" if d.impact else ""))
    if d.summary_fr:
        st.info(d.summary_fr)
    if d.concepts:
        st.caption("Notions touchées : " + ", ".join(d.concepts))

    if d.inline_html:
        st.markdown("#### Différences mot à mot")
        st.markdown(
            f"<div style='font-size:0.92rem;line-height:1.6;background:#fcfcfb;"
            f"border:1px solid rgba(11,11,11,0.10);border-radius:8px;"
            f"padding:1rem;'>{d.inline_html}</div>", unsafe_allow_html=True)
        st.caption("Barré : retiré · souligné : ajouté, aux couleurs de la palette active.")
    else:
        cc1, cc2 = st.columns(2)
        cc1.markdown(f"**{etiquette(old_id)[:60]}**")
        cc1.text(d.old_text[:4000] or "(absent)")
        cc2.markdown(f"**{etiquette(new_id)[:60]}**")
        cc2.text(d.new_text[:4000] or "(supprimé)")

# ==================================================================== export
with t4:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Comparaison", index=False)
        pd.DataFrame([
            {"Article": d.section_label, "Statut": d.status,
             "Version de départ": d.old_text[:30000],
             "Version d'arrivée": d.new_text[:30000]}
            for d in changed
        ]).to_excel(writer, sheet_name="Textes", index=False)
    st.download_button(
        "Télécharger la comparaison (.xlsx)", data=buf.getvalue(),
        file_name="comparaison_versions.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch", type="primary")
    st.caption(
        "Deux feuilles : la synthèse chiffrée par article, et le texte intégral "
        "des articles modifiés dans les deux versions, côte à côte.")

pour_aller_plus_loin(
    "Comment la comparaison est faite",
    """
**Appariement.** Les articles des deux versions sont rapprochés par leur
identifiant de section (`art_5`, `rec_12`), pas par leur position dans le
document : insérer un article ne décale donc pas toute la comparaison.

**Écarts.** Comparaison mot à mot (`difflib`), qui donne la similarité, le
nombre de mots ajoutés et retirés, et le rendu souligné / barré. Tout cela est
déterministe : deux exécutions donnent exactement le même résultat, et aucun
modèle n'intervient.

**Qualification.** C'est la seule étape où le modèle parle, et il ne parle
qu'après : on lui donne un écart déjà constaté et on lui demande d'en dire la
portée. Il ne peut pas inventer un changement, ni en masquer un.

**Ordre des versions.** Nature et date sont détectées à l'import depuis
l'en-tête du document et modifiables dans **Bibliothèque → Corpus**. Une date
absente n'empêche rien : l'ordre se rabat sur l'ordre d'import.

**Limite connue.** Un article entièrement renuméroté d'une version à l'autre
apparaît comme une suppression suivie d'un ajout. C'est le cas le plus
fréquent de faux positif ; le fil du texte, qui montre les deux, permet de le
repérer d'un coup d'œil.
""")
