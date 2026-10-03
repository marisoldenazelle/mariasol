"""Positions des États membres — matrice d'alignement et alliés."""

from __future__ import annotations

import json
import time

import pandas as pd
import streamlit as st

from core import store
from core.duree import avancement, duree_estimee
from core.fiabilite import desaccord_referentiels, positions as alertes_positions
from core.labels import preciser, sujet_article
from core.llm import get_client
from core.schemas import STANCE_LABEL_FR
from core.wk_parser import MS_CODES
from core.scoring import (FR_SILENCE_REFERENCE, ally_ranking, analyse_batch,
                          contentious_articles, derive_fr_reference)
from core.titres import (bornes_depuis_rattachement, ordre_des_titres,
                         titres_depuis_bornes, titres_depuis_texte)
from core.excel import build_xlsx
from core.palette import PALETTES, actif, couleurs
from core.nonpaper import (deviner_auteur, en_contributions as positions_en_contributions,
                            extraire as extraire_positions)
from core.ponderation import classement_pondere, evaluer as evaluer_ponderation
from core.report import (build_docx, engagement_png, heatmap_png, ranking_png)
from core.ui import comment_ca_marche, panneau_fiabilite, tableau_suivi
from core.viz import (ally_bars, alignment_heatmap, contentious_scatter,
                      stance_breakdown)


def _themes(brut) -> list[str]:
    """Thèmes d'une contribution, tolérant aux valeurs absentes ou mal formées."""
    try:
        return [str(t).strip() for t in json.loads(brut or "[]") if str(t).strip()]
    except (TypeError, ValueError):
        return []


st.title("Qui est avec nous, article par article ?")
st.caption(
    "L'outil lit les contributions écrites des États membres, les classe par "
    "rapport à un référentiel que vous choisissez, et vous donne la matrice, "
    "les alliés, les articles qui divisent, puis les livrables Word et Excel."
)

docs = store.list_documents()
wk = docs[docs.get("kind", pd.Series(dtype=str)) == "wk_table"] if not docs.empty else docs
if wk.empty:
    st.info(
        "Aucun document de commentaires consolidés au corpus. "
        "Chargez-en un depuis la **Bibliothèque**."
    )
    st.stop()

index_wk = wk.set_index("id")
# Plusieurs documents à la fois : les titres d'un même règlement arrivent
# souvent dans des tableaux de travail distincts — Titre III d'un côté,
# Titre IV de l'autre — et la vue d'ensemble suppose de les réunir.
doc_ids = st.multiselect(
    "Documents de commentaires consolidés", options=list(wk["id"]),
    default=[list(wk["id"])[0]],
    format_func=lambda i: index_wk.loc[i, "name"],
    help="Sélectionnez-en plusieurs pour réunir les contributions, utile "
         "quand chaque titre du règlement a son propre tableau.")
if not doc_ids:
    st.warning("Sélectionnez au moins un document.")
    st.stop()

doc_id = doc_ids[0]                     # document principal, pour les repères
doc = index_wk.loc[doc_id]

df = store.load_contributions(doc_ids)
analysed = df[df["stance"].notna()]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contributions", len(df))
k2.metric("États membres", df["ms_code"].nunique())
k3.metric("Articles couverts", df["section_id"].nunique())
k4.metric("Analysées", f"{len(analysed)} / {len(df)}")

if len(doc_ids) > 1:
    st.caption(
        f"{len(doc_ids)} documents réunis. La position française de référence "
        "reste enregistrée document par document : sur un article présent "
        "dans deux tableaux, c'est la première trouvée qui s'applique, "
        "vérifiez-la dans l'encadré ci-dessous.")

st.divider()

# --------------------------------------------------------------- préparation
# Trois réglages préparatoires — la position française de référence, le
# lancement de l'analyse, le regroupement par titre — occupaient trois bandes
# empilées avant d'arriver au premier tableau. Ils sont réunis dans un seul
# encadré à onglets : rien n'est retiré, mais la page commence par ce qu'on
# vient y chercher.
_prep = st.expander(
    "Préparer : position française, analyse, regroupement par titre",
    expanded=analysed.empty)
with _prep:
    prep_fr, prep_analyse, prep_titres = st.tabs(
        ["Position française de référence", "Lancer l'analyse",
         "Regroupement par titre"])

# ----------------------------------------------------------- position de la FR
ref_df = store.load_fr_reference(doc_ids)
refs = dict(zip(ref_df["section_id"], ref_df["summary_fr"])) if not ref_df.empty else {}
kinds = dict(zip(ref_df["section_id"], ref_df["source"])) if not ref_df.empty else {}
ref_kinds = {k: ("silence" if "silence" in (v or "") else "explicite")
             for k, v in kinds.items()}

sections = (df[["section_id", "section_label", "section_order"]]
            .drop_duplicates().sort_values("section_order"))
silent_sections = [s for s in sections["section_id"] if s not in refs]

