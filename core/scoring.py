"""
Qualification des positions des États membres par rapport à la position française.

Deux méthodes, explicitement tracées dans la base :
  - « llm »       : classement par le modèle sous schéma Pydantic contraint,
                    avec citation obligatoire du passage justifiant le verdict ;
  - « heuristique »: classement déterministe par marqueurs lexicaux, utilisé en
                    mode hors ligne et comme filet de sécurité.

Dans les deux cas le score final reste un entier de barème (2 / 1 / 0) et la
matrice d'alignement est calculée par le code, jamais par le modèle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .schemas import FrenchReference, PositionAnalysis, Stance

# Quand la France n'amende pas un article, elle en accepte le texte en l'état.
# C'est une position, pas une absence de position : elle sert donc de référence
# au même titre qu'un amendement écrit.
FR_SILENCE_REFERENCE = (
    "La France n'a déposé ni amendement ni commentaire sur cet article. "
    "Elle accepte donc le texte initial dans sa rédaction actuelle et "
    "ne demande aucune modification. La position française de référence est "
    "le maintien de l'article tel quel."
)

SILENCE_RULE = """
ATTENTION, cas particulier applicable ici : la position française de référence
est un STATU QUO (la France n'a pas amendé cet article, ce qui vaut acceptation
du texte en l'état). Applique alors le barème suivant :
- « aligne »  : l'État membre accepte l'article tel quel, ou ne demande qu'une
                correction de forme sans effet sur le fond.
- « partiel » : l'État membre soutient l'article mais demande une précision,
                une clarification, ou pose une condition limitée.
- « oppose »  : l'État membre demande la suppression de l'article, une
                réécriture de fond, ou pose une réserve d'examen sur son
                principe même, tout cela contredit le maintien en l'état.
- « neutre »  : l'État membre n'exprime AUCUNE demande, question de
                compréhension, remarque de procédure, renvoi à un autre
                article. Ni la France ni lui n'ont amendé la disposition :
                c'est une absence d'information, pas un alignement. Ne mets
                « aligne » que si l'État membre soutient EXPLICITEMENT le
                texte ou l'accepte en toutes lettres.
"""

SYSTEM_PROMPT = """Tu es un assistant d'analyse juridique au service d'une administration française.
Ta tâche est strictement délimitée : tu remplis un formulaire structuré à partir d'un texte source.

Règles impératives :
1. Tu ne juges jamais du fond du droit. Tu qualifies uniquement le degré de convergence
   entre la contribution d'un État membre et la position française de référence fournie.
2. Le champ « evidence » doit contenir une citation LITTÉRALE extraite du texte de la
   contribution, recopiée mot pour mot. N'invente jamais de citation.
3. Si le texte ne permet pas de trancher, utilise la position « neutre » avec une
   confiance basse plutôt que de deviner.
4. Le résumé est factuel, en français, sans commentaire ni recommandation.

Barème des positions :
- « aligne »  : la contribution converge nettement avec la demande française
                (même objectif, même mécanisme, ou soutien explicite).
- « partiel » : convergence sur l'objectif mais divergence sur les moyens, soutien
                assorti de conditions, ou accord limité à une partie de la demande.
- « oppose »  : la contribution contredit la demande française, ou défend la solution
                que la France cherche à écarter.
- « neutre »  : commentaire rédactionnel, question de clarification, ou sujet sans
                rapport avec la demande française.
"""

# --- heuristique déterministe ----------------------------------------------

_OPPOSE = [
    r"\bwe (?:do not|don't) support\b", r"\boppose[sd]?\b", r"\bcannot support\b",
    r"\bdisagree\b", r"\bwe object\b", r"\bstrongly against\b", r"\bnot in a position\b",
    r"\bshould be deleted\b", r"\bwe are against\b", r"\bno added value\b",
]
_ALIGNE = [
    r"\bwe support\b", r"\bfully support\b", r"\bwelcome[sd]?\b", r"\bagree\b",
    r"\bwe are in favour\b", r"\bstrongly support\b", r"\bappreciate\b",
    r"\bcan support\b", r"\bendorse\b",
]
_PARTIEL = [
    r"\bhowever\b", r"\bnevertheless\b", r"\bprovided that\b", r"\bsubject to\b",
    r"\bwould prefer\b", r"\bclarif", r"\bsuggest", r"\bwe propose\b",
]
_SCRUTINY = [r"scrutiny reservation", r"reserve d'examen", r"réserve d'examen",
             r"\bparliamentary reservation\b", r"\bexamination reservation\b"]
_DELETION = [
    r"\bdelet(?:e|ed|es|ing|ion)\b", r"\bshould be removed\b",
    r"\bbe deleted\b", r"\bsuppress", r"\bsupprim",
]


def _any(patterns: list[str], text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in patterns)


def heuristic_analysis(text: str, reference_kind: str = "explicite",
                       contribution_kind: str = "") -> PositionAnalysis:
    """Classement lexical déterministe — sans réseau, reproductible."""
    first = text.strip().split("\n")[0][:600] or text[:600]
    scrutiny = _any(_SCRUTINY, text)
    deletion = _any(_DELETION, text)

    if reference_kind == "silence":
        # Référence = maintien de l'article en l'état. Toute demande de
        # modification de fond s'en écarte mécaniquement.
        #
        # Un point mérite d'être explicite : l'alignement exige un soutien
        # EXPRIMÉ. Quand la France n'a pas amendé l'article et que l'État
        # membre n'en demande rien non plus, on ne sait rien de sa position —
        # c'est une absence d'information, pas un accord. La classer
        # « alignée » gonflerait artificiellement le camp français.
        if deletion or scrutiny or _any(_OPPOSE, text):
            stance, conf = Stance.OPPOSE, 0.45
        elif contribution_kind == "drafting" or _any(_PARTIEL, text):
            stance, conf = Stance.PARTIEL, 0.35
        elif _any(_ALIGNE, text):
            stance, conf = Stance.ALIGNE, 0.40
        else:
            stance, conf = Stance.NEUTRE, 0.25
        return PositionAnalysis(
            stance=stance,
            summary_fr=f"[Classement lexical, non validé] {first[:300]}",
            evidence=first, themes=[], is_scrutiny_reservation=scrutiny,
            proposes_deletion=deletion, confidence=conf,
        )

    if _any(_OPPOSE, text) or deletion:
        stance, conf = Stance.OPPOSE, 0.45
    elif _any(_ALIGNE, text) and _any(_PARTIEL, text):
        stance, conf = Stance.PARTIEL, 0.40
    elif _any(_ALIGNE, text):
        stance, conf = Stance.ALIGNE, 0.45
    elif _any(_PARTIEL, text):
        stance, conf = Stance.PARTIEL, 0.35
    else:
        stance, conf = Stance.NEUTRE, 0.25

    if scrutiny and stance is Stance.ALIGNE:
        stance, conf = Stance.PARTIEL, 0.35

    return PositionAnalysis(
        stance=stance,
        summary_fr=f"[Classement lexical, non validé] {first[:300]}",
        evidence=first,
        themes=[],
        is_scrutiny_reservation=scrutiny,
        proposes_deletion=deletion,
        confidence=conf,
    )


# --- analyse par LLM contraint ---------------------------------------------

def llm_analysis(ms_code: str, section_label: str, fr_reference: str,
                 contribution: str, reference_kind: str = "explicite") -> PositionAnalysis:
    client = get_client()
    system = SYSTEM_PROMPT + (SILENCE_RULE if reference_kind == "silence" else "")
    user = f"""Article examiné : {section_label}

POSITION FRANÇAISE DE RÉFÉRENCE :
\"\"\"{fr_reference.strip()[:3000]}\"\"\"

CONTRIBUTION DE L'ÉTAT MEMBRE {ms_code} :
\"\"\"{contribution.strip()[:6000]}\"\"\"

Qualifie la position de {ms_code} par rapport à la position française."""
    return client.structured(PositionAnalysis, system, user, max_tokens=900)


def verify_evidence(analysis: PositionAnalysis, source: str,
                    min_ratio: float = 0.6) -> bool:
    """Vérifie que la citation produite existe réellement dans le texte source.

    Garde-fou anti-hallucination : une analyse dont la citation est introuvable
    est dégradée (confiance nulle) plutôt que retenue telle quelle.
    """
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower()).strip()

    src, ev = norm(source), norm(analysis.evidence)
    if not ev:
        return False
    if ev in src:
        return True
    words = [w for w in ev.split() if len(w) > 3]
    if not words:
        return False
    hits = sum(1 for w in words if w in src)
    return hits / len(words) >= min_ratio


# --- position française de référence ---------------------------------------

FR_SYSTEM = """Tu synthétises la position de la France sur un article d'un texte européen,
à partir de ses contributions écrites. Tu restes strictement factuel, en français,
sans ajouter d'analyse ni de recommandation. Tu listes les demandes françaises
concrètes (« key_asks ») telles qu'elles figurent dans le texte."""


def derive_fr_reference(section_id: str, section_label: str,
                        fr_texts: list[str]) -> FrenchReference:
    joined = "\n\n---\n\n".join(t.strip() for t in fr_texts if t.strip())
    if not joined:
        return FrenchReference(section_id=section_id, summary_fr="Pas de contribution française.",
                               key_asks=[], confidence=0.0)
    if not get_client().available:
        return FrenchReference(
            section_id=section_id,
            summary_fr=joined[:600],
            key_asks=[],
            confidence=0.2,
        )
    user = (f"Article : {section_label}\n\nContributions françaises :\n\"\"\"{joined[:8000]}\"\"\"")
    ref = get_client().structured(FrenchReference, FR_SYSTEM, user, max_tokens=700)
    return ref.model_copy(update={"section_id": section_id})


# --- traitement par lot -----------------------------------------------------

@dataclass
class BatchResult:
    analysed: int = 0
    llm_ok: int = 0
    fallback: int = 0
    evidence_failed: int = 0
    errors: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def analyse_batch(
    rows: Iterable[dict],
    fr_reference_by_section: dict[str, str],
    use_llm: bool = True,
    on_progress: Callable[[int, int, str], None] | None = None,
    save: Callable[[int, PositionAnalysis, str, str], None] | None = None,
    reference_kind_by_section: dict[str, str] | None = None,
) -> BatchResult:
    """Analyse une liste de contributions et persiste les résultats.

    Les articles sans référence française explicite sont traités avec la
    référence de silence : ne pas amender vaut acceptation du texte.
    """
    rows = list(rows)
    res = BatchResult()
    client = get_client()
    active_llm = use_llm and client.available
    kinds = reference_kind_by_section or {}

    for i, row in enumerate(rows, start=1):
        if on_progress:
            on_progress(i, len(rows), f"{row['ms_code']} · {row['section_label']}")

        sid = row["section_id"]
        ref = fr_reference_by_section.get(sid) or FR_SILENCE_REFERENCE
        ref_kind = kinds.get(sid) or (
            "explicite" if fr_reference_by_section.get(sid) else "silence")
        analysis, method = None, f"heuristique ({ref_kind})"

        if active_llm and ref:
            try:
                analysis = llm_analysis(row["ms_code"], row["section_label"],
                                        ref, row["text"], reference_kind=ref_kind)
                method = f"llm ({ref_kind})"
                if not verify_evidence(analysis, row["text"]):
                    res.evidence_failed += 1
                    analysis = analysis.model_copy(update={"confidence": 0.0})
                    method = "llm (citation non vérifiée)"
                res.llm_ok += 1
            except (LLMUnavailable, LLMInvalidOutput) as exc:
                res.errors.append(f"{row['ms_code']} {row['section_label']}: {exc}")

        if analysis is None:
            analysis = heuristic_analysis(
                row["text"], reference_kind=ref_kind,
                contribution_kind=row.get("kind", ""))
            res.fallback += 1

        if save:
            save(int(row["id"]), analysis, method,
                 client.model if method.startswith("llm") else "-")
        res.analysed += 1

    return res


def ally_ranking(matrix: pd.DataFrame) -> pd.DataFrame:
    """Classement des EM par proximité moyenne avec la position française."""
    if matrix.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "Score moyen": matrix.mean(axis=0).round(2),
        "Articles analysés": matrix.notna().sum(axis=0),
        "Alignements": (matrix == 2).sum(axis=0),
        "Partiels": (matrix == 1).sum(axis=0),
        "Oppositions": (matrix == 0).sum(axis=0),
    })
    out.index.name = "EM"
    return out.sort_values("Score moyen", ascending=False)


