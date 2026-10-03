"""
Recherche et questions — réponse sourcée sur le corpus.

Pourquoi cet outil plutôt qu'un assistant conversationnel généraliste ? Trois
différences, qui sont aussi ce que la page doit montrer à l'écran :

1. **Il ne connaît que vos documents.** Aucune réponse ne vient d'une
   connaissance générale du droit européen : tout sort des fichiers chargés,
   y compris ceux qui ne sont pas publics.
2. **Chaque affirmation est vérifiée par le programme**, pas par le modèle :
   la citation est recherchée littéralement dans le segment source, et
   l'affirmation est retirée si elle ne s'y trouve pas.
3. **Il est exhaustif par construction.** Chaque extrait est examiné
   séparément — un modèle à qui l'on donne quinze extraits d'un coup répond
   sur le premier et oublie les autres, ce qui est précisément le défaut
   observé sur « qui a posé une réserve d'examen ? ».

La page affiche donc systématiquement combien de passages ont été examinés,
d'où vient chaque élément, et ce qui a été écarté.
"""

from __future__ import annotations

import time

import pandas as pd
import plotly.express as px
import streamlit as st

from core import store
from core.duree import CADENCE_EXTRAIT, avancement, duree_estimee
from core.fiabilite import reponse_sourcee as alertes_reponse
from core.ingest import DOC_KINDS
from core.qa import answer
from core.retrieval import search
from core.ui import comment_ca_marche, panneau_fiabilite
from core.wk_parser import MS_CODES


AIDE_SELECTION = (
    "Comment les passages sont choisis : votre question est d'abord traduite "
    "en termes de recherche, en français ET en anglais, les documents de "
    "négociation sont rédigés en anglais. L'index plein texte remonte les "
    "passages les mieux classés (BM25), en faisant passer devant ceux de "
    "l'article que vous nommez. Chaque passage remonté est ensuite examiné "
    "SÉPARÉMENT par le modèle : c'est plus lent, mais un passage pertinent ne "
    "peut pas être oublié au profit du premier trouvé."
)

st.title("Que disent les documents chargés ?")
st.caption(
    "Une question en français, une réponse dont chaque affirmation cite un "
    "passage vérifié dans vos documents, et rien d'autre. L'outil ne sait "
    "rien du droit européen : il ne sait que ce que vous avez chargé."
)

comment_ca_marche("recherche")

docs = store.list_documents()
if docs.empty:
    st.info("Corpus vide. Chargez des documents depuis la **Bibliothèque**.")
    st.stop()

question = st.text_input(
    "Question ou termes recherchés",
    placeholder="Qui a posé une réserve d'examen sur la certification de posture ?",
    help="Les groupes entre guillemets sont cherchés comme expressions exactes. "
         "Un numéro d'article cité dans la question fait remonter d'abord les "
         "passages de cet article.",
)

with st.expander("Restreindre la recherche"):
    c1, c2, c3 = st.columns(3)
    dossiers = sorted({d for d in docs["dossier"].fillna("") if d})
    sel_dossier = c1.multiselect("Dossiers", dossiers)
    sel_kinds = c2.multiselect("Types de document", list(DOC_KINDS),
                               format_func=lambda k: DOC_KINDS[k])
    sel_ms = c3.multiselect("États membres", MS_CODES)

    pool = docs
    if sel_dossier:
        pool = pool[pool["dossier"].isin(sel_dossier)]
    sel_docs = st.multiselect(
        "Documents", options=list(pool["id"]),
        format_func=lambda i: docs.set_index("id").loc[i, "name"])

doc_ids = sel_docs or (list(pool["id"]) if sel_dossier else None)

c1, c2 = st.columns([2, 1])
mode = c1.radio(
    "Mode", ["Réponse sourcée", "Extraits bruts"], horizontal=True,
    help="La réponse sourcée examine chaque passage séparément et vérifie "
         "chaque citation contre le texte source. Les extraits bruts "
         "n'appellent aucun modèle : c'est la recherche plein texte seule.",
)
profondeur = c2.number_input(
    "Passages à examiner", min_value=5, max_value=500, value=20, step=5,
    help="Il n'y a plus de plafond bas : montez à 100 ou 200 sur une question "
         "large · « qui a posé une réserve d'examen ? », pour être exhaustif. "
         "Chaque passage examiné coûte environ trois secondes en mode réponse "
         "sourcée ; la durée estimée est affichée avant le lancement.")

st.caption(duree_estimee(int(profondeur), CADENCE_EXTRAIT,
                         f"{int(profondeur)} passage(s) au maximum"))

go = st.button("Rechercher", type="primary", disabled=not question.strip())

