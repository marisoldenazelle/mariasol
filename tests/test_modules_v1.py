"""
Tests des modules ajoutés en 1.0 : titres, pondération, fiabilité, suivi des
amendements, dépouillement des non-papers, assistant d'aide, noms EUR-Lex.

Ce qui est protégé ici, ce sont les règles qui feraient une erreur d'analyse
si elles cédaient — pas les détails d'affichage. Trois d'entre elles méritent
d'être citées : un verdict d'amendement sans citation retrouvée ne doit jamais
être affiché comme acquis ; une position extraite d'un non-paper ne doit
jamais entrer dans la matrice sans validation ; et l'assistant d'aide ne doit
jamais répondre en dehors de ses fiches.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.aide import (FICHES, FICHES_PAR_CLE, chercher,  # noqa: E402
                       guide_complet, question_technique, repondre)
from core.amendements import suivre  # noqa: E402
from core.eurlex import nom_usuel  # noqa: E402
from core.fiabilite import positions as alertes_positions  # noqa: E402
from core.fiabilite import reponse_sourcee, resume  # noqa: E402
from core.nonpaper import (Proposition, deviner_auteur,  # noqa: E402
                           en_contributions)
from core.ponderation import (ResultatPonderation,  # noqa: E402
                              classement_pondere, matrice_ponderee)
from core.titres import (bornes_depuis_rattachement,  # noqa: E402
                        ordre_des_titres, titres_depuis_bornes,
                        titres_depuis_texte)


# ---------------------------------------------------------------------------
# Regroupement par titre
# ---------------------------------------------------------------------------

def _texte_avec_titres() -> pd.DataFrame:
    return pd.DataFrame({
        "section_order": [1, 2, 3, 4],
        "section_label": ["Article 96", "Article 97", "Article 98", "Article 120"],
        "text": [
            "Article 96. Dispositions du titre précédent.",
            "TITRE IV — SÉCURITÉ DE LA CHAÎNE D'APPROVISIONNEMENT\n"
            "Article 97. Objet.",
            "Article 98. Champ du cadre.",
            "TITRE V\nArticle 120. Entrée en vigueur."],
    })


def test_titre_lu_dans_le_texte_reglementaire():
    r = titres_depuis_texte(_texte_avec_titres())
    assert r["Article 97"].startswith("Titre IV")
    assert r["Article 98"].startswith("Titre IV")
    assert r["Article 120"] == "Titre V"
    # L'article qui PRÉCÈDE l'en-tête n'appartient pas au titre.
    assert "Article 96" not in r


def test_intitule_de_titre_ne_happe_pas_la_ligne_suivante():
    """« TITRE V » suivi d'un article ne doit pas devenir « Titre V — Article 120 »."""
    r = titres_depuis_texte(_texte_avec_titres())
    assert r["Article 120"] == "Titre V"


def test_rattachement_par_bornes_saisies():
    r = titres_depuis_bornes({"Titre III": (71, 97), "Titre IV": (98, 118)},
                             ["Article 80", "Article 100", "Commentaires généraux"])
    assert r == {"Article 80": "Titre III", "Article 100": "Titre IV"}


def test_bornes_et_ordre_des_titres():
    bornes = bornes_depuis_rattachement(
        {"Article 98": "Titre IV", "Article 118": "Titre IV",
         "Article 12": "Titre I"})
    assert bornes["Titre IV"] == (98, 118)
    assert ordre_des_titres(["Titre X", "Titre II", "Titre IV"]) == [
        "Titre II", "Titre IV", "Titre X"]


# ---------------------------------------------------------------------------
# Pondération
# ---------------------------------------------------------------------------

def _contributions() -> pd.DataFrame:
    return pd.DataFrame({
        "id": [1, 2, 3, 4],
        "ms_code": ["DE", "DE", "NL", "NL"],
        "section_label": ["Article 1", "Article 2"] * 2,
        "section_order": [1, 2, 1, 2],
        "score": [2.0, 0.0, 2.0, 0.0],
        "text": ["x"] * 4,
    })


def test_ponderation_ne_change_pas_les_positions():
    """Le poids change les moyennes, jamais le classement d'une position."""
    r = ResultatPonderation(critere="comitologie", facteur=3.0,
                            correspondances={2: "citation"})
    m = matrice_ponderee(_contributions(), r)
    assert m.loc["Article 1", "DE"] == 2.0
    assert m.loc["Article 2", "DE"] == 0.0


