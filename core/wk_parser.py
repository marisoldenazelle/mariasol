"""
Parser des documents WK du Conseil de l'UE (commentaires consolidés des États membres).

Format cible : tableau à deux colonnes réparti sur N pages
  - colonne gauche  : « Commission proposal » (texte de l'article / considérant)
  - colonne droite  : « Drafting suggestions and Comments », segmentée par
                      code pays sur deux lignes, ex. « FR\n(Comments): »

Le parsing est 100 % déterministe (pdfplumber + expressions régulières).
Aucun LLM n'intervient à ce stade : l'extraction structurelle doit être
reproductible et auditable.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import pdfplumber

# Codes ISO des 27 États membres + entités fréquemment citées dans les WK
MS_CODES = [
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "EL",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
]
MS_NAMES = {
    "AT": "Autriche", "BE": "Belgique", "BG": "Bulgarie", "HR": "Croatie",
    "CY": "Chypre", "CZ": "Tchéquie", "DK": "Danemark", "EE": "Estonie",
    "FI": "Finlande", "FR": "France", "DE": "Allemagne", "EL": "Grèce",
    "HU": "Hongrie", "IE": "Irlande", "IT": "Italie", "LV": "Lettonie",
    "LT": "Lituanie", "LU": "Luxembourg", "MT": "Malte", "NL": "Pays-Bas",
    "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie", "SK": "Slovaquie",
    "SI": "Slovénie", "ES": "Espagne", "SE": "Suède",
}

# « FR (Comments): » / « FR\n(Drafting suggestions): » / « FR (comments) »
_MS_MARKER = re.compile(
    r"(?:^|\n)\s*(?P<code>" + "|".join(MS_CODES) + r")\s*[\n ]\s*"
    r"\(\s*(?P<kind>Comments?|Drafting suggestions?|Comment|Drafting)\s*\)\s*:?",
    re.IGNORECASE,
)

# Titres de section dans la colonne de gauche
_ARTICLE_RE = re.compile(
    r"^\s*(?:Article|Art\.?)\s*(?P<num>\d+[a-z]?)\b", re.IGNORECASE
)
_RECITAL_RE = re.compile(r"^\s*(?:Recital|Considérant)s?\s*(?P<num>\d+[a-z]?)", re.IGNORECASE)
_GENERAL_RE = re.compile(r"^\s*General\s+Comments?", re.IGNORECASE)
_ANNEX_RE = re.compile(r"^\s*Annex\b", re.IGNORECASE)


@dataclass
class Contribution:
    """Une prise de position d'un État membre sur une section du texte."""

    document: str
    section_id: str          # ex. « art_71 », « rec_79 », « general »
    section_label: str       # ex. « Article 71 »
    section_kind: str        # article | recital | general | annex
    ms_code: str
    ms_name: str
    kind: str                # comments | drafting
    text: str
    page_start: int
    page_end: int
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Section:
    id: str
    label: str
    kind: str


def _classify_left_cell(cell: str) -> _Section | None:
    """Détermine si la cellule de gauche ouvre une nouvelle section."""
    if not cell:
        return None
    # On ne regarde que les premières lignes : le corps de l'article suit
    head = "\n".join(cell.strip().splitlines()[:3])

    if _GENERAL_RE.search(head):
        return _Section("general", "Commentaires généraux", "general")
    m = _ARTICLE_RE.search(head)
    if m:
        num = m.group("num").lower()
        return _Section(f"art_{num}", f"Article {m.group('num')}", "article")
    m = _RECITAL_RE.search(head)
    if m:
        num = m.group("num").lower()
        return _Section(f"rec_{num}", f"Considérant {m.group('num')}", "recital")
    if _ANNEX_RE.search(head):
        return _Section("annex", "Annexe", "annex")
    return None


def _normalise_kind(raw: str) -> str:
    return "drafting" if raw.lower().startswith("drafting") else "comments"


