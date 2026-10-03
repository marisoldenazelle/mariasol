"""Persistance SQLite : corpus, contributions, analyses, positions de référence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from .config import settings
from .wk_parser import Contribution

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    dossier       TEXT,
    sha256        TEXT,
    imported_at   TEXT,
    n_contributions INTEGER,
    meta          TEXT
);

-- Unité indexable commune à tous les types de documents. Les contributions
-- d'États membres y figurent aussi : un seul index couvre tout le corpus.
CREATE TABLE IF NOT EXISTS segments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   TEXT NOT NULL,
    section_id    TEXT NOT NULL,
    section_label TEXT NOT NULL,
    section_kind  TEXT NOT NULL,
    section_order INTEGER,
    ms_code       TEXT,
    contribution_kind TEXT,
    text          TEXT NOT NULL,
    page_start    INTEGER,
    page_end      INTEGER,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);
CREATE INDEX IF NOT EXISTS idx_seg_doc ON segments(document_id);
CREATE INDEX IF NOT EXISTS idx_seg_sec ON segments(document_id, section_id);

CREATE TABLE IF NOT EXISTS contributions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   TEXT NOT NULL,
    section_id    TEXT NOT NULL,
    section_label TEXT NOT NULL,
    section_kind  TEXT NOT NULL,
    section_order INTEGER,
    ms_code       TEXT NOT NULL,
    ms_name       TEXT,
    kind          TEXT NOT NULL,
    text          TEXT NOT NULL,
    page_start    INTEGER,
    page_end      INTEGER,
    char_count    INTEGER,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);
CREATE INDEX IF NOT EXISTS idx_contrib_doc ON contributions(document_id);
CREATE INDEX IF NOT EXISTS idx_contrib_sec ON contributions(document_id, section_id);
CREATE INDEX IF NOT EXISTS idx_contrib_ms  ON contributions(document_id, ms_code);

CREATE TABLE IF NOT EXISTS analyses (
    contribution_id INTEGER PRIMARY KEY,
    stance          TEXT,
    score           INTEGER,
    summary_fr      TEXT,
    evidence        TEXT,
    themes          TEXT,
    scrutiny        INTEGER,
    deletion        INTEGER,
    confidence      REAL,
    method          TEXT,
    model           TEXT,
    analysed_at     TEXT,
    FOREIGN KEY (contribution_id) REFERENCES contributions(id)
);

CREATE TABLE IF NOT EXISTS fr_reference (
    document_id  TEXT NOT NULL,
    section_id   TEXT NOT NULL,
    summary_fr   TEXT,
    key_asks     TEXT,
    source       TEXT,
    updated_at   TEXT,
    PRIMARY KEY (document_id, section_id)
);
"""


@contextmanager
def connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_path or settings.db_path, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Version du schéma d'ordonnancement. Elle sert à recalculer `section_order`
# sur une base déjà constituée quand la règle change — sans quoi les documents
# importés avant et après la correction s'entremêleraient à l'affichage.
ORDRE_VERSION = 2


