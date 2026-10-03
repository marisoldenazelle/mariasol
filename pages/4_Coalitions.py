"""
Coalitions — à qui parler, avec qui, et cela suffit-il ?

La page répond à trois questions, dans cet ordre d'utilité pratique :

1. **Qui aller chercher.** Quels États membres portent une position proche de
   la nôtre sur les articles qui nous intéressent — c'est la liste d'appels à
   passer.
2. **Qui pense comme qui.** Les alliances qui se forment sans nous, et qui
   peuvent nous barrer la route.
3. **Cela suffit-il ?** C'est ici, et seulement ici, que servent les chiffres
   de population : au Conseil une position ne l'emporte pas au nombre d'États
   mais au nombre d'États *et* à la population qu'ils représentent. Savoir que
   Malte nous suit ne dit pas la même chose que savoir que l'Allemagne nous
   suit.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import store
from core.coalition import (BLOCKING_MIN_STATES, QMV_POP_THRESHOLD,
                            QMV_STATES_THRESHOLD, agreement_matrix,
                            best_additions, coalition_report, detect_blocs,
                            load_populations, negotiation_targets, pivot_states,
                            qmv_status, shared_positions)
from core.fiabilite import coalitions as alertes_coalitions
from core.ui import (comment_ca_marche, entete_module,
                     panneau_fiabilite, pour_aller_plus_loin)
from core.viz import (agreement_heatmap, bloc_network, qmv_meter,
                      targets_bars, targets_scatter)


entete_module(
    "Avec qui négocier, et cela suffit-il ?",
    "Quatre lectures du même document : qui appeler en premier, quelles "
    "alliances se forment sans nous, qui s'entend avec qui, et ce que pèse un "
    "groupe au Conseil.")

with st.expander("À quoi sert chacun des quatre onglets", expanded=False):
    st.markdown(
        """
| Onglet | La question à laquelle il répond | Quand s'en servir |
|---|---|---|
| **Qui aller chercher** | Quels États membres portent une position proche de la nôtre, et que pèse leur ralliement ? | En premier, pour établir la liste des appels à passer. |
| **Blocs** | Quels États s'entendent entre eux, indépendamment de la France ? | Pour repérer une alliance qui se formerait sans nous, et pourrait nous barrer la route. |
| **Accords deux à deux** | Quel est le taux d'accord de chaque paire d'États ? | Pour vérifier une intuition sur un couple précis, ou préparer une démarche conjointe. |
| **Arithmétique du Conseil** | Cette répartition atteint-elle la majorité qualifiée, ou constitue-t-elle une minorité de blocage ? | En dernier, une fois la coalition envisagée, pour savoir si elle suffit. |