def test_ponderation_deplace_la_moyenne_et_affiche_l_ecart():
    r = ResultatPonderation(critere="comitologie", facteur=3.0,
                            correspondances={2: "citation"})
    classement = classement_pondere(_contributions(), r).set_index("EM")
    # DE : une opposition comptée trois fois → moyenne tirée vers le bas.
    assert classement.loc["DE", "Score brut"] == 1.0
    assert classement.loc["DE", "Score pondéré"] == 0.5
    assert classement.loc["DE", "Écart"] == -0.5
    # NL : aucune contribution retenue → le critère ne le discrimine pas.
    assert classement.loc["NL", "Écart"] == 0.0


def test_sans_critere_la_ponderation_est_neutre():
    r = ResultatPonderation()
    classement = classement_pondere(_contributions(), r)
    assert (classement["Écart"] == 0).all()


# ---------------------------------------------------------------------------
# Suivi des amendements
# ---------------------------------------------------------------------------

def _demandes() -> pd.DataFrame:
    return pd.DataFrame({
        "ms_code": ["FR", "DE"],
        "section_label": ["Article 100", "Article 99"],
        "text": ["FR requests the deletion of this Article.",
                 "We suggest clarifying the scope."],
        "summary_fr": ["Demande la suppression de l'article 100.",
                       "Demande une clarification du champ."],
        "deletion": [1, 0],
    })


def test_suppression_obtenue_se_tranche_sans_modele():
    cible = pd.DataFrame({"section_label": ["Article 99"],
                          "text": ["Article 99. Le champ est précisé."]})
    res = suivre(_demandes(), cible, "Compromis 3")
    par_em = {s.ms_code: s for s in res.suivis}
    assert par_em["FR"].verdict == "retenue"
    assert par_em["FR"].methode == "structure"


def test_suppression_refusee_se_tranche_aussi_sans_modele():
    cible = pd.DataFrame({
        "section_label": ["Article 99", "Article 100"],
        "text": ["Article 99. Le champ est précisé.",
                 "Article 100. La désignation reste possible."]})
    res = suivre(_demandes(), cible, "Compromis 3")
    par_em = {s.ms_code: s for s in res.suivis}
    assert par_em["FR"].verdict == "ecartee"


def test_taux_de_reprise_exclut_les_indetermines():
    cible = pd.DataFrame({"section_label": ["Article 99"],
                          "text": ["Article 99. Le champ est précisé."]})
    taux = suivre(_demandes(), cible, "Compromis 3").taux().set_index("EM")
    assert taux.loc["FR", "Taux de reprise"] == 1.0
    # DE n'a pas pu être tranché sans modèle : pas de taux inventé.
    assert pd.isna(taux.loc["DE", "Taux de reprise"])


# ---------------------------------------------------------------------------
# Non-papers
# ---------------------------------------------------------------------------

def test_auteur_devine_en_francais_comme_en_anglais():
    assert deviner_auteur("Non-paper from Germany on the supply chain") == "DE"
    assert deviner_auteur("Non-paper des Pays-Bas") == "NL"
    assert deviner_auteur("Document anonyme", "FR") == "FR"


def test_seules_les_propositions_retenues_sont_enregistrables():
    """Rien n'entre dans la matrice sans validation explicite."""
    gardee = Proposition("DE", "Article 100", "suppression",
                         "Demande la suppression.", "should be deleted",
                         source="Non-paper DE", page=2)
    ecartee = Proposition("DE", "Article 99", "modification",
                          "Demande une clarification.", "we suggest",
                          source="Non-paper DE", page=3, retenue=False)
    contributions, analyses = en_contributions([gardee, ecartee], "Non-paper DE")
    assert len(contributions) == 1 and len(analyses) == 1
    assert contributions[0].section_id == "art_100"
    # La source reste lisible dans le texte enregistré.
    assert "Non-paper DE" in contributions[0].text
    assert contributions[0].kind == "non-paper"
    assert analyses[0].proposes_deletion


# ---------------------------------------------------------------------------
# Fiabilité
# ---------------------------------------------------------------------------

def test_alerte_quand_le_plafond_de_passages_est_atteint():
    """Le principal risque de réponse incomplète doit être dit."""

    class _Res:
        dropped = 0
        hits = list(range(20))
        claims: list = []
        indirect: list = []

    alertes = reponse_sourcee(_Res(), limite_demandee=20)
    assert any("plafond" in a.titre.lower() for a in alertes)


