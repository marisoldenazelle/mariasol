"""
Tests des repères ajoutés en 0.9 : intitulés précis, double référentiel,
nature et date de version, estimations de durée.

Ces tests protègent des règles métier, pas des détails d'affichage. Le plus
important est le dernier de la première série : une absence de position ne
doit jamais compter comme un alignement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.duree import avancement, duree_estimee, formater  # noqa: E402
from core.ingest import (VERSION_KINDS, detect_version_date,  # noqa: E402
                         detect_version_kind)
from core.labels import (apercu, label_fragment, preciser,  # noqa: E402
                         reference_dans_texte)
from core.scoring import ecart_au_texte, heuristic_analysis  # noqa: E402
from core.schemas import Stance  # noqa: E402


# --- intitulés --------------------------------------------------------------

def test_reference_lue_dans_le_commentaire():
    assert reference_dans_texte("Art. 5(2): we suggest deleting") == "§ 2"
    assert reference_dans_texte("Art. 5(2)(a): unclear") == "§ 2 (a)"
    assert reference_dans_texte("Recital 12 should be aligned") == "considérant 12"
    assert reference_dans_texte("Paragraph 3 is disproportionate") == "§ 3"
    assert reference_dans_texte("We generally welcome the proposal") == ""


def test_reference_ignoree_en_fin_de_commentaire():
    """Une référence citée loin dans le texte vise le plus souvent autre chose."""
    long = "We welcome the approach. " * 30 + "Art. 90(2) is different."
    assert reference_dans_texte(long) == ""


def test_fragment_automatique_remplace_par_la_disposition():
    """« Article 24 (2/12) » ne renvoie à rien dans le texte officiel."""
    avec = label_fragment("Article 24 (2/12)",
                          "Art. 24(3) provides that the Commission shall act.")
    assert avec == "Article 24, à partir du § 3"

    sans = label_fragment("Article 24 (2/12)", "The scope remains ambiguous.")
    assert "extrait 2/12" in sans and "ambiguous" in sans


def test_intitules_de_deux_contributions_se_distinguent():
    a = preciser("Article 5", "We suggest limiting the scope to large firms.")
    b = preciser("Article 5", "We ask for a longer transition period.")
    assert a != b


def test_apercu_retire_les_formules_creuses():
    assert not apercu("We would like to clarify the scope").startswith("We would")


# --- double référentiel -----------------------------------------------------

def test_ecart_au_texte_est_deterministe():
    assert ecart_au_texte("We support this Article as drafted.") == 2
    assert ecart_au_texte("This Article should be deleted.") == 0
    assert ecart_au_texte("We suggest clarifying the scope.") == 1


def test_absence_de_position_ne_vaut_pas_alignement():
    """Ni la France ni l'État membre n'ont amendé : on ne sait rien."""
    a = heuristic_analysis("What is the intended timeline for implementation?",
                           reference_kind="silence")
    assert a.stance is Stance.NEUTRE
    assert ecart_au_texte("What is the intended timeline?") is None


def test_matrice_selon_le_referentiel(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("REGWATCH_DB", str(tmp_path / "t.sqlite3"))
    for module in [m for m in list(sys.modules) if m.startswith("core.")]:
        sys.modules.pop(module, None)
    os.environ["REGWATCH_DB"] = str(tmp_path / "t.sqlite3")

    from core import store
    from core.wk_parser import Contribution

    contribs = [
        Contribution(document="WK", section_id="art_1", section_label="Article 1",
                     section_kind="article", ms_code="DE", ms_name="DE",
                     kind="comments", text="We support this Article as drafted.",
                     page_start=1, page_end=1),
        Contribution(document="WK", section_id="art_1", section_label="Article 1",
                     section_kind="article", ms_code="NL", ms_name="NL",
                     kind="comments", text="This Article should be deleted.",
                     page_start=1, page_end=1),
    ]
    store.register_document("d", "WK", "D", "sha", n=2, kind="wk_table")
    store.save_contributions("d", contribs)

    # Aucune analyse enregistrée : le référentiel « fr » ne peut rien dire…
    assert store.score_matrix("d", referentiel="fr").empty
    # …alors que l'écart au texte se calcule sans modèle ni analyse préalable.
    m = store.score_matrix("d", referentiel="texte")
    assert m.loc["Article 1", "DE"] == 2
    assert m.loc["Article 1", "NL"] == 0


# --- repère de version ------------------------------------------------------

def test_nature_de_version_detectee():
    compromis = ["Council of the European Union\nBrussels, 24 July 2026\n"
                 "Presidency compromise text"]
    commission = ["EUROPEAN COMMISSION\nBrussels, 15.3.2025\nCOM(2025) 123 final\n"
                  "Proposal for a Regulation"]
    assert detect_version_kind(compromis) == "compromis"
    assert detect_version_kind(commission) == "com"
    assert detect_version_kind(["texte quelconque"]) == "autre"
    assert set(VERSION_KINDS) >= {"com", "compromis", "jo", "autre"}


def test_date_de_version_detectee():
    assert detect_version_date(["Brussels, 24 July 2026\nWK 9876"]) == "2026-07-24"
    assert detect_version_date(["Bruxelles, le 15.3.2025"]) == "2025-03-15"
    assert detect_version_date(["aucune date ici"]) == ""


def test_date_du_corps_du_texte_ignoree():
    """Une date d'entrée en application n'est pas la date du document."""
    pages = ["Council of the European Union\nWK 1234",
             "Le présent règlement s'applique à partir du 12 septembre 2027."]
    # La date est en page 2, dans le corps : ce n'est pas la date du document.
    assert detect_version_date(pages) == ""


# --- durées -----------------------------------------------------------------

def test_duree_annoncee_avant_lancement():
    assert "seconde" in duree_estimee(3, 3.0)
    texte = duree_estimee(329, 4.0, "329 articles")
    assert "22 minutes" in texte and "329 articles" in texte
    assert duree_estimee(0) == "Rien à traiter."


def test_temps_restant_calcule_sur_le_rythme_observe():
    import time

    debut = time.time() - 30          # 30 s pour 25 unités
    texte = avancement(25, 100, debut)
    assert "25 / 100" in texte and "il reste" in texte
    assert "terminé" in avancement(100, 100, debut)


def test_duree_lisible():
    assert formater(10) == "moins d'une minute"
    assert formater(600) == "environ 10 minutes"
    assert formater(3600).startswith("environ 1 h")


# --- garde-fou de l'échantillonnage ----------------------------------------

def test_echantillon_reparti_couvre_tous_les_articles():
    """La fraction choisie doit couvrir tous les articles, pas les premiers."""
    lignes = [{"section_id": f"art_{a}", "section_order": a, "ms_code": ms}
              for a in range(1, 21) for ms in ["DE", "NL", "IT", "ES", "PL"]]
    df = pd.DataFrame(lignes)
    cap = round(len(df) * 0.1)        # un dixième

    reparti = (df.assign(_rang=df.groupby("section_id").cumcount())
               .sort_values(["_rang", "section_order", "ms_code"]).head(cap))
    naif = df.head(cap)

    # Dix contributions ne peuvent pas couvrir vingt articles : ce qu'on exige,
    # c'est qu'elles portent sur dix articles DIFFÉRENTS, et non sur les deux
    # premiers — c'était le défaut constaté au test.
    assert reparti["section_id"].nunique() == cap
    assert naif["section_id"].nunique() <= 2
