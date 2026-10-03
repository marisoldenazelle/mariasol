"""
MARI(a)SOL — outil interne de négociation européenne et de régimes d'accès
aux données.

Lancement :  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.config import APP_SOUS_TITRE
from core.ui import nom_marque


entete, titre = st.columns([1, 9], vertical_alignment="center")
marque = Path(__file__).parent / "assets" / "mariasol_marque_256.png"
if marque.exists():
    entete.image(str(marque), width=76)
titre.markdown(f"# {nom_marque()}", unsafe_allow_html=True)
titre.caption(APP_SOUS_TITRE)
st.markdown(
    "**Outil de négociation européenne et de cartographie des régimes d'accès "
    "aux données.** Tous les outils travaillent sur les documents que vous "
    "chargez, l'application ne connaît rien d'autre que votre corpus."
)

st.divider()

CARDS = [
    ("Bibliothèque", "Charger et gérer",
     "Commentaires consolidés du Conseil, textes de compromis, non-papers, "
     "comptes rendus. Découpage déterministe, indexation immédiate."),
    ("Recherche", "Interroger le corpus",
     "« Qui a dit quoi sur tel sujet ? » Réponse rédigée dont chaque "
     "affirmation cite un passage vérifié dans le texte source."),
    ("Positions des États membres", "Cartographier",
     "Matrice d'alignement article par article avec la position française, "
     "classement des alliés, articles clivants."),
    ("Coalitions", "Compter les voix",
     "Blocs d'États membres indépendamment de la France, majorité qualifiée "
     "et minorités de blocage, États pivots."),
    ("Comparaison de versions", "Suivre les textes",
     "Le fil complet d'un texte, l'évolution d'un article à travers toutes "
     "ses versions, et ce qui a changé mot à mot."),
    ("Suivi des amendements", "Vérifier ce qu'on a obtenu",
     "Chaque demande écrite confrontée au texte finalement publié : reprise, "
     "reprise à moitié, écartée, et qui a obtenu quoi."),
    ("Régimes d'accès", "Orienter une entreprise",
     "Une situation d'entreprise, et ce que disent les textes chargés, "
     "disposition par disposition."),
    ("Mode d'emploi", "Comprendre l'outil",
     "Un assistant qui répond sur le fonctionnement de l'application, et le "
     "guide complet de tous les modules."),
]

for row in range(0, len(CARDS), 3):
    cols = st.columns(3, gap="large")
    for col, (title, kicker, body) in zip(cols, CARDS[row:row + 3]):
        col.markdown(
            f'<div class="rw-card"><div class="rw-kicker">{kicker}</div>'
            f'<div class="rw-title">{title}</div>'
            f'<div class="rw-sub">{body}</div></div>',
            unsafe_allow_html=True,
        )

st.divider()

st.subheader("Ce qui est déterministe, ce qui ne l'est pas")
st.markdown(
    """
| Étape | Nature | Composant |
|---|---|---|
| Découpage des documents | déterministe | `pdfplumber`, `python-docx`, expressions régulières |
| Index et recherche | déterministe | SQLite FTS5, local, aucun texte transmis pour vectorisation |
| Comparaison de versions | déterministe | `difflib`, mot à mot |
| Scores, matrices, coalitions, majorité qualifiée | déterministe | `pandas`, `networkx` |
| Synthèse d'une réponse | modèle contraint | sortie validée, **chaque affirmation citée et vérifiée** |
| Qualification d'une position ou d'un changement | modèle contraint | schéma Pydantic, citation vérifiée dans la source |

Le garde-fou principal n'est pas une consigne donnée au modèle, c'est un
contrôle exécuté par le programme : une affirmation dont la citation ne se
retrouve pas dans le texte source **n'est pas affichée**.
"""
)

st.info(
    "L'outil ne connaît que les documents chargés. Il ne complète jamais avec "
    "des connaissances extérieures : si le corpus ne permet pas de répondre, "
    "il le dit plutôt que de deviner.",
    icon="📚",
)
