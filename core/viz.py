"""
Restitutions graphiques (Plotly).

Palette validée : bleu ↔ rouge divergent avec point neutre gris pour les scores
d'alignement (polarité), palette de statut réservée pour les effets juridiques
(état). Le statut n'est jamais porté par la couleur seule : chaque marque est
accompagnée d'une étiquette textuelle.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

# --- jetons de couleur ------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

STATUS = {
    "autorise": "#0ca30c",     # good
    "conditionne": "#fab219",  # warning
    "restreint": "#ec835a",    # serious
    "interdit": "#d03b3b",     # critical
}
STATUS_ICON = {
    "autorise": "●", "conditionne": "▲", "restreint": "◆", "interdit": "■",
}

# Échelle divergente : opposé ↔ aligné. Lue à chaque tracé depuis la palette
# active, pour que le choix « accessible / convention des notes » prenne effet
# immédiatement et partout.
from .palette import couleurs, diverging  # noqa: E402

_LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
              size=13, color=INK),
    margin=dict(l=8, r=8, t=48, b=8),
    hoverlabel=dict(bgcolor="#ffffff", bordercolor=BASELINE,
                    font=dict(color=INK, size=12)),
)

SCORE_TEXT = {0: "Opposé", 1: "Partiel", 2: "Aligné"}


def _layout(**overrides) -> dict:
    """Base commune de mise en page, avec surcharges ponctuelles.

    Passer `**_LAYOUT` et une clé déjà présente lèverait une erreur de
    doublon : cette fonction fusionne au lieu de superposer.
    """
    base = dict(_LAYOUT)
    base.update(overrides)
    return base


def alignment_heatmap(matrix: pd.DataFrame, title: str = "") -> go.Figure:
    """Matrice articles × États membres. Sequentiel divergent, 0 → 2."""
    if matrix.empty:
        return _empty("Aucune donnée analysée pour l'instant.")

    text = matrix.map(lambda v: "" if pd.isna(v) else SCORE_TEXT.get(int(v), ""))
    fig = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=list(matrix.columns),
            y=list(matrix.index),
            zmin=0, zmax=2,
            colorscale=diverging(),
            xgap=2, ygap=2,                     # séparation de 2 px entre cellules
            text=text.values,
            hovertemplate="<b>%{y}</b><br>%{x} · %{text}<extra></extra>",
            colorbar=dict(
                # pas de titre : les trois graduations se suffisent, et un
                # titre viendrait chevaucher la graduation du haut
                tickmode="array", tickvals=[0, 1, 2],
                ticktext=["Opposé", "Partiel", "Aligné"],
                thickness=12, len=0.6, outlinewidth=0,
                tickfont=dict(size=11, color=INK_SECONDARY),
            ),
        )
    )
    # Étiquettes posées en annotations : l'encre doit contraster avec sa propre
    # case (les extrêmes du divergent sont sombres, le milieu très clair).
    for yi, row_label in enumerate(matrix.index):
        for xi, col_label in enumerate(matrix.columns):
            v = matrix.iloc[yi, xi]
            if pd.isna(v):
                continue
            fig.add_annotation(
                x=col_label, y=row_label, text=SCORE_TEXT.get(int(v), ""),
                showarrow=False,
                font=dict(size=10, color="#ffffff" if int(v) in (0, 2) else INK_SECONDARY),
            )

    fig.update_layout(
        # l'axe des colonnes est en haut : il faut de la place sous le titre
        **_layout(margin=dict(l=8, r=8, t=88, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(320, 34 * len(matrix.index) + 150),
        xaxis=dict(side="top", tickfont=dict(size=12, color=INK_SECONDARY),
                   showgrid=False, zeroline=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12, color=INK_SECONDARY),
                   showgrid=False, zeroline=False),
    )
    return fig


def ally_bars(ranking: pd.DataFrame, title: str = "") -> go.Figure:
    """Classement des États membres par proximité moyenne avec la France."""
    if ranking.empty:
        return _empty("Aucun classement disponible.")

    d = ranking.sort_values("Score moyen")
    fig = go.Figure(
        go.Bar(
            x=d["Score moyen"], y=d.index, orientation="h",
            marker=dict(color=SERIES[0], line=dict(width=2, color=SURFACE)),
            width=0.62,
            text=[f"{v:.2f}" for v in d["Score moyen"]],
            textposition="outside",
            textfont=dict(size=12, color=INK_SECONDARY),
            customdata=d[["Articles analysés", "Alignements", "Oppositions"]].values,
            hovertemplate=("<b>%{y}</b><br>Score moyen %{x:.2f}<br>"
                           "%{customdata[0]} articles · %{customdata[1]} alignements · "
                           "%{customdata[2]} oppositions<extra></extra>"),
        )
    )
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(300, 26 * len(d) + 120),
        bargap=0.34,
        xaxis=dict(range=[0, 2.25], showgrid=True, gridcolor=GRID, gridwidth=1,
                   zeroline=True, zerolinecolor=BASELINE,
                   tickfont=dict(size=11, color=INK_MUTED),
                   title=dict(text="Score moyen d'alignement (0 opposé → 2 aligné)",
                              font=dict(size=11, color=INK_MUTED))),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=INK_SECONDARY)),
    )
    return fig


def stance_breakdown(df: pd.DataFrame, title: str = "") -> go.Figure:
    """Répartition empilée des positions par État membre."""
    if df.empty:
        return _empty("Aucune donnée analysée.")

    order = ["aligne", "partiel", "oppose", "neutre"]
    labels = {"aligne": "Aligné", "partiel": "Partiel",
              "oppose": "Opposé", "neutre": "Neutre"}
    pal = couleurs()
    colors = {"aligne": pal["aligne"], "partiel": pal["partiel_ecran"],
              "oppose": pal["oppose"], "neutre": BASELINE}

    counts = (df.groupby(["ms_code", "stance"]).size()
              .unstack(fill_value=0).reindex(columns=order, fill_value=0))
    counts = counts.loc[counts.sum(axis=1).sort_values(ascending=True).index]

    fig = go.Figure()
    for stance in order:
        fig.add_bar(
            y=counts.index, x=counts[stance], orientation="h",
            name=labels[stance],
            marker=dict(color=colors[stance], line=dict(width=2, color=SURFACE)),
            hovertemplate=f"<b>%{{y}}</b><br>{labels[stance]} : %{{x}}<extra></extra>",
        )
    fig.update_layout(
        **_LAYOUT,
        barmode="stack", bargap=0.34,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(300, 26 * len(counts) + 130),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=12, color=INK_SECONDARY)),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=True,
                   zerolinecolor=BASELINE, tickfont=dict(size=11, color=INK_MUTED),
                   title=dict(text="Nombre de contributions analysées",
                              font=dict(size=11, color=INK_MUTED))),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=INK_SECONDARY)),
    )
    return fig


def contentious_scatter(stats: pd.DataFrame, title: str = "") -> go.Figure:
    """Articles positionnés selon le score moyen et la dispersion des positions."""
    if stats.empty:
        return _empty("Aucune donnée analysée.")
    d = stats.dropna(subset=["Score moyen"])
    # Un article commenté par un seul État membre n'a pas de dispersion :
    # l'écart-type vaut NaN. Le remplir par zéro plaçait cette opinion isolée
    # dans le coin que la légende décrit comme « opposition large et
    # homogène ». On l'écarte du nuage plutôt que d'inventer un consensus.
    if "EM analysés" in d.columns:
        isoles = int((d["EM analysés"] < 2).sum())
        d = d[d["EM analysés"] >= 2]
        if d.empty:
            return _empty(
                f"{isoles} article(s) commenté(s) par un seul État membre : "
                "trop peu pour parler de dispersion.")
    # Étiquetage sélectif : seuls les articles les plus clivants portent un
    # libellé permanent ; les autres restent accessibles au survol.
    flagged = set(d.head(5).index) | set(
        d.nlargest(3, "Dispersion").index if "Dispersion" in d else []
    )
    labels = [name if name in flagged else "" for name in d.index]

    fig = go.Figure(
        go.Scatter(
            x=d["Score moyen"], y=d["Dispersion"],
            mode="markers+text",
            marker=dict(size=13, color=SERIES[0], opacity=0.85,
                        line=dict(width=2, color=SURFACE)),
            text=labels, textposition="top center",
            textfont=dict(size=10, color=INK_MUTED),
            customdata=list(d.index),
            hovertemplate=("<b>%{customdata}</b><br>Score moyen %{x:.2f}<br>"
                           "Dispersion %{y:.2f}<extra></extra>"),
        )
    )
    xpad = max(0.12, (d["Score moyen"].max() - d["Score moyen"].min()) * 0.12)
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=460,
        xaxis=dict(title=dict(text="Score moyen (0 opposé → 2 aligné)",
                              font=dict(size=11, color=INK_MUTED)),
                   range=[d["Score moyen"].min() - xpad, d["Score moyen"].max() + xpad],
                   showgrid=True, gridcolor=GRID, zeroline=False,
                   tickfont=dict(size=11, color=INK_MUTED)),
        yaxis=dict(title=dict(text="Dispersion des positions (écart-type)",
                              font=dict(size=11, color=INK_MUTED)),
                   showgrid=True, gridcolor=GRID, zeroline=False,
                   tickfont=dict(size=11, color=INK_MUTED)),
    )
    return fig


def coverage_bars(df: pd.DataFrame, title: str = "") -> go.Figure:
    """Volume de contributions par État membre — lecture de la mobilisation."""
    if df.empty:
        return _empty("Aucune contribution.")
    counts = df.groupby("ms_code").size().sort_values()
    fig = go.Figure(
        go.Bar(
            x=counts.values, y=counts.index, orientation="h",
            marker=dict(color=SERIES[2], line=dict(width=2, color=SURFACE)),
            width=0.62,
            # étiquettes visibles : la teinte aqua passe sous 3:1 sur fond clair,
            # le nombre ne doit donc jamais dépendre de la seule couleur
            text=counts.values, textposition="outside",
            textfont=dict(size=11, color=INK_SECONDARY),
            hovertemplate="<b>%{y}</b><br>%{x} contributions<extra></extra>",
        )
    )
    fig.update_layout(
        **_LAYOUT, bargap=0.34,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(280, 24 * len(counts) + 110),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=True,
                   zerolinecolor=BASELINE, tickfont=dict(size=11, color=INK_MUTED)),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=INK_SECONDARY)),
    )
    return fig


# --- coalitions -------------------------------------------------------------

# Séquentiel : une seule teinte, du clair au foncé — le taux d'accord est une
# magnitude, pas une polarité.
SEQUENTIAL = [
    [0.0, "#f2f5fa"], [0.25, "#c3d7f0"], [0.5, "#86b6ef"],
    [0.75, "#3d86dd"], [1.0, "#17427d"],
]


def agreement_heatmap(agree: pd.DataFrame, title: str = "") -> go.Figure:
    """Taux d'accord entre États membres, toutes paires."""
    if agree.empty:
        return _empty("Pas assez de positions communes pour comparer les États.")
    fig = go.Figure(
        go.Heatmap(
            z=agree.values, x=list(agree.columns), y=list(agree.index),
            zmin=0, zmax=1, colorscale=SEQUENTIAL, xgap=2, ygap=2,
            hovertemplate="<b>%{y} / %{x}</b><br>Accord : %{z:.0%}<extra></extra>",
            colorbar=dict(
                tickformat=".0%", thickness=12, len=0.6, outlinewidth=0,
                tickfont=dict(size=11, color=INK_SECONDARY)),
        )
    )
    fig.update_layout(
        **_layout(margin=dict(l=8, r=8, t=88, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(420, 26 * len(agree.index) + 180),
        xaxis=dict(side="top", showgrid=False, zeroline=False,
                   tickfont=dict(size=11, color=INK_SECONDARY)),
        yaxis=dict(autorange="reversed", showgrid=False, zeroline=False,
                   tickfont=dict(size=11, color=INK_SECONDARY)),
    )
    return fig


def bloc_network(agree: pd.DataFrame, threshold: float,
                 blocs: list, title: str = "") -> go.Figure:
    """Graphe des accords : une arête au-dessus du seuil, un nœud par État."""
    import networkx as nx

    if agree.empty:
        return _empty("Pas assez de données pour dessiner les blocs.")

    g = nx.Graph()
    g.add_nodes_from(agree.columns)
    for i, a in enumerate(agree.columns):
        for b in list(agree.columns)[i + 1:]:
            v = agree.loc[a, b]
            if pd.notna(v) and v >= threshold:
                g.add_edge(a, b, weight=float(v))

    # Les États reliés sont disposés par force ; ceux qui n'ont aucune arête
    # sont alignés en bas, hors du nuage — un nœud isolé placé au hasard au
    # milieu du graphe se lit à tort comme un membre du groupe voisin.
    linked = [n for n in g.nodes if g.degree(n) > 0]
    loners = [n for n in g.nodes if g.degree(n) == 0]
    pos = (nx.spring_layout(g.subgraph(linked), seed=7, k=1.2, iterations=300)
           if linked else {})
    for i, n in enumerate(sorted(loners)):
        step = 2.0 / max(len(loners), 1)
        pos[n] = (-1.0 + (i + 0.5) * step, -1.55)

    # Un État seul n'est pas un bloc : il rejoint les isolés plutôt que de
    # consommer une teinte de la palette et une ligne de légende.
    real = [b for b in blocs if b.n_states > 1][:len(SERIES)]
    overflow = [b for b in blocs if b.n_states > 1][len(SERIES):]
    grouped = {m for b in real for m in b.members}

    edge_x, edge_y = [], []
    for a, b in g.edges():
        edge_x += [pos[a][0], pos[b][0], None]
        edge_y += [pos[a][1], pos[b][1], None]

    fig = go.Figure()
    fig.add_scatter(x=edge_x, y=edge_y, mode="lines",
                    line=dict(width=2, color=GRID), hoverinfo="skip",
                    showlegend=False)

    for i, bloc in enumerate(real):
        members = [m for m in bloc.members if m in pos]
        if not members:
            continue
        fig.add_scatter(
            x=[pos[m][0] for m in members], y=[pos[m][1] for m in members],
            mode="markers+text",
            marker=dict(size=22, color=SERIES[i],
                        line=dict(width=2, color=SURFACE)),
            text=members, textposition="middle center",
            textfont=dict(size=10, color="#ffffff"),
            name=(f"Bloc {i + 1} · {bloc.n_states} EM · "
                  f"{bloc.population_share:.0%} pop."
                  + (" · bloquant" if bloc.is_blocking else "")),
            hovertemplate="<b>%{text}</b><extra></extra>",
        )

    if overflow:
        members = [m for b in overflow for m in b.members if m in pos]
        fig.add_scatter(
            x=[pos[m][0] for m in members], y=[pos[m][1] for m in members],
            mode="markers+text",
            marker=dict(size=20, color=INK_SECONDARY,
                        line=dict(width=2, color=SURFACE)),
            text=members, textposition="middle center",
            textfont=dict(size=10, color="#ffffff"),
            name=f"Autres blocs ({len(overflow)})",
            hovertemplate="<b>%{text}</b><extra></extra>",
        )
        grouped |= set(members)

    isolated = [n for n in g.nodes if n not in grouped and n in pos]
    if isolated:
        fig.add_scatter(
            x=[pos[m][0] for m in isolated], y=[pos[m][1] for m in isolated],
            mode="markers+text",
            marker=dict(size=20, color=BASELINE, line=dict(width=2, color=SURFACE)),
            text=isolated, textposition="middle center",
            textfont=dict(size=10, color=INK),
            name=f"Sans bloc à ce seuil ({len(isolated)})",
            hovertemplate="<b>%{text}</b><extra></extra>",
        )

    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=600,
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, x=0,
                    font=dict(size=11, color=INK_SECONDARY)),
        xaxis=dict(visible=False, range=[-1.25, 1.25]),
        yaxis=dict(visible=False, range=[-1.8, 1.25]),
    )
    return fig