with prep_fr:
    st.markdown(
        "**Règle appliquée : ne pas amender vaut acceptation.** Sur un article "
        "où la France n'a déposé ni amendement ni commentaire, la référence est "
        "le maintien du texte initial en l'état. Un État membre qui en "
        "demande la suppression ou la réécriture s'en écarte ; celui qui "
        "l'accepte s'y aligne."
    )
    c1, c2 = st.columns([2, 1])
    c1.caption(
        f"{len(refs)} article(s) avec position française explicite · "
        f"{len(silent_sections)} article(s) traités par la règle du silence."
    )
    st.caption(
        ":material/info: **Rien n'est bloqué tant qu'il reste des articles "
        "« silence ».** Les deux cas sont traités : sur un article sans "
        "position explicite, la référence est le texte initial. Dériver les "
        "positions explicites ne conditionne donc pas l'analyse, cela la "
        "précise sur les articles que la France a effectivement amendés, et "
        "il vaut mieux le faire avant, parce qu'un changement de référence "
        "reclasse tout l'article.")
    if c2.button("Dériver les positions explicites", width="stretch"):
        fr_rows = df[df["ms_code"] == "FR"]
        groups = list(fr_rows.groupby(["section_id", "section_label"]))
        bar = st.progress(0.0, text="Synthèse des contributions françaises…")
        echecs: list[str] = []
        for i, ((sid, slabel), grp) in enumerate(groups, start=1):
            # Un article qui échoue ne doit pas emporter tous les autres :
            # on le note et on continue, la reprise se fera à l'identique.
            try:
                ref = derive_fr_reference(sid, slabel, list(grp["text"]))
                store.save_fr_reference(doc_id, sid, ref.summary_fr, ref.key_asks,
                                        "dérivée des contributions FR")
            except Exception as exc:
                echecs.append(f"{slabel}, {type(exc).__name__}: {exc}")
            bar.progress(i / max(len(groups), 1), text=slabel)
        bar.empty()
        if echecs:
            st.warning(
                f"{len(echecs)} article(s) sur {len(groups)} n'ont pas pu être "
                "synthétisés. Les autres sont enregistrés ; relancez pour "
                "réessayer, ou saisissez leur référence à la main ci-dessous.")
            with st.expander("Détail des échecs"):
                for e in echecs:
                    st.caption(e)
        else:
            st.rerun()

    st.divider()
    sid = st.selectbox(
        "Consulter ou corriger un article",
        options=list(sections["section_id"]),
        format_func=lambda s: (
            sections.set_index("section_id").loc[s, "section_label"]
            + ("  ✓ explicite" if s in refs else "  · silence = accord")),
    )
    fr_texts = df[(df["ms_code"] == "FR") & (df["section_id"] == sid)]["text"]
    if not fr_texts.empty:
        with st.popover("Contributions françaises sur cet article"):
            for t in fr_texts:
                st.markdown(f"> {t}")
                st.divider()

    new_ref = st.text_area(
        "Position de référence", height=160,
        value=refs.get(sid, FR_SILENCE_REFERENCE),
        help="Écraser ce texte crée une référence explicite qui prend le pas "
             "sur la règle du silence.")
    cc1, cc2 = st.columns(2)
    if cc1.button("Enregistrer comme position explicite", width="stretch"):
        store.save_fr_reference(doc_id, sid, new_ref, [], "saisie manuelle")
        st.rerun()
    if cc2.button("Revenir à la règle du silence", width="stretch",
                  disabled=sid not in refs):
        with store.connect() as con:
            con.execute("DELETE FROM fr_reference WHERE document_id = ? "
                        "AND section_id = ?", (doc_id, sid))
        st.rerun()

