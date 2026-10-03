"""
Recherche dans le corpus — index plein texte SQLite FTS5.

Choix assumé : pas d'embeddings, pas de base vectorielle. Trois raisons.

1. Souveraineté : l'index reste un fichier local, aucun texte ne sort pour être
   vectorisé. Sur des documents LIMITE c'est la propriété qui compte le plus.
2. Auditabilité : un résultat de recherche lexicale s'explique — on voit quel
   terme a déclenché la remontée. Une similarité cosinus ne s'explique pas.
3. Le corpus est juridique : les agents cherchent des termes exacts
   (« cyber posture », « art. 100 », « scrutiny reservation »), cas où le
   lexical est au moins aussi bon que le vectoriel.

Le point d'extension est prévu : `rerank()` peut appeler un service de
reclassement si l'endpoint en expose un, sans changer le reste de la chaîne.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from .store import connect

# Index autonome, sans « external content » ni déclencheurs.
#
# La première version utilisait un index FTS5 adossé à la table `segments`
# (`content='segments'`) avec des déclencheurs. C'était plus économe en place,
# et c'était fragile : une commande de suppression émise deux fois pour la même
# ligne — une par le code, une par le déclencheur — corrompt l'index de façon
# irréversible (« database disk image is malformed »), ce qui s'est produit au
# ré-import d'un document déjà présent.
#
# Ici l'index porte sa propre copie du texte et se remplit explicitement. Il
# coûte un peu de place, il se reconstruit en une commande, et rien ne peut le
# désynchroniser silencieusement. Pour un outil qui manipule les seuls
# exemplaires de travail d'un agent, la robustesse prime sur la place disque.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts USING fts5(
    segment_id UNINDEXED,
    label,
    text,
    tokenize="unicode61 remove_diacritics 2"
);
"""

# Mots vides écartés de la requête : ils feraient remonter tout le corpus.
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "que", "qui",
    "quoi", "dont", "pour", "par", "sur", "dans", "avec", "sans", "est", "sont",
    "quel", "quelle", "quels", "quelles", "ce", "cet", "cette", "ces", "au",
    "aux", "en", "il", "elle", "ils", "elles", "on", "se", "sa", "son", "ses",
    "leur", "leurs", "a", "à", "the", "of", "and", "or", "to", "in", "on", "for",
    "is", "are", "what", "which", "how", "does", "do", "be", "by", "with", "as",
    "that", "this", "it", "at", "from",
}


@dataclass
class Hit:
    segment_id: int
    document_id: int
    document_name: str
    section_label: str
    ms_code: str
    page_start: int
    page_end: int
    text: str
    score: float
    snippet: str = ""

    @property
    def citation(self) -> str:
        who = f"{self.ms_code} · " if self.ms_code else ""
        pages = (f"p. {self.page_start}"
                 if self.page_start == self.page_end
                 else f"p. {self.page_start}-{self.page_end}")
        return f"{who}{self.document_name}, {self.section_label}, {pages}"


# Colonnes attendues dans l'index. Sert au contrôle de migration ci-dessous.
FTS_COLUMNS = ("segment_id", "label", "text")


def _index_est_obsolete(con) -> bool:
    """L'index existant a-t-il l'ancienne structure, sans l'intitulé ?"""
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='segment_fts'"
    ).fetchone()
    if not exists:
        return False
    cols = {r[1] for r in con.execute("PRAGMA table_info(segment_fts)")}
    return not set(FTS_COLUMNS).issubset(cols)


def ensure_index() -> None:
    """Crée l'index si besoin, et migre celui des versions antérieures.

    L'intitulé de section a été ajouté à l'index après coup. Une base créée
    avant cet ajout a une table à deux colonnes : y insérer trois valeurs
    échoue. On la reconstruit à partir des segments, qui sont la source.
    """
    with connect() as con:
        if _index_est_obsolete(con):
            con.execute("DROP TABLE IF EXISTS segment_fts")
            con.executescript(FTS_SCHEMA)
            rows = con.execute(
                "SELECT id, section_label, text FROM segments").fetchall()
            if rows:
                con.executemany(
                    "INSERT INTO segment_fts(segment_id, label, text) "
                    "VALUES (?, ?, ?)",
                    [(r[0], r[1] or "", r[2]) for r in rows])
        else:
            con.executescript(FTS_SCHEMA)
        # Nettoyage des installations antérieures : les déclencheurs de la
        # première version doivent disparaître, sinon ils réintroduisent la
        # corruption sur une base existante.
        for trigger in ("segments_ai", "segments_ad", "segments_au"):
            con.execute(f"DROP TRIGGER IF EXISTS {trigger}")


def index_segments(con, rows: list[tuple[int, str, str]]) -> None:
    """Ajoute des segments à l'index. `rows` = [(segment_id, intitulé, texte), …].

    L'intitulé de section est indexé au même titre que le texte : sans lui,
    « article 90 » ne trouve rien, parce que le numéro d'article vit dans le
    libellé de la section et non dans le corps de la contribution.
    """
    con.executemany(
        "INSERT INTO segment_fts(segment_id, label, text) VALUES (?, ?, ?)", rows)


def unindex_document(con, doc_id: str) -> None:
    """Retire de l'index tous les segments d'un document."""
    con.execute(
        "DELETE FROM segment_fts WHERE segment_id IN "
        "(SELECT id FROM segments WHERE document_id = ?)", (doc_id,))


