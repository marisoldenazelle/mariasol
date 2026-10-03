"""
Cartographie de coalition.

Deux questions distinctes, souvent confondues :

  « qui pense comme nous ? »  → proximité avec la position française
  « qui pense comme qui ? »   → structure des blocs, indépendamment de la France

Le second est celui qui compte en négociation : il montre les alliances qui se
formeraient même sans nous, et donc les minorités de blocage possibles.

Le calcul de majorité qualifiée suit l'article 16(4) TUE : 55 % des États
membres (15 sur 27) représentant 65 % de la population. Une minorité de
blocage doit réunir au moins 4 États membres.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from itertools import combinations

import networkx as nx
import numpy as np
import pandas as pd

from .config import DATA_DIR

POP_FILE = DATA_DIR / "reference" / "populations.csv"

QMV_STATES_THRESHOLD = 0.55      # 55 % des États membres
QMV_POP_THRESHOLD = 0.65         # 65 % de la population
BLOCKING_MIN_STATES = 4          # une minorité de blocage compte au moins 4 EM
EU_STATES = 27


def load_populations() -> pd.DataFrame:
    """Chiffres de population utilisés pour le calcul de majorité qualifiée.

    Fichier éditable : les chiffres officiels sont fixés chaque année par
    décision du Conseil modifiant son règlement intérieur. Ils doivent être
    remplacés par ceux de l'annexe en vigueur avant tout usage en négociation.
    """
    if not POP_FILE.exists():
        return pd.DataFrame(columns=["code", "nom", "population"])
    with open(POP_FILE, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    df = pd.DataFrame(rows)
    df["population"] = pd.to_numeric(df["population"], errors="coerce")
    df["part"] = df["population"] / df["population"].sum()
    return df.set_index("code")


# ---------------------------------------------------------------------------
# Proximité entre États membres
# ---------------------------------------------------------------------------

def agreement_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    """Taux d'accord entre chaque paire d'États membres.

    Deux États « s'accordent » sur un article lorsqu'ils y tiennent la même
    position vis-à-vis de la référence. Seuls les articles où les deux se sont
    exprimés entrent dans le calcul : un silence n'est pas un accord.
    """
    if matrix.empty:
        return pd.DataFrame()
    states = list(matrix.columns)
    out = pd.DataFrame(np.nan, index=states, columns=states, dtype=float)
    for a, b in combinations(states, 2):
        pair = matrix[[a, b]].dropna()
        if len(pair) < 2:
            continue
        score = float((pair[a] == pair[b]).mean())
        out.loc[a, b] = out.loc[b, a] = round(score, 3)
    for s in states:
        out.loc[s, s] = 1.0
    return out


def shared_positions(matrix: pd.DataFrame) -> pd.DataFrame:
    """Nombre d'articles sur lesquels chaque paire s'est exprimée."""
    if matrix.empty:
        return pd.DataFrame()
    states = list(matrix.columns)
    out = pd.DataFrame(0, index=states, columns=states, dtype=int)
    for a, b in combinations(states, 2):
        n = len(matrix[[a, b]].dropna())
        out.loc[a, b] = out.loc[b, a] = n
    return out


@dataclass
class Bloc:
    members: list[str]
    cohesion: float
    n_states: int = 0
    population_share: float = 0.0
    is_blocking: bool = False

    def __post_init__(self) -> None:
        self.n_states = len(self.members)


def detect_blocs(matrix: pd.DataFrame, threshold: float = 0.75,
                 min_shared: int = 2) -> list[Bloc]:
    """Regroupe les États membres en blocs par accord mutuel.

    Méthode : graphe d'accord (une arête si le taux d'accord dépasse le seuil
    sur un nombre suffisant d'articles communs), puis composantes connexes.
    Simple et lisible — un agent doit pouvoir refaire le calcul à la main sur
    un cas, ce qui n'est pas le cas d'un clustering spectral.
    """
    agree = agreement_matrix(matrix)
    shared = shared_positions(matrix)
    if agree.empty:
        return []

    g = nx.Graph()
    g.add_nodes_from(agree.columns)
    for a, b in combinations(agree.columns, 2):
        val = agree.loc[a, b]
        if pd.notna(val) and val >= threshold and shared.loc[a, b] >= min_shared:
            g.add_edge(a, b, weight=float(val))

    pop = load_populations()
    blocs: list[Bloc] = []
    for comp in nx.connected_components(g):
        members = sorted(comp)
        sub = g.subgraph(members)
        cohesion = (float(np.mean([d["weight"] for *_, d in sub.edges(data=True)]))
                    if sub.number_of_edges() else 0.0)
        share = float(pop.loc[[m for m in members if m in pop.index], "part"].sum()) \
            if not pop.empty else 0.0
        blocs.append(Bloc(members, round(cohesion, 3), population_share=round(share, 4),
                          is_blocking=is_blocking_minority(members, pop)))
    return sorted(blocs, key=lambda b: (-b.n_states, -b.cohesion))


# ---------------------------------------------------------------------------
# Majorité qualifiée
# ---------------------------------------------------------------------------

def is_blocking_minority(states: list[str], pop: pd.DataFrame | None = None) -> bool:
    """Le groupe constitue-t-il une minorité de blocage ?

    Il faut au moins 4 États membres, et que la population restante passe sous
    le seuil de 65 % — c'est-à-dire que le groupe pèse plus de 35 % de la
    population de l'Union.
    """
    pop = load_populations() if pop is None else pop
    if len(states) < BLOCKING_MIN_STATES or pop.empty:
        return False
    known = [s for s in states if s in pop.index]
    return float(pop.loc[known, "part"].sum()) > (1 - QMV_POP_THRESHOLD)


@dataclass
class QMVResult:
    supporting: list[str] = field(default_factory=list)
    opposing: list[str] = field(default_factory=list)
    silent: list[str] = field(default_factory=list)
    share_states: float = 0.0
    share_population: float = 0.0
    reaches_qmv: bool = False
    opposition_blocks: bool = False
    missing_population: float = 0.0

    @property
    def verdict(self) -> str:
        if self.opposition_blocks:
            return "Minorité de blocage constituée"
        if self.reaches_qmv:
            return "Majorité qualifiée atteinte"
        return "Majorité qualifiée non atteinte en l'état"


def qmv_status(supporting: list[str], opposing: list[str],
               all_states: list[str] | None = None) -> QMVResult:
    """Évalue une répartition de positions au regard des seuils du Conseil.

    Avertissement d'usage : les positions écrites d'un groupe de travail ne
    sont pas des votes. Ce calcul dit ce que donnerait cette répartition si
    elle se transposait en vote — pas ce qui se passera.
    """
    pop = load_populations()
    known = list(pop.index) if not pop.empty else []
    universe = all_states or known
    supporting = [s for s in supporting if s in known]
    opposing = [s for s in opposing if s in known]
    silent = [s for s in universe if s not in supporting and s not in opposing]

    share_states = len(supporting) / EU_STATES if EU_STATES else 0.0
    share_pop = float(pop.loc[supporting, "part"].sum()) if supporting else 0.0

    res = QMVResult(
        supporting=sorted(supporting), opposing=sorted(opposing),
        silent=sorted(silent),
        share_states=round(share_states, 4),
        share_population=round(share_pop, 4),
        reaches_qmv=(share_states >= QMV_STATES_THRESHOLD
                     and share_pop >= QMV_POP_THRESHOLD),
        opposition_blocks=is_blocking_minority(opposing, pop),
        missing_population=round(max(0.0, QMV_POP_THRESHOLD - share_pop), 4),
    )
    return res


def pivot_states(matrix: pd.DataFrame, opposing: list[str]) -> pd.DataFrame:
    """États dont le ralliement ferait basculer une minorité de blocage.

    On teste, pour chaque État non encore opposé, si son ajout au groupe
    d'opposition suffirait à constituer une minorité de blocage.
    """
    pop = load_populations()
    if pop.empty:
        return pd.DataFrame()
    rows = []
    base = [s for s in opposing if s in pop.index]
    for code in pop.index:
        if code in base:
            continue
        candidate = base + [code]
        rows.append({
            "EM": code,
            "Nom": pop.loc[code, "nom"],
            "Part de population": round(float(pop.loc[code, "part"]), 4),
            "Bloque si rallié": is_blocking_minority(candidate, pop),
            "Total du groupe": round(float(pop.loc[candidate, "part"].sum()), 4),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["Bloque si rallié", "Part de population"],
                           ascending=[False, False])


# ---------------------------------------------------------------------------
# Ciblage de négociation — le point de départ pratique
# ---------------------------------------------------------------------------
#
# À quoi servent les chiffres de population ? La question mérite une réponse
# nette, parce qu'elle décide de l'usage de cette page.
#
# Savoir « qui pense comme la France » suffit à décider qui appeler. Cela ne
# suffit pas à décider si l'appel change quelque chose : au Conseil, une
# position ne l'emporte pas au nombre d'États mais au nombre d'États ET à la
# population qu'ils représentent. Trois petits États ralliés ne pèsent pas ce
# que pèse l'Allemagne. La population sert donc à une seule chose ici :
# répondre à « ce groupe suffit-il ? » — c'est-à-dire, atteint-il la majorité
# qualifiée si nous portons le texte, ou la minorité de blocage si nous nous y
# opposons.
#
# C'est aussi ce qui hiérarchise le démarchage : à proximité égale, on va
# d'abord chercher l'État dont le ralliement fait franchir un seuil.

STATUT_ALLIE = "Allié"
STATUT_CONVAINCRE = "À convaincre"
STATUT_OPPOSE = "Opposé"
STATUT_MUET = "Ne s'est pas exprimé"


def negotiation_targets(matrix: pd.DataFrame,
                        articles: list[str] | None = None) -> pd.DataFrame:
    """Classe les États membres par utilité pour ouvrir une négociation.

    Sur le périmètre d'articles retenu : combien de fois chacun est aligné sur
    la position française, partiellement aligné, opposé — et ce que pèse son
    ralliement en population.

    Le statut est délibérément grossier (allié / à convaincre / opposé) : c'est
    une liste d'appels à passer, pas une note d'analyse. L'agent affine ensuite
    article par article.
    """
    if matrix.empty:
        return pd.DataFrame()
    sous = matrix.loc[articles] if articles else matrix
    pop = load_populations()

    lignes = []
    for code in sous.columns:
        colonne = sous[code].dropna()
        alignes = int((colonne == 2).sum())
        partiels = int((colonne == 1).sum())
        opposes = int((colonne == 0).sum())
        exprimes = alignes + partiels + opposes
        if exprimes == 0:
            statut, score = STATUT_MUET, float("nan")
        else:
            score = float(colonne.mean())
            if opposes > alignes:
                statut = STATUT_OPPOSE
            elif alignes >= max(1, exprimes / 2):
                statut = STATUT_ALLIE
            else:
                statut = STATUT_CONVAINCRE
        part = (float(pop.loc[code, "part"])
                if not pop.empty and code in pop.index else 0.0)
        lignes.append({
            "EM": code,
            "Statut": statut,
            "Score moyen": round(score, 2) if exprimes else None,
            "Articles alignés": alignes,
            "Alignements partiels": partiels,
            "Divergences": opposes,
            "Articles où il s'exprime": exprimes,
            "Part de population": round(part, 4),
        })

    ordre = {STATUT_ALLIE: 0, STATUT_CONVAINCRE: 1, STATUT_OPPOSE: 2,
             STATUT_MUET: 3}
    df = pd.DataFrame(lignes)
    return df.assign(_o=df["Statut"].map(ordre)).sort_values(
        ["_o", "Score moyen", "Part de population"],
        ascending=[True, False, False]).drop(columns="_o").reset_index(drop=True)


def coalition_report(membres: list[str]) -> dict:
    """Ce que pèse un groupe : États, population, seuils franchis.

    Renvoie un dictionnaire prêt à afficher, y compris quand les chiffres de
    population sont absents — auquel cas les parts valent zéro et les verdicts
    sont explicitement indisponibles.
    """
    pop = load_populations()
    connus = [m for m in membres if not pop.empty and m in pop.index]
    part = float(pop.loc[connus, "part"].sum()) if connus else 0.0
    return {
        "membres": sorted(membres),
        "n_etats": len(membres),
        "part_population": round(part, 4),
        "part_etats": round(len(membres) / EU_STATES, 4),
        "atteint_qmv": (len(membres) / EU_STATES >= QMV_STATES_THRESHOLD
                        and part >= QMV_POP_THRESHOLD),
        "bloque": is_blocking_minority(membres, pop),
        "population_disponible": not pop.empty,
        "manque_etats": max(0, int(round(QMV_STATES_THRESHOLD * EU_STATES))
                            - len(membres)),
        "manque_population": round(max(0.0, QMV_POP_THRESHOLD - part), 4),
    }


def best_additions(membres: list[str], candidats: list[str],
                   objectif: str = "qmv") -> pd.DataFrame:
    """Quel ralliement fait le plus avancer vers le seuil visé.

    `objectif` vaut « qmv » (nous portons le texte) ou « blocage » (nous nous
    y opposons). Le classement met en tête l'État qui apporte le plus de
    population, et signale celui dont le seul ralliement franchit le seuil.
    """
    pop = load_populations()
    if pop.empty:
        return pd.DataFrame()
    base = [m for m in membres if m in pop.index]
    lignes = []
    for code in candidats:
        if code in base or code not in pop.index:
            continue
        groupe = base + [code]
        rapport = coalition_report(groupe)
        lignes.append({
            "EM": code,
            "Nom": pop.loc[code, "nom"],
            "Apport de population": round(float(pop.loc[code, "part"]), 4),
            "Population du groupe": rapport["part_population"],
            "Franchit le seuil": (rapport["atteint_qmv"] if objectif == "qmv"
                                  else rapport["bloque"]),
        })
    if not lignes:
        return pd.DataFrame()
    return (pd.DataFrame(lignes)
            .sort_values(["Franchit le seuil", "Apport de population"],
                         ascending=[False, False]).reset_index(drop=True))