# --------------------------------------------------------------------- analyse
with prep_analyse:
    c1, c2 = st.columns(2)
    use_llm = c1.toggle("Utiliser le LLM", value=get_client().available,
                        disabled=not get_client().available)
    only_missing = c2.toggle("Ne traiter que les contributions non analysées", value=True)

    target = df[df["ms_code"] != "FR"]
    if only_missing:
        target = target[target["stance"].isna()]

    # Restreindre le lot : une première passe doit se juger sur dix minutes,
    # pas sur une heure. On garde le filtrage explicite plutôt qu'un
    # échantillon aléatoire, pour que le test soit reproductible.
    f1, f2 = st.columns(2)
    art_filter = f1.multiselect(
        "Limiter à certains articles",
        options=list(dict.fromkeys(df["section_label"])),
        help="Laisser vide pour traiter tous les articles.")
    ms_filter = f2.multiselect(
        "Limiter à certains États membres",
        options=sorted(df[df["ms_code"] != "FR"]["ms_code"].unique()),
        help="Laisser vide pour traiter tous les États membres.")
    if art_filter:
        target = target[target["section_label"].isin(art_filter)]
    if ms_filter:
        target = target[target["ms_code"].isin(ms_filter)]

    # Le volume se choisit en proportion, pas en nombre absolu : « un dixième »
    # veut dire quelque chose sans connaître la taille du document, « 40 » non.
    disponible = len(target)
    FRACTIONS = {
        "Un dixième, pour juger la qualité": 0.1,
        "La moitié": 0.5,
        "Toutes les contributions": 1.0,
    }
    choix = st.radio(
        "Quelle part des contributions traiter ?", list(FRACTIONS),
        index=2, horizontal=True,
        help="Commencez par un dixième pour juger la qualité du classement, "
             "puis lancez tout. Les contributions déjà analysées ne sont pas "
             "reprises si la case ci-dessus est cochée.")
    cap = max(1, round(disponible * FRACTIONS[choix]))

    repartir = st.checkbox(
        "Répartir l'échantillon sur tous les articles", value=True,
        help="Décoché, l'outil prend les premières contributions du document, "
             "donc les premiers articles seulement.")

    if len(target) > int(cap):
        if repartir:
            # Un tour de table article par article : on prend une contribution
            # sur chaque article, puis on recommence, jusqu'au plafond. Sinon
            # l'échantillon ne couvre que le début du document et la matrice
            # n'affiche que trois articles.
            target = target.assign(
                _rang=target.groupby("section_id").cumcount()
            ).sort_values(["_rang", "section_order", "ms_code"]).head(int(cap))
            target = target.drop(columns="_rang").sort_values(
                ["section_order", "ms_code"])
        else:
            target = target.head(int(cap))

    # Ordre de grandeur mesuré : environ 3 secondes par appel sur un modèle
    # de 24 milliards de paramètres. Sans modèle, le classement lexical est
    # instantané.
    st.info(duree_estimee(len(target), 3.0 if use_llm else 0.01,
                          f"{len(target)} contribution(s) à traiter"),
            icon=":material/schedule:")
    # D'où vient l'écart entre le nombre de contributions du document et le
    # nombre à traiter : la question se pose à chaque lancement.
    n_fr = int((df["ms_code"] == "FR").sum())
    n_deja = int(df[df["ms_code"] != "FR"]["stance"].notna().sum())
    details = [f"{len(df)} contribution(s) dans le document"]
    if n_fr:
        details.append(f"−{n_fr} française(s), qui servent de référence et ne "
                       "sont jamais classées")
    if only_missing and n_deja:
        details.append(f"−{n_deja} déjà analysée(s)")
    if art_filter or ms_filter:
        details.append("− le filtre article / État membre ci-dessus")
    if choix != "Toutes les contributions":
        details.append(f"× {FRACTIONS[choix]:.0%} ({choix.split(',')[0]})")
    st.caption(" · ".join(details) + f" = **{len(target)}**.")

    if st.button("Analyser", type="primary", width="stretch", disabled=target.empty):
        bar = st.progress(0.0)
        status = st.empty()
        depart = time.time()

        def progress(i: int, n: int, label: str) -> None:
            bar.progress(i / n, text=avancement(i, n, depart))
            status.caption(label)

        res = analyse_batch(
            target.to_dict("records"), refs, use_llm=use_llm,
            on_progress=progress, reference_kind_by_section=ref_kinds,
            save=lambda cid, a, m, mod: store.save_analysis(cid, a, m, mod),
        )
        bar.empty()
        status.empty()
        st.success(f"{res.analysed} contributions traitées, {res.llm_ok} par le "
                   f"modèle, {res.fallback} par heuristique.")
        if res.evidence_failed:
            st.warning(f"{res.evidence_failed} citations introuvables dans le "
                       "texte source : confiance ramenée à zéro, signalées dans le détail.")
        if res.errors:
            with st.expander(f"{len(res.errors)} erreurs"):
                for e in res.errors[:50]:
                    st.caption(e)
        st.rerun()

if analysed.empty:
    st.stop()

# --------------------------------------------------------------- référentiel
# Deux lectures du même document, et elles ne répondent pas à la même question.
REF_LABELS = {
    "fr": "Par rapport à la position française · « qui est avec nous ? »",
    "texte": "Par rapport au texte initial · « qui veut le changer ? »",
}
referentiel = st.radio(
    "Comparé à quoi ?", list(REF_LABELS), horizontal=True,
    format_func=lambda r: REF_LABELS[r],
    help="Position française : l'écart mesuré est l'écart à ce que demande la "
         "France (règle du silence comprise). Texte initial : l'écart "
         "mesuré est la demande de modification du texte lui-même, quel que "
         "soit l'avis français, c'est le calcul déterministe, sans modèle. "
         "Sur un article que la France n'a pas amendé, les deux coïncident.")

matrix = store.score_matrix(doc_ids, referentiel=referentiel)
st.session_state["last_matrix_doc"] = doc_ids

if matrix.empty:
    st.warning("Aucune position exploitable avec ce référentiel.")
    st.stop()

titre_ref = ("la position française" if referentiel == "fr"
             else "le texte initial")

# ------------------------------------------------------- regroupement par titre
# Un règlement se négocie titre par titre autant qu'article par article.
# Le rattachement vient du texte réglementaire s'il est chargé, sinon de
# bornes saisies à la main — jamais d'une devinette sur le numéro.
@st.cache_data(show_spinner=False)
def _titres_du_corpus(dossier: str) -> dict:
    corpus = store.list_documents()
    if corpus.empty:
        return {}
    textes = corpus[corpus.get("kind", pd.Series(dtype=str)) == "legal_text"]
    if dossier:
        meme = textes[textes["dossier"] == dossier]
        textes = meme if not meme.empty else textes
    trouves: dict[str, str] = {}
    for ref in textes["id"]:
        trouves.update(titres_depuis_texte(store.load_segments(ref)))
    return trouves


