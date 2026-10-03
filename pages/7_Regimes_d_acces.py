"""
Régimes d'accès aux données — orientation de premier niveau pour les entreprises.

L'agent qui accompagne une entreprise n'a pas à formuler une requête
documentaire : il décrit une situation, l'outil la traduit en recherche, lit
les textes chargés et rapporte ce qu'ils disent, citation à l'appui.

Deux corrections tirées de la phase de test :

*Plus de filtre sur le type de document.* La page ne retenait que les documents
marqués « texte réglementaire ». Un texte mal classé au chargement — ce qui
arrive, la détection automatique se trompe — devenait invisible, et l'outil
répondait « les textes chargés ne tranchent pas » alors que le règlement était
dans la base. Le périmètre est désormais explicite et modifiable.

*Une restitution, pas un verdict.* La réponse montre d'où vient chaque élément,
quel texte a été interrogé, ce qui n'a pas été trouvé — et produit une fiche
Word que l'agent peut envoyer telle quelle.
"""

from __future__ import annotations

import time

import pandas as pd
import plotly.express as px
import streamlit as st

from core import store
from core.duree import CADENCE_EXTRAIT, avancement, duree_estimee
from core.fiabilite import reponse_sourcee as alertes_reponse
from core.qa import answer
from core.report import build_fiche_docx
from core.ui import comment_ca_marche, panneau_fiabilite


ACTEURS = ["Startup / PME", "ETI ou grande entreprise", "Fournisseur de service cloud",
           "Intermédiaire de données", "Organisme de recherche",
           "Organisme du secteur public"]
DONNEES = ["Données personnelles", "Données personnelles sensibles",
           "Données non personnelles", "Jeu mixte", "Données de produit connecté"]
SECTEURS = ["Santé", "Transports", "Énergie", "Finance", "Industrie",
            "Secteur public", "Autre"]

# Chaque cas d'usage porte trois choses : les termes de recherche, les textes
# où regarder en priorité, et les questions que l'agent doit se poser. La
# troisième est ce qui manquait le plus : l'outil renvoyait des articles sans
# dire quoi en faire.
CAS = {
    "Réutiliser des données détenues par le secteur public": {
        "termes": "conditions de réutilisation des données détenues par un "
                  "organisme du secteur public, redevances, droits de tiers, "
                  "licences, données protégées",
        "textes": ["Directive Open Data (UE) 2019/1024",
                   "Data Governance Act (UE) 2022/868, chapitre II"],
        "points": [
            "Les données relèvent-elles d'une catégorie protégée "
            "(secret d'affaires, données personnelles, propriété "
            "intellectuelle de tiers) ?",
            "L'organisme public peut-il exiger une redevance, et sur quelle "
            "base de calcul ?",
            "Une exclusivité a-t-elle été accordée à un tiers ?",
        ],
    },
    "Accéder aux données d'un produit connecté": {
        "termes": "accès de l'utilisateur aux données générées par un produit "
                  "connecté, partage avec un tiers, détenteur de données, "
                  "conception facilitant l'accès",
        "textes": ["Data Act (UE) 2023/2854, chapitres II et III"],
        "points": [
            "Qui est l'utilisateur, qui est le détenteur des données ?",
            "L'accès demandé porte-t-il sur des données brutes ou dérivées ?",
            "Le tiers destinataire est-il un fournisseur de service de "
            "traitement, ou une entreprise désignée comme contrôleur d'accès ?",
        ],
    },
    "Partager des données entre entreprises": {
        "termes": "mise à disposition des données entre entreprises, "
                  "compensation raisonnable, clauses contractuelles abusives, "
                  "conditions équitables non discriminatoires",
        "textes": ["Data Act (UE) 2023/2854, chapitre IV",
                   "Data Governance Act (UE) 2022/868, chapitre III"],
        "points": [
            "Le partage est-il volontaire ou imposé par un texte ?",
            "La compensation demandée est-elle encadrée ?",
            "Une clause imposée unilatéralement à une PME est-elle opposable ?",
        ],
    },
    "Transférer des données hors de l'Union": {
        "termes": "transfert international de données, accès gouvernemental "
                  "d'un pays tiers, garanties appropriées, décision "
                  "d'adéquation, données non personnelles",
        "textes": ["RGPD (UE) 2016/679, chapitre V",
                   "Data Governance Act (UE) 2022/868, article 31",
                   "Data Act (UE) 2023/2854, article 32"],
        "points": [
            "S'agit-il de données personnelles, non personnelles, ou d'un jeu "
            "mixte, le régime n'est pas le même ?",
            "Le pays de destination fait-il l'objet d'une décision "
            "d'adéquation ?",
            "Le fournisseur est-il exposé à une injonction d'un pays tiers ?",
        ],
    },
    "Entraîner un système d'intelligence artificielle": {
        "termes": "gouvernance des données d'entraînement, documentation "
                  "technique, jeux de données, qualité des données, système "
                  "d'IA à haut risque",
        "textes": ["Règlement IA (UE) 2024/1689, articles 10 et 11",
                   "RGPD (UE) 2016/679, articles 5, 6 et 9"],
        "points": [
            "Le système entre-t-il dans une catégorie à haut risque ?",
            "Quelle base légale pour les données personnelles d'entraînement ?",
            "Les obligations de documentation des jeux de données sont-elles "
            "tenues ?",
        ],
    },
    "Changer de fournisseur de service cloud": {
        "termes": "changement de fournisseur de service de traitement de "
                  "données, portabilité, frais de transfert, délai de préavis, "
                  "équivalence fonctionnelle",
        "textes": ["Data Act (UE) 2023/2854, chapitre VI"],
        "points": [
            "Le contrat prévoit-il le délai de préavis et la période de "
            "transition prévus par le texte ?",
            "Quels frais le fournisseur peut-il encore facturer, et jusqu'à "
            "quand ?",
            "L'équivalence fonctionnelle est-elle due pour ce type de service ?",
        ],
    },
}

