"""
« Nos amendements ont-ils été retenus ? »

La question qui suit toute publication d'un nouveau compromis. L'outil
confronte les demandes écrites — les vôtres, ou celles de toutes les
délégations — au texte finalement retenu, article par article, et dit ce
qu'elles sont devenues.

Deux lectures :

- **la vôtre** : ce que la France a obtenu, demande par demande ;
- **la lecture politique** : quelles délégations ont obtenu quelque chose
  dans ce texte, et lesquelles en sortent les mains vides.
"""

from __future__ import annotations

import io
import time

import pandas as pd
import streamlit as st

from core import store
from core.amendements import VERDICT_COULEUR, VERDICTS, suivre
from core.duree import avancement, duree_estimee
from core.palette import PALETTES, actif
from core.ui import comment_ca_marche, entete_module, pour_aller_plus_loin


entete_module(
    "Nos amendements ont-ils été retenus ?",
    "Chaque demande écrite est confrontée au texte finalement publié. Le "
    "verdict est adossé à un passage du nouveau texte, vérifié par le "
    "programme, sans quoi il est déclaré indéterminé plutôt qu'affiché comme "
    "acquis.")

comment_ca_marche("amendements")

docs = store.list_documents()
if docs.empty:
    st.info("Corpus vide. Chargez vos documents depuis la **Bibliothèque**.")
    st.stop()

kinds = docs.get("kind", pd.Series(dtype=str))
tableaux = docs[kinds == "wk_table"]
textes = docs[kinds != "wk_table"]

if tableaux.empty:
    st.warning(
        "Aucun tableau de commentaires au corpus : c'est lui qui porte les "
        "demandes à suivre. Chargez-le depuis la **Bibliothèque**.")
    st.stop()
if textes.empty:
    st.warning(
        "Aucun texte d'arrivée au corpus. Chargez le compromis publié, "
        "depuis EUR-Lex s'il est publié, ou en important le PDF s'il ne "
        "l'est pas, puis revenez ici.")
    st.stop()

index_tab, index_txt = tableaux.set_index("id"), textes.set_index("id")

c1, c2 = st.columns(2)
source_id = c1.selectbox(
    "Demandes à suivre (tableau de commentaires)", options=list(tableaux["id"]),
    format_func=lambda i: index_tab.loc[i, "name"],
    help="Le tableau à trois colonnes qui rassemble les amendements, ou "
         "celui que vous avez déjà analysé dans « Positions des États "
         "membres ».")
cible_id = c2.selectbox(
    "Texte d'arrivée (le compromis publié)", options=list(textes["id"]),
    format_func=lambda i: index_txt.loc[i, "name"],
    help="La version qui intègre, ou non, les amendements : compromis de "
         "présidence, texte de la Commission après arbitrage, texte publié "
         "au Journal officiel.")

demandes = store.load_contributions(source_id)
if demandes.empty:
    st.warning("Ce tableau ne contient aucune contribution exploitable.")
    st.stop()

segments_cible = store.load_segments(cible_id)

# Le même piège que dans la comparaison de versions : le suivi apparie les
# demandes au texte d'arrivée **par numéro d'article**. Si le texte d'arrivée
# est un acte modificatif — un omnibus —, ses articles ne sont pas ceux du
# règlement commenté, et tous les verdicts seraient faux sans que rien ne le
# signale.
if segments_cible is not None and not segments_cible.empty:
    from core.modificatif import est_acte_modificatif

    if est_acte_modificatif("\n".join(str(x) for x in segments_cible["text"])):
        st.warning(
            "**Le texte d'arrivée choisi est un acte modificatif** (un "
            "omnibus, ou un règlement « portant modification de… »). Ses "
            "articles ne sont pas ceux du règlement commenté : son article "
            "premier énumère des modifications, il ne remplace pas l'article "
            "premier du texte d'origine. Le suivi apparie les demandes par "
            "numéro d'article, les verdicts seraient donc faux.\n\n"
            "Choisissez comme texte d'arrivée **une version du même texte** "
            "que celui sur lequel portent les demandes. Pour savoir ce qu'un "
            "omnibus change dans un règlement, allez à **Comparaison de "
            "versions → Omnibus et actes modificatifs**.",
            icon=":material/rule_settings:")
        st.stop()

# ------------------------------------------------------------------ périmètre
etats = sorted({str(m) for m in demandes["ms_code"] if str(m).strip()})
f1, f2 = st.columns([2, 1])
qui = f1.multiselect(
    "États membres suivis", etats,
    default=["FR"] if "FR" in etats else etats[:1],
    help="La France seule pour savoir ce que nous avons obtenu ; tous les "
         "États pour la lecture politique du texte.")
articles = f2.multiselect(
    "Articles", list(dict.fromkeys(demandes["section_label"])),
    help="Laisser vide pour tous les articles.")

travail = demandes[demandes["ms_code"].isin(qui)] if qui else demandes
if articles:
    travail = travail[travail["section_label"].isin(articles)]

st.caption(duree_estimee(len(travail), 4.0,
                         f"{len(travail)} demande(s) à suivre"))

cle = f"amendements::{source_id}::{cible_id}::{','.join(sorted(qui))}"

if st.button("Confronter au texte d'arrivée", type="primary",
             width="stretch", disabled=travail.empty):
    bar = st.progress(0.0)
    etat = st.empty()
    depart = time.time()

    def suivi(i, n, libelle):
        bar.progress(i / n, text=avancement(i, n, depart))
        etat.caption(libelle)

    st.session_state[cle] = suivre(
        travail, segments_cible,
        nom_cible=str(index_txt.loc[cible_id, "name"]), on_progress=suivi)
    bar.empty()
    etat.empty()