rattachement = dict(_titres_du_corpus(str(doc.get("dossier") or "")))
rattachement.update(st.session_state.get("titres_manuels", {}))

with prep_titres:
    st.caption(
        f"{len(set(rattachement.values()))} titre(s) reconnu(s)."
        if rattachement else "Aucun titre reconnu pour l'instant.")
    st.caption(
        "Le rattachement est lu dans le texte réglementaire du dossier quand "
        "il est chargé (en-têtes « TITRE IV, … »). Sinon, saisissez les "
        "bornes ci-dessous : « Titre IV, de l'article 98 à l'article 118 ».")

    connus = bornes_depuis_rattachement(rattachement)
    if connus:
        st.dataframe(
            pd.DataFrame([{"Titre": t, "Du": d, "Au": f}
                          for t, (d, f) in connus.items()]),
            width="stretch", hide_index=True)

    saisie = st.data_editor(
        pd.DataFrame(st.session_state.get(
            "bornes_titres",
            [{"Titre": "", "Premier article": 0, "Dernier article": 0}])),
        num_rows="dynamic", width="stretch", hide_index=True,
        key="editeur_bornes")
    if st.button("Appliquer ces bornes"):
        bornes = {}
        for _, ligne in saisie.iterrows():
            nom = str(ligne.get("Titre") or "").strip()
            try:
                debut, fin = int(ligne["Premier article"]), int(ligne["Dernier article"])
            except (TypeError, ValueError):
                continue
            if nom and debut and fin >= debut:
                bornes[nom] = (debut, fin)
        st.session_state["bornes_titres"] = saisie.to_dict("records")
        st.session_state["titres_manuels"] = titres_depuis_bornes(
            bornes, list(matrix.index))
        st.rerun()

titres_disponibles = ordre_des_titres(
    [t for t in rattachement.values()]) if rattachement else []
if titres_disponibles:
    choix_titres = st.multiselect(
        "N'afficher que ces titres", titres_disponibles,
        help="Laisser vide pour tout afficher. Le filtre vaut pour la "
             "matrice, les alliés, les articles clivants et l'export.")
    if choix_titres:
        retenus = [a for a in matrix.index
                   if rattachement.get(str(a)) in choix_titres]
        if retenus:
            matrix = matrix.loc[retenus]
            analysed = analysed[analysed["section_label"].isin(retenus)]
        else:
            st.warning("Aucun article de ce périmètre dans la matrice.")

# ------------------------------------------------------------------ fiabilité
comment_ca_marche("positions")
alertes = alertes_positions(df, matrix)
if referentiel == "fr":
    alertes += desaccord_referentiels(
        matrix, store.score_matrix(doc_ids, referentiel="texte"))
panneau_fiabilite(alertes)

# ----------------------------------------------------------------- restitution
t1, t2, t3, t4, t5, t6, t7 = st.tabs(
    ["Matrice d'alignement", "Tableau de suivi", "Alliés", "Articles clivants",
     "Détail", "Non-papers et notes", "Export"])

# Position française par intitulé d'article : sans elle, « opposé » ne veut
# rien dire. C'est le rappel que le suivi tenu à la main met en première
# colonne, et il manquait ici.
label_par_id = dict(zip(sections["section_id"], sections["section_label"]))
fr_positions = {label_par_id[sid]: (refs.get(sid) or "").strip()
                for sid in sections["section_id"] if sid in label_par_id}

# Sujet de l'article, lu dans un texte réglementaire du même dossier s'il est
# chargé : « Art. 111 » ne dit rien, « Art. 111 — Interdictions réseaux de
# communication » se lit en réunion.
@st.cache_data(show_spinner=False)
def _sujets_depuis_textes(dossier: str) -> dict:
    trouves: dict[str, str] = {}
    corpus = store.list_documents()
    if corpus.empty:
        return trouves
    textes = corpus[corpus.get("kind", pd.Series(dtype=str)) == "legal_text"]
    if dossier:
        meme = textes[textes["dossier"] == dossier]
        textes = meme if not meme.empty else textes
    for doc_ref in textes["id"]:
        segs = store.load_segments(doc_ref)
        if segs is None or segs.empty:
            continue
        for label, texte in zip(segs["section_label"], segs["text"]):
            if label not in trouves:
                sujet = sujet_article(str(texte or ""))
                if sujet:
                    trouves[str(label)] = sujet
    return trouves


sujets = _sujets_depuis_textes(str(doc.get("dossier") or ""))

with t1:
    with st.expander("Position française de référence, article par article",
                     expanded=False):
        st.caption(
            "À lire avant la matrice : « opposé » veut dire « s'écarte de "
            "cette position-là ». Sur un article sans amendement français, la "
            "référence est le maintien du texte en l'état.")
        st.dataframe(
            pd.DataFrame({
                "Article": list(matrix.index),
                "Sujet": [sujets.get(a, "—") for a in matrix.index],
                "Position française": [
                    fr_positions.get(a) or
                    "Aucun amendement français : maintien du texte en l'état."
                    for a in matrix.index],
                "Origine": ["amendement écrit" if fr_positions.get(a)
                            else "règle du silence" for a in matrix.index],
            }), width="stretch", hide_index=True)

    st.plotly_chart(
        alignment_heatmap(matrix, f"Écart à {titre_ref}, article par article"),
        width="stretch")
    st.caption(
        "2 aligné · 1 partiel · 0 opposé. Case vide = pas de contribution, ou "
        "aucune position exprimée, et une absence de position n'est pas un "
        "accord : quand ni la France ni l'État membre n'ont amendé l'article, "
        "la case reste vide. Quand un État s'exprime plusieurs fois sur un "
        "article, la position la plus défavorable est retenue."
    )
    with st.expander("Voir les données sous forme de tableau"):
        st.dataframe(matrix, width="stretch")