def qmv_meter(label: str, value: float, threshold: float,
              detail: str = "") -> str:
    """Jauge HTML : un seuil, une valeur, toujours doublés du chiffre écrit."""
    pct = max(0.0, min(1.0, value))
    reached = value >= threshold
    color = STATUS["autorise"] if reached else STATUS["restreint"]
    icon = "●" if reached else "◆"
    return f"""
<div style="margin-bottom:1.1rem;">
  <div style="display:flex;justify-content:space-between;font-size:0.82rem;
              color:#52514e;margin-bottom:0.3rem;">
    <span>{label}</span>
    <span style="font-variant-numeric:tabular-nums;">
      {icon} {value:.1%} <span style="color:#898781;">/ seuil {threshold:.0%}</span>
    </span>
  </div>
  <div style="position:relative;height:10px;background:#f0efec;border-radius:5px;">
    <div style="width:{pct * 100:.1f}%;height:10px;background:{color};
                border-radius:5px;"></div>
    <div style="position:absolute;left:{threshold * 100:.1f}%;top:-3px;
                width:2px;height:16px;background:#52514e;"></div>
  </div>
  <div style="font-size:0.78rem;color:#898781;margin-top:0.25rem;">{detail}</div>
</div>"""


# --- graphe de décision -----------------------------------------------------

