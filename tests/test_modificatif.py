"""
Lecture d'un acte modificatif — omnibus et règlements « portant modification ».

Ce qui est protégé ici est la règle qui rendait la comparaison inutilisable :
un omnibus n'est pas une version du Data Act, et ses instructions doivent être
rangées par texte cible et par article cible. Deux points méritent d'être
cités : une instruction qu'on ne sait pas appliquer ne doit jamais être
présentée comme appliquée, et les paragraphes numérotés qui figurent DANS le
texte cité ne sont pas des instructions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.modificatif import (appliquer, celex_de,  # noqa: E402
                              comparer, est_acte_modificatif, lire)

OMNIBUS = """
Considérant (60) Le règlement (UE) 2023/2854 est modifié comme suit par ailleurs.
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. L'article 5 est remplacé par le texte suivant:
«Article 5
Le détenteur met les données à disposition sans délai.»;
2. À l'article 12, le paragraphe 2 est remplacé par le texte suivant:
«2. Le destinataire justifie d'un intérêt légitime.
3. Ce paragraphe ne fait pas obstacle au stockage.»;
3. L'article 20 est supprimé.
Article 2
Modifications du règlement (UE) 2016/679 (RGPD)
Le règlement (UE) 2016/679 est modifié comme suit:
1. À l'article 4, les points suivants sont ajoutés:
«32) “équipement terminal”, un équipement terminal au sens de la directive.»;
Article 3
Entrée en vigueur
Le présent règlement entre en vigueur le vingtième jour suivant sa publication.
"""


def _lecture():
    return lire([OMNIBUS])


def test_un_acte_modificatif_se_reconnait():
    assert est_acte_modificatif(OMNIBUS)
    assert not est_acte_modificatif(
        "Article 5. Le détenteur met les données à disposition.")


def test_les_modifications_sont_rangees_par_texte_cible():
    """C'est tout le sujet : l'omnibus modifie plusieurs textes à la fois."""
    res = _lecture()
    assert res.est_modificatif
    assert res.actes_cibles == ["règlement (UE) 2023/2854",
                                "règlement (UE) 2016/679"]
    # L'article « Entrée en vigueur » ne modifie aucun texte : il n'est pas
    # retenu comme bloc, sans quoi il inventerait un texte cible.
    assert len(res.blocs) == 2


def test_l_exposé_des_motifs_ne_produit_pas_de_modifications():
    """Les considérants citent les mêmes règlements et n'en modifient aucun."""
    res = _lecture()
    bloc = res.blocs[0]
    assert all("Considérant" not in m.instruction for m in bloc.modifications)


def test_chaque_modification_porte_son_article_cible_et_son_operation():
    bloc = _lecture().blocs[0]
    par_num = {m.numero: m for m in bloc.modifications}
    assert par_num["1."].article_cible == "Article 5"
    assert par_num["1."].operation == "remplacement"
    assert par_num["2."].article_cible == "Article 12"
    assert par_num["3."].operation == "suppression"


def test_les_paragraphes_du_texte_cite_ne_sont_pas_des_instructions():
    """« 3. Ce paragraphe ne fait pas obstacle… » est du texte, pas une consigne."""
    bloc = _lecture().blocs[0]
    assert len(bloc.modifications) == 3
    assert all("obstacle" not in m.instruction for m in bloc.modifications)


def test_celex_deduit_des_deux_ecritures():
    assert celex_de("règlement (UE) 2023/2854") == "32023R2854"
    assert celex_de("directive 2002/58/CE") == "32002L0058"
    assert celex_de("règlement (UE) nº 910/2014") == "32014R0910"


def _data_act() -> pd.DataFrame:
    return pd.DataFrame({
        "section_id": ["art_5", "art_12", "art_20", "art_30"],
        "section_label": ["Article 5", "Article 12", "Article 20", "Article 30"],
        "text": ["Article 5. Le détenteur met les données à disposition dans un "
                 "délai raisonnable.",
                 "Article 12. Conditions.\n1. Les conditions sont équitables.\n"
                 "2. Le destinataire paie une compensation.",
                 "Article 20. Micro-entreprises.",
                 "Article 30. Entrée en vigueur."]})