with t2:
    st.caption(
        "Le tableau de suivi tel qu'il se tient à la main : une ligne par "
        "article, la position française en première colonne, un État membre "
        "par colonne. La couleur est celle de la compatibilité avec "
        f"{titre_ref}, c'est exactement la feuille « Détail par article » du "
        "classeur exporté, à l'écran et avant de l'exporter.")

    c1, c2 = st.columns([3, 2], gap="large")
    articles_suivi = c1.multiselect(
        "Articles à afficher", options=list(matrix.index),
        help="Laisser vide pour tous les afficher. Sur un règlement long, "
             "se limiter à un titre rend le tableau lisible sans défilement.")
    ms_suivi = c2.multiselect(
        "États membres à afficher", options=list(matrix.columns),
        help="Laisser vide pour tous les afficher.")

    vue = matrix
    if articles_suivi:
        vue = vue.loc[articles_suivi]
    if ms_suivi:
        vue = vue[ms_suivi]

    detail_suivi = analysed
    if articles_suivi:
        detail_suivi = detail_suivi[
            detail_suivi["section_label"].isin(articles_suivi)]
    if ms_suivi:
        detail_suivi = detail_suivi[detail_suivi["ms_code"].isin(ms_suivi)]

    pal_active = couleurs(st.session_state.get("palette"))
    tableau_suivi(vue, detail_suivi, fr_positions, sujets, pal_active)

    l1, l2, l3, l4 = st.columns(4)
    for col, (couleur, libelle) in zip(
            (l1, l2, l3, l4),
            ((pal_active["aligne"], "Aligné"),
             (pal_active["partiel"], "Partiellement aligné"),
             (pal_active["oppose"], "Divergent"),
             (pal_active["absent"], "Pas de position exprimée"))):
        col.markdown(
            f"<div style='background:{couleur};color:#0b0b0b;padding:4px 8px;"
            f"border-radius:4px;font-size:0.82rem;text-align:center'>"
            f"{libelle}</div>", unsafe_allow_html=True)
    st.caption(
        "Chaque case porte le résumé de la contribution et, entre crochets, la "
        "disposition citée ou la page. Au-delà de deux contributions d'un même "
        "État sur un article, la case indique combien il en reste, toutes "
        "figurent dans l'onglet Détail et dans le classeur. La couleur suit la "
        "position la plus défavorable exprimée.")

with t3:
    ranking = ally_ranking(matrix)
    c1, c2 = st.columns([3, 2], gap="large")
    c1.plotly_chart(ally_bars(ranking, f"Proximité moyenne avec {titre_ref}"),
                    width="stretch")
    c2.plotly_chart(stance_breakdown(analysed[analysed["ms_code"] != "FR"],
                                     "Répartition des positions"), width="stretch")
    st.dataframe(ranking, width="stretch")

    # ------------------------------------------------ pondération d'un critère
    # Volontairement repliée et lancée à la main : rien n'est pondéré tant que
    # l'agent n'a pas écrit son critère. Le classement brut reste au-dessus.
    st.divider()
    with st.expander("Donner plus de poids à un type de position "
                     "(facultatif)"):
        st.caption(
            "Toutes les divergences ne pèsent pas pareil : une opposition sur "
            "une virgule et une opposition sur le rôle de la Commission "
            "comptent autant dans une moyenne, ce qui est faux "
            "politiquement. Décrivez ci-dessous le type de position qui "
            "compte double pour vous.")
        critere = st.text_area(
            "Critère, en français", height=90,
            placeholder="Les positions qui demandent de supprimer "
                        "l'intervention de la Commission dans la désignation "
                        "des fournisseurs à risque.")
        pc1, pc2 = st.columns([1, 2])
        facteur = pc1.slider("Facteur", 1.5, 5.0, 2.0, 0.5,
                             help="Une contribution retenue par le critère "
                                  "compte pour ce nombre de contributions.")
        cible_pond = analysed[analysed["ms_code"] != "FR"]
        pc2.caption(duree_estimee(len(cible_pond), 3.0,
                                  f"{len(cible_pond)} contribution(s) à examiner"))

        if st.button("Évaluer le critère", type="primary",
                     disabled=not critere.strip() or cible_pond.empty):
            bar = st.progress(0.0)
            etat = st.empty()
            depart = time.time()

            def suivi(i, n, libelle):
                bar.progress(i / n, text=avancement(i, n, depart))
                etat.caption(libelle)

            st.session_state["ponderation"] = evaluer_ponderation(
                cible_pond, critere, facteur, on_progress=suivi)
            bar.empty()
            etat.empty()
            st.rerun()

        resultat_pond = st.session_state.get("ponderation")
        if resultat_pond and resultat_pond.critere:
            st.success(
                f"**{resultat_pond.retenues}** contribution(s) retenue(s) par "
                f"le critère sur {resultat_pond.examinees} examinée(s), "
                f"pondérées ×{resultat_pond.facteur:g}.")
            if resultat_pond.refusees:
                st.warning(
                    f"{resultat_pond.refusees} correspondance(s) écartée(s) : "
                    "la citation n'a pas été retrouvée dans le texte source.")
            for e in resultat_pond.erreurs[:3]:
                st.caption(e)

            classement = classement_pondere(cible_pond, resultat_pond)
            st.markdown("**Classement pondéré, et ce que la pondération change**")
            st.caption(
                "La colonne « Écart » est celle qu'il faut lire : un écart nul "
                "signifie que le critère ne discrimine pas cet État membre.")
            st.dataframe(classement, width="stretch", hide_index=True)

            if st.button("Oublier cette pondération"):
                st.session_state.pop("ponderation", None)
                st.rerun()