if go and question.strip():
    if mode == "Extraits bruts":
        hits = search(question, limit=max(25, int(profondeur)),
                      document_ids=doc_ids, doc_kinds=sel_kinds or None,
                      ms_codes=sel_ms or None)
        if not hits:
            st.warning(
                "Aucun passage trouvé. Essayez les termes anglais, les textes "
                "de négociation sont rédigés en anglais, ou vérifiez que le "
                "document est bien chargé et son index reconstruit "
                "(page **Administration**)."
            )
            st.stop()

        st.caption(f"{len(hits)} extraits")

        # Où sont les occurrences ? Sur un corpus de plusieurs milliers de
        # segments, cette répartition vaut souvent la réponse elle-même :
        # elle montre quels États se sont exprimés sur le sujet cherché.
        repartition = pd.DataFrame({
            "Document": [h.document_name[:40] for h in hits],
            "EM": [h.ms_code or "—" for h in hits],
            "Article": [h.section_label for h in hits],
        })
        v1, v2 = st.columns(2)
        par_em = repartition.groupby("EM").size().reset_index(name="Extraits")
        v1.plotly_chart(
            px.bar(par_em.sort_values("Extraits"), x="Extraits", y="EM",
                   orientation="h", title="Par État membre")
            .update_layout(height=max(260, 24 * len(par_em) + 90),
                           margin=dict(l=8, r=8, t=48, b=8),
                           plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                           showlegend=False)
            .update_traces(marker_color="#1c5cab"),
            width="stretch")
        par_art = repartition.groupby("Article").size().reset_index(name="Extraits")
        v2.plotly_chart(
            px.bar(par_art.sort_values("Extraits").tail(15), x="Extraits",
                   y="Article", orientation="h", title="Par article")
            .update_layout(height=max(260, 24 * min(len(par_art), 15) + 90),
                           margin=dict(l=8, r=8, t=48, b=8),
                           plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                           showlegend=False)
            .update_traces(marker_color="#9db8dc"),
            width="stretch")

        for h in hits:
            with st.expander(h.citation):
                st.markdown(h.snippet or h.text[:600])
                with st.popover("Segment complet"):
                    st.write(h.text)
        st.stop()

    bar = st.progress(0.0)
    etat = st.empty()
    depart = time.time()

    def progression(i: int, n: int, libelle: str) -> None:
        bar.progress(i / n, text=avancement(i, n, depart))
        etat.caption(libelle)

    res = answer(question, limit=int(profondeur), document_ids=doc_ids,
                 doc_kinds=sel_kinds or None, ms_codes=sel_ms or None,
                 on_progress=progression)
    bar.empty()
    etat.empty()

    if res.error:
        st.error(res.error)

    m1, m2, m3 = st.columns(3)
    m1.metric("Passages examinés", res.examines or len(res.hits),
              help=AIDE_SELECTION)
    m2.metric("Affirmations vérifiées", len(res.claims),
              help="Chaque affirmation est adossée à une citation retrouvée "
                   "littéralement dans le passage source. Une affirmation "
                   "dont la citation est introuvable est retirée, pas "
                   "signalée.")
    m3.metric("Éléments de contexte", len(res.indirect),
              help="Quand aucun passage ne répond directement, une seconde "
                   "lecture d'ensemble rapporte ce que les textes éclairent "
                   "malgré tout, mêmes exigences de citation.")

    if res.answer_fr:
        st.markdown("### Réponse")
        st.markdown(res.answer_fr)

    def _bloc(items, titre: str, note: str = "") -> None:
        if not items:
            return
        st.markdown(f"### {titre}")
        if note:
            st.caption(note)
        for i, c in enumerate(items, start=1):
            st.markdown(f"**{i}. {c.statement}**")
            st.markdown(
                f"<div style='border-left:3px solid #c3c2b7;padding-left:0.9rem;"
                f"color:#52514e;font-size:0.92rem;margin:0.3rem 0 0.6rem 0;'>"
                f"« {c.quote} »<br><span style='color:#898781;font-size:0.82rem;'>"
                f"{c.hit.citation}</span></div>",
                unsafe_allow_html=True,
            )

    _bloc(res.claims, "Affirmations et sources",
          "Chaque affirmation cite un passage réellement présent dans le "
          "corpus, vérifié par le programme. Une affirmation dont la citation "
          "n'était pas retrouvable a été retirée.")
    _bloc(res.indirect, "Éléments de contexte",
          "Aucun passage ne répond directement à la question. Ces extraits "
          "l'éclairent, et restent adossés à une citation vérifiée.")

    # Qui s'est exprimé ? Sur une question du type « qui a demandé la
    # suppression de l'article 7 ? », c'est la réponse attendue.
    tous = res.tous_elements
    par_em = [c.hit.ms_code for c in tous if c.hit.ms_code]
    if par_em:
        compte = (pd.Series(par_em).value_counts()
                  .rename_axis("EM").reset_index(name="Éléments"))
        st.markdown("### États membres concernés")
        st.plotly_chart(
            px.bar(compte.sort_values("Éléments"), x="Éléments", y="EM",
                   orientation="h")
            .update_layout(height=max(240, 26 * len(compte) + 90),
                           margin=dict(l=8, r=8, t=20, b=8),
                           plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            .update_traces(marker_color="#1c5cab"),
            width="stretch")

    panneau_fiabilite(alertes_reponse(res, int(profondeur)))

    if res.dropped:
        st.warning(
            f"{res.dropped} affirmation(s) retirée(s) : citation introuvable "
            "dans le corpus, y compris après une seconde demande de recopie. "
            "C'est le garde-fou qui a joué, ces affirmations ne vous sont pas "
            "montrées."
        )

    if res.unanswered:
        st.markdown("### Ce que le corpus ne permet pas d'établir")
        for u in res.unanswered:
            st.markdown(f"- {u}")

    if res.hits:
        with st.expander(f"Les {len(res.hits)} passages examinés"):
            retenus = {id(c.hit) for c in tous}
            for i, h in enumerate(res.hits, start=1):
                marque = "✓ retenu" if id(h) in retenus else "· écarté"
                st.markdown(f"**[Extrait {i}]** {h.citation}  ·  {marque}")
                st.caption(h.text[:900] + (" […]" if len(h.text) > 900 else ""))
                st.divider()
