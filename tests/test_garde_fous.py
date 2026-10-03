"""
Tests des garde-fous — les propriétés dont dépend la fiabilité de l'outil.

Lancement :  python -m pytest tests/ -q     (ou : python tests/test_garde_fous.py)

Ce qui est vérifié ici n'est pas du confort : c'est la promesse faite à
l'utilisateur. Une affirmation sans citation retrouvable dans le corpus ne
doit jamais s'afficher.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import qa
from core.qa import quote_matches
from core.retrieval import Hit, build_query
from core.scoring import heuristic_analysis, verify_evidence
from core.schemas import PositionAnalysis, Stance


def _hit(text: str, sid: int = 1) -> Hit:
    return Hit(segment_id=sid, document_id="d1", document_name="Doc",
               section_label="Article 5", ms_code="DE", page_start=1,
               page_end=1, text=text, score=1.0)


SOURCE = (
    "The proposed concept of a Cyber Posture is under scrutiny reservation. "
    "In particular, we would like to wait and see what results the workshop "
    "on cyber posture announced by the Commission brings."
)


# --- vérification de citation ----------------------------------------------

def test_citation_litterale_acceptee():
    assert quote_matches("Cyber Posture is under scrutiny reservation", SOURCE)


def test_citation_tolere_ponctuation_et_cesure():
    assert quote_matches("cyber posture is under - scrutiny reservation.", SOURCE)


def test_citation_inventee_rejetee():
    assert not quote_matches(
        "Germany fully supports the Commission proposal without reservation",
        SOURCE)


def test_reformulation_rejetee():
    # même sens, mots différents : ce n'est pas une citation
    assert not quote_matches(
        "L'Allemagne émet une réserve d'examen sur la posture cyber", SOURCE)


def test_citation_trop_courte_rejetee():
    assert not quote_matches("the", SOURCE)


# --- retrait effectif des affirmations non sourcées -------------------------

class _FakeClient:
    """Client qui invente une citation sur le second extrait.

    Le pipeline appelle le modèle plusieurs fois avec des schémas différents —
    plan de recherche, examen d'un extrait, recopie, lecture d'ensemble,
    synthèse. Le faux client répond selon le schéma demandé, ce qui permet de
    tester le garde-fou là où il joue : la vérification de la citation.
    """

    available = True
    model = "fake"

    def structured(self, schema, system, user, max_tokens=0):
        nom = schema.__name__
        if nom == "SearchPlan":
            return schema(termes=["reservation"], expressions=[], articles=[])
        if nom == "ExtraitVerdict":
            if "scrutiny reservation" in user:
                return schema(
                    pertinent=True,
                    statement="L'Allemagne pose une réserve d'examen.",
                    quote="Cyber Posture is under scrutiny reservation")
            return schema(
                pertinent=True,
                statement="L'Allemagne demande la suppression de l'article.",
                quote="Germany requests the deletion of this Article")
        if nom == "Recopie":
            # Même au second essai le modèle ne retrouve pas le passage :
            # l'affirmation doit être retirée, pas affichée avec réserve.
            return schema(quote="Germany requests the deletion of this Article")
        if nom == "Lecture":
            return schema(elements=[], manques=[])
        if nom == "Synthese":
            return schema(answer_fr="L'Allemagne pose une réserve d'examen.",
                          unanswered=[])
        raise AssertionError(f"schéma inattendu : {nom}")


def test_affirmation_hallucinee_retiree():
    """Une citation introuvable dans le texte source ne s'affiche jamais."""
    hits = [_hit(SOURCE, sid=1),
            _hit("This provision is acceptable to our delegation.", sid=2)]
    original_search, original_client = qa.search, qa.get_client
    qa.search = lambda *a, **k: hits
    qa.get_client = lambda: _FakeClient()
    try:
        res = qa.answer("réserve d'examen ?")
    finally:
        qa.search, qa.get_client = original_search, original_client

    assert len(res.claims) == 1, "seule l'affirmation réellement citée subsiste"
    assert res.dropped == 1, "la citation inventée est écartée, même après recopie"
    assert "suppression" not in " ".join(c.statement for c in res.claims)


def test_lecture_ensemble_verifie_aussi_les_citations():
    """La seconde lecture est plus inclusive, pas moins vérifiée."""

    class _Client(_FakeClient):
        def structured(self, schema, system, user, max_tokens=0):
            nom = schema.__name__
            if nom == "ExtraitVerdict":
                return schema(pertinent=False, statement="", quote="")
            if nom == "Lecture":
                from core.qa import LectureElement
                return schema(elements=[
                    LectureElement(
                        extract_number=1,
                        statement="Élément réellement cité.",
                        quote="Cyber Posture is under scrutiny reservation"),
                    LectureElement(
                        extract_number=1,
                        statement="Élément inventé.",
                        quote="this Article shall not apply to microenterprises"),
                ], manques=[])
            return super().structured(schema, system, user, max_tokens)

    hits = [_hit(SOURCE)]
    original_search, original_client = qa.search, qa.get_client
    qa.search = lambda *a, **k: hits
    qa.get_client = lambda: _Client()
    try:
        res = qa.answer("réserve d'examen ?")
    finally:
        qa.search, qa.get_client = original_search, original_client

    assert len(res.claims) == 0
    assert len(res.indirect) == 1
    assert res.indirect[0].statement == "Élément réellement cité."


# --- règle du silence français ---------------------------------------------

def test_silence_une_demande_de_suppression_est_une_opposition():
    a = heuristic_analysis(
        "We believe this Article should be deleted.", reference_kind="silence")
    assert a.stance is Stance.OPPOSE
    assert a.proposes_deletion


def test_silence_une_reserve_dexamen_est_une_opposition():
    a = heuristic_analysis(
        "We maintain a scrutiny reservation on this provision.",
        reference_kind="silence")
    assert a.stance is Stance.OPPOSE


def test_silence_un_amendement_redactionnel_est_partiel():
    a = heuristic_analysis(
        "Replace 'shall' by 'may' for consistency.",
        reference_kind="silence", contribution_kind="drafting")
    assert a.stance is Stance.PARTIEL


def test_silence_un_soutien_est_un_alignement():
    a = heuristic_analysis(
        "We welcome this Article as drafted.", reference_kind="silence")
    assert a.stance is Stance.ALIGNE


# --- vérification des citations dans le module de positions -----------------

def test_position_sans_citation_retrouvable_est_detectee():
    bad = PositionAnalysis(
        stance=Stance.ALIGNE, summary_fr="Soutient la position française.",
        evidence="Nous soutenons pleinement la proposition de la France.",
        confidence=0.9)
    assert not verify_evidence(bad, SOURCE)


def test_position_avec_citation_reelle_est_validee():
    good = PositionAnalysis(
        stance=Stance.OPPOSE, summary_fr="Réserve d'examen.",
        evidence="Cyber Posture is under scrutiny reservation", confidence=0.9)
    assert verify_evidence(good, SOURCE)


# --- construction de requête ------------------------------------------------

def test_expression_exacte_preservee():
    q = build_query('qui parle de "cyber posture" ?')
    assert '"cyber posture"' in q


def test_mots_vides_ecartes():
    q = build_query("quels sont les États qui ont commenté")
    assert "quels" not in q and "commente" in q.replace('"', "").replace("*", "")


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