with t4:
    stats = contentious_articles(matrix)
    st.caption(
        f"Consensus mesuré par rapport à {titre_ref}. Basculez le référentiel "
        "en haut de page : un article peut faire consensus contre la position "
        "française et diviser sur le texte lui-même.")
    st.plotly_chart(contentious_scatter(stats, "Articles par niveau de consensus"),
                    width="stretch")
    st.caption(
        "En bas à gauche : opposition large et homogène. En haut : article "
        "clivant, où les États membres se divisent, ce sont les points "
        "d'appui d'une négociation."
    )
    st.dataframe(stats, width="stretch")

with t5:
    c1, c2, c3, c4 = st.columns(4)
    ms = c1.multiselect("États membres", sorted(analysed["ms_code"].unique()))
    themes_dispo = sorted({t for liste in analysed["themes"].dropna()
                           for t in _themes(liste)})
    themes_sel = c2.multiselect(
        "Thèmes", themes_dispo,
        help="Un dossier se négocie enjeu par enjeu autant qu'article par "
             "article : le filtre thématique vient donc avant les articles.")
    arts = c3.multiselect("Articles", list(dict.fromkeys(analysed["section_label"])))
    stances = c4.multiselect("Positions", list(STANCE_LABEL_FR),
                             format_func=lambda s: STANCE_LABEL_FR[s])
    view = analysed
    if ms:
        view = view[view["ms_code"].isin(ms)]
    if themes_sel:
        view = view[view["themes"].map(
            lambda liste: bool(set(_themes(liste)) & set(themes_sel)))]
    if arts:
        view = view[view["section_label"].isin(arts)]
    if stances:
        view = view[view["stance"].isin(stances)]

    st.caption(
        f"{len(view)} contributions. L'intitulé reprend la disposition visée "
        "par la délégation quand elle la cite · « § 2 », « considérant 12 », "
        "et, à défaut, les premiers mots du commentaire : quatre lignes "
        "« Article 5 » ne se distinguaient pas les unes des autres.")
    for _, row in view.head(120).iterrows():
        icon = {"aligne": "▲", "partiel": "◆", "oppose": "▼"}.get(row["stance"], "·")
        intitule = preciser(row["section_label"], row["text"])
        with st.expander(f"{icon} {row['ms_code']} · {intitule} · "
                         f"{STANCE_LABEL_FR.get(row['stance'], '?')}"):
            reference_fr = fr_positions.get(row["section_label"], "")
            st.markdown(
                "**Position française de référence**, "
                + (reference_fr or "aucun amendement français : maintien du "
                                   "texte en l'état (règle du silence)."))
            st.markdown(f"**Ce qu'en dit {row['ms_code']}**, {row['summary_fr']}")
            st.markdown("**Passage cité dans le texte source**")
            st.markdown(f"> {row['evidence']}")
            meta = []
            if row["scrutiny"]:
                meta.append("réserve d'examen")
            if row["deletion"]:
                meta.append("demande de suppression")
            themes = json.loads(row["themes"]) if row["themes"] else []
            if themes:
                meta.append("thèmes : " + ", ".join(themes))
            meta += [f"méthode : {row['method']}",
                     f"confiance : {row['confidence']:.2f}",
                     f"pages {row['page_start']}–{row['page_end']}"]
            st.caption(" · ".join(meta))
            with st.popover("Texte intégral"):
                st.write(row["text"])