def test_alerte_sur_les_citations_non_retrouvees():
    df = pd.DataFrame({
        "id": [1, 2], "ms_code": ["DE", "NL"],
        "section_label": ["Article 1"] * 2,
        "stance": ["oppose", "aligne"], "confidence": [0.0, 0.9],
        "method": ["llm", "llm"], "scrutiny": [0, 0], "text": ["x", "y"]})
    m = pd.DataFrame({"DE": [0], "NL": [2]}, index=["Article 1"])
    alertes = alertes_positions(df, m)
    assert any("citation" in a.titre.lower() for a in alertes)
    assert resume(alertes)


# ---------------------------------------------------------------------------
# Assistant d'aide
# ---------------------------------------------------------------------------

def test_assistant_trouve_la_bonne_fiche():
    assert chercher("comment les scores sont calculés")[0][0].cle == "scores"
    assert chercher("est-ce sauvegardé si je ferme")[0][0].cle == "sauvegarde"
    assert chercher("comment sont choisis les 30 passages")[0][0].cle == "passages"


def test_assistant_refuse_ce_qui_n_est_pas_dans_les_fiches():
    """Il ne connaît que le fonctionnement de l'outil, et le dit."""
    res = repondre("quelle est la capitale de l'Italie ?")
    assert not res.couverte
    assert "Recherche" in res.reponse


def test_assistant_reconnait_une_question_de_calcul():
    """« Comment tu calcules les coalitions ? » n'appelle pas une réponse d'usage."""
    assert question_technique("quelle formule calcule les coalitions ?")
    assert question_technique("quelles bibliothèques python sont utilisées ?")
    assert not question_technique("est-ce sauvegardé si je ferme l'application ?")


def test_pluriel_et_singulier_trouvent_la_meme_fiche():
    """Le mot-clé est « coalition » ; la question dit « les coalitions »."""
    cles = {f.cle for f, _ in chercher("comment tu calcules les coalitions ?")}
    assert {"blocs", "accord"} & cles


def test_les_fiches_de_calcul_portent_leur_formule():
    """Sans le détail, l'assistant retombe dans la réponse d'usage vague."""
    for cle in ("scores", "accord", "blocs", "qmv", "diff", "passages",
                "amendements", "ponderation", "architecture"):
        assert FICHES_PAR_CLE[cle].technique, cle
    # Et ce détail nomme bien les outils : c'est ce qui a été demandé.
    assert "networkx" in FICHES_PAR_CLE["blocs"].technique
    assert "difflib" in FICHES_PAR_CLE["diff"].technique
    assert "bm25" in FICHES_PAR_CLE["passages"].technique.lower()


def test_reponse_technique_sans_modele_donne_quand_meme_la_formule():
    """Hors ligne, le repli doit être la fiche complète, pas son résumé."""
    res = repondre("quelle est la formule du taux d'accord ?")
    assert res.technique
    assert "Sous le capot" in res.reponse or "accord(i,j)" in res.reponse


def test_guide_complet_couvre_tous_les_modules():
    guide = guide_complet()
    for module in ("Bibliothèque", "Coalitions", "Suivi des amendements"):
        assert module in guide
    assert len(FICHES) >= 25
    # La version détaillée ajoute les blocs d'implémentation, pas des fiches.
    detaille = guide_complet(technique=True)
    assert len(detaille) > len(guide) and "networkx" in detaille


# ---------------------------------------------------------------------------
# Noms EUR-Lex
# ---------------------------------------------------------------------------

def test_nom_usuel_plutot_qu_un_nom_de_fichier():
    """« L_2022152FR.01000101.xml » ne dit à personne de quel texte il s'agit."""
    assert nom_usuel("32022R0868",
                     titre_html="L_2022152FR.01000101.xml") == "Data Governance Act"
    assert nom_usuel("32023R2854") == "Data Act"

    inconnu = nom_usuel(
        "32026R0123",
        texte="RÈGLEMENT (UE) 2026/123 DU PARLEMENT EUROPÉEN ET DU CONSEIL "
              "du 3 mars 2026 relatif à la résilience des infrastructures")
    assert "résilience des infrastructures" in inconnu
    assert nom_usuel("32026R0999", titre_html="EUR-Lex - 32026R0999") == "32026R0999"


# ---------------------------------------------------------------------------
# Marque
# ---------------------------------------------------------------------------

def test_les_images_de_la_marque_sont_des_png_presents():
    """`st.logo` refuse un chemin SVG selon la version de Streamlit installée.

    Le défaut n'apparaît qu'au démarrage sur le poste de destination, et il
    arrête l'application entière : il vaut mieux le voir ici.
    """
    racine = Path(__file__).resolve().parent.parent
    for nom in ("mariasol_logo.png", "mariasol_marque_256.png"):
        chemin = racine / "assets" / nom
        assert chemin.exists(), nom
        assert chemin.suffix == ".png"
    source = (racine / "app.py").read_text(encoding="utf-8")
    assert ".svg" not in source, "l'application ne doit référencer aucun SVG"


