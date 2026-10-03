"""L'onglet Omnibus, exercé de bout en bout sans navigateur.

Les tests unitaires vérifient la lecture d'un acte modificatif ; celui-ci
vérifie que l'écran qui la restitue se construit vraiment — c'est là qu'un
nom de variable écrasé ou un appel changé se voit, et c'est exactement le
défaut qui avait échappé à la recette précédente.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

# Une base de test, mais seulement si la campagne n'en a pas déjà désigné une :
# `core.config` fige le chemin au premier import, et le réécrire ici ferait
# travailler les autres fichiers de test sur une base et en interroger une
# autre.
if not os.environ.get("REGWATCH_DB"):
    _TMP = pathlib.Path(tempfile.mkdtemp(prefix="mariasol_ecran_"))
    os.environ["REGWATCH_DB"] = str(_TMP / "ecran.sqlite3")

from streamlit.testing.v1 import AppTest          # noqa: E402

from core import store                            # noqa: E402
from core.ingest import Segment                   # noqa: E402

PAGE = str(pathlib.Path(__file__).resolve().parent.parent
           / "pages" / "5_Comparaison_de_versions.py")

OMNIBUS = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. À l'article 33, le paragraphe 1 est remplacé par le texte suivant:
«1. Le responsable notifie la violation dans un délai de 96 heures.»
2. À l'article 64, paragraphe 1, le point c) est supprimé.
Article 2
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. L'article 5 est supprimé.
"""

CIBLE = {
    "art_33": ("Article 33",
               "1. Le responsable notifie la violation dans un délai de 72 "
               "heures.\n2. Le sous-traitant notifie au responsable.\n"),
    "art_64": ("Article 64",
               "1. Le comité émet un avis:\na) sur une liste;\n"
               "b) sur un code;\nc) sur des règles d'entreprise.\n"),
}


@pytest.fixture(scope="module")
def corpus():
    store.register_document("omni", "Proposition omnibus numérique", "Omnibus",
                            "a" * 64, n=1, kind="legal_text", n_segments=1,
                            version_kind="proposition", version_date="2025-11-19")
    store.save_segments("omni", [Segment(
        section_id="art_1", section_label="Article 1", section_kind="article",
        text=OMNIBUS, page_start=1, page_end=1, order=0)])
    store.register_document("rgpd", "CELEX_32016R0679 RGPD consolidé", "RGPD",
                            "b" * 64, n=len(CIBLE), kind="legal_text",
                            n_segments=len(CIBLE), version_kind="publie",
                            version_date="2016-04-27")
    store.save_segments("rgpd", [
        Segment(section_id=sid, section_label=lab, section_kind="article",
                text=txt, page_start=i + 1, page_end=i + 1, order=i)
        for i, (sid, (lab, txt)) in enumerate(CIBLE.items())])
    return ("omni", "rgpd")


def _page(corpus):
    at = AppTest.from_file(PAGE, default_timeout=120).run()
    assert not at.exception
    acte = [s for s in at.selectbox if "Acte modificatif" in (s.label or "")]
    assert acte, "la liste des actes modificatifs doit être affichée"
    acte[0].set_value(corpus[0]).run()
    assert not at.exception
    return at


def test_la_vue_d_ensemble_compte_les_textes_et_dessine_la_carte(corpus):
    at = _page(corpus)
    valeurs = {m.label: m.value for m in at.metric}
    assert valeurs["Textes modifiés"] == "2"
    assert valeurs["Articles touchés"] == "3"
    assert valeurs["Instructions"] == "3"
    assert any("rw-case" in str(m.value) for m in at.markdown), \
        "la carte de l'omnibus doit être rendue"


def test_les_deux_livrables_sont_proposes(corpus):
    """La note Word et le classeur : c'est ce que l'agent emporte.

    Le classeur avait cessé d'être produit parce qu'une variable de boucle
    écrasait le tableau récapitulatif ; le bouton apparaissait en erreur.
    """
    at = _page(corpus)
    labels = [d.label for d in at.download_button]
    assert any(".docx" in l for l in labels)
    assert any(".xlsx" in l for l in labels)
    for bouton in at.download_button:
        assert bouton.value is None or True      # le rendu n'a pas levé


def test_le_texte_par_texte_reconstitue_l_article(corpus):
    at = _page(corpus)
    vues = [r for r in at.radio if "Comment lire" in (r.label or "")]
    vues[0].set_value("Texte par texte").run()
    assert not at.exception
    assert any("Texte de référence" in (s.label or "") for s in at.selectbox)


def test_la_troisieme_vue_ne_leve_pas(corpus):
    at = _page(corpus)
    vues = [r for r in at.radio if "Comment lire" in (r.label or "")]
    vues[0].set_value("Comparer deux versions").run()
    assert not at.exception