with t6:
    st.info(
        "**Toutes les positions n'arrivent pas dans un tableau.** Un "
        "non-paper, un papier blanc, une note ministre, un compte rendu de "
        "réunion : chargez le document depuis la Bibliothèque, puis "
        "sélectionnez-le ici. L'outil propose les positions qu'il y lit ; "
        "**rien n'entre dans la matrice avant que vous ayez validé.**",
        icon=":material/note_add:")

    libres = docs[docs.get("kind", pd.Series(dtype=str)).isin(
        ["free_text", "legal_text"])] if not docs.empty else docs
    if libres.empty:
        st.warning(
            "Aucun document libre au corpus. Chargez le non-paper depuis la "
            "**Bibliothèque**, en type « Texte libre ».")
    else:
        index_libres = libres.set_index("id")
        n1, n2 = st.columns([2, 1])
        source_id = n1.selectbox(
            "Document à dépouiller", options=list(libres["id"]),
            format_func=lambda i: index_libres.loc[i, "name"])
        segments_source = store.load_segments(source_id)

        entete = "\n".join(str(t) for t in segments_source["text"].head(2)) \
            if not segments_source.empty else ""
        propose = (index_libres.loc[source_id].get("author_ms")
                   or deviner_auteur(
                       str(index_libres.loc[source_id, "name"]) + " " + entete))
        codes = [""] + MS_CODES
        auteur = n2.selectbox(
            "État membre auteur", options=codes,
            index=codes.index(propose) if propose in codes else 0,
            help="Deviné depuis le titre et l'en-tête du document. Corrigez "
                 "si besoin : c'est la colonne dans laquelle les positions "
                 "iront.")

        st.caption(duree_estimee(min(len(segments_source), 60), 3.0,
                                 f"{min(len(segments_source), 60)} segment(s) "
                                 "à dépouiller"))

        if st.button("Proposer les positions", type="primary",
                     disabled=not auteur or segments_source.empty):
            bar = st.progress(0.0)
            etat = st.empty()
            depart = time.time()

            def suivi(i, n, libelle):
                bar.progress(i / n, text=avancement(i, n, depart))
                etat.caption(libelle)

            st.session_state["extraction_np"] = extraire_positions(
                segments_source, auteur,
                source=str(index_libres.loc[source_id, "name"]),
                articles_connus=list(matrix.index), on_progress=suivi)
            bar.empty()
            etat.empty()
            st.rerun()

        extraction = st.session_state.get("extraction_np")
        if extraction is not None:
            for e in extraction.erreurs[:3]:
                st.warning(e)
            if extraction.sans_citation:
                st.caption(
                    f"{extraction.sans_citation} position(s) écartée(s) "
                    "d'office : citation introuvable dans le document.")

            table = extraction.table()
            if table.empty:
                st.info("Aucune position exploitable trouvée dans ce document.")
            else:
                st.markdown("### À valider avant enregistrement")
                st.caption(
                    "Décochez ce qui est faux, corrigez l'article quand le "
                    "rattachement se trompe. « Rattachement sûr » à faux "
                    "signale une position dont l'article n'est pas cité "
                    "explicitement dans le texte, ou inconnu de la matrice.")
                valide = st.data_editor(
                    table, width="stretch", hide_index=True, num_rows="fixed",
                    column_config={
                        "Retenir": st.column_config.CheckboxColumn(
                            "Retenir", default=True),
                        "Citation": st.column_config.TextColumn(
                            "Citation", disabled=True, width="large"),
                        "Rattachement sûr": st.column_config.CheckboxColumn(
                            "Rattachement sûr", disabled=True),
                    })

                cible_doc = st.selectbox(
                    "Rattacher ces positions au document",
                    options=doc_ids,
                    format_func=lambda i: index_wk.loc[i, "name"],
                    help="Les positions rejoignent la matrice de ce document, "
                         "en gardant la trace de leur source.")

                if st.button("Enregistrer les positions retenues",
                             type="primary"):
                    for i, prop in enumerate(extraction.propositions):
                        if i < len(valide):
                            ligne = valide.iloc[i]
                            prop.retenue = bool(ligne["Retenir"])
                            prop.article = str(ligne["Article"]).strip()
                    contributions, analyses = positions_en_contributions(
                        extraction.propositions,
                        str(index_libres.loc[source_id, "name"]))
                    if not contributions:
                        st.warning("Aucune position retenue.")
                    else:
                        ids = store.append_contributions(cible_doc, contributions)
                        for cid, analyse in zip(ids, analyses):
                            store.save_analysis(cid, analyse, "non-paper validé",
                                                "—")
                        st.session_state.pop("extraction_np", None)
                        st.success(
                            f"{len(ids)} position(s) ajoutée(s) à la matrice.")
                        st.rerun()