def rebuild_index() -> int:
    """Reconstruit l'index de zéro à partir de la table `segments`.

    C'est aussi la procédure de réparation : elle repart des données, jamais
    de l'index lui-même.
    """
    with connect() as con:
        con.executescript(FTS_SCHEMA)
        for trigger in ("segments_ai", "segments_ad", "segments_au"):
            con.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        con.execute("DELETE FROM segment_fts")
        rows = con.execute(
            "SELECT id, section_label, text FROM segments").fetchall()
        index_segments(con, [(r[0], r[1] or "", r[2]) for r in rows])
        return len(rows)


# « article 90 », « art. 5 », « l'article 100 »
# La borne finale évite de happer la première lettre du mot suivant :
# « article 17 et … » ne doit pas donner « 17 e ».
_NUMERO_ARTICLE = re.compile(
    r"\bart(?:icle)?\.?\s*(\d+(?:\s*(?:bis|ter|quater))?)\b", re.IGNORECASE)


def articles_cites(question: str) -> list[str]:
    """Numéros d'article explicitement nommés dans la question."""
    return [m.group(1).strip().lower() for m in _NUMERO_ARTICLE.finditer(question)]


def _normalise(term: str) -> str:
    term = unicodedata.normalize("NFKD", term)
    return "".join(c for c in term if not unicodedata.combining(c))


def build_query(question: str) -> str:
    """Transforme une question en expression FTS5.

    Les groupes entre guillemets sont conservés comme expressions exactes ;
    le reste devient une liste de termes en OR, préfixés pour attraper les
    variantes morphologiques.
    """
    phrases = re.findall(r'"([^"]+)"', question)
    rest = re.sub(r'"[^"]+"', " ", question)

    terms = []
    for raw in re.findall(r"[\w'-]+", rest, flags=re.UNICODE):
        word = _normalise(raw.lower().strip("'-"))
        # Un nombre est toujours signifiant ici — « article 90 », « art. 5 » —
        # et se cherche à l'identique, sans troncature qui ferait remonter 900.
        if word.isdigit():
            terms.append(f'"{word}"')
            continue
        if len(word) < 3 or word in STOPWORDS:
            continue
        terms.append(f'"{word}"*' if word.isalnum() else f'"{word}"')

    parts = [f'"{_normalise(p)}"' for p in phrases] + terms
    return " OR ".join(dict.fromkeys(parts)) if parts else ""


def search(
    question: str,
    limit: int = 12,
    document_ids: list[str] | None = None,
    ms_codes: list[str] | None = None,
    doc_kinds: list[str] | None = None,
    requete_brute: str | None = None,
) -> list[Hit]:
    """Recherche plein texte, classée par BM25.

    `requete_brute` permet de passer une expression FTS déjà construite —
    typiquement enrichie des équivalents anglais des termes de la question.
    """
    query = requete_brute or build_query(question)
    if not query:
        return []

    ensure_index()
    sql = """
        SELECT s.id, s.document_id, d.name AS doc_name, d.kind AS doc_kind,
               s.section_label, s.ms_code, s.page_start, s.page_end, s.text,
               bm25(segment_fts) AS rank,
               -- colonne 2 = « text » (0 = segment_id, 1 = label). Viser la
               -- mauvaise colonne affiche l'identifiant ou l'intitulé à la
               -- place de l'extrait.
               snippet(segment_fts, 2, '«', '»', ' … ', 24) AS snip
        FROM segment_fts
        JOIN segments  s ON s.id = segment_fts.segment_id
        JOIN documents d ON d.id = s.document_id
        WHERE segment_fts MATCH ?
    """
    params: list = [query]
    if document_ids:
        sql += f" AND s.document_id IN ({','.join('?' * len(document_ids))})"
        params += document_ids
    if ms_codes:
        sql += f" AND s.ms_code IN ({','.join('?' * len(ms_codes))})"
        params += ms_codes
    if doc_kinds:
        sql += f" AND d.kind IN ({','.join('?' * len(doc_kinds))})"
        params += doc_kinds
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    with connect() as con:
        try:
            rows = con.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    hits = [
        Hit(
            segment_id=r["id"], document_id=r["document_id"],
            document_name=r["doc_name"], section_label=r["section_label"],
            ms_code=r["ms_code"] or "", page_start=r["page_start"],
            page_end=r["page_end"], text=r["text"],
            score=-float(r["rank"]), snippet=r["snip"] or "",
        )
        for r in rows
    ]

    # Quand la question nomme un article, ses segments passent devant. Sans
    # cela « que disent les États membres sur l'article 90 ? » remonte des
    # contributions sur d'autres articles, simplement parce qu'elles
    # contiennent le mot « article ».
    cites = articles_cites(question)
    if cites:
        def vise(h: Hit) -> bool:
            label = h.section_label.lower().replace("article", "").strip()
            return any(label.startswith(n) for n in cites)

        hits.sort(key=lambda h: (not vise(h), -h.score))
    return hits


def by_section(section_id: str, document_ids: list[str] | None = None) -> list[Hit]:
    """Tous les segments d'une section — utilisé par les fiches par article."""
    sql = """
        SELECT s.id, s.document_id, d.name AS doc_name, s.section_label,
               s.ms_code, s.page_start, s.page_end, s.text
        FROM segments s JOIN documents d ON d.id = s.document_id
        WHERE s.section_id = ?
    """
    params: list = [section_id]
    if document_ids:
        sql += f" AND s.document_id IN ({','.join('?' * len(document_ids))})"
        params += document_ids
    sql += " ORDER BY s.ms_code, s.id"
    with connect() as con:
        rows = con.execute(sql, params).fetchall()
    return [
        Hit(segment_id=r["id"], document_id=r["document_id"],
            document_name=r["doc_name"], section_label=r["section_label"],
            ms_code=r["ms_code"] or "", page_start=r["page_start"],
            page_end=r["page_end"], text=r["text"], score=0.0)
        for r in rows
    ]
