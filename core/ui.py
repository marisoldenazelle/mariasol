"""
Éléments d'interface partagés — surtout : comment un module s'explique.

Une règle, tirée de la phase de test : **l'explication courte va en haut, le
détail va en bas.** Un agent qui ouvre un onglet pour la première fois doit
comprendre en deux phrases ce que l'écran lui montre et à quelle question il
répond. Celui qui veut savoir comment le calcul est fait le trouve en bas de
page, replié, sans que cela encombre l'usage courant.

Le corollaire tient à la formulation : un intitulé posé comme une question
— « Qui est avec nous ? » — dit ce qu'on vient chercher ; un intitulé nominal
— « Matrice d'alignement » — dit ce que le programme fabrique. Le premier
s'adresse à l'agent, le second au développeur.
"""

from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Le lettrage de la marque
# ---------------------------------------------------------------------------
#
# Le nom s'écrit comme le logo le dessine : « mar », le « i » et le « a » en
# rouge Marianne — l'IA —, le « a » en exposant pour que le mot se lise
# « marisol », puis « sol » en bleu France. Écrit en texte ordinaire, le nom
# perdait cette lecture partout ailleurs que dans le logo.
#
# Les styles sont posés en ligne plutôt que par une feuille de style : chaque
# page doit pouvoir s'afficher seule — c'est le cas dans les tests, et sur une
# page ouverte directement — sans dépendre d'un CSS injecté par `app.py`.
BLEU_FRANCE = "#000091"
ROUGE_MARIANNE = "#e1000f"


def nom_marque(taille: str = "1em", couleur: str = BLEU_FRANCE,
               accent: str = ROUGE_MARIANNE) -> str:
    """Le nom de l'application au lettrage du logo, en HTML."""
    return (
        f'<span style="font-weight:800;letter-spacing:-0.015em;'
        f'font-size:{taille};color:{couleur};white-space:nowrap;'
        f'line-height:1.1">'
        f'mar<span style="color:{accent}">i</span>'
        f'<span style="color:{accent};font-size:0.6em;vertical-align:0.62em;'
        f'font-weight:800">a</span>'
        f'sol</span>')


def entete_module(question: str, resume: str) -> None:
    """Titre de page formulé en question, plus une phrase de cadrage.

    `question` peut contenir le lettrage de la marque : le titre est donc
    rendu en HTML, à la taille d'un `st.title`.
    """
    # `st.markdown("# …")` produit exactement le h1 de `st.title`, à ceci près
    # qu'il accepte le lettrage de la marque à l'intérieur du titre.
    st.markdown(f"# {question}", unsafe_allow_html=True)
    st.caption(resume)


def encadre(resume: str, icone: str = ":material/lightbulb:") -> None:
    """Explication courte, en tête d'onglet. Deux phrases au plus."""
    st.info(resume, icon=icone)


def pour_aller_plus_loin(titre: str, corps: str) -> None:
    """Le détail de méthode, replié, en bas de page."""
    st.divider()
    with st.expander(titre):
        st.markdown(corps)


def aide_duree(message: str) -> None:
    st.caption(f":material/schedule: {message}")


def comment_ca_marche(module: str, titre: str = "Comment ça marche ?") -> None:
    """Fenêtre dépliante d'explication, alimentée par la base de connaissance.

    Une seule source pour toutes les explications de l'application : si un
    calcul change, la fiche change, et les six endroits qui l'expliquent
    changent avec elle.
    """
    from .aide import fiches_du_module

    fiches = fiches_du_module(module)
    if not fiches:
        return
    with st.expander(f":material/help: {titre}"):
        for i, fiche in enumerate(fiches):
            st.markdown(f"**{fiche.question}**")
            st.markdown(fiche.reponse)
            if i < len(fiches) - 1:
                st.divider()
        st.caption(
            "Une question qui n'est pas traitée ici ? La page **Mode "
            "d'emploi** porte un assistant qui répond sur le fonctionnement "
            "de l'application.")