TEXTES_ATTENDUS = [
    "RGPD, règlement (UE) 2016/679",
    "Data Governance Act, règlement (UE) 2022/868",
    "Data Act, règlement (UE) 2023/2854",
    "Directive Open Data, directive (UE) 2019/1024",
    "Règlement IA, règlement (UE) 2024/1689",
]

st.title("Quelles règles s'appliquent à cette situation ?")
st.caption(
    "Décrivez la situation d'une entreprise ; l'outil rapporte ce que les "
    "textes que VOUS avez chargés en disent, citation à l'appui, et produit "
    "une fiche d'orientation Word."
)

comment_ca_marche("regimes")

docs = store.list_documents()
if docs.empty:
    st.warning(
        "Aucun document au corpus. Chargez les textes de référence depuis la "
        "**Bibliothèque**, l'outil ne répond qu'à partir des textes chargés."
    )
    with st.expander("Textes généralement utiles à cette page"):
        for t in TEXTES_ATTENDUS:
            st.markdown(f"- {t}")
    st.stop()

# Le type de document sert de proposition, plus de filtre : un texte mal classé
# au chargement reste sélectionnable.
kinds = docs.get("kind", pd.Series(dtype=str))
suggeres = list(docs[kinds == "legal_text"]["id"])
defaut = suggeres or list(docs["id"])
noms = dict(zip(docs["id"], docs["name"]))

with st.expander(
        f"Textes interrogés · {len(defaut)} sur {len(docs)} document(s) au corpus",
        expanded=not suggeres):
    if not suggeres:
        st.caption(
            "Aucun document n'est marqué « texte réglementaire ». La détection "
            "automatique se trompe souvent sur les textes consolidés ; tous les "
            "documents sont donc proposés. Vous pouvez corriger le type d'un "
            "document depuis la Bibliothèque."
        )
    perimetre = st.multiselect(
        "Documents à interroger", options=list(docs["id"]), default=defaut,
        format_func=lambda i: noms.get(i, i))
    st.caption(
        "Restreindre le périmètre accélère la recherche et évite qu'un "
        "document de négociation vienne se mêler aux textes en vigueur."
    )

if not perimetre:
    st.warning("Sélectionnez au moins un document à interroger.")
    st.stop()

left, right = st.columns([1, 2], gap="large")

