"""
Tests de la couche de stockage et de l'index de recherche.

Ces tests existent à cause d'un défaut réel : la première version supprimait
les entrées d'index à la fois par le code et par un déclencheur SQLite, ce qui
corrompait irréversiblement l'index au ré-import d'un document déjà présent
(« database disk image is malformed »). Le scénario est couvert ici pour qu'il
ne puisse pas revenir.

Lancement :  python tests/test_base.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = Path(tempfile.mkdtemp(prefix="regwatch-test-"))
os.environ["REGWATCH_DB"] = str(_TMP / "test.sqlite3")
os.environ["REGWATCH_LLM_PROVIDER"] = "offline"

from core import store                      # noqa: E402
from core.ingest import Segment             # noqa: E402
from core.retrieval import search           # noqa: E402


def _segments(n: int = 5, marker: str = "cyber posture") -> list[Segment]:
    return [
        Segment(section_id=f"art_{i}", section_label=f"Article {i}",
                section_kind="article",
                text=f"Contribution {i} concerning {marker} and certification.",
                page_start=i, page_end=i, ms_code="DE", order=i)
        for i in range(1, n + 1)
    ]


def _register(doc_id: str = "doc1") -> str:
    store.register_document(doc_id, "Document test", "TEST", "sha", 0,
                            kind="wk_table", n_segments=0)
    return doc_id


def test_import_puis_recherche():
    doc = _register("doc_import")
    store.save_segments(doc, _segments())
    # La recherche porte sur tout le corpus : on la restreint au document
    # testé, sinon les documents des autres tests faussent le compte.
    assert len(search("cyber posture", document_ids=[doc])) == 5


def test_reimport_ne_corrompt_pas_la_base():
    """Le scénario exact du défaut : trois imports successifs du même document."""
    doc = _register("doc_reimport")
    for _ in range(3):
        store.save_segments(doc, _segments())
        healthy, message = store.check_integrity()
        assert healthy, f"base corrompue après ré-import : {message}"
    assert len(store.load_segments(doc)) == 5, "les segments ne doivent pas s'empiler"
    assert len(search("cyber posture", document_ids=[doc])) == 5, \
        "l'index ne doit pas doublonner"


def test_suppression_retire_de_l_index():
    doc = _register("doc_suppr")
    store.save_segments(doc, _segments(marker="terme unique xyzzy"))
    assert search("xyzzy")
    store.delete_document(doc)
    assert not search("xyzzy"), "un document supprimé ne doit plus remonter"
    healthy, message = store.check_integrity()
    assert healthy, message


def test_detection_des_declencheurs_obsoletes():
    """Une base issue de l'ancienne version doit être signalée comme à risque."""
    path = _TMP / "ancienne.sqlite3"
    with store.connect(str(path)):
        pass
    con = sqlite3.connect(str(path))
    con.executescript(
        "CREATE TRIGGER segments_ad AFTER DELETE ON segments BEGIN "
        "SELECT 1; END;")
    con.commit()
    con.close()
    healthy, message = store.check_integrity(str(path))
    assert not healthy
    assert "ancienne version" in message


def test_reparation_conserve_les_donnees():
    doc = _register("doc_repair")
    store.save_segments(doc, _segments())

    # On casse volontairement l'index, sans toucher aux données
    con = sqlite3.connect(os.environ["REGWATCH_DB"])
    con.execute("DROP TABLE IF EXISTS segment_fts")
    con.executescript(
        "CREATE TRIGGER segments_ad AFTER DELETE ON segments BEGIN SELECT 1; END;")
    con.commit()
    con.close()

    assert not store.check_integrity()[0]
    store.repair()
    healthy, message = store.check_integrity()
    assert healthy, message
    assert len(store.load_segments(doc)) == 5, "la réparation ne perd aucun segment"
    assert len(search("cyber posture", document_ids=[doc])) == 5


def test_documents_independants():
    a, b = _register("doc_a"), _register("doc_b")
    store.save_segments(a, _segments(3, marker="alpha unique"))
    store.save_segments(b, _segments(4, marker="beta unique"))
    store.delete_document(a)
    assert not search("alpha")
    assert len(search("beta")) == 4, "supprimer un document ne touche pas les autres"


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception:
            failed += 1
            print(f"  ÉCHEC {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés")
    sys.exit(1 if failed else 0)