def test_le_nom_s_affiche_au_lettrage_du_logo():
    """« mariasol » écrit en texte ordinaire perd la lecture « marisol »."""
    from core.ui import nom_marque

    marque = nom_marque()
    assert "mar" in marque and "sol" in marque
    # Le « i » et le « a » portent le rouge Marianne, le « a » est en exposant.
    assert marque.count("#e1000f") == 2
    assert "vertical-align" in marque
    # Les pages qui nomment l'application utilisent ce lettrage, pas APP_NOM.
    racine = Path(__file__).resolve().parent.parent
    for fichier in ("accueil.py", "pages/0_Mode_d_emploi.py"):
        source = (racine / fichier).read_text(encoding="utf-8")
        assert "nom_marque(" in source, fichier


def test_un_considerant_n_est_pas_juge_sur_l_article_de_meme_numero():
    """« Considérant 79 » et « Article 79 » ne doivent pas partager de clé."""
    from core.amendements import _cle_article

    assert _cle_article("Considérant 79") != _cle_article("Article 79")
    assert _cle_article("Art. 79 (2/3)") == _cle_article("Article 79")

    demandes = pd.DataFrame({
        "ms_code": ["FR"],
        "section_label": ["Considérant 79"],
        "text": ["FR requests the deletion of this recital."],
        "summary_fr": ["Demande la suppression du considérant 79."],
        "deletion": [1],
    })
    # Le texte d'arrivée conserve l'ARTICLE 79 mais plus le considérant 79 :
    # la demande a donc été retenue, et l'inverse serait un contresens.
    cible = pd.DataFrame({
        "section_label": ["Article 79"],
        "text": ["Article 79. Entrée en vigueur."]})
    verdict = suivre(demandes, cible, "Compromis 4").suivis[0]
    assert verdict.verdict == "retenue"


def test_un_article_scinde_a_l_import_reste_un_seul_article():
    """Un article allongé ne doit pas apparaître supprimé puis ajouté.

    L'import scinde tout article de plus de 2 500 caractères en `art_5_1`,
    `art_5_2`… Comparés tels quels, ces morceaux faisaient conclure à une
    suppression suivie de deux ajouts, sans différence mot à mot — soit
    l'inverse de ce que la page « Comparaison de versions » doit montrer.
    """
    from core.diff import compare

    v1 = pd.DataFrame({
        "section_id": ["art_5"], "section_label": ["Article 5"],
        "text": ["Article 5. Le détenteur met à disposition."]})
    v2 = pd.DataFrame({
        "section_id": ["art_5_1", "art_5_2"],
        "section_label": ["Article 5 (1/2)", "Article 5 (2/2)"],
        "text": ["Article 5. Le détenteur met à disposition sans délai.",
                 "Le destinataire justifie d'un intérêt légitime."]})

    deltas = compare(v1, v2)
    assert len(deltas) == 1
    assert deltas[0].status == "reformulation"
    assert deltas[0].section_label == "Article 5"      # sans le « (1/2) »
    assert deltas[0].inline_html                       # le diff mot à mot existe


def test_les_fragments_d_un_article_long_restent_groupes_dans_l_ordre():
    """art_5_1 se range juste après art_5, pas entre art_50 et art_51."""
    from core.store import _section_sort_key

    ordonne = sorted(["art_50", "art_5_2", "art_51", "art_5", "art_5_1",
                      "preambule", "rec_12"], key=_section_sort_key)
    assert ordonne == ["preambule", "art_5", "art_5_1", "art_5_2",
                       "art_50", "art_51", "rec_12"]


def test_les_contributions_francaises_ne_comptent_pas_comme_non_analysees():
    """La France est le référentiel : ses contributions ne sont jamais classées.

    Les compter parmi les « non analysées » affichait « 70 contributions non
    analysées sur 725 » sur une analyse pourtant complète.
    """
    import pandas as pd
    from core.fiabilite import positions

    df = pd.DataFrame(
        [{"ms_code": "FR", "stance": None, "confidence": None, "method": None,
          "text": "position française", "section_label": "Article 5"}] * 70
        + [{"ms_code": "DE", "stance": "aligned", "confidence": 0.9,
            "method": "llm", "text": "ok", "section_label": "Article 5"}] * 655)
    titres = [a.titre for a in positions(df, pd.DataFrame())]
    assert not any("non analysée" in t for t in titres)