with left:
    st.subheader("Situation")
    acteur = st.selectbox("Acteur", ["— non précisé —"] + ACTEURS)
    donnees = st.selectbox("Typologie de données", ["— non précisé —"] + DONNEES)
    secteur = st.selectbox("Secteur", ["— non précisé —"] + SECTEURS)
    cas = st.selectbox("Cas d'usage", ["— non précisé —"] + list(CAS))
    hors_ue = st.checkbox("Un transfert hors UE/EEE est en jeu")

    st.divider()
    precision = st.text_area(
        "Question précise", height=110,
        placeholder="Cet acteur peut-il transférer ses données de maintenance "
                    "industrielle hors de l'Union européenne ?")
    profondeur = st.number_input(
        "Passages à examiner", min_value=5, max_value=500, value=20, step=5,
        help="Sans plafond bas : sur une question large, montez à 100 ou 200. "
             "Chaque passage coûte environ trois secondes.")
    st.caption(duree_estimee(int(profondeur), CADENCE_EXTRAIT,
                             f"{int(profondeur)} passage(s) au maximum"))
    go = st.button("Chercher dans les textes", type="primary", width="stretch")

    st.caption(
        "L'outil ne donne pas d'avis : il rapporte ce que les textes chargés "
        "disent, en citant les passages. Toute affirmation dont la citation "
        "n'est pas retrouvée dans le texte source est retirée avant affichage."
    )