def decision_graph(sub: nx.DiGraph, title: str = "") -> go.Figure:
    """Chemin juridique parcouru. Le statut est doublé d'un libellé et d'une icône."""
    if sub.number_of_nodes() == 0:
        return _empty("Aucun chemin à afficher.")

    # Disposition en couches : profondeur depuis les entrées. Les régimes,
    # qui sont terminaux, sont tous alignés dans la dernière colonne pour que
    # leurs libellés — les plus longs — ne recouvrent jamais un autre nœud.
    entries = [n for n, d in sub.nodes(data=True) if d.get("type") == "entree"]
    depth: dict[str, int] = {n: 0 for n in entries}
    for n in nx.topological_sort(sub):
        for _, m in sub.out_edges(n):
            depth[m] = max(depth.get(m, 0), depth.get(n, 0) + 1)

    last = max(depth.values(), default=0)
    for n, d in sub.nodes(data=True):
        if d.get("type") == "regime":
            depth[n] = last

    layers: dict[int, list[str]] = {}
    for n, d in depth.items():
        layers.setdefault(d, []).append(n)

    span = max(len(v) for v in layers.values())
    pos: dict[str, tuple[float, float]] = {}
    for d, nodes in layers.items():
        step = span / max(len(nodes), 1)
        for i, n in enumerate(sorted(nodes)):
            pos[n] = (d * 1.0, -((i + 0.5) * step - span / 2))

    edge_x, edge_y = [], []
    for a, b in sub.edges():
        if a in pos and b in pos:
            edge_x += [pos[a][0], pos[b][0], None]
            edge_y += [pos[a][1], pos[b][1], None]

    fig = go.Figure()
    fig.add_scatter(x=edge_x, y=edge_y, mode="lines",
                    line=dict(width=2, color=BASELINE),
                    hoverinfo="skip", showlegend=False)

    def wrap(text: str, width: int = 34) -> str:
        words, lines, cur = text.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > width and cur:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        lines.append(cur)
        return "<br>".join(lines[:3])

    for n, (x, y) in pos.items():
        d = sub.nodes[n]
        kind = d.get("type")
        terminal = kind == "regime"
        if terminal:
            color = STATUS.get(d.get("effet", "conditionne"), BASELINE)
            icon = STATUS_ICON.get(d.get("effet", "conditionne"), "●")
            label = f"{icon} {wrap(d.get('label', n))}"
            hover = (f"<b>{d.get('label', n)}</b><br>{d.get('texte','')}<br>"
                     f"{', '.join(d.get('articles', []))}<extra></extra>")
        else:
            color = SERIES[0] if kind == "entree" else BASELINE
            label = wrap(d.get("label", n))
            hover = f"<b>{d.get('label', n)}</b><extra></extra>"
        fig.add_scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=18, color=color, line=dict(width=2, color=SURFACE)),
            text=[label],
            # les nœuds terminaux étiquettent à droite, les intermédiaires
            # au-dessus : deux couloirs de texte qui ne se croisent pas
            textposition="middle right" if terminal else "top center",
            textfont=dict(size=11, color=INK_SECONDARY),
            hovertemplate=hover, showlegend=False,
        )

    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(360, 86 * span + 140),
        xaxis=dict(visible=False, range=[-0.6, last + 1.9]),
        yaxis=dict(visible=False, range=[-span / 2 - 0.8, span / 2 + 0.8]),
    )
    return fig