def test_le_texte_cible_est_reconstitue_article_par_article():
    bloc = _lecture().blocs[0]
    articles = {a.article: a for a in appliquer(bloc, _data_act())}

    # Remplacement d'un article entier : reconstitution exacte.
    assert articles["Article 5"].fiabilite == "exacte"
    assert "sans délai" in articles["Article 5"].texte_apres

    # Remplacement d'un paragraphe repérable par son numéro : exact aussi.
    assert articles["Article 12"].fiabilite == "exacte"
    assert "intérêt légitime" in articles["Article 12"].texte_apres
    assert "Les conditions sont équitables" in articles["Article 12"].texte_apres

    # Suppression : le texte d'arrivée est vide, et le statut le dit.
    assert articles["Article 20"].statut == "Supprimé"
    assert articles["Article 20"].texte_apres == ""


def test_un_article_non_touche_figure_quand_meme_marque_inchange():
    """Un article absent de la liste laisserait croire à un oubli."""
    bloc = _lecture().blocs[0]
    articles = {a.article: a for a in appliquer(bloc, _data_act())}
    assert articles["Article 30"].statut == "Inchangé"
    assert articles["Article 30"].texte_apres == articles["Article 30"].texte_avant
    assert not articles["Article 30"].modifications


def test_les_articles_sont_rendus_dans_l_ordre_du_texte():
    bloc = _lecture().blocs[0]
    ordre = [a.article for a in appliquer(bloc, _data_act())]
    assert ordre == ["Article 5", "Article 12", "Article 20", "Article 30"]


def test_deux_versions_d_un_omnibus_se_comparent_instruction_par_instruction():
    """La question posée : sur quels articles la présidence a-t-elle changé ?"""
    v1 = _lecture()
    compromis = OMNIBUS.replace("sans délai", "dans un délai de trente jours")
    compromis = compromis.replace("3. L'article 20 est supprimé.\n", "")
    v2 = lire([compromis])

    ecarts = {(e.acte_cible, e.article): e for e in comparer(v1, v2)}
    assert ecarts[("règlement (UE) 2023/2854", "Article 5")].statut == "modifiee"
    assert ecarts[("règlement (UE) 2023/2854", "Article 20")].statut == "retiree"
    assert ecarts[("règlement (UE) 2016/679", "Article 4")].statut == "identique"


# ---------------------------------------------------------------------------
# Caractérisation
# ---------------------------------------------------------------------------

class _FauxClient:
    """Client de modèle factice : retient ce qu'on lui donne à qualifier."""

    available = True

    def __init__(self):
        self.prompts: list[str] = []

    def structured(self, schema, system, user, **kw):
        from core.schemas import DeltaAnalysis

        self.prompts.append(user)
        return DeltaAnalysis(
            change_type="reformulation",
            summary_fr="Le délai de notification passe de 72 à 96 heures.",
            impact="majeur", affected_concepts=["notification", "délai"])


def test_la_caracterisation_porte_sur_une_modification_ecrite(monkeypatch):
    """Le modèle qualifie ce que le législateur a écrit, pas un rapprochement.

    C'est la différence avec la version qui comparait deux textes sans
    rapport : le résumé y était fluide et faux. Ici, l'instruction et le texte
    nouveau viennent du document, et ils sont dans le prompt.
    """
    import core.llm
    from core.modificatif import qualifier

    faux = _FauxClient()
    monkeypatch.setattr(core.llm, "get_client", lambda: faux)

    bloc = _lecture().blocs[0]
    art = {a.article: a for a in appliquer(bloc, _data_act())}["Article 5"]
    qualifier(art, bloc.acte_cible)

    assert art.impact == "majeur"
    assert "72 à 96" in art.resume
    prompt = faux.prompts[0]
    assert "Article 5" in prompt
    assert "est remplacé par le texte suivant" in prompt   # l'instruction
    assert "sans délai" in prompt                          # le texte nouveau
    assert "règlement (UE) 2023/2854" in prompt            # le texte cible