with t7:
    st.markdown("### Périmètre de l'export")
    sel_articles = st.multiselect(
        "Articles à inclure", options=list(matrix.index),
        help="Laisser vide pour tout inclure. Utile pour produire une note "
             "sur un titre ou un enjeu précis.")
    sel_ms = st.multiselect(
        "États membres à inclure", options=list(matrix.columns),
        help="Laisser vide pour tous les inclure.")

    export_matrix = matrix
    if sel_articles:
        export_matrix = export_matrix.loc[sel_articles]
    if sel_ms:
        export_matrix = export_matrix[sel_ms]

    palette = st.session_state.get("palette", actif())
    st.caption(
        f"Couleurs : **{PALETTES[palette]['nom']}**. Le choix se fait une fois "
        "pour toute l'application, en bas du bandeau de gauche, écrans, "
        "images, note Word et classeur suivent le même code.")

    # Les intitulés d'articles peuvent être réécrits pour la note : « Art. 100 »
    # devient « Désignation des pays tiers » si l'analyste le souhaite.
    with st.expander("Intitulés et sujets des articles"):
        st.caption(
            "Un intitulé parlant vaut mieux qu'un numéro dans une note de "
            "direction. Le sujet est repris sous le numéro d'article dans le "
            "tableau de suivi, comme dans votre fichier tenu à la main, il "
            "est pré-rempli depuis le texte réglementaire quand il est chargé. "
            "Ces modifications ne valent que pour l'export.")
        labels_df = st.data_editor(
            pd.DataFrame({
                "Article": list(export_matrix.index),
                "Intitulé pour la note": list(export_matrix.index),
                "Sujet de l'article": [sujets.get(a, "") for a in export_matrix.index],
            }),
            width="stretch", hide_index=True, num_rows="fixed",
            column_config={"Article": st.column_config.TextColumn(disabled=True)},
        )
        labels = dict(zip(labels_df["Article"], labels_df["Intitulé pour la note"]))
        sujets_export = {a: str(t).strip() for a, t in
                         zip(labels_df["Article"], labels_df["Sujet de l'article"])
                         if str(t).strip()}

    export_ranking = ally_ranking(export_matrix)
    export_contentious = contentious_articles(export_matrix)
    export_df = analysed
    if sel_articles:
        export_df = export_df[export_df["section_label"].isin(sel_articles)]
    if sel_ms:
        export_df = export_df[export_df["ms_code"].isin(sel_ms)]

    d1, d2 = st.columns([1, 1])
    avec_detail = d1.checkbox(
        "Inclure le texte de détail dans la note Word", value=True,
        help="Ajoute, article par article, ce que dit chaque État membre et la "
             "citation qui le fonde. La note s'allonge, mais elle devient "
             "vérifiable sans rouvrir le document source.")
    detail_max = d2.number_input(
        "Contributions détaillées au maximum", min_value=20, max_value=2000,
        value=400, step=50, disabled=not avec_detail,
        help="Au-delà, la note renvoie au classeur Excel, qui les porte toutes.")

    st.divider()
    st.markdown("### Livrables")

    if export_matrix.empty:
        st.warning("Le périmètre sélectionné ne contient aucune donnée.")
        st.stop()

    base = f"{doc['name'][:50]}"

    # --- images ------------------------------------------------------------
    figures: list[tuple[str, bytes]] = []
    try:
        figures.append(("Positions article par article",
                        heatmap_png(export_matrix,
                                    "Positions article par article × État membre",
                                    palette=palette, labels=labels)))
        if not export_ranking.empty:
            figures.append(("Proximité avec la position française",
                            ranking_png(export_ranking,
                                        "Proximité moyenne avec la France")))
        figures.append(("Niveau d'engagement des États membres",
                        engagement_png(export_df,
                                       "Contributions écrites par État membre")))
    except ValueError as exc:
        st.warning(f"Certaines figures n'ont pas pu être produites : {exc}")

    cols = st.columns(min(3, max(len(figures), 1)))
    for col, (legende, png) in zip(cols, figures):
        col.image(png, caption=legende)
        col.download_button(
            "PNG", data=png, file_name=f"{base}_{legende[:28]}.png",
            mime="image/png", width="stretch", key=f"png_{legende}")

    st.divider()
    c1, c2, c3 = st.columns(3)

    METHODE = (
        "Positions établies à partir des contributions écrites des États "
        "membres. Sur un article que la France n'a pas amendé, la référence "
        "est le maintien du texte initial en l'état. Lorsqu'un État "
        "s'exprime plusieurs fois sur un article, la position la plus "
        "éloignée est retenue. Chaque classement est adossé à une citation "
        "vérifiée dans le document source.")

    # --- note Word ---------------------------------------------------------
    docx_bytes = build_docx(
        titre="Cartographie des positions des États membres",
        dossier=f"{doc.get('dossier') or 'Dossier'} · {doc['name']}",
        matrix=export_matrix, ranking=export_ranking,
        contentious=export_contentious, images=figures, labels=labels,
        palette=palette, methodologie=METHODE,
        detail=export_df if avec_detail else None,
        detail_max=int(detail_max),
        fr_positions=fr_positions, sujets=sujets_export,
    )
    c1.download_button(
        "Note Word modifiable (.docx)", data=docx_bytes,
        file_name=f"{base}_note.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch", type="primary")

    # --- classeur ----------------------------------------------------------
    xlsx_bytes = build_xlsx(
        titre="Cartographie des positions des États membres",
        dossier=f"{doc.get('dossier') or 'Dossier'} · {doc['name']}",
        matrix=export_matrix, ranking=export_ranking,
        contentious=export_contentious, detail=export_df,
        images=figures, labels=labels, palette=palette,
        methodologie=METHODE,
        fr_positions=fr_positions, sujets=sujets_export,
    )
    c2.download_button(
        "Classeur Excel (.xlsx)", data=xlsx_bytes,
        file_name=f"{base}_analyse.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch", type="primary")

    c3.download_button(
        "Contributions brutes (.csv)",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{base}_contributions.csv", mime="text/csv",
        width="stretch")

    st.caption(
        "La note Word contient de vrais tableaux, pas des captures, et, si la "
        "case est cochée, le texte de chaque contribution avec sa citation. "
        "Le classeur Excel porte des graphiques liés aux cellules : corriger "
        "une valeur met le graphique à jour, sans repasser par l'outil."
    )
