"""
MARI(a)SOL — point d'entrée de l'application Streamlit.

Lancement :  streamlit run app.py
             (ou double-clic sur demarrer.bat / ./demarrer.sh)

Ce fichier ne fait que déclarer la navigation. Chaque outil vit dans son
propre fichier sous `pages/` et reste lisible isolément.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import palette
from core.config import APP_NOM, VERSION_DATE, __version__, settings
from core.ui import nom_marque
from core.llm import get_client
from core.store import list_documents

# La marque est un fichier du dépôt : Streamlit accepte un chemin d'image
# comme icône d'onglet, ce qui vaut mieux qu'un émoji pour une application
# d'administration.
# PNG et non SVG : selon la version de Streamlit installée sur le poste,
# `st.logo` refuse un chemin de fichier SVG et lève une exception qui arrête
# l'application entière avant même l'affichage de la navigation. Le PNG est
# accepté par toutes les versions ; les SVG restent dans `assets/` pour les
# usages hors application (note, présentation, impression).
MARQUE = Path(__file__).parent / "assets" / "mariasol_marque_256.png"
LOGO = Path(__file__).parent / "assets" / "mariasol_logo.png"

st.set_page_config(
    page_title=f"{APP_NOM} · DGE",
    page_icon=str(MARQUE) if MARQUE.exists() else "⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Les libellés du menu sont définis ici, et non déduits des noms de fichiers :
# les accents et la ponctuation restent corrects sans dépendre du système de
# fichiers du poste.
PAGES = [
    st.Page("accueil.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("pages/0_Mode_d_emploi.py", title="Mode d'emploi",
            icon=":material/help:"),
    st.Page("pages/1_Bibliotheque.py", title="Bibliothèque",
            icon=":material/library_books:"),
    st.Page("pages/2_Recherche.py", title="Recherche",
            icon=":material/search:"),
    st.Page("pages/3_Positions_Etats_membres.py", title="Positions des États membres",
            icon=":material/flag:"),
    st.Page("pages/4_Coalitions.py", title="Coalitions",
            icon=":material/groups:"),
    st.Page("pages/5_Comparaison_de_versions.py", title="Comparaison de versions",
            icon=":material/compare_arrows:"),
    st.Page("pages/6_Suivi_des_amendements.py",
            title="Suivi des amendements", icon=":material/fact_check:"),
    st.Page("pages/7_Regimes_d_acces.py", title="Régimes d'accès aux données",
            icon=":material/gavel:"),
    st.Page("pages/8_Administration.py", title="Administration",
            icon=":material/settings:"),
]

st.markdown(
    """
<style>
  .block-container { padding-top: 2.2rem; max-width: 1500px; }
  h1, h2, h3 { letter-spacing: -0.01em; }
  /* Charte : le titre de page et les chiffres clés portent le bleu France,
     les traits de séparation le reprennent en très clair. Le corps de texte
     reste noir, un écran de travail entièrement bleu se lit moins bien. */
  h1 { color: #000091; }
  h2 { color: #1b1b35; }
  hr { border-color: rgba(0,0,145,0.16) !important; }
  [data-testid="stMetricValue"] { color: #000091; }
  [data-testid="stMetricLabel"] { color: #52514e; }
  /* L'onglet actif est souligné en bleu France, comme la marque. */
  [data-baseweb="tab-highlight"] { background-color: #000091 !important; }
  .rw-card { border: 1px solid rgba(0,0,145,0.14); border-radius: 10px;
             padding: 1rem 1.2rem; background: #fbfbfe; height: 100%;
             border-top: 3px solid #000091; }
  .rw-kicker { font-size: 0.74rem; text-transform: uppercase;
               letter-spacing: 0.06em; color: #898781; margin-bottom: 0.3rem; }
  .rw-title { font-size: 1.15rem; font-weight: 650; color: #000091;
              line-height: 1.2; }
  .rw-sub { color: #52514e; font-size: 0.88rem; margin-top: 0.4rem; }
</style>
""",
    unsafe_allow_html=True,
)

if settings.demo_mode:
    st.warning(
        "**Instance de démonstration, publique et partagée.** Les documents "
        "que vous chargez sont visibles par les autres utilisateurs et "
        "effacés à chaque redémarrage. **Ne chargez que des documents "
        "publics** : aucun document marqué LIMITE, aucun document de travail. "
        "Les synthèses rédigées sont désactivées ; l'import, la recherche et "
        "la comparaison de versions fonctionnent normalement.",
        icon="⚠️")

if LOGO.exists():
    # `st.logo` place la marque en haut du bandeau de navigation, à sa place.
    # Enveloppé : une marque que Streamlit refuse est un défaut d'habillage,
    # jamais une raison d'empêcher l'application de démarrer sur un poste.
    try:
        st.logo(str(LOGO), icon_image=str(MARQUE) if MARQUE.exists() else None,
                size="large")
    except Exception:
        pass

with st.sidebar:
    st.markdown("### État du système")
    client = get_client()
    if settings.demo_mode:
        st.info("Démonstration, modèle désactivé.")
    elif settings.llm_provider == "offline":
        st.info("Mode hors ligne, aucun appel réseau.")
    elif client.available:
        st.success(f"LLM : {settings.llm_provider}")
        st.caption(f"Modèle : `{settings.llm_model}`")
    else:
        st.warning("Clé API absente.")
        st.caption("Recherche plein texte, import et comparaison de versions "
                   "restent disponibles.")

    docs = list_documents()
    st.metric("Documents au corpus", len(docs))
    if not docs.empty and "kind" in docs:
        counts = docs["kind"].fillna("—").value_counts()
        for k, v in counts.items():
            st.caption(f"{k} : {v}")

    st.divider()
    # Le choix de palette vaut pour toute l'application — écrans, PNG, note
    # Word et classeur Excel — parce qu'une même matrice ne doit pas changer
    # de code couleur selon le support.
    choix_palette = st.selectbox(
        "Couleurs", list(palette.PALETTES),
        index=list(palette.PALETTES).index(
            st.session_state.get("palette", "accessible")),
        format_func=lambda p: palette.PALETTES[p]["nom"],
        help="« Accessible » sépare l'aligné du divergent par le bleu et le "
             "rouge : lisible en vision daltonienne, ce que le vert / rouge "
             "n'est pas. Les symboles + ~ − doublent la couleur dans les deux "
             "cas, de sorte qu'une impression en noir et blanc garde son sens.")
    st.session_state["palette"] = choix_palette
    palette.utiliser(choix_palette)

    st.divider()
    st.markdown(
        f'<div style="color:#898781;font-size:0.8rem;line-height:1.6">'
        f'{nom_marque("0.95rem")}&nbsp;&nbsp;{__version__} · {VERSION_DATE}'
        f'</div>', unsafe_allow_html=True)

st.navigation(PAGES).run()