def panneau_fiabilite(alertes: list, titre: str = "Fiabilité et points d'attention") -> None:
    """Ce qui, dans le résultat affiché, demande l'œil de l'agent.

    Volontairement dans une fenêtre à part : ces alertes ne partent pas dans
    les livrables. Une note de direction n'a pas à porter les doutes de
    l'outil ; l'analyste, si.
    """
    from .fiabilite import resume

    if not alertes:
        st.caption(":material/check_circle: Aucun point d'attention détecté "
                   "sur ce périmètre.")
        return

    # Le panneau reste replié, y compris quand une alerte est bloquante : le
    # résumé est déjà visible dans l'intitulé, et un encadré qui s'ouvre seul
    # au milieu d'une page de travail déplace tout ce qui est en dessous.
    with st.expander(f":material/troubleshoot: {titre} · {resume(alertes)}",
                     expanded=False):
        st.caption(
            "Ces points ne figurent pas dans les documents exportés : ils "
            "s'adressent à vous, pas au destinataire de la note.")
        for a in alertes:
            st.markdown(f"{a.icone} **{a.titre}**")
            st.markdown(
                f"<div style='color:#52514e;font-size:0.9rem;"
                f"margin:-0.4rem 0 0.2rem 1.4rem;'>{a.detail}</div>",
                unsafe_allow_html=True)
            if a.quoi_faire:
                st.markdown(
                    f"<div style='color:#0b0b0b;font-size:0.9rem;"
                    f"margin:0 0 0.8rem 1.4rem;'>→ {a.quoi_faire}</div>",
                    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tableau de suivi — la même chose que la feuille Excel, mais à l'écran
# ---------------------------------------------------------------------------

def _echapper(texte: str) -> str:
    """HTML échappé : le texte vient des documents, pas de nous."""
    return (str(texte or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>"))


def tableau_suivi(matrix, detail, fr_positions: dict, sujets: dict,
                  pal: dict, hauteur: int = 620) -> None:
    """Le suivi tenu à la main, reproduit à l'écran, en couleur.

    C'est la forme que la direction lit déjà : une ligne par article, la
    position française en première colonne — sans elle « opposé » ne veut rien
    dire), puis un État membre par colonne, chaque case portant le résumé de
    la contribution et la référence de la disposition citée. La couleur est
    celle de la palette active, la même que dans le classeur exporté.

    Streamlit ne sait pas colorer une cellule de `st.dataframe` cellule par
    cellule avec du texte long : on écrit donc le tableau en HTML, dans un
    conteneur qui défile dans les deux sens. C'est le seul endroit de
    l'application où l'affichage est produit à la main, et la raison est
    celle-là.
    """
    # Import tardif : ces deux fonctions décident du contenu et de la couleur
    # d'une case dans le classeur. Les réécrire ici ferait diverger l'écran et
    # l'export au premier changement de règle.
    from .excel import _stance_dominante, _texte_de_case

    if matrix is None or matrix.empty:
        st.caption("Aucun article à afficher.")
        return

    colonnes = [c for c in matrix.columns if c != "FR"]
    couleurs_stance = {"aligne": pal["aligne"], "partiel": pal["partiel"],
                       "oppose": pal["oppose"], "neutre": pal["absent"]}
    texte_case = "#0b0b0b"

    entete = "".join(
        f'<th class="rw-ms">{_echapper(c)}</th>' for c in colonnes)
    lignes = []
    for article in matrix.index:
        sujet = str(sujets.get(article, "") or "").strip()
        reference = (fr_positions.get(article) or "").strip()
        cellules = [
            f'<th class="rw-art">{_echapper(article)}'
            + (f'<div class="rw-sujet">{_echapper(sujet)}</div>' if sujet else "")
            + "</th>",
            f'<td class="rw-fr">{_echapper(reference) if reference else ""}'
            + ("" if reference else
               '<span class="rw-silence">Aucun amendement français : '
               'maintien du texte en l\'état<br>[règle du silence]</span>')
            + "</td>",
        ]
        bloc = detail[detail["section_label"] == article] if detail is not None \
            else None
        for code in colonnes:
            lot = bloc[bloc["ms_code"] == code] if bloc is not None else None
            if lot is None or lot.empty:
                cellules.append(
                    f'<td style="background:{pal["absent"]};'
                    f'color:{texte_case}">—</td>')
                continue
            fond = couleurs_stance.get(_stance_dominante(lot), pal["absent"])
            cellules.append(
                f'<td style="background:{fond};color:{texte_case}">'
                f'{_echapper(_texte_de_case(lot))}</td>')
        lignes.append("<tr>" + "".join(cellules) + "</tr>")

    html = f"""
<div class="rw-suivi" style="max-height:{hauteur}px">
<table>
  <thead><tr>
    <th class="rw-art">Article</th>
    <th class="rw-fr">Position française de référence</th>{entete}
  </tr></thead>
  <tbody>{''.join(lignes)}</tbody>
</table>
</div>
<style>
.rw-suivi {{ overflow:auto; border:1px solid #ddddd8; border-radius:6px; }}
.rw-suivi table {{ border-collapse:separate; border-spacing:0;
                   font-size:0.82rem; line-height:1.35; }}
.rw-suivi th, .rw-suivi td {{ border-right:1px solid #ffffff;
    border-bottom:1px solid #ffffff; padding:6px 8px; vertical-align:top;
    min-width:230px; max-width:230px; }}
.rw-suivi thead th {{ position:sticky; top:0; z-index:3;
    background:{pal["entete_ms"]}; color:#ffffff; font-weight:600; }}
.rw-suivi thead th.rw-art, .rw-suivi thead th.rw-fr {{
    background:{pal["entete"]}; }}
.rw-suivi th.rw-art {{ position:sticky; left:0; z-index:2;
    background:{pal["reference"]}; color:#0b0b0b; text-align:left;
    min-width:150px; max-width:150px; font-weight:700; }}
.rw-suivi td.rw-fr {{ background:{pal["reference"]}; color:#0b0b0b;
    font-weight:600; min-width:260px; max-width:260px; }}
.rw-suivi thead th.rw-art {{ z-index:4; }}
.rw-suivi .rw-sujet {{ font-weight:400; font-size:0.76rem; color:#3b3a37; }}
.rw-suivi .rw-silence {{ font-weight:400; font-style:italic; color:#3b3a37; }}
</style>
"""
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Carte d'un acte modificatif
# ---------------------------------------------------------------------------

COULEUR_IMPACT = {
    "majeur": ("#e1000f", "#ffffff"),
    "mineur": ("#f0a202", "#0b0b0b"),
    "redactionnel": ("#c9c8c2", "#0b0b0b"),
    "": ("#eeedea", "#52514e"),
}
# Sans caractérisation, la couleur suit l'opération : elle dit ce que le
# législateur écrit, ce qui est déjà une information, et elle évite un écran
# uniformément gris tant que le modèle n'a pas tourné.
COULEUR_OPERATION = {
    "Supprimé": "#e1000f", "Abrogé": "#a3000b", "Inséré": "#0ca30c",
    "Ajouté": "#5aa02c", "Remplacé": "#000091", "Modifié": "#6a6af4",
    "Maintien transitoire": "#898781", "Non analysée": "#c9c8c2",
}


def carte_modificatif(synthese, par_impact: bool = True) -> str:
    """La carte d'un omnibus : une ligne par texte modifié, une case par article.

    Un omnibus qui touche dix règlements se lit d'abord de haut. Un tableau à
    dix lignes fait défiler ; une carte tient dans un écran et répond en une
    seconde à la seule question qui vaut au moment où le dossier arrive : où
    ce texte frappe-t-il fort. Chaque case porte l'article, sa couleur dit la
    portée (ou l'opération tant que la portée n'est pas caractérisée), et
    l'infobulle porte le résumé.
    """
    if not synthese.lignes:
        return ""

    cases_par_texte = []
    for _, lignes in synthese.par_texte.items():
        titre = lignes[0].nom_cible or lignes[0].acte_cible
        sous_titre = lignes[0].acte_cible if lignes[0].nom_cible else ""
        cases = []
        for ligne in lignes:
            if par_impact:
                fond, encre = COULEUR_IMPACT.get(
                    ligne.impact, COULEUR_IMPACT[""])
            else:
                fond = COULEUR_OPERATION.get(
                    ligne.operations[0] if ligne.operations else "", "#eeedea")
                encre = "#ffffff"
            infobulle = " · ".join(filter(None, [
                ligne.article,
                ", ".join(ligne.operations),
                f"{ligne.nb_modifications} modification(s)",
                f"page {ligne.page_min}" if ligne.page_min else "",
                ligne.impact or "portée non caractérisée",
                (ligne.resume or "")[:400]]))
            numero = ligne.article.replace("Article ", "art. ").replace(
                "Annexe ", "ann. ")
            cases.append(
                f'<span class="rw-case" title="{_echapper(infobulle)}" '
                f'style="background:{fond};color:{encre};">'
                f'{_echapper(numero)}'
                + (f'<sup>{ligne.nb_modifications}</sup>'
                   if ligne.nb_modifications > 1 else "")
                + '</span>')
        cases_par_texte.append(
            '<div class="rw-rang">'
            f'<div class="rw-titre">{_echapper(titre)}'
            + (f'<div class="rw-ref">{_echapper(sous_titre)}</div>'
               if sous_titre else "")
            + '</div>'
            f'<div class="rw-cases">{"".join(cases)}</div>'
            '</div>')

    legende_source = (COULEUR_IMPACT if par_impact else
                      {k: (v, "#ffffff") for k, v in COULEUR_OPERATION.items()})
    libelles = {"majeur": "Majeur", "mineur": "Mineur",
                "redactionnel": "Rédactionnel", "": "Non caractérisé"}
    legende = "".join(
        f'<span class="rw-leg"><i style="background:{fond}"></i>'
        f'{_echapper(libelles.get(cle, cle))}</span>'
        for cle, (fond, _) in legende_source.items())

    return f"""
<style>
.rw-carte {{ font-size:0.9rem; }}
.rw-rang {{ display:flex; gap:0.8rem; align-items:flex-start;
            padding:0.45rem 0; border-bottom:1px solid rgba(11,11,11,0.07); }}
.rw-rang:last-child {{ border-bottom:none; }}
.rw-titre {{ flex:0 0 15rem; font-weight:600; line-height:1.25; }}
.rw-ref {{ font-weight:400; font-size:0.78rem; color:#898781; }}
.rw-cases {{ display:flex; flex-wrap:wrap; gap:0.3rem; }}
.rw-case {{ display:inline-block; padding:0.18rem 0.5rem; border-radius:5px;
            font-size:0.8rem; font-weight:600; white-space:nowrap;
            cursor:help; }}
.rw-case sup {{ font-size:0.62rem; margin-left:0.15rem; opacity:0.85; }}
.rw-legende {{ margin-top:0.7rem; font-size:0.78rem; color:#52514e; }}
.rw-leg {{ margin-right:0.9rem; white-space:nowrap; }}
.rw-leg i {{ display:inline-block; width:0.72rem; height:0.72rem;
             border-radius:3px; margin-right:0.3rem;
             vertical-align:-0.05rem; }}
</style>
<div class="rw-carte">{"".join(cases_par_texte)}</div>
<div class="rw-legende">{legende}</div>
"""