def contentious_articles(matrix: pd.DataFrame) -> pd.DataFrame:
    """Articles les plus clivants : score moyen bas et/ou forte dispersion."""
    if matrix.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "Score moyen": matrix.mean(axis=1).round(2),
        "Dispersion": matrix.std(axis=1).round(2),
        "EM analysés": matrix.notna().sum(axis=1),
        "Oppositions": (matrix == 0).sum(axis=1),
    })
    out.index.name = "Article"
    return out.sort_values(["Score moyen", "Dispersion"], ascending=[True, False])


def ecart_au_texte(text: str, contribution_kind: str = "") -> int | None:
    """Écart d'une contribution au texte initial, sans appeler le modèle.

    Applique la règle du silence au texte lui-même : accepter la disposition
    vaut alignement (2), demander une précision vaut alignement partiel (1),
    en demander la suppression ou la réécriture vaut écart (0). Une
    contribution qui n'exprime aucune demande ne compte pas — elle renvoie
    None et laisse la case vide, plutôt que de gonfler un camp ou l'autre.

    Ce calcul est déterministe : deux exécutions donnent le même résultat, et
    un agent peut le refaire à la main sur un cas pour le contester.
    """
    if not (text or "").strip():
        return None
    return heuristic_analysis(text, reference_kind="silence",
                              contribution_kind=contribution_kind or "").score