def test_un_article_non_touche_n_appelle_pas_le_modele(monkeypatch):
    import core.llm
    from core.modificatif import qualifier

    faux = _FauxClient()
    monkeypatch.setattr(core.llm, "get_client", lambda: faux)

    bloc = _lecture().blocs[0]
    art = {a.article: a for a in appliquer(bloc, _data_act())}["Article 30"]
    qualifier(art, bloc.acte_cible)

    assert art.impact == "nul"
    assert not faux.prompts


def test_sans_modele_les_instructions_restent_lisibles(monkeypatch):
    """Hors ligne, on n'invente rien : pas de résumé, pas de portée."""
    import core.llm
    from core.modificatif import qualifier

    class _Indisponible:
        available = False

    monkeypatch.setattr(core.llm, "get_client", lambda: _Indisponible())
    bloc = _lecture().blocs[0]
    art = {a.article: a for a in appliquer(bloc, _data_act())}["Article 5"]
    qualifier(art, bloc.acte_cible)
    assert art.resume == "" and art.impact == ""
    assert art.modifications                      # les instructions sont là


def test_sans_texte_cible_aucun_article_n_est_declare_insere():
    """L'absence de texte « avant » ne prouve rien : elle dit qu'on ne l'a pas.

    Sans cette règle, tous les articles d'un texte non chargé s'affichaient
    « Inséré » — y compris l'article 1 du Data Act, qui existe depuis 2023.
    """
    bloc = _lecture().blocs[0]
    sans_cible = {a.article: a for a in appliquer(bloc, None)}
    assert sans_cible["Article 5"].statut == "Modifié"     # remplacé, pas inséré
    assert sans_cible["Article 20"].statut == "Supprimé"   # l'instruction le dit

    avec_cible = {a.article: a for a in appliquer(bloc, _data_act())}
    assert avec_cible["Article 5"].statut == "Modifié"
    assert avec_cible["Article 20"].statut == "Supprimé"


def test_une_disposition_maintenue_n_est_pas_une_modification():
    """« Par dérogation, les dispositions suivantes continuent de s'appliquer »."""
    from core.modificatif import lire

    abrogation = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. L'article 5 est supprimé.
Article 2
Abrogations et dispositions transitoires
1. Le règlement (UE) 2019/1150 est abrogé avec effet au 1er janvier 2028.
2. Par dérogation au paragraphe 1, les dispositions suivantes continuent de
s'appliquer jusqu'au 1er janvier 2030:
(a) article 2, point 1);
(b) article 4;
"""
    bloc = lire([abrogation]).bloc("règlement (UE) 2019/1150")
    par_num = {m.numero: m for m in bloc.modifications}
    assert par_num["1."].operation == "abrogation"
    assert par_num["2."].operation == "maintien"
    # Le sous-point hérite de la nature de son instruction parente.
    assert par_num["2. (a)"].libelle_operation == "Maintien transitoire"


def test_retirer_un_point_ne_supprime_pas_l_article():
    """« À l'article 64, le point a) est supprimé » : l'article survit."""
    from core.modificatif import lire

    texte = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. À l'article 64, paragraphe 1, le point a) est supprimé.
2. L'article 20 est supprimé.
"""
    articles = {a.article: a for a in appliquer(lire([texte]).blocs[0], None)}
    assert articles["Article 64"].statut == "Modifié"
    assert articles["Article 20"].statut == "Supprimé"


def _segments(label, sid, texte):
    """Un DataFrame de segments minimal, comme en produit le corpus."""
    import pandas as pd
    return pd.DataFrame([{"section_label": label, "section_id": sid,
                          "text": texte, "section_kind": "article"}])