def _section_sort_key(section_id: str) -> int:
    """Rang d'une section dans son document.

    Trois exigences, et l'ancienne formule en manquait deux :

    - art_3 < art_10 (numérique, pas lexicographique) et art_94 < art_94a ;
    - **les fragments d'un article long restent groupés** : l'import scinde
      tout article de plus de 2 500 caractères en `art_5_1`, `art_5_2`… ;
      l'ancienne formule concaténait les chiffres et rangeait ces morceaux
      entre l'article 50 et l'article 53 — dans la matrice, dans les listes
      déroulantes, dans l'export, et jusque dans le rattachement aux titres
      du règlement ;
    - le préambule vient en tête : il est produit sous l'identifiant
      `preambule`, que l'ancienne liste — qui ne connaissait que `preamble` —
      renvoyait en dernier.
    """
    sid = str(section_id or "").strip().lower()
    prefix, _, reste = sid.partition("_")

    # Sections hors numérotation d'articles : l'exposé des motifs ouvre le
    # document, les considérants viennent ensuite, les annexes ferment. Elles
    # peuvent être fragmentées (« expose_12 »), et leurs fragments doivent
    # rester groupés et dans l'ordre.
    SPECIALES = {"expose": -3_000_000, "preambule": -2_000_000,
                 "preamble": -2_000_000, "general": -2_000_000,
                 "generalites": -2_000_000, "annexe": 90_000_000,
                 "annexes": 90_000_000}
    if sid in SPECIALES:
        return SPECIALES[sid]
    if prefix in SPECIALES:
        suite = "".join(c for c in reste if c.isdigit())
        return SPECIALES[prefix] + (int(suite) if suite else 0)

    corps, _, fragment = reste.partition("_")
    chiffres = "".join(c for c in corps if c.isdigit())
    numero = int(chiffres) if chiffres else 9_900
    lettres = "".join(c for c in corps if c.isalpha())
    lettre = min(ord(lettres[0]) - 96, 26) if lettres else 0
    rang_fragment = min(int(fragment), 9) if fragment.isdigit() else 0

    # numéro · lettre · fragment, chacun dans sa décade : art_5 (5000) <
    # art_5_1 (5001) < art_5_2 (5002) < art_6 (6000) ; art_94 (94000) <
    # art_94a (94010) ; art_50 (50000) reste après art_5 et ses fragments.
    base = numero * 1000 + lettre * 10 + rang_fragment
    return base + (0 if prefix == "art" else 10_000_000)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def _ensure_columns() -> None:
    """Migrations légères : ajout de colonnes sur une base existante."""
    with connect() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(documents)")}
        for name, decl in (("kind", "TEXT"), ("author_ms", "TEXT"),
                           ("version_label", "TEXT"), ("n_segments", "INTEGER"),
                           # Repère de version : nature dans la procédure et
                           # date du document. Ajoutés après coup — une base
                           # existante se migre sans réimport.
                           ("version_kind", "TEXT"), ("version_date", "TEXT"),
                           # Nom du fichier conservé dans data/corpus. Le nom
                           # d'usage du document, lui, se corrige à la main :
                           # les deux ne peuvent donc plus être confondus.
                           ("fichier", "TEXT")):
            if name not in cols:
                con.execute(f"ALTER TABLE documents ADD COLUMN {name} {decl}")

    _migrer_ordre_des_sections()


def _migrer_ordre_des_sections() -> None:
    """Recalcule `section_order` quand la règle d'ordonnancement a changé.

    Sans cela, une base constituée avec l'ancienne règle garderait ses rangs
    et les documents importés ensuite s'intercaleraient n'importe où. La
    migration ne touche qu'une colonne dérivée : elle ne peut rien perdre.
    """
    with connect() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version >= ORDRE_VERSION:
            return
        for table in ("segments", "contributions"):
            try:
                lignes = con.execute(
                    f"SELECT DISTINCT section_id FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            # Les paragraphes d'un tableau de commentaires portent leur propre
            # ordre de lecture, qui n'est pas un rang d'article : on les
            # laisse tels quels.
            sql = f"UPDATE {table} SET section_order = ? WHERE section_id = ?"
            if table == "segments":
                sql += (" AND (section_kind IS NULL OR section_kind NOT IN "
                        "('paragraphe', 'modification'))")
            con.executemany(
                sql, [(_section_sort_key(r[0]), r[0]) for r in lignes])
        con.execute(f"PRAGMA user_version = {ORDRE_VERSION}")


def register_document(doc_id: str, name: str, dossier: str, sha256: str,
                      n: int, meta: dict | None = None, kind: str = "",
                      author_ms: str = "", version_label: str = "",
                      n_segments: int = 0, version_kind: str = "",
                      version_date: str = "", fichier: str = "") -> None:
    _ensure_columns()
    ancien = ""
    if not fichier:
        # Une mise à jour partielle — corriger le type ou le nom — ne doit pas
        # effacer le fichier d'origine déjà enregistré.
        with connect() as con:
            ligne = con.execute(
                "SELECT fichier FROM documents WHERE id = ?", (doc_id,)).fetchone()
            ancien = (ligne["fichier"] if ligne and ligne["fichier"] else "")
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO documents
               (id, name, dossier, sha256, imported_at, n_contributions, meta,
                kind, author_ms, version_label, n_segments, version_kind,
                version_date, fichier)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, name, dossier, sha256, _now(), n,
             json.dumps(meta or {}, ensure_ascii=False),
             kind, author_ms, version_label, n_segments, version_kind,
             version_date, fichier or ancien),
        )