**Les chiffres de population ne servent qu'au dernier onglet**, et au calcul
de poids du premier. Au Conseil, une position l'emporte au nombre d'États *et*
à la population représentée : rallier Malte et rallier l'Allemagne ne
produisent pas le même résultat.
        """)

docs = store.list_documents()
wk = docs[docs.get("kind", pd.Series(dtype=str)) == "wk_table"] if not docs.empty else docs
if wk.empty:
    st.info("Chargez un document de commentaires consolidés depuis la **Bibliothèque**.")
    st.stop()

doc_id = st.selectbox("Document", options=list(wk["id"]),
                      format_func=lambda i: wk.set_index("id").loc[i, "name"])
referentiel = st.radio(
    "Positions mesurées par rapport à", ["fr", "texte"], horizontal=True,
    format_func=lambda r: ("la position française" if r == "fr"
                           else "le texte initial"),
    help="Deux États peuvent être d'accord entre eux contre la France, ou "
         "d'accord pour laisser le texte tel quel. Le référentiel change donc "
         "les blocs, pas seulement leur intitulé.")
matrix = store.score_matrix(doc_id, referentiel=referentiel)
if matrix.empty:
    st.warning("Aucune position analysée pour ce document. Lancez d'abord "
               "l'analyse depuis la page **Positions des États membres**.")
    st.stop()

agree = agreement_matrix(matrix)
shared = shared_positions(matrix)

comment_ca_marche("coalitions")
panneau_fiabilite(alertes_coalitions(
    agree, shared, not load_populations().empty))

t0, t1, t2, t3 = st.tabs(
    ["Qui aller chercher", "Blocs", "Accords deux à deux",
     "Arithmétique du Conseil"])

# --------------------------------------------------------------- ciblage FR
with t0:
    st.info(
        "**Votre liste d'appels.** Sur les articles que vous choisissez, "
        "l'outil classe chaque État membre en allié, à convaincre ou opposé, "
        "et croise cette proximité avec son poids démographique au Conseil.",
        icon=":material/call:")
    arts = st.multiselect(
        "Articles à considérer", options=list(matrix.index),
        help="Laisser vide pour prendre tous les articles analysés. "
             "Restreindre au titre en discussion donne une liste d'appels "
             "beaucoup plus juste.")
    targets = negotiation_targets(matrix, arts or None)

    if targets.empty:
        st.info("Aucune position analysée sur ce périmètre.")
    else:
        allies = list(targets[targets["Statut"] == "Allié"]["EM"])
        convaincre = list(targets[targets["Statut"] == "À convaincre"]["EM"])
        opposes = list(targets[targets["Statut"] == "Opposé"]["EM"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Alliés", len(allies))
        c2.metric("À convaincre", len(convaincre))
        c3.metric("Opposés", len(opposes))

        st.plotly_chart(
            targets_scatter(targets,
                            "Proximité avec la France × poids au Conseil"),
            width="stretch")
        st.caption(
            "En haut à droite : proches de nous **et** lourds au Conseil, les "
            "appels à passer en premier. La taille du point est le nombre "
            "d'articles sur lesquels l'État s'est exprimé : un point minuscule "
            "très bien placé repose sur une ou deux prises de position, à "
            "confirmer avant d'en tirer une stratégie."
        )

        st.plotly_chart(
            targets_bars(targets, "Positions par État membre, sur ce périmètre"),
            width="stretch")

        st.dataframe(targets, width="stretch", hide_index=True)

        # --- ce que pèse la coalition -------------------------------------
        st.divider()
        st.markdown("### Ce que pèse la coalition envisagée")
        st.caption(
            "C'est à cette question, et à elle seule, que servent les "
            "chiffres de population. Une coalition de treize États qui "
            "représente 30 % de la population ne bloque rien ; quatre États "
            "qui en représentent 36 % bloquent."
        )
        defaut = ["FR"] + allies
        membres = st.multiselect(
            "Coalition (France comprise)",
            options=["FR"] + list(matrix.columns),
            default=[m for m in dict.fromkeys(defaut)])
        objectif = st.radio(
            "Ce que nous cherchons", ["Faire adopter le texte",
                                      "Bloquer le texte"], horizontal=True)

        rapport = coalition_report(membres)
        if not rapport["population_disponible"]:
            st.warning(
                "Chiffres de population absents : renseignez "
                "`data/reference/populations.csv` depuis la page "
                "**Administration** pour activer ce calcul.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("États membres", rapport["n_etats"])
            m2.metric("Population représentée",
                      f"{rapport['part_population']:.1%}")
            if objectif == "Faire adopter le texte":
                m3.metric("Majorité qualifiée",
                          "atteinte" if rapport["atteint_qmv"] else "non atteinte")
                if not rapport["atteint_qmv"]:
                    st.markdown(
                        f"Il manque **{rapport['manque_etats']} État(s) membre(s)** "
                        f"et **{rapport['manque_population']:.1%} de population** "
                        "pour atteindre le seuil.")
            else:
                m3.metric("Minorité de blocage",
                          "constituée" if rapport["bloque"] else "non constituée")
                if not rapport["bloque"]:
                    manque_etats = max(0, BLOCKING_MIN_STATES - rapport["n_etats"])
                    manque_pop = max(0.0, (1 - QMV_POP_THRESHOLD)
                                     - rapport["part_population"])
                    st.markdown(
                        f"Il manque **{manque_etats} État(s) membre(s)** et "
                        f"**{manque_pop:.1%} de population** pour bloquer.")

            candidats = [s for s in list(matrix.columns) + ["FR"]
                         if s not in membres]
            gains = best_additions(
                membres, candidats,
                "qmv" if objectif == "Faire adopter le texte" else "blocage")
            if not gains.empty:
                st.markdown("**Ralliements les plus utiles**")
                st.caption(
                    "Classés par apport de population. « Franchit le seuil » "
                    "signale l'État dont le seul ralliement suffirait.")
                st.dataframe(gains.head(10), width="stretch", hide_index=True)

        st.info(
            "Les positions écrites d'un groupe de travail ne sont pas des "
            "votes. Ce calcul dit ce que donnerait cette répartition si elle "
            "se transposait en vote, pas ce qui se passera.", icon="⚠️")

# ------------------------------------------------------------------- blocs
with t1:
    st.info(
        "**Les alliances qui se forment sans nous.** Deux États sont reliés "
        "quand ils tiennent la même position sur une proportion suffisante "
        "des articles où ils se sont tous deux exprimés ; un bloc est un "
        "groupe d'États ainsi reliés de proche en proche. La France n'entre "
        "pas dans le calcul : c'est précisément l'intérêt.",
        icon=":material/hub:")
    c1, c2 = st.columns([1, 1])
    threshold = c1.slider(
        "Seuil d'accord pour relier deux États", 0.4, 1.0, 0.75, 0.05,
        help="Deux États sont reliés s'ils tiennent la même position sur au "
             "moins cette proportion des articles où ils se sont tous deux exprimés.")
    min_shared = c2.slider(
        "Articles communs minimum", 1, 10, 3,
        help="Empêche de conclure à une alliance sur une ou deux coïncidences.")

    blocs = detect_blocs(matrix, threshold=threshold, min_shared=min_shared)
    largest = max((b.n_states for b in blocs), default=0)
    if largest > 0.6 * len(matrix.columns):
        st.warning(
            f"Un seul bloc regroupe {largest} États sur {len(matrix.columns)} : "
            "le seuil est trop bas pour distinguer quoi que ce soit, ou les "
            "positions sont trop homogènes. Montez le seuil."
        )

    st.plotly_chart(
        bloc_network(agree, threshold, blocs,
                     "Graphe des accords entre États membres"),
        width="stretch")

    st.markdown("### Blocs détectés")
    for i, b in enumerate(blocs, start=1):
        if b.n_states < 2:
            continue
        badge = ("  ·  **constitue une minorité de blocage**" if b.is_blocking else "")
        st.markdown(
            f"**Bloc {i}** · {', '.join(b.members)}  \n"
            f"{b.n_states} États · {b.population_share:.1%} de la population · "
            f"cohésion interne {b.cohesion:.0%}{badge}"
        )
    isolated = [s for s in matrix.columns
                if not any(s in b.members and b.n_states > 1 for b in blocs)]
    if isolated:
        st.caption("Isolés à ce seuil : " + ", ".join(isolated))

    st.info(
        "Méthode : deux États sont reliés quand leur taux d'accord dépasse le "
        "seuil ; un bloc est une composante connexe du graphe obtenu. Le calcul "
        "est refaisable à la main sur un cas, c'est délibéré, un regroupement "
        "que personne ne peut vérifier n'a pas sa place dans une note.",
        icon="🔍",
    )

# --------------------------------------------------------- accords deux à deux
with t2:
    st.info(
        "**Le détail paire par paire.** Le taux d'accord de chaque couple "
        "d'États, calculé sur les seuls articles où les deux se sont "
        "exprimés, un silence n'est pas un accord.",
        icon=":material/compare_arrows:")
    st.plotly_chart(
        agreement_heatmap(agree, "Taux d'accord entre États membres"),
        width="stretch")
    st.caption(
        "Un silence n'est pas un accord : seuls les articles où les deux États "
        "se sont exprimés entrent dans le calcul de leur taux d'accord."
    )
    # Tableau des paires : on retire la diagonale et on ne garde qu'un sens
    pairs = agree.copy()
    for s in pairs.index:
        pairs.loc[s, s] = float("nan")
    stacked = (pairs.stack().reset_index()
               .rename(columns={"level_0": "A", "level_1": "B", 0: "Accord"}))
    stacked = stacked[stacked["A"] < stacked["B"]].copy()
    stacked["Articles communs"] = [
        int(shared.loc[a, b]) for a, b in zip(stacked["A"], stacked["B"])]

    min_common = st.slider("Articles communs minimum pour figurer au tableau",
                           1, 12, 3)
    stacked = stacked[stacked["Articles communs"] >= min_common]

    c1, c2 = st.columns(2)
    c1.markdown("**Paires les plus proches**")
    c1.dataframe(stacked.sort_values("Accord", ascending=False).head(15),
                 width="stretch", hide_index=True)
    c2.markdown("**Paires les plus éloignées**")
    c2.dataframe(stacked.sort_values("Accord").head(15),
                 width="stretch", hide_index=True)

# ------------------------------------------------- arithmétique du Conseil
with t3:
    st.info(
        "**Est-ce que ça suffit ?** Vous composez un groupe d'États, à la "
        "main ou pré-rempli depuis un article, et l'outil dit ce que ce "
        "groupe donnerait s'il votait : majorité qualifiée atteinte, minorité "
        "de blocage constituée, ou ni l'un ni l'autre.",
        icon=":material/how_to_vote:")
    pop = load_populations()
    st.markdown(
        f"Majorité qualifiée : **{QMV_STATES_THRESHOLD:.0%} des États membres** "
        f"(15 sur 27) représentant **{QMV_POP_THRESHOLD:.0%} de la population**. "
        f"Une minorité de blocage réunit au moins **{BLOCKING_MIN_STATES} États** "
        f"pesant plus de **{1 - QMV_POP_THRESHOLD:.0%}** de la population."
    )
    st.warning(
        "Les positions écrites d'un groupe de travail ne sont pas des votes. "
        "Ce calcul indique ce que donnerait cette répartition si elle se "
        "transposait en vote, pas ce qui se passera.",
        icon="⚠️",
    )

    states = list(pop.index)
    article = st.selectbox(
        "Pré-remplir depuis un article", options=[None] + list(matrix.index),
        format_func=lambda a: "— saisie libre —" if a is None else a)

    default_support, default_oppose = ["FR"], []
    if article is not None:
        row = matrix.loc[article].dropna()
        default_support = ["FR"] + [s for s, v in row.items() if v == 2]
        default_oppose = [s for s, v in row.items() if v == 0]

    c1, c2 = st.columns(2)
    supporting = c1.multiselect("Soutiennent", states, default=default_support)
    opposing = c2.multiselect("S'opposent", states, default=default_oppose)

    res = qmv_status(supporting, opposing)

    st.markdown(f"### {res.verdict}")
    st.markdown(
        qmv_meter("États membres favorables", res.share_states, QMV_STATES_THRESHOLD,
                  f"{len(res.supporting)} États sur 27"),
        unsafe_allow_html=True)
    st.markdown(
        qmv_meter("Population représentée", res.share_population, QMV_POP_THRESHOLD,
                  ("Seuil atteint." if res.share_population >= QMV_POP_THRESHOLD
                   else f"Il manque {res.missing_population:.1%} de population.")),
        unsafe_allow_html=True)

    if res.opposing:
        blocking_share = float(pop.loc[[s for s in res.opposing
                                        if s in pop.index], "part"].sum())
        st.markdown(
            f"**Opposition** : {len(res.opposing)} États, {blocking_share:.1%} "
            f"de la population, "
            + ("minorité de blocage constituée."
               if res.opposition_blocks else
               "insuffisant pour bloquer en l'état.")
        )

    st.divider()
    st.markdown("**États pivots**, dont le ralliement à l'opposition ferait bloc")
    pivots = pivot_states(matrix, opposing)
    if pivots.empty:
        st.caption("Aucun calcul possible sans chiffres de population.")
    else:
        st.dataframe(pivots.head(12), width="stretch", hide_index=True)

    st.caption(
        "Chiffres de population : `data/reference/populations.csv`. Ils doivent "
        "être remplacés par ceux de l'annexe en vigueur du règlement intérieur "
        "du Conseil avant tout usage en négociation."
    )

pour_aller_plus_loin(
    "Comment ces chiffres sont calculés",
    """