resultat = st.session_state.get(cle)
if resultat is None:
    st.info("Choisissez les deux documents, puis lancez la confrontation.")
    st.stop()

for e in resultat.erreurs[:3]:
    st.warning(e)

table = resultat.table()
if table.empty:
    st.warning("Aucune demande n'a pu être confrontée.")
    st.stop()

# ------------------------------------------------------------------ résultats
compte = table["Sort de la demande"].value_counts()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Reprises", int(compte.get("Reprise", 0)))
m2.metric("Reprises partiellement", int(compte.get("Reprise partiellement", 0)))
m3.metric("Écartées", int(compte.get("Écartée", 0)))
m4.metric("Indéterminées", int(compte.get("Indéterminé", 0)),
          help="Verdict impossible : article renuméroté, ou justification non "
               "retrouvée dans le texte d'arrivée. À vérifier à la main.")

if resultat.sans_citation:
    st.warning(
        f"{resultat.sans_citation} verdict(s) écarté(s) : le modèle a rendu "
        "un avis dont la justification n'était pas retrouvable dans le texte "
        "d'arrivée. Ils sont comptés comme indéterminés, jamais comme "
        "acquis.")

t1, t2, t3 = st.tabs(["Demande par demande", "Qui a obtenu quoi", "Export"])

with t1:
    filtre = st.multiselect(
        "N'afficher que", list(VERDICTS.values()),
        default=[VERDICTS["retenue"], VERDICTS["partielle"], VERDICTS["ecartee"]])
    vues = [s for s in resultat.suivis
            if not filtre or s.verdict_fr in filtre]
    st.caption(f"{len(vues)} demande(s)")

    pal = PALETTES[st.session_state.get("palette", actif())]
    for s in vues[:200]:
        couleur = pal[VERDICT_COULEUR.get(s.verdict, "absent")]
        with st.expander(f"{s.ms_code} · {s.section_label} · {s.verdict_fr}"):
            st.markdown(
                f"<div style='border-left:5px solid {couleur};"
                f"padding:0.35rem 0 0.35rem 0.9rem;margin-bottom:0.6rem;'>"
                f"<b>Ce qui était demandé</b><br>{s.demande}</div>",
                unsafe_allow_html=True)
            if s.explication:
                st.markdown(f"**Ce qu'en a fait le texte d'arrivée**, "
                            f"{s.explication}")
            if s.citation:
                st.markdown("**Passage du texte d'arrivée**")
                st.markdown(f"> {s.citation}")
            st.caption(
                f"Méthode : {s.methode}"
                + ("  ·  demande de suppression" if s.demandait_suppression else "")
                + ("" if s.article_present
                   else "  ·  article absent du texte d'arrivée"))

with t2:
    taux = resultat.taux()
    st.caption(
        "Le taux de reprise se calcule sur les seules demandes tranchées : "
        "une reprise partielle compte pour une demi-reprise, les "
        "indéterminées sont exclues du dénominateur. Un taux calculé sur deux "
        "demandes ne veut rien dire, regardez d'abord la colonne « Demandes "
        "suivies ».")
    st.dataframe(taux, width="stretch", hide_index=True,
                 column_config={
                     "Taux de reprise": st.column_config.ProgressColumn(
                         "Taux de reprise", min_value=0.0, max_value=1.0,
                         format="%.2f")})

    if len(taux) > 1:
        import plotly.express as px

        fig = px.bar(taux.dropna(subset=["Taux de reprise"]),
                     x="Taux de reprise", y="EM", orientation="h",
                     title="Ce que chaque délégation a obtenu")
        fig.update_layout(height=max(280, 26 * len(taux) + 120),
                          margin=dict(l=8, r=8, t=48, b=8),
                          plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
        fig.update_traces(marker_color="#1c5cab")
        st.plotly_chart(fig, width="stretch")

with t3:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Demande par demande", index=False)
        resultat.taux().to_excel(writer, sheet_name="Taux de reprise",
                                 index=False)
    st.download_button(
        "Télécharger le suivi (.xlsx)", data=buf.getvalue(),
        file_name="suivi_amendements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch", type="primary")
    st.caption(
        "Deux feuilles : chaque demande avec son sort et le passage du texte "
        "d'arrivée qui le justifie, puis le taux de reprise par délégation.")

pour_aller_plus_loin(
    "Ce que ce calcul ne dit pas",
    """
**Il ne dit pas pourquoi.** Une demande écartée peut l'avoir été pour des
raisons juridiques, politiques, ou parce qu'une autre délégation a obtenu
l'inverse. L'outil constate, il n'explique pas.

**Il ne dit pas si la rédaction retenue vous satisfait.** Une demande classée
« reprise » peut l'être dans des termes qui en changent la portée. Le passage
du texte d'arrivée est affiché précisément pour que vous en jugiez.

**Les indéterminés ne sont pas des échecs.** Ils signalent soit une
renumérotation, l'article n'existe plus sous ce numéro, soit un verdict que
le programme a refusé faute de justification retrouvable. Dans les deux cas,
c'est une invitation à regarder, pas un résultat.

**Un taux de reprise n'est pas un score de puissance.** Une délégation qui
dépose peu de demandes, mais des demandes consensuelles, affichera un taux
élevé. Le nombre de demandes suivies se lit à côté du taux, jamais après.
""")