def save_segments(doc_id: str, segments) -> int:
    """Enregistre les segments d'un document et met l'index à jour.

    Le ré-import d'un document déjà présent est un cas normal : on remplace
    ses segments et les entrées d'index correspondantes, dans cet ordre.
    """
    from .retrieval import ensure_index, index_segments, unindex_document

    ensure_index()
    rows = [
        (doc_id, s.section_id, s.section_label, s.section_kind,
         # Les paragraphes d'un tableau et les instructions d'un acte
         # modificatif portent leur propre ordre de lecture : leur
         # identifiant ne contient pas de numéro d'article à trier.
         (s.order if s.section_kind in ("paragraphe", "modification")
          else _section_sort_key(s.section_id)),
         s.ms_code or None, s.contribution_kind or None,
         s.text, s.page_start, s.page_end)
        for s in segments
    ]
    with connect() as con:
        unindex_document(con, doc_id)       # avant la suppression des segments
        con.execute("DELETE FROM segments WHERE document_id = ?", (doc_id,))
        con.executemany(
            """INSERT INTO segments
               (document_id, section_id, section_label, section_kind,
                section_order, ms_code, contribution_kind, text,
                page_start, page_end)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        fresh = con.execute(
            "SELECT id, section_label, text FROM segments WHERE document_id = ?",
            (doc_id,)).fetchall()
        index_segments(con, [(r[0], r[1] or "", r[2]) for r in fresh])
    return len(rows)


def load_segments(doc_id: str) -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query(
            "SELECT * FROM segments WHERE document_id = ? ORDER BY section_order, id",
            con, params=(doc_id,))


def save_contributions(doc_id: str, contribs: Iterable[Contribution]) -> int:
    rows = [
        (
            doc_id, c.section_id, c.section_label, c.section_kind,
            _section_sort_key(c.section_id), c.ms_code, c.ms_name, c.kind,
            c.text, c.page_start, c.page_end, c.char_count,
        )
        for c in contribs
    ]
    with connect() as con:
        con.execute("DELETE FROM contributions WHERE document_id = ?", (doc_id,))
        con.executemany(
            """INSERT INTO contributions
               (document_id, section_id, section_label, section_kind, section_order,
                ms_code, ms_name, kind, text, page_start, page_end, char_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def append_contributions(doc_id: str, contribs: Iterable[Contribution]) -> list[int]:
    """Ajoute des contributions SANS effacer les existantes, et rend leurs id.

    `save_contributions` remplace le contenu d'un document : c'est ce qu'on
    veut à l'import d'un tableau. Ici on complète — une position tirée d'un
    non-paper ou d'une note vient s'ajouter à la matrice existante — et il
    faut récupérer les identifiants pour y rattacher l'analyse.
    """
    ids: list[int] = []
    with connect() as con:
        for c in contribs:
            cur = con.execute(
                """INSERT INTO contributions
                   (document_id, section_id, section_label, section_kind,
                    section_order, ms_code, ms_name, kind, text, page_start,
                    page_end, char_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_id, c.section_id, c.section_label, c.section_kind,
                 _section_sort_key(c.section_id), c.ms_code, c.ms_name, c.kind,
                 c.text, c.page_start, c.page_end, c.char_count))
            ids.append(int(cur.lastrowid))
    return ids


def save_analysis(contribution_id: int, analysis, method: str, model: str) -> None:
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                contribution_id,
                analysis.stance.value,
                analysis.score,
                analysis.summary_fr,
                analysis.evidence,
                json.dumps(analysis.themes, ensure_ascii=False),
                int(analysis.is_scrutiny_reservation),
                int(analysis.proposes_deletion),
                analysis.confidence,
                method,
                model,
                _now(),
            ),
        )


def save_fr_reference(doc_id: str, section_id: str, summary: str,
                      key_asks: list[str], source: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO fr_reference VALUES (?,?,?,?,?,?)",
            (doc_id, section_id, summary,
             json.dumps(key_asks, ensure_ascii=False), source, _now()),
        )


def delete_document(doc_id: str) -> None:
    from .retrieval import ensure_index, unindex_document

    ensure_index()
    with connect() as con:
        unindex_document(con, doc_id)       # avant la suppression des segments
        con.execute("DELETE FROM segments WHERE document_id = ?", (doc_id,))
        con.execute(
            "DELETE FROM analyses WHERE contribution_id IN "
            "(SELECT id FROM contributions WHERE document_id = ?)", (doc_id,))
        con.execute("DELETE FROM contributions WHERE document_id = ?", (doc_id,))
        con.execute("DELETE FROM fr_reference WHERE document_id = ?", (doc_id,))
        con.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Diagnostic et réparation
# ---------------------------------------------------------------------------

def sauvegarde(db_path: str | None = None) -> bytes:
    """Copie cohérente de la base entière, prête à être téléchargée.

    `sqlite3.Connection.backup()` copie une base **en cours d'utilisation**
    sans risquer la copie à moitié écrite que donnerait un simple copier-coller
    du fichier. C'est le seul chemin de sauvegarde de l'outil, et il compte :
    ce qui est en jeu, ce ne sont pas les documents — ils restent sur le disque
    dans `data/corpus/` — mais tout ce qui a coûté du temps de modèle, à savoir
    les analyses, les positions françaises de référence, les repères de version
    et les corrections faites à la main.
    """
    import tempfile

    source = sqlite3.connect(db_path or settings.db_path, timeout=30)
    try:
        with tempfile.TemporaryDirectory() as dossier:
            cible_path = Path(dossier) / "sauvegarde.sqlite3"
            cible = sqlite3.connect(cible_path)
            try:
                source.backup(cible)
            finally:
                cible.close()
            return cible_path.read_bytes()
    finally:
        source.close()


def restaurer(donnees: bytes, db_path: str | None = None) -> tuple[bool, str]:
    """Remplace la base par une sauvegarde, après vérification.

    On ne remplace jamais une base par un fichier qu'on n'a pas ouvert : le
    fichier reçu est d'abord ouvert, soumis à `PRAGMA integrity_check` et
    contrôlé sur la présence de ses tables. La base en place est conservée à
    côté, horodatée, plutôt qu'écrasée — une restauration faite par erreur
    doit rester réversible.
    """
    import tempfile

    chemin = Path(db_path or settings.db_path)
    with tempfile.TemporaryDirectory() as dossier:
        candidat = Path(dossier) / "candidat.sqlite3"
        candidat.write_bytes(donnees)
        try:
            con = sqlite3.connect(candidat)
            verdict = con.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            n_docs = con.execute("SELECT count(*) FROM documents").fetchone()[0]
            con.close()
        except Exception as exc:
            return False, f"Ce fichier n'est pas une base exploitable : {exc}"

        if verdict != "ok":
            return False, f"La sauvegarde est elle-même endommagée ({verdict})."
        manquantes = {"documents", "segments", "contributions"} - tables
        if manquantes:
            return False, ("Ce fichier ne contient pas les tables attendues "
                           f"({', '.join(sorted(manquantes))}).")

        if chemin.exists():
            horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
            ancienne = chemin.with_name(f"{chemin.stem}_avant_{horodatage}.sqlite3")
            chemin.replace(ancienne)
        else:
            ancienne = None
        chemin.write_bytes(candidat.read_bytes())

    message = f"Base restaurée · {n_docs} document(s)."
    if ancienne is not None:
        message += (f" L'ancienne base a été conservée sous "
                    f"« {ancienne.name} » dans le même dossier.")
    return True, message


def check_integrity(db_path: str | None = None) -> tuple[bool, str]:
    """Contrôle d'intégrité. Renvoie (base saine, message).

    Deux contrôles, parce que le premier ne suffit pas : `PRAGMA
    integrity_check` valide les pages SQLite mais ne regarde pas l'intérieur
    d'un index FTS5. Une base peut donc être déclarée saine et faire échouer
    la première recherche. On interroge donc aussi l'index directement.
    """
    path = db_path or settings.db_path
    if not Path(path).exists():
        return True, "Base absente : elle sera créée au premier import."

    problems: list[str] = []
    try:
        con = sqlite3.connect(path, timeout=15)
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            problems.append(f"structure SQLite : {result}")

        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "segment_fts" in tables:
            try:
                con.execute(
                    "INSERT INTO segment_fts(segment_fts) VALUES('integrity-check')")
            except sqlite3.DatabaseError as exc:
                problems.append(f"index de recherche : {exc}")
            try:
                con.execute(
                    "SELECT count(*) FROM segment_fts WHERE segment_fts MATCH ?",
                    ("test",)).fetchone()
            except sqlite3.DatabaseError as exc:
                problems.append(f"lecture de l'index : {exc}")

        legacy = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        if legacy & {"segments_ai", "segments_ad", "segments_au"}:
            problems.append(
                "déclencheurs de l'ancienne version encore présents, "
                "ils recorrompront l'index au prochain ré-import")
        con.close()
    except sqlite3.DatabaseError as exc:
        return False, str(exc)

    if problems:
        return False, " · ".join(problems)
    return True, "Aucune anomalie détectée."


def repair(db_path: str | None = None) -> str:
    """Répare la base sans perdre les documents ni les analyses.

    L'index de recherche se reconstruit intégralement à partir des segments :
    c'est une donnée dérivée, jamais une source. Si la corruption touche les
    tables de données elles-mêmes, on tente une reconstruction par export SQL.
    """
    from .retrieval import rebuild_index

    path = Path(db_path or settings.db_path)
    steps: list[str] = []

    # 1. Purger l'ancien mécanisme à déclencheurs, source du problème d'origine
    try:
        con = sqlite3.connect(str(path), timeout=30)
        for trigger in ("segments_ai", "segments_ad", "segments_au"):
            con.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        con.execute("DROP TABLE IF EXISTS segment_fts")
        con.commit()
        con.close()
        steps.append("index de recherche supprimé")
    except sqlite3.DatabaseError as exc:
        steps.append(f"suppression de l'index impossible ({exc})")

    # 2. Reconstruire l'index depuis les données
    try:
        n = rebuild_index()
        steps.append(f"index reconstruit sur {n} segments")
    except sqlite3.DatabaseError as exc:
        steps.append(f"reconstruction impossible ({exc})")

        # 3. Dernier recours : réécrire la base entière via un export SQL
        backup = path.with_suffix(".corrompue.sqlite3")
        try:
            src = sqlite3.connect(str(path), timeout=30)
            dump = "\n".join(src.iterdump())
            src.close()
            path.rename(backup)
            dst = sqlite3.connect(str(path), timeout=30)
            dst.executescript(dump)
            dst.commit()
            dst.close()
            rebuild_index()
            steps.append(f"base réécrite depuis un export SQL ; "
                         f"ancien fichier conservé sous {backup.name}")
        except Exception as exc2:
            steps.append(f"réécriture impossible ({exc2}), "
                         "supprimez le fichier de base et réimportez")

    ok, msg = check_integrity(str(path))
    steps.append("contrôle final : " + ("base saine" if ok else msg))
    return " · ".join(steps)


def list_documents() -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query(
            "SELECT * FROM documents ORDER BY imported_at DESC", con)


def load_contributions(doc_id: str | list[str] | None = None,
                       with_analysis: bool = True) -> pd.DataFrame:
    """Contributions d'un document, ou de plusieurs.

    Le cas « plusieurs » sert au suivi d'un texte dont les titres ont été
    traités dans des documents de travail distincts : le Titre III et le
    Titre IV du même règlement arrivent dans deux tableaux séparés, et
    l'agent veut la vue d'ensemble.
    """
    sql = """
        SELECT c.*, a.stance, a.score, a.summary_fr, a.evidence, a.themes,
               a.scrutiny, a.deletion, a.confidence, a.method, a.model
        FROM contributions c
        LEFT JOIN analyses a ON a.contribution_id = c.id
    """ if with_analysis else "SELECT c.* FROM contributions c"

    ids = ([doc_id] if isinstance(doc_id, str) else list(doc_id or []))
    params: tuple = ()
    if ids:
        sql += f" WHERE c.document_id IN ({','.join('?' * len(ids))})"
        params = tuple(ids)
    sql += " ORDER BY c.section_order, c.ms_code, c.id"
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def load_fr_reference(doc_id: str | list[str]) -> pd.DataFrame:
    ids = [doc_id] if isinstance(doc_id, str) else list(doc_id or [])
    if not ids:
        return pd.DataFrame()
    with connect() as con:
        return pd.read_sql_query(
            "SELECT * FROM fr_reference WHERE document_id IN "
            f"({','.join('?' * len(ids))})", con, params=tuple(ids))


# Deux référentiels de comparaison, et ils ne disent pas la même chose.
#
#   « fr »    — écart à la position française. Répond à « qui est avec nous ? ».
#               C'est le référentiel de la négociation.
#   « texte » — écart au texte initial, c'est-à-dire au texte sur lequel les
#               États membres ont commenté, tel qu'il est écrit. Répond à
#               « qui veut changer ce texte, et dans quel sens ? », France
#               comprise. C'est le référentiel de la lecture du dossier : sur
#               un article que la France n'a pas amendé, les deux coïncident ;
#               sur un article où elle demande une réécriture, ils divergent,
#               et c'est précisément là que la distinction compte.
REFERENTIELS = {
    "fr": "Écart à la position française",
    "texte": "Écart au texte initial",
}


def score_matrix(doc_id: str | list[str], exclude_fr: bool = True,
                 referentiel: str = "fr") -> pd.DataFrame:
    """Matrice articles × EM des scores (0/1/2, NaN si non analysé ou neutre).

    Quand un EM a plusieurs contributions sur un même article, on retient la
    position la plus défavorable : une objection ne s'annule pas par un
    commentaire de soutien exprimé ailleurs sur le même article.

    Le référentiel « texte » ne rappelle pas le modèle : il applique la règle
    du silence — accepter le texte vaut alignement, en demander la
    modification vaut écart — au texte de chaque contribution. Le calcul est
    donc déterministe, immédiat, et refaisable à la main sur un cas.
    """
    df = load_contributions(doc_id)
    if df.empty:
        return pd.DataFrame()

    if referentiel == "texte":
        from .scoring import ecart_au_texte

        df = df.assign(score=[
            ecart_au_texte(t, k) for t, k in zip(df["text"], df.get(
                "kind", pd.Series([""] * len(df), index=df.index)))])
    df = df[df["score"].notna()]
    if exclude_fr:
        df = df[df["ms_code"] != "FR"]
    if df.empty:
        return pd.DataFrame()
    piv = df.pivot_table(
        index=["section_order", "section_label"],
        columns="ms_code",
        values="score",
        aggfunc="min",
    )
    piv.index = piv.index.droplevel(0)
    return piv
