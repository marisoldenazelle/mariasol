"""
Comparaison de deux versions d'un même texte.

L'appariement des articles et le calcul des écarts sont déterministes
(`difflib`). Le modèle n'intervient qu'ensuite, pour qualifier la portée d'un
écart déjà constaté — jamais pour dire s'il y a eu un changement.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import pandas as pd

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .schemas import DeltaAnalysis

CHANGE_LABEL = {
    "ajout": "Article ajouté",
    "suppression": "Article supprimé",
    "reformulation": "Article modifié",
    "inchange": "Inchangé",
}
IMPACT_ORDER = ["majeur", "mineur", "redactionnel", "nul"]


@dataclass
class ArticleDelta:
    section_id: str
    section_label: str
    status: str                     # ajout | suppression | reformulation | inchange
    similarity: float               # 0 à 1
    words_added: int = 0
    words_removed: int = 0
    old_text: str = ""
    new_text: str = ""
    inline_html: str = ""
    impact: str = ""                # renseigné par la qualification LLM
    summary_fr: str = ""
    concepts: list[str] = field(default_factory=list)

    @property
    def churn(self) -> int:
        return self.words_added + self.words_removed


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", re.sub(r"\s+", " ", text or "").strip())


# Plafond du rendu mot à mot. Il était à 900 mots, ce qui coupait la fin d'un
# article long : sur l'article premier du Data Act, les paragraphes ajoutés par
# l'omnibus arrivent après le millier de mots, et l'écran n'affichait donc
# aucune modification — le pire résultat possible, puisqu'il ressemble à un
# résultat. Le plafond est relevé au-delà de tout article réel, et sa coupure,
# quand elle survient, est écrite à l'écran.
PLAFOND_MOTS = 4000


def _inline_diff(old: str, new: str, max_words: int | None = PLAFOND_MOTS,
                 contexte: int = 0) -> str:
    """Rendu HTML mot à mot : ajouts soulignés, suppressions barrées.

    Les couleurs suivent la palette active : le retrait prend la teinte de
    l'opposition, l'ajout celle de l'alignement — bleu France dans la palette
    accessible, vert dans la convention des notes de la direction. Le
    soulignement et la barre doublent la couleur, pour qu'une impression en
    noir et blanc garde son sens.

    `max_words` plafonne le nombre de mots comparés. Le plafond protège
    l'affichage sur un article démesuré, mais il **coupe la fin du texte** :
    une modification portant au-delà du plafond disparaît de l'écran sans que
    rien ne le dise. Passer `None` compare tout ; `ecart_hors_champ()` dit si
    un plafond donné amputerait le texte.

    `contexte` ne garde, autour de chaque passage modifié, que ce nombre de
    mots inchangés, et remplace le reste par une élision. Sur l'article
    premier du Data Act — dix mille mots dont trois passages changent — c'est
    la différence entre un mur de texte et une lecture.
    """
    from .palette import couleurs

    pal = couleurs()
    retrait, ajout = pal["oppose"], pal["aligne"]
    a, b = _words(old), _words(new)
    coupe = max_words is not None and (len(a) > max_words or len(b) > max_words)
    if max_words is not None:
        a, b = a[:max_words], b[:max_words]
    ELISION = ("<span style='color:#898781'> […] </span>")

    opcodes = list(difflib.SequenceMatcher(None, a, b).get_opcodes())
    out: list[str] = []
    for rang, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            mots = a[i1:i2]
            # Un passage inchangé n'est raccourci que s'il est nettement plus
            # long que le contexte demandé : élider six mots pour en montrer
            # cinq de chaque côté n'aide personne.
            if contexte and len(mots) > 2 * contexte + 12:
                debut = [] if rang == 0 else mots[:contexte]
                fin = [] if rang == len(opcodes) - 1 else mots[-contexte:]
                out.append(" ".join(debut) + ELISION + " ".join(fin))
            else:
                out.append(" ".join(mots))
        elif tag == "delete":
            out.append(f"<del style='color:{retrait}'>{' '.join(a[i1:i2])}</del>")
        elif tag == "insert":
            out.append(f"<ins style='color:{ajout};text-decoration:underline'>"
                       f"{' '.join(b[j1:j2])}</ins>")
        else:
            out.append(f"<del style='color:{retrait}'>{' '.join(a[i1:i2])}</del> "
                       f"<ins style='color:{ajout};text-decoration:underline'>"
                       f"{' '.join(b[j1:j2])}</ins>")
    if coupe:
        out.append(
            f"<div style='color:#b34000;font-size:0.85rem;margin-top:0.6rem'>"
            f"[Rendu arrêté à {max_words} mots. La suite de l'article n'est "
            f"pas comparée ici : ouvrez-la dans « Article par article ».]</div>")
    return " ".join(out)


def ecart_hors_champ(avant: str, apres: str, plafond: int) -> bool:
    """Un plafond de `plafond` mots couperait-il une partie de ces textes ?"""
    return max(len(_words(avant)), len(_words(apres))) > plafond


def ecart_mots(avant: str, apres: str) -> tuple[int, int]:
    """Mots ajoutés et mots retirés entre deux textes.

    Sert à dire, en une ligne, si le rendu mot à mot montre quelque chose :
    « aucun mot ajouté ni retiré » est une information, un écran gris ne
    l'est pas.
    """
    a, b = _words(avant), _words(apres)
    sm = difflib.SequenceMatcher(None, a, b)
    ajoutes = sum(j2 - j1 for tag, _, _, j1, j2 in sm.get_opcodes()
                  if tag in ("insert", "replace"))
    retires = sum(i2 - i1 for tag, i1, i2, _, _ in sm.get_opcodes()
                  if tag in ("delete", "replace"))
    return ajoutes, retires


# Un article de plus de 2 500 caractères est scindé à l'import en `art_5_1`,
# `art_5_2`… (voir `ingest._subdiviser_articles`). Comparer ces morceaux tels
# quels donnait le pire résultat possible : un article simplement enrichi d'une
# version à l'autre apparaissait comme « art_5 supprimé » plus « art_5_1 et
# art_5_2 ajoutés », sans différence mot à mot — c'est-à-dire exactement le
# contraire de ce que la page est censée montrer. On recolle donc les
# fragments avant d'apparier, comme le fait déjà le suivi des amendements.
_FRAGMENT = re.compile(r"^(?P<racine>[a-z]+_\d+[a-z]?)_(?P<rang>\d+)$")


def _recoller_fragments(segments: pd.DataFrame) -> dict:
    """Sections d'un document, fragments d'un même article réunis."""
    entier: dict[str, dict] = {}
    if segments is None or segments.empty:
        return entier
    for _, row in segments.iterrows():
        sid = str(row.get("section_id") or "")
        m = _FRAGMENT.match(sid)
        racine = m.group("racine") if m else sid
        rang = int(m.group("rang")) if m else 0
        bloc = entier.setdefault(
            racine, {"section_label": "", "morceaux": []})
        # L'intitulé retenu est celui du premier morceau, débarrassé de la
        # mention « (2/4) » que le découpage y avait ajoutée.
        if not bloc["section_label"] or rang <= 1:
            bloc["section_label"] = re.sub(
                r"\s*\(\d+/\d+\)\s*$", "",
                str(row.get("section_label") or racine)).strip()
        bloc["morceaux"].append((rang, str(row.get("text") or "")))
    return {
        sid: {"section_label": bloc["section_label"],
              "text": "\n".join(texte for _, texte
                                in sorted(bloc["morceaux"], key=lambda x: x[0]))}
        for sid, bloc in entier.items()
    }


def rendu_mot_a_mot(avant: str, apres: str, max_mots: int | None = 900,
                    contexte: int = 0) -> str:
    """Diff mot à mot en HTML — la même fonction que pour les versions.

    Publique parce que la lecture d'un acte modificatif s'en sert : le texte
    d'un article avant et après l'omnibus se lit exactement comme deux
    versions successives.
    """
    return _inline_diff(avant, apres, max_words=max_mots, contexte=contexte)


def compare(old_segments: pd.DataFrame, new_segments: pd.DataFrame,
            threshold: float = 0.995) -> list[ArticleDelta]:
    """Apparie les articles des deux versions par identifiant de section."""
    old = _recoller_fragments(old_segments)
    new = _recoller_fragments(new_segments)

    def sort_key(sid: str) -> tuple:
        m = re.search(r"(\d+)([a-z]?)", sid)
        return (int(m.group(1)) if m else 9999, m.group(2) if m else "")

    deltas: list[ArticleDelta] = []
    for sid in sorted(set(old) | set(new), key=sort_key):
        o, n = old.get(sid), new.get(sid)
        label = (n if n is not None else o)["section_label"]
        o_text = (o["text"] if o is not None else "") or ""
        n_text = (n["text"] if n is not None else "") or ""

        if o is None:
            status, sim = "ajout", 0.0
        elif n is None:
            status, sim = "suppression", 0.0
        else:
            sim = difflib.SequenceMatcher(None, _words(o_text), _words(n_text)).ratio()
            status = "inchange" if sim >= threshold else "reformulation"

        a, b = _words(o_text), _words(n_text)
        sm = difflib.SequenceMatcher(None, a, b)
        added = sum(j2 - j1 for tag, _, _, j1, j2 in sm.get_opcodes()
                    if tag in ("insert", "replace"))
        removed = sum(i2 - i1 for tag, i1, i2, _, _ in sm.get_opcodes()
                      if tag in ("delete", "replace"))

        deltas.append(ArticleDelta(
            section_id=sid, section_label=label, status=status,
            similarity=round(sim, 4), words_added=added, words_removed=removed,
            old_text=o_text, new_text=n_text,
            inline_html=_inline_diff(o_text, n_text) if status == "reformulation" else "",
        ))
    return deltas


QUALIF_SYSTEM = """Tu qualifies la portée d'une modification apportée à un article
d'un texte réglementaire européen. La modification t'est donnée : tu ne dis pas
s'il y a eu changement, tu dis ce qu'il change.