def _iter_table_rows(pdf_path: str | Path) -> Iterator[tuple[int, str, str]]:
    """Rend (numéro de page, cellule de gauche, cellule des contributions).

    Les documents WK existent en deux et en trois colonnes selon le stade de
    la négociation : « proposition de la Commission | commentaires » d'un côté,
    « proposition | texte de compromis de la présidence | commentaires » de
    l'autre. Dans les deux cas la première colonne porte le titre d'article et
    la **dernière** porte les contributions des États membres. On lit donc les
    extrémités, jamais la colonne d'indice 1 — sur un tableau à trois colonnes
    elle contient le texte de compromis, et les contributions étaient perdues.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.find_tables():
                for row in table.extract():
                    if not row or len(row) < 2:
                        continue
                    left = (row[0] or "").strip()
                    right = (row[-1] or "").strip()
                    # ligne d'en-tête, répétée à chaque page
                    if left.lower().startswith("commission proposal"):
                        continue
                    if not left and not right:
                        continue
                    yield page_no, left, right


def parse_wk_pdf(pdf_path: str | Path, document_name: str | None = None) -> list[Contribution]:
    """Extrait toutes les contributions d'un document WK consolidé."""
    pdf_path = Path(pdf_path)
    document = document_name or pdf_path.stem

    section = _Section("preamble", "Préambule", "general")
    current: dict | None = None          # contribution en cours de constitution
    out: list[Contribution] = []

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        text = re.sub(r"\n{3,}", "\n\n", current["text"]).strip()
        # « — » et cellules vides : pas de contribution réelle
        if text and text not in {"—", "-", "–"}:
            out.append(
                Contribution(
                    document=document,
                    section_id=current["section"].id,
                    section_label=current["section"].label,
                    section_kind=current["section"].kind,
                    ms_code=current["code"],
                    ms_name=MS_NAMES.get(current["code"], current["code"]),
                    kind=current["kind"],
                    text=text,
                    page_start=current["page_start"],
                    page_end=current["page_end"],
                )
            )
        current = None

    for page_no, left, right in _iter_table_rows(pdf_path):
        new_section = _classify_left_cell(left)
        if new_section and new_section.id != section.id:
            flush()
            section = new_section

        if not right:
            continue

        markers = list(_MS_MARKER.finditer(right))
        if not markers:
            # continuation du bloc précédent (débordement de page)
            if current is not None:
                current["text"] += "\n" + right
                current["page_end"] = page_no
            continue

        # texte précédant le premier marqueur : suite du bloc précédent
        head = right[: markers[0].start()].strip()
        if head and current is not None:
            current["text"] += "\n" + head
            current["page_end"] = page_no

        for i, m in enumerate(markers):
            flush()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(right)
            current = {
                "section": section,
                "code": m.group("code").upper(),
                "kind": _normalise_kind(m.group("kind")),
                "text": right[m.end():end].strip(),
                "page_start": page_no,
                "page_end": page_no,
            }

    flush()
    return out


def merge_contributions(contribs: list[Contribution]) -> list[Contribution]:
    """Fusionne les blocs consécutifs d'un même (section, EM, type)."""
    merged: list[Contribution] = []
    for c in contribs:
        if merged:
            p = merged[-1]
            if (p.section_id, p.ms_code, p.kind) == (c.section_id, c.ms_code, c.kind):
                p.text = f"{p.text}\n{c.text}".strip()
                p.page_end = c.page_end
                p.char_count = len(p.text)
                continue
        merged.append(c)
    return merged


if __name__ == "__main__":  # diagnostic rapide
    import sys, collections

    for path in sys.argv[1:]:
        rows = merge_contributions(parse_wk_pdf(path))
        print(f"\n=== {Path(path).name}: {len(rows)} contributions")
        by_ms = collections.Counter(r.ms_code for r in rows)
        print("EM :", dict(sorted(by_ms.items())))
        secs = []
        for r in rows:
            if r.section_label not in secs:
                secs.append(r.section_label)
        print("Sections :", secs)