def _empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False,
                       font=dict(size=13, color=INK_MUTED))
    fig.update_layout(**_LAYOUT, height=220,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ---------------------------------------------------------------------------
# Comparaison de versions
# ---------------------------------------------------------------------------
#
# Un tableau de similarités répond à « qu'est-ce qui a changé ? » mais pas à
# « par où commencer ? ». Ces trois vues répondent à la seconde question, et
# chacune sous un angle différent :
#
#   - la carte donne l'ampleur relative — un article qui a doublé de volume
#     saute aux yeux avant qu'on ait lu une ligne ;
#   - les barres divergentes séparent ce qui a été ajouté de ce qui a été
#     retiré, distinction qu'un compte net efface ;
#   - le nuage croise ampleur et similarité : en bas à droite, les articles
#     entièrement réécrits.
#
# Toutes trois sont cliquables : la sélection remonte à la page, qui ouvre
# l'article correspondant. C'est ce qui fait la différence entre une
# illustration et un instrument de navigation.

STATUT_COULEUR = {
    "Article ajouté": "#1c5cab",
    "Article supprimé": "#d03b3b",
    "Article modifié": "#ec835a",
    "Inchangé": "#e1e0d9",
}
IMPACT_COULEUR = {
    "majeur": "#d03b3b",
    "mineur": "#ec835a",
    "redactionnel": "#9db8dc",
    "nul": "#e1e0d9",
    "—": "#c3c2b7",
}


def _table_utile(table: pd.DataFrame, inclure_inchanges: bool) -> pd.DataFrame:
    d = table.copy()
    if not inclure_inchanges:
        d = d[d["Statut"] != "Inchangé"]
    d["Ampleur"] = d["Mots ajoutés"] + d["Mots retirés"]
    return d


def change_treemap(table: pd.DataFrame, par: str = "Statut",
                   inclure_inchanges: bool = False, title: str = "",
                   top: int = 40) -> go.Figure:
    """Carte des changements : une tuile par article, taille = mots touchés.

    `top` borne le nombre de tuiles. Sur un texte de cent articles, une carte
    exhaustive donne cent tuiles dont aucune n'est lisible : elle a l'air d'un
    résultat et ne se lit pas. On garde donc les plus gros changements, et
    l'appelant affiche combien d'articles ne sont pas représentés — une coupe
    silencieuse serait pire que la carte illisible.
    """
    d = _table_utile(table, inclure_inchanges)
    d = d[d["Ampleur"] > 0]
    if d.empty:
        return _empty("Aucun changement à cartographier.")
    d = d.sort_values("Ampleur", ascending=False).head(max(1, int(top)))

    couleurs = STATUT_COULEUR if par == "Statut" else IMPACT_COULEUR
    groupes = d[par].fillna("—").astype(str)

    fig = go.Figure(go.Treemap(
        labels=list(d["Article"]),
        parents=list(groupes),
        values=list(d["Ampleur"]),
        marker=dict(colors=[couleurs.get(g, "#c3c2b7") for g in groupes]),
        text=[f"+{a} / −{r}" for a, r in zip(d["Mots ajoutés"], d["Mots retirés"])],
        textinfo="label+text",
        textfont=dict(size=14, color="#ffffff"),
        insidetextfont=dict(size=14, color="#ffffff"),
        hovertemplate="<b>%{label}</b><br>%{text}<br>"
                      "%{value} mots touchés<extra></extra>",
        tiling=dict(pad=4, squarifyratio=1.6),
        branchvalues="remainder",
    ))
    # Les groupes doivent exister comme nœuds racines, sinon Plotly les ignore.
    racines = list(dict.fromkeys(groupes))
    fig.data[0].labels = list(d["Article"]) + racines
    fig.data[0].parents = list(groupes) + [""] * len(racines)
    fig.data[0].values = list(d["Ampleur"]) + [0] * len(racines)
    fig.data[0].marker.colors = (
        [couleurs.get(g, "#c3c2b7") for g in groupes]
        + [couleurs.get(r, "#c3c2b7") for r in racines])
    fig.data[0].text = ([f"+{a} / −{r}" for a, r in
                         zip(d["Mots ajoutés"], d["Mots retirés"])]
                        + [""] * len(racines))

    fig.update_layout(
        **_layout(margin=dict(l=6, r=6, t=48, b=6)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=max(520, min(860, 120 + 34 * len(d))),
        uniformtext=dict(minsize=11, mode="show"),
    )
    return fig


def change_bars(table: pd.DataFrame, top: int = 25,
                inclure_inchanges: bool = False, title: str = "") -> go.Figure:
    """Barres divergentes : mots retirés à gauche, ajoutés à droite."""
    d = _table_utile(table, inclure_inchanges)
    d = d[d["Ampleur"] > 0].sort_values("Ampleur", ascending=False).head(top)
    if d.empty:
        return _empty("Aucun changement à représenter.")
    d = d.iloc[::-1]                       # le plus gros en haut du graphique

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=list(d["Article"]), x=[-v for v in d["Mots retirés"]],
        orientation="h", name="Mots retirés",
        marker=dict(color="#d03b3b"),
        customdata=list(zip(d["Article"], d["Mots retirés"])),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} mots "
                      "retirés<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=list(d["Article"]), x=list(d["Mots ajoutés"]),
        orientation="h", name="Mots ajoutés",
        marker=dict(color="#1c5cab"),
        customdata=list(zip(d["Article"], d["Mots ajoutés"])),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} mots "
                      "ajoutés<extra></extra>",
    ))
    fig.update_layout(
        **_layout(margin=dict(l=8, r=8, t=64, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        barmode="relative",
        height=max(320, 30 * len(d) + 130),
        legend=dict(orientation="h", y=1.06, x=0),
        xaxis=dict(title="mots retirés ← → mots ajoutés", zeroline=True,
                   zerolinecolor=BASELINE, gridcolor=GRID),
        yaxis=dict(automargin=True, tickfont=dict(size=11)),
    )
    return fig


def change_scatter(table: pd.DataFrame, inclure_inchanges: bool = False,
                   title: str = "") -> go.Figure:
    """Ampleur × similarité : en bas à droite, les articles réécrits."""
    d = _table_utile(table, inclure_inchanges)
    if d.empty:
        return _empty("Aucun changement à représenter.")

    fig = go.Figure()
    for statut, groupe in d.groupby("Statut"):
        fig.add_trace(go.Scatter(
            x=list(groupe["Ampleur"]), y=list(groupe["Similarité"]),
            mode="markers+text", name=str(statut),
            text=list(groupe["Article"]),
            textposition="middle right",
            textfont=dict(size=10, color=INK_SECONDARY),
            marker=dict(size=13, color=STATUT_COULEUR.get(str(statut), "#c3c2b7"),
                        line=dict(width=1, color=SURFACE)),
            # L'intitulé voyage dans customdata : c'est ce que la page relit
            # pour savoir quel article a été cliqué.
            customdata=list(zip(groupe["Article"], groupe["Mots ajoutés"],
                                groupe["Mots retirés"])),
            hovertemplate="<b>%{customdata[0]}</b><br>similarité %{y:.0%}<br>"
                          "+%{customdata[1]} / −%{customdata[2]} mots<extra></extra>",
        ))
    fig.update_layout(
        **_layout(margin=dict(l=8, r=90, t=64, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=460,
        legend=dict(orientation="h", y=1.06, x=0),
        xaxis=dict(title="mots touchés", gridcolor=GRID),
        yaxis=dict(title="similarité avec la version antérieure",
                   tickformat=".0%", gridcolor=GRID, range=[-0.05, 1.05]),
    )
    return fig


# ---------------------------------------------------------------------------
# Ciblage de négociation
# ---------------------------------------------------------------------------

STATUT_CIBLE_COULEUR = {
    "Allié": "#1c5cab",
    "À convaincre": "#ec835a",
    "Opposé": "#d03b3b",
    "Ne s'est pas exprimé": "#c3c2b7",
}


def targets_scatter(targets: pd.DataFrame, title: str = "") -> go.Figure:
    """Proximité avec la France × poids au Conseil.

    Les deux dimensions qui décident d'un démarchage : à quel point l'État est
    d'accord avec nous, et ce que son ralliement pèse. En haut à droite, les
    appels à passer en premier.
    """
    d = targets.dropna(subset=["Score moyen"]) if not targets.empty else targets
    if d is None or d.empty:
        return _empty("Aucune position analysée sur ce périmètre.")

    fig = go.Figure()
    for statut, groupe in d.groupby("Statut"):
        fig.add_trace(go.Scatter(
            x=list(groupe["Score moyen"]),
            y=list(groupe["Part de population"]),
            mode="markers+text", name=str(statut),
            text=list(groupe["EM"]),
            textposition="top center",
            textfont=dict(size=11, color=INK_SECONDARY),
            marker=dict(
                size=[10 + 2.2 * n for n in groupe["Articles où il s'exprime"]],
                color=STATUT_CIBLE_COULEUR.get(str(statut), BASELINE),
                line=dict(width=1, color=SURFACE), opacity=0.88),
            customdata=list(zip(groupe["EM"], groupe["Articles alignés"],
                                groupe["Alignements partiels"],
                                groupe["Divergences"])),
            hovertemplate="<b>%{customdata[0]}</b><br>score %{x:.2f}<br>"
                          "%{y:.1%} de la population<br>"
                          "%{customdata[1]} alignés · %{customdata[2]} partiels · "
                          "%{customdata[3]} divergents<extra></extra>",
        ))

    # Repère : au-delà de 35 % de population cumulée, un groupe bloque. Le
    # trait ne vaut évidemment que pour un cumul, pas pour un État seul — il
    # est là pour rappeler l'échelle.
    fig.add_hline(y=0.15, line=dict(color=GRID, width=1, dash="dot"),
                  annotation_text="poids notable au Conseil",
                  annotation_position="top left",
                  annotation_font=dict(size=10, color=INK_MUTED))
    fig.update_layout(
        **_layout(margin=dict(l=8, r=20, t=64, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=480,
        legend=dict(orientation="h", y=1.06, x=0),
        xaxis=dict(title="proximité moyenne avec la position française "
                         "(0 = opposé, 2 = aligné)",
                   gridcolor=GRID, range=[-0.15, 2.15]),
        yaxis=dict(title="part de la population de l'Union",
                   tickformat=".0%", gridcolor=GRID),
    )
    return fig


def targets_bars(targets: pd.DataFrame, title: str = "") -> go.Figure:
    """Répartition alignés / partiels / divergents, État par État."""
    d = targets[targets["Articles où il s'exprime"] > 0] if not targets.empty \
        else targets
    if d is None or d.empty:
        return _empty("Aucune position analysée sur ce périmètre.")
    d = d.iloc[::-1]

    series = [("Articles alignés", "#1c5cab"),
              ("Alignements partiels", "#9db8dc"),
              ("Divergences", "#d03b3b")]
    fig = go.Figure()
    for nom, couleur in series:
        fig.add_trace(go.Bar(
            y=list(d["EM"]), x=list(d[nom]), orientation="h", name=nom,
            marker=dict(color=couleur),
            customdata=list(d["EM"]),
            hovertemplate="<b>%{customdata}</b><br>%{x} " + nom.lower()
                          + "<extra></extra>",
        ))
    fig.update_layout(
        **_layout(margin=dict(l=8, r=8, t=64, b=8)),
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        barmode="stack",
        height=max(320, 26 * len(d) + 140),
        legend=dict(orientation="h", y=1.06, x=0),
        xaxis=dict(title="nombre d'articles", gridcolor=GRID),
        yaxis=dict(automargin=True, tickfont=dict(size=11)),
    )
    return fig