Règles :
1. « majeur » : le changement modifie une obligation, un champ d'application,
   un seuil, une compétence ou un délai.
2. « mineur » : le changement précise ou encadre sans déplacer l'équilibre.
3. « redactionnel » : formulation, terminologie, renvoi, sans effet de fond.
4. Tu restes factuel, en français, sans recommandation."""


def qualify(delta: ArticleDelta) -> ArticleDelta:
    """Fait qualifier un écart déjà constaté. Sans LLM, renvoie l'écart tel quel."""
    if delta.status == "inchange":
        delta.impact, delta.summary_fr = "nul", "Aucun changement."
        return delta
    client = get_client()
    if not client.available:
        return delta

    user = (
        f"Article : {delta.section_label}\n\n"
        f"VERSION ANTÉRIEURE :\n\"\"\"{delta.old_text[:4000] or '(absent)'}\"\"\"\n\n"
        f"VERSION NOUVELLE :\n\"\"\"{delta.new_text[:4000] or '(supprimé)'}\"\"\"\n\n"
        "Qualifie la portée de la modification."
    )
    try:
        out = client.structured(DeltaAnalysis, QUALIF_SYSTEM, user, max_tokens=700)
    except (LLMUnavailable, LLMInvalidOutput):
        return delta
    delta.impact = out.impact
    delta.summary_fr = out.summary_fr
    delta.concepts = list(out.affected_concepts)
    return delta