with right:
    if cas != "— non précisé —":
        fiche = CAS[cas]
        with st.container(border=True):
            st.markdown(f"**{cas}**")
            st.caption(
                "Repères de méthode, liste fixe, écrite d'avance pour ce cas "
                "d'usage. **Ce n'est pas un résultat de recherche** : l'outil "
                "n'interroge que les documents cochés au-dessus, et un texte "
                "cité ici mais absent du corpus ne sera pas lu.")
            noms_charges = " ".join(str(n).lower() for n in docs["name"])
            for t in fiche["textes"]:
                # Un repère utile dit aussi si le texte est disponible : sinon
                # l'agent croit que l'outil l'a consulté.
                cle = t.split("(")[0].strip().lower()[:14]
                present = cle and cle in noms_charges
                marque = "✓ au corpus" if present else "absent du corpus"
                st.markdown(f"- {t} · *{marque}*")
            st.caption("Questions à trancher avant de conclure")
            for q in fiche["points"]:
                st.markdown(f"- {q}")

    if not go:
        st.info("Décrivez la situation à gauche, puis lancez la recherche.")
        st.stop()

    bits = []
    if cas != "— non précisé —":
        bits.append(CAS[cas]["termes"])
    if donnees != "— non précisé —":
        bits.append(donnees.lower())
    if secteur != "— non précisé —":
        bits.append(secteur.lower())
    if acteur != "— non précisé —":
        bits.append(acteur.lower())
    if hors_ue:
        bits.append("transfert pays tiers hors Union européenne")
    if precision.strip():
        bits.append(precision.strip())

    query = " ".join(bits).strip()
    if not query:
        st.warning("Précisez au moins un élément de la situation.")
        st.stop()

    bar = st.progress(0.0)
    etat = st.empty()
    depart = time.time()

    def progression(i: int, n: int, libelle: str) -> None:
        bar.progress(i / n, text=avancement(i, n, depart))
        etat.caption(libelle)

    res = answer(query, limit=int(profondeur), document_ids=list(perimetre),
                 on_progress=progression)
    bar.empty()
    etat.empty()

    if res.error:
        st.error(res.error)

    tous = res.tous_elements
    m1, m2, m3 = st.columns(3)
    m1.metric("Passages examinés", res.examines or len(res.hits),
              help="Seuls les documents cochés dans « Textes interrogés » ont "
                   "été lus. La situation décrite est traduite en termes de "
                   "recherche, en français et en anglais ; chaque passage "
                   "remonté est ensuite examiné séparément.")
    m2.metric("Dispositions retenues", len(res.claims))
    m3.metric("Éléments de contexte", len(res.indirect))

    if res.answer_fr:
        st.markdown("### Ce que disent les textes chargés")
        st.markdown(res.answer_fr)

    if res.claims:
        st.markdown("### Dispositions applicables")
        for i, c in enumerate(res.claims, start=1):
            with st.expander(f"{i}. {c.statement}", expanded=i <= 3):
                st.markdown(f"> {c.quote}")
                st.caption(c.hit.citation)
                with st.popover("Passage complet"):
                    st.write(c.hit.text)

    if res.indirect:
        st.markdown("### Éléments de contexte")
        st.caption(
            "Aucun passage ne répond directement à la situation décrite. Ces "
            "extraits l'éclairent, définitions, conditions voisines, "
            "exceptions, et restent adossés à une citation vérifiée."
        )
        for i, c in enumerate(res.indirect, start=1):
            with st.expander(f"{i}. {c.statement}"):
                st.markdown(f"> {c.quote}")
                st.caption(c.hit.citation)
                with st.popover("Passage complet"):
                    st.write(c.hit.text)

    # --- d'où vient la réponse --------------------------------------------
    if tous:
        st.markdown("### D'où vient la réponse")
        origine = pd.DataFrame({
            "Texte": [c.hit.document_name[:44] for c in tous],
            "Disposition": [c.hit.section_label for c in tous],
            "Nature": (["Réponse directe"] * len(res.claims)
                       + ["Contexte"] * len(res.indirect)),
        })
        compte = (origine.groupby(["Texte", "Nature"]).size()
                  .reset_index(name="Passages"))
        fig = px.bar(compte, x="Passages", y="Texte", color="Nature",
                     orientation="h",
                     color_discrete_map={"Réponse directe": "#1c5cab",
                                         "Contexte": "#9db8dc"})
        fig.update_layout(height=90 + 34 * compte["Texte"].nunique(),
                          margin=dict(l=10, r=10, t=30, b=10),
                          plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                          legend=dict(orientation="h", y=1.15, x=0))
        st.plotly_chart(fig, width="stretch")

        st.dataframe(
            origine.assign(Extrait=[c.quote[:160] + "…" for c in tous]),
            width="stretch", hide_index=True)

    panneau_fiabilite(alertes_reponse(res, int(profondeur)))

    if res.dropped:
        st.warning(
            f"{res.dropped} affirmation(s) retirée(s) faute de citation "
            "vérifiable, y compris après une seconde demande de recopie. "
            "Elles ne vous sont pas montrées."
        )

    if res.unanswered:
        st.markdown("### Points que les textes chargés ne tranchent pas")
        for u in res.unanswered:
            st.markdown(f"- {u}")
        st.caption(
            "Ces points appellent une analyse humaine, ou le chargement du "
            "texte manquant."
        )

    # --- livrable ----------------------------------------------------------
    if tous:
        st.divider()
        situation = [(k, v) for k, v in [
            ("Acteur", acteur), ("Typologie de données", donnees),
            ("Secteur", secteur), ("Cas d'usage", cas),
            ("Transfert hors UE/EEE", "oui" if hors_ue else "non"),
            ("Question posée", precision.strip() or "—"),
        ] if v and v != "— non précisé —"]

        def _liste(claims):
            return [{"statement": c.statement, "quote": c.quote,
                     "citation": c.hit.citation} for c in claims]

        fiche_bytes = build_fiche_docx(
            titre="Régimes d'accès aux données, fiche d'orientation",
            situation=situation, synthese=res.answer_fr,
            elements=_liste(res.claims), contexte=_liste(res.indirect),
            manques=res.unanswered,
            corpus=[noms.get(i, i) for i in perimetre],
        )
        st.download_button(
            "Fiche d'orientation Word (.docx)", data=fiche_bytes,
            file_name="fiche_regimes_acces.docx",
            mime="application/vnd.openxmlformats-officedocument."
                 "wordprocessingml.document",
            type="primary")
        st.caption(
            "La fiche reprend la situation, les dispositions citées et leurs "
            "références. Elle est modifiable : complétez-la avant de "
            "l'envoyer à l'entreprise."
        )

    st.divider()
    st.caption(
        "Orientation documentaire de premier niveau. Ce n'est pas un conseil "
        "juridique et cela ne dispense pas d'une analyse au cas d'espèce."
    )