def test_suppression_d_un_point_se_voit_dans_le_texte_reconstitue():
    """« Le point c) est supprimé » doit retirer le point, pas ne rien faire.

    Sans cela, le texte « après » était identique au texte « avant » : rien
    n'apparaissait barré à l'écran alors que l'omnibus supprime bien quelque
    chose, et l'agent concluait que l'article n'était pas touché.
    """
    from core.modificatif import lire, appliquer

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. À l'article 5, le point c) est supprimé.
"""
    cible = ("Les données sont mises à disposition:\n"
             "a) sans délai;\n"
             "b) gratuitement;\n"
             "c) sous forme agrégée;\n"
             "d) de manière sécurisée.\n")
    bloc = lire([omnibus]).blocs[0]
    art = {a.article: a for a in
           appliquer(bloc, _segments("Article 5", "art_5", cible))}["Article 5"]

    assert "sous forme agrégée" in art.texte_avant
    assert "sous forme agrégée" not in art.texte_apres
    assert "gratuitement" in art.texte_apres and "sécurisée" in art.texte_apres
    assert art.fiabilite == "exacte"
    assert art.modifications[0].appliquee is True
    assert art.statut == "Modifié"


def test_suppression_d_un_paragraphe_entier():
    from core.modificatif import lire, appliquer

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. À l'article 7, le paragraphe 2 est supprimé.
"""
    cible = ("1. Premier paragraphe.\n"
             "2. Deuxième paragraphe, celui qui disparaît.\n"
             "3. Troisième paragraphe.\n")
    art = {a.article: a for a in appliquer(
        lire([omnibus]).blocs[0],
        _segments("Article 7", "art_7", cible))}["Article 7"]
    assert "celui qui disparaît" not in art.texte_apres
    assert "Troisième paragraphe" in art.texte_apres


def test_une_instruction_non_localisable_est_signalee_comme_telle():
    """Ce qui n'a pas pu être reporté doit se dire, instruction par instruction."""
    from core.modificatif import lire, appliquer

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. À l'article 9, les mots «dans un délai raisonnable» sont supprimés.
"""
    art = {a.article: a for a in appliquer(
        lire([omnibus]).blocs[0],
        _segments("Article 9", "art_9",
                  "Le détenteur répond dans un délai raisonnable."))}["Article 9"]
    assert art.modifications[0].appliquee is False
    assert art.fiabilite == "non_appliquee"
    assert art.texte_apres == art.texte_avant


def test_nom_d_usage_du_texte_modifie():
    """Le menu doit dire « RGPD », pas seulement « règlement (UE) 2016/679 »."""
    from core.modificatif import lire

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. L'article 5 est supprimé.
"""
    bloc = lire([omnibus]).blocs[0]
    assert bloc.nom_cible == "RGPD"
    assert bloc.libelle.startswith("RGPD · règlement (UE) 2016/679")


def test_un_paragraphe_insere_se_range_a_sa_place():
    """« 2 bis. » s'insère après le paragraphe 2, pas à la fin de l'article."""
    from core.modificatif import lire, appliquer

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. À l'article 5, le paragraphe suivant est inséré:
«2 bis. Le détenteur informe l'utilisateur sans délai.»
"""
    cible = ("1. Premier paragraphe.\n"
             "2. Deuxième paragraphe.\n"
             "3. Troisième paragraphe.\n")
    art = {a.article: a for a in appliquer(
        lire([omnibus]).blocs[0],
        _segments("Article 5", "art_5", cible))}["Article 5"]
    apres = art.texte_apres
    assert "sans délai" in apres
    assert apres.index("Deuxième") < apres.index("sans délai") < apres.index("Troisième")
    assert art.fiabilite == "exacte"


OMNIBUS_DEUX_TEXTES = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. À l'article 33, paragraphe 1, le texte est remplacé par le texte suivant:
«1. Le responsable notifie dans un délai de 96 heures.»
2. L'article 20 est supprimé.
Article 2
Modifications du règlement (UE) 2023/2854
Le règlement (UE) 2023/2854 est modifié comme suit:
1. À l'article 5, le point c) est supprimé.
"""