def summary_table(deltas: list[ArticleDelta]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Article": d.section_label,
            "Statut": CHANGE_LABEL.get(d.status, d.status),
            "Similarité": d.similarity,
            "Mots ajoutés": d.words_added,
            "Mots retirés": d.words_removed,
            "Impact": d.impact or "—",
            "Résumé": d.summary_fr or "",
        }
        for d in deltas
    ])


# ---------------------------------------------------------------------------
# Suivi d'un article à travers toutes les versions
# ---------------------------------------------------------------------------
#
# Comparer deux versions répond à « qu'est-ce qui a changé la dernière fois ? ».
# Sur un omnibus, la question posée est autre : « comment cet article a-t-il
# évolué depuis la proposition de la Commission ? ». Il faut alors la suite
# complète — proposition, compromis 1, compromis 2 — et non un couple.

@dataclass
class Etape:
    document_id: str
    document_name: str
    version_kind: str = ""
    version_date: str = ""
    texte: str = ""
    present: bool = True
    similarite: float | None = None      # avec l'étape précédente
    mots_ajoutes: int = 0
    mots_retires: int = 0
    inline_html: str = ""

    @property
    def churn(self) -> int:
        return self.mots_ajoutes + self.mots_retires


def evolution_article(versions: list[dict], section_id: str) -> list[Etape]:
    """Suit un article à travers une suite ordonnée de versions.

    `versions` est une liste de dictionnaires ordonnés du plus ancien au plus
    récent, chacun portant au minimum `id`, `name` et un tableau de segments
    (`segments`, avec les colonnes `section_id` et `text`).

    Un article absent d'une version n'est pas une erreur : c'est une
    information — il a été supprimé, ou il n'existait pas encore.
    """
    etapes: list[Etape] = []
    precedent = ""
    for v in versions:
        segments = v.get("segments")
        texte = ""
        if segments is not None and not segments.empty:
            lignes = segments[segments["section_id"] == section_id]
            texte = "\n".join(str(t) for t in lignes["text"]) if not lignes.empty else ""

        etape = Etape(
            document_id=str(v.get("id", "")),
            document_name=str(v.get("name", "")),
            version_kind=str(v.get("version_kind") or ""),
            version_date=str(v.get("version_date") or ""),
            texte=texte, present=bool(texte.strip()),
        )
        if etapes and (texte.strip() or precedent.strip()):
            a, b = _words(precedent), _words(texte)
            sm = difflib.SequenceMatcher(None, a, b)
            etape.similarite = round(sm.ratio(), 4)
            etape.mots_ajoutes = sum(j2 - j1 for tag, _, _, j1, j2
                                     in sm.get_opcodes()
                                     if tag in ("insert", "replace"))
            etape.mots_retires = sum(i2 - i1 for tag, i1, i2, _, _
                                     in sm.get_opcodes()
                                     if tag in ("delete", "replace"))
            if etape.similarite < 0.995:
                etape.inline_html = _inline_diff(precedent, texte)
        etapes.append(etape)
        precedent = texte
    return etapes