**Taux d'accord.** Pour chaque paire d'États, la proportion des articles où
les deux tiennent la même position, calculée sur les seuls articles où les
deux se sont exprimés. Un silence n'entre pas dans le calcul : il ne vaut ni
accord ni désaccord.

**Blocs.** Graphe d'accord, une arête entre deux États quand leur taux
d'accord dépasse le seuil que vous fixez, sur un nombre minimum d'articles
communs, puis composantes connexes de ce graphe. Méthode volontairement
simple : un agent doit pouvoir refaire le calcul à la main sur un cas, ce qui
n'est pas le cas d'un regroupement statistique plus savant.

**Majorité qualifiée** (article 16(4) TUE) : 55 % des États membres, soit 15
sur 27, représentant 65 % de la population de l'Union. **Minorité de
blocage** : au moins 4 États membres représentant plus de 35 % de la
population. Les deux conditions sont cumulatives, c'est pourquoi trois grands
États, même à eux seuls 46 % de la population, ne bloquent rien.

**Chiffres de population** : `data/reference/populations.csv`, modifiable
depuis la page Administration. Ils doivent être remplacés par ceux de l'annexe
en vigueur du règlement intérieur du Conseil avant tout usage en négociation.

**Limite de méthode.** Les positions écrites d'un groupe de travail ne sont
pas des votes. Tout ce que dit cet onglet, c'est ce que donnerait cette
répartition si elle se transposait en vote, ce qui n'arrive jamais tel quel.
""")