def test_synthese_transversale_d_un_omnibus():
    """La lecture de haut : combien de textes, d'articles, d'instructions."""
    from core.modificatif import lire, synthese

    syn = synthese(lire([OMNIBUS_DEUX_TEXTES]))
    assert syn.nb_textes == 2
    assert syn.nb_articles == 3
    assert syn.nb_instructions == 3
    assert syn.par_operation["Supprimé"] == 2
    assert [l.article for l in syn.par_texte["règlement (UE) 2016/679"]] \
        == ["Article 20", "Article 33"]      # ordre du texte cible, pas de l'acte
    assert syn.lignes[0].nom_cible == "RGPD"


def test_la_synthese_reprend_la_caracterisation_et_croise_les_notions():
    """Les notions communes à plusieurs textes font la lecture horizontale."""
    from core.modificatif import lire, synthese

    carac = {
        ("règlement (UE) 2016/679", "Article 33"):
            ("Le délai passe de 72 à 96 heures.", "majeur", ["délai de notification"]),
        ("règlement (UE) 2023/2854", "Article 5"):
            ("Un cas de mise à disposition disparaît.", "mineur",
             ["délai de notification"]),
    }
    syn = synthese(lire([OMNIBUS_DEUX_TEXTES]), carac)
    assert syn.caracterises == 2
    assert [l.article for l in syn.points_durs] == ["Article 33"]
    assert syn.par_impact == {"majeur": 1, "mineur": 1}
    notions = dict(syn.notions)
    assert len(notions["délai de notification"]) == 2   # deux textes différents


def test_la_carte_de_l_omnibus_porte_une_case_par_article():
    from core.modificatif import lire, synthese
    from core.ui import carte_modificatif

    html = carte_modificatif(synthese(lire([OMNIBUS_DEUX_TEXTES])),
                             par_impact=False)
    assert html.count('class="rw-case"') == 3
    assert "RGPD" in html and "Data Act" in html
    # Le HTML est écrit à la main : le texte des documents doit être échappé.
    assert "<script" not in html


def test_la_note_de_synthese_word_se_construit():
    from core.modificatif import lire, synthese
    from core.report import note_omnibus_docx

    carac = {("règlement (UE) 2016/679", "Article 33"):
             ("Le délai passe de 72 à 96 heures.", "majeur", ["délai"])}
    donnees = note_omnibus_docx("Omnibus numérique",
                                synthese(lire([OMNIBUS_DEUX_TEXTES]), carac),
                                version="test")
    assert donnees[:2] == b"PK"          # un .docx est une archive zip
    assert len(donnees) > 8000


def test_le_pied_de_page_du_journal_officiel_ne_pollue_pas_les_instructions():
    """« au paragraphe 2, les points suivants sont ajoutés: FR FR 23 »."""
    from core.ingest import _sans_pied_de_page

    page = ("au paragraphe 2, les points suivants sont ajoutés:\n"
            "FR FR\n23")
    assert _sans_pied_de_page(page).endswith("sont ajoutés:")
    # Un texte qui se termine vraiment par un nombre n'est pas amputé.
    assert _sans_pied_de_page("le délai est porté à 96 heures.\n96") \
        .endswith("\n96")


def test_une_portee_nulle_sur_un_article_touche_devient_redactionnelle(monkeypatch):
    """« nul » est réservé aux articles que l'acte ne touche pas."""
    import core.llm
    from core.modificatif import lire, appliquer, qualifier
    from core.schemas import DeltaAnalysis

    class _Faux:
        available = True

        def structured(self, modele, system, user, **kw):
            return DeltaAnalysis(change_type="reformulation",
                                 summary_fr="Coordination avec un autre texte.",
                                 impact="nul", affected_concepts=[])

    monkeypatch.setattr(core.llm, "get_client", lambda: _Faux())
    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. L'article 5 est remplacé par le texte suivant:
«Article 5 — nouveau texte.»
"""
    art = [a for a in appliquer(lire([omnibus]).blocs[0], None) if a.touche][0]
    assert qualifier(art, "RGPD").impact == "redactionnel"


def test_une_modification_en_fin_d_article_long_reste_visible():
    """Le plafond de 900 mots coupait la fin d'un article et masquait le changement.

    L'article premier du Data Act fait plusieurs milliers de mots ; les
    paragraphes que l'omnibus y ajoute arrivent à la fin. Avec un plafond, le
    rendu mot à mot n'affichait rien de changé — l'agent en concluait que
    l'article n'était pas touché.
    """
    from core.diff import rendu_mot_a_mot, ecart_hors_champ, ecart_mots

    avant = " ".join(f"mot{i}" for i in range(3000))
    apres = avant + " PARAGRAPHE AJOUTE PAR L OMNIBUS"

    assert ecart_hors_champ(avant, apres, 900)
    assert "PARAGRAPHE" not in rendu_mot_a_mot(avant, apres, max_mots=900)
    assert "PARAGRAPHE" in rendu_mot_a_mot(avant, apres, max_mots=None)
    assert ecart_mots(avant, apres) == (5, 0)


def test_le_rendu_condense_elide_les_passages_inchanges():
    """Trois mots changés dans dix mille ne se lisent pas dans un mur de texte."""
    from core.diff import rendu_mot_a_mot

    avant = " ".join(f"mot{i}" for i in range(400))
    apres = avant + " AJOUT FINAL"

    complet = rendu_mot_a_mot(avant, apres, max_mots=None, contexte=0)
    condense = rendu_mot_a_mot(avant, apres, max_mots=None, contexte=25)
    assert "AJOUT FINAL" in condense
    assert "[…]" in condense
    assert len(condense) < len(complet) / 3
    # Le début du texte n'est pas escamoté quand rien ne le précède.
    assert "mot0" not in condense or condense.index("mot0") < 200


def test_la_synthese_porte_le_texte_cite_par_chaque_instruction():
    """« les points suivants sont ajoutés: » ne veut rien dire sans les points."""
    from core.modificatif import lire, synthese

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2016/679
Le règlement (UE) 2016/679 est modifié comme suit:
1. À l'article 4, les points suivants sont ajoutés:
«30) “donnée synthétique”, une donnée produite par un modèle.»
"""
    ligne = synthese(lire([omnibus])).lignes[0]
    assert len(ligne.textes_nouveaux) == len(ligne.instructions)
    assert "donnée synthétique" in ligne.textes_nouveaux[0]


def test_une_coupure_du_rendu_est_ecrite_a_l_ecran():
    """Un rendu tronqué doit le dire : un silence ressemble à « rien n'a changé »."""
    from core.diff import rendu_mot_a_mot

    avant = " ".join(f"mot{i}" for i in range(200))
    apres = avant + " AJOUT"
    rendu = rendu_mot_a_mot(avant, apres, max_mots=50)
    assert "Rendu arrêté à 50 mots" in rendu
    assert "Rendu arrêté" not in rendu_mot_a_mot(avant, apres, max_mots=None)


def test_un_article_insere_avec_ordinal_latin_n_est_pas_rattache_au_precedent():
    """« L'article 18 bis suivant est inséré » crée un article, n'en modifie pas un.

    Le groupe du numéro absorbait l'espace qui le suivait, de sorte que
    l'ordinal ne trouvait plus l'espace qu'il exigeait : l'instruction était
    rattachée à l'article 18, c'est-à-dire à un article existant plutôt qu'à
    celui que l'acte crée. Défaut trouvé en fabriquant le corpus de
    démonstration.
    """
    from core.modificatif import lire

    omnibus = """
ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:
Article premier
Modifications du règlement (UE) 2024/1000
Le règlement (UE) 2024/1000 est modifié comme suit:
1. L'article 18, paragraphe 2, est remplacé par le texte suivant:
«2. Les autorités compétentes coopèrent.»
2. L'article 18 bis suivant est inséré:
«Article 18 bis
Comité européen des données»
3. L'article 32 novovicies est supprimé.
"""
    bloc = lire([omnibus]).blocs[0]
    vises = {m.numero: m.article_cible for m in bloc.modifications}
    assert vises["1."] == "Article 18"
    assert vises["2."] == "Article 18 bis"
    assert vises["3."] == "Article 32 novovicies"
    assert "Article 18 bis" in bloc.articles_touches
