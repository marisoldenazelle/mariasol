"""Build a small, entirely synthetic corpus so the application can be run
without any credentials and without any restricted document.

Why this exists. The documents this tool was built for — consolidated comments
tables from Council working parties, presidency compromise texts — are not
public. A repository that cannot be run is a repository nobody evaluates. So
this script fabricates a miniature legislative world: a fictional regulation,
a fictional amending act ("omnibus") that modifies it, and a fictional table of
member state comments. Nothing here corresponds to a real text, a real
delegation or a real position.

Two things are genuinely exercised, and that is the point:

* the **amending-act reader** runs on a real PDF, parsed by the same
  deterministic code path as a real COM proposal. The drafting conventions
  reproduced below ("is amended as follows", numbered instructions, quoted new
  text in guillemets, Latin ordinals) are the ones the parser targets;
* the **position classification** runs in its offline, lexical mode, so the
  alignment matrix and the coalition arithmetic fill up with no model and no
  API key.

    python examples/make_demo_corpus.py
    streamlit run app.py

The database is written wherever REGWATCH_DB points, as usual. Pass --reset to
start from an empty one.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from core import store                                    # noqa: E402
from core.config import CORPUS_DIR                        # noqa: E402
from core.ingest import ingest                            # noqa: E402
from core.scoring import analyse_batch                    # noqa: E402
from core.wk_parser import Contribution                   # noqa: E402

# ---------------------------------------------------------------------------
# 1. A fictional regulation, as it would appear once consolidated
# ---------------------------------------------------------------------------

REGLEMENT_TITRE = ("RÈGLEMENT (UE) 2024/1000 DU PARLEMENT EUROPÉEN ET DU "
                   "CONSEIL du 14 mars 2024 relatif aux capteurs connectés "
                   "et à la circulation des données qu'ils produisent")

ARTICLES = {
    "Article premier": (
        "Objet et champ d'application\n"
        "1. Le présent règlement établit des règles harmonisées relatives à "
        "la mise à disposition des données produites par les capteurs "
        "connectés mis sur le marché de l'Union.\n"
        "2. Il s'applique aux fabricants de capteurs connectés, aux "
        "détenteurs de données et aux destinataires de données établis dans "
        "l'Union.\n"
        "3. Il ne s'applique pas aux capteurs utilisés exclusivement à des "
        "fins de défense ou de sécurité nationale.\n"),
    "Article 2": (
        "Définitions\n"
        "Aux fins du présent règlement, on entend par:\n"
        "1) «capteur connecté», un dispositif qui produit des données "
        "relatives à son environnement et les transmet par un réseau de "
        "communications électroniques;\n"
        "2) «détenteur de données», la personne physique ou morale qui a le "
        "droit ou l'obligation de mettre des données à disposition;\n"
        "3) «destinataire de données», la personne à laquelle des données "
        "sont mises à disposition.\n"),
    "Article 5": (
        "Mise à disposition des données\n"
        "1. Le détenteur de données met les données à la disposition du "
        "destinataire dans les conditions suivantes:\n"
        "a) sans délai injustifié;\n"
        "b) gratuitement pour l'utilisateur;\n"
        "c) sous une forme agrégée lorsque la demande le permet;\n"
        "d) de manière sécurisée et traçable.\n"
        "2. Le détenteur de données ne peut subordonner la mise à "
        "disposition à l'acceptation de conditions contractuelles abusives.\n"),
    "Article 7": (
        "Conditions contractuelles\n"
        "1. Une clause contractuelle est abusive lorsqu'elle s'écarte "
        "gravement des bonnes pratiques en matière d'accès aux données.\n"
        "2. Le présent article s'applique aux relations entre entreprises.\n"),
    "Article 9": (
        "Obligations des fabricants\n"
        "1. Le fabricant conçoit le capteur connecté de manière que les "
        "données produites soient accessibles par défaut à l'utilisateur.\n"
        "2. Le fabricant informe l'utilisateur, avant la conclusion du "
        "contrat, de la nature et du volume des données produites.\n"),
    "Article 11": (
        "Protection des secrets d'affaires\n"
        "1. Le détenteur de données peut refuser la mise à disposition "
        "lorsqu'elle compromettrait un secret d'affaires protégé.\n"
        "2. Le refus est motivé et notifié par écrit au destinataire.\n"),
    "Article 14": (
        "Notification des incidents\n"
        "1. Le détenteur de données notifie à l'autorité compétente tout "
        "incident affectant l'intégrité des données dans les meilleurs "
        "délais et, lorsque cela est possible, 72 heures au plus tard après "
        "en avoir pris connaissance.\n"
        "2. La notification précise la nature de l'incident, les catégories "
        "de données concernées et les mesures prises.\n"),
    "Article 16": (
        "Transferts vers les pays tiers\n"
        "1. Le détenteur de données prend des mesures raisonnables pour "
        "empêcher l'accès par les autorités d'un pays tiers lorsque cet "
        "accès serait contraire au droit de l'Union.\n"),
    "Article 18": (
        "Autorités compétentes\n"
        "1. Chaque État membre désigne une ou plusieurs autorités "
        "compétentes chargées de l'application du présent règlement.\n"
        "2. Les autorités compétentes coopèrent entre elles et avec la "
        "Commission.\n"),
    "Article 20": (
        "Interopérabilité\n"
        "1. Les exploitants d'espaces de données respectent les exigences "
        "essentielles d'interopérabilité fixées à l'annexe I.\n"),
    "Article 22": (
        "Sanctions\n"
        "1. Les États membres déterminent le régime des sanctions "
        "applicables aux violations du présent règlement.\n"
        "2. Les sanctions prévues sont effectives, proportionnées et "
        "dissuasives.\n"),
    "Article 25": (
        "Entrée en vigueur\n"
        "Le présent règlement entre en vigueur le vingtième jour suivant "
        "celui de sa publication au Journal officiel de l'Union "
        "européenne.\n"),
}

# ---------------------------------------------------------------------------
# 2. A fictional amending act, written the way the Union drafts them
# ---------------------------------------------------------------------------
#
# Every construction below is one the parser is meant to recognise: the
# dispositif marker, the per-target article heading, the chapeau, numbered
# instructions, lettered sub-instructions, quoted new text, an inserted
# article with a Latin ordinal, and a transitional survival clause.

OMNIBUS = """Proposition de RÈGLEMENT DU PARLEMENT EUROPÉEN ET DU CONSEIL
modifiant les règlements (UE) 2024/1000 et (UE) 2024/2000 en ce qui concerne
la simplification des obligations de déclaration (règlement omnibus de
démonstration)

COM(2026) 100 final

EXPOSÉ DES MOTIFS

La présente proposition vise à alléger les obligations déclaratives pesant sur
les détenteurs de données, sans revenir sur les droits reconnus aux
utilisateurs. Elle modifie à cette fin le règlement (UE) 2024/1000 et le
règlement (UE) 2024/2000.

ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:

Article premier
Modifications du règlement (UE) 2024/1000

Le règlement (UE) 2024/1000 est modifié comme suit:

1. L'article 5 est modifié comme suit:
(a) au paragraphe 1, le point c) est supprimé;
(b) au paragraphe 1, le point suivant est ajouté:
«e) dans un format lisible par machine, lorsque la nature des données le
permet.»;
(c) le paragraphe suivant est ajouté:
«3. Le détenteur de données publie, sur son site internet, les conditions
générales de mise à disposition des données.»

2. À l'article 14, le paragraphe 1 est remplacé par le texte suivant:
«1. Le détenteur de données notifie à l'autorité compétente tout incident
affectant l'intégrité des données dans les meilleurs délais et, lorsque cela
est possible, 96 heures au plus tard après en avoir pris connaissance.»

3. L'article 18, paragraphe 2, est remplacé par le texte suivant:
«2. Les autorités compétentes coopèrent entre elles, avec la Commission et
avec le comité européen des données institué par l'article 18 bis.»

4. L'article 18 bis suivant est inséré:
«Article 18 bis
Comité européen des données
1. Il est institué un comité européen des données, composé d'un représentant
par État membre.
2. Le comité conseille la Commission sur l'application cohérente du présent
règlement.»

5. L'article 22 est supprimé.

Article 2
Modifications du règlement (UE) 2024/2000

Le règlement (UE) 2024/2000 est modifié comme suit:

1. À l'article 4, les mots «dans un délai raisonnable» sont supprimés.

2. À l'article 7, le paragraphe 2 est supprimé.

Article 3
Abrogations et dispositions transitoires

1. La directive 2019/9999 est abrogée avec effet au 1er janvier 2029.
2. Par dérogation au paragraphe 1, les dispositions suivantes continuent de
s'appliquer jusqu'au 1er janvier 2031:
(a) article 3, point 2);
(b) article 6.

Article 4
Entrée en vigueur

Le présent règlement entre en vigueur le vingtième jour suivant celui de sa
publication au Journal officiel de l'Union européenne.
"""

# ---------------------------------------------------------------------------
# 3. A fictional consolidated comments table
# ---------------------------------------------------------------------------
#
# Positions are invented. They are written in the register of real working
# party comments — scrutiny reservations, drafting suggestions, outright
# opposition — so that the lexical classifier has something to bite on, and so
# that coalitions emerge rather than being drawn by hand.

ETATS = {
    "AT": "Autriche", "BE": "Belgique", "BG": "Bulgarie", "CY": "Chypre",
    "CZ": "Tchéquie", "DE": "Allemagne", "DK": "Danemark", "EE": "Estonie",
    "EL": "Grèce", "ES": "Espagne", "FI": "Finlande", "FR": "France",
    "HR": "Croatie", "HU": "Hongrie", "IE": "Irlande", "IT": "Italie",
    "LT": "Lituanie", "LU": "Luxembourg", "LV": "Lettonie", "MT": "Malte",
    "NL": "Pays-Bas", "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie",
    "SE": "Suède", "SI": "Slovénie", "SK": "Slovaquie",
}

# Three loose camps, so that blocs emerge from the positions rather than being
# drawn by hand. The grouping is invented for this fixture and carries no claim
# whatsoever about how these delegations behave in reality; it exists so that
# the coalition graph and the contentious-article scatter have something to
# show.
CAMPS = {
    "ouverture": ["NL", "SE", "DK", "IE", "FI", "EE", "LV", "LT", "CZ",
                  "LU", "MT"],
    "protection": ["FR", "DE", "IT", "ES", "AT", "BE", "PT", "SI", "EL", "CY"],
    "charge": ["PL", "HU", "RO", "BG", "SK", "HR"],
}
CAMP_DE = {code: camp for camp, codes in CAMPS.items() for code in codes}

# Per article: the subject in one phrase, and each camp's leaning. Some
# articles are consensual, some split the room — that contrast is the point of
# the contentious-article view.
ARTICLES_WK = {
    "Article premier": ("the scope of the Regulation",
                        {"ouverture": "support", "protection": "partial",
                         "charge": "support"}),
    "Article 2": ("the definitions, in particular 'data holder'",
                  {"ouverture": "support", "protection": "partial",
                   "charge": "partial"}),
    "Article 5": ("the conditions for making data available",
                  {"ouverture": "support", "protection": "oppose",
                   "charge": "oppose"}),
    "Article 7": ("the unfairness test for contractual terms",
                  {"ouverture": "partial", "protection": "support",
                   "charge": "oppose"}),
    "Article 9": ("the obligations placed on manufacturers",
                  {"ouverture": "support", "protection": "support",
                   "charge": "partial"}),
    "Article 11": ("the trade secrets exception",
                   {"ouverture": "oppose", "protection": "support",
                    "charge": "oppose"}),
    "Article 14": ("the incident notification deadline",
                   {"ouverture": "support", "protection": "oppose",
                    "charge": "support"}),
    "Article 16": ("safeguards against third-country access",
                   {"ouverture": "partial", "protection": "partial",
                    "charge": "partial"}),
    "Article 18": ("the creation of a European data board",
                   {"ouverture": "oppose", "protection": "support",
                    "charge": "partial"}),
    "Article 20": ("the interoperability requirements",
                   {"ouverture": "support", "protection": "support",
                    "charge": "support"}),
    "Article 22": ("the penalties regime",
                   {"ouverture": "support", "protection": "oppose",
                    "charge": "partial"}),
    "Article 25": ("entry into force and transitional periods",
                   {"ouverture": "support", "protection": "support",
                    "charge": "support"}),
}

# Wording drawn from the register of working party comments. The lexical
# classifier keys on these formulas, which is why the offline mode fills the
# matrix without any model.
FORMULES = {
    "support": [
        "{ms} supports the Commission proposal on {sujet}.",
        "{ms} welcomes the approach taken on {sujet} and can support the text "
        "as drafted.",
        "{ms} can support {sujet} as proposed.",
        "{ms} fully supports the text on {sujet}.",
    ],
    "oppose": [
        "{ms} does not support the proposal on {sujet}. The provision creates "
        "a disproportionate burden and should be deleted.",
        "{ms} cannot support {sujet} as drafted.",
        "{ms} opposes the approach retained on {sujet} and sees no added "
        "value in it.",
        "{ms} is not in a position to accept {sujet} in its current form.",
    ],
    "partial": [
        "{ms} can support {sujet} subject to clarification of the scope.",
        "{ms} supports the objective but would prefer a more precise wording "
        "on {sujet}.",
        "{ms} welcomes the provision; however, {ms} suggests aligning {sujet} "
        "with the wording used in related instruments.",
        "{ms} enters a scrutiny reservation on {sujet}.",
    ],
}

# Deterministic pseudo-randomness: the fixture must be identical on every
# machine, so no `random` module and no seed to forget.
def _tirage(code: str, article: str, modulo: int) -> int:
    graine = sum(ord(c) * (i + 7) for i, c in enumerate(code + article))
    return (graine * 2654435761) % modulo


def _positions() -> list[tuple[str, str, str, str]]:
    """(article, member state, kind, text) for the whole fictional table.

    Not every delegation speaks on every article — a real consolidated table is
    sparse, and a dense one would make agreement rates meaningless. Roughly a
    quarter of the cells are left empty, and about one delegation in seven
    departs from its camp, so that blocs are tendencies rather than blocks.
    """
    lignes = []
    for article, (sujet, tendances) in ARTICLES_WK.items():
        for code in sorted(ETATS):
            if _tirage(code, article, 100) < 26:        # silence
                continue
            penchant = tendances[CAMP_DE[code]]
            if _tirage(code, article + "dev", 100) < 14:   # dissidence
                autres = [p for p in ("support", "oppose", "partial")
                          if p != penchant]
                penchant = autres[_tirage(code, article + "alt", 2)]
            gabarits = FORMULES[penchant]
            texte = gabarits[_tirage(code, article + "f", len(gabarits))].format(
                ms=code, sujet=sujet)
            nature = "drafting" if penchant == "partial" and \
                _tirage(code, article + "k", 2) else "comments"
            lignes.append((article, code, nature, texte))
    return lignes


POSITIONS = _positions()


# ---------------------------------------------------------------------------
# Fabrication
# ---------------------------------------------------------------------------

def _pdf(chemin: Path, titre: str, corps: str) -> Path:
    """Writes a plain, text-layer PDF — the parser reads text, not layout."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    style = ParagraphStyle("corps", fontName="Helvetica", fontSize=10,
                           leading=13.5, spaceAfter=4)
    doc = SimpleDocTemplate(str(chemin), pagesize=A4,
                            leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=22 * mm, bottomMargin=20 * mm,
                            title=titre)
    histoire = []
    for ligne in corps.split("\n"):
        if not ligne.strip():
            histoire.append(Spacer(1, 6))
            continue
        histoire.append(Paragraph(ligne.replace("&", "&amp;")
                                  .replace("<", "&lt;"), style))
    doc.build(histoire)
    return chemin


def _texte_du_reglement() -> str:
    morceaux = [REGLEMENT_TITRE, "", "ONT ADOPTÉ LE PRÉSENT RÈGLEMENT:", ""]
    for titre, corps in ARTICLES.items():
        morceaux += [titre, corps, ""]
    return "\n".join(morceaux)


def construire(reset: bool = False) -> None:
    if reset:
        for doc_id in list(store.list_documents().get("id", [])):
            store.delete_document(doc_id)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    # --- the target regulation ---------------------------------------------
    cible = _pdf(CORPUS_DIR / "demo_reglement_2024_1000.pdf",
                 "Règlement (UE) 2024/1000 (fictif)", _texte_du_reglement())
    res = ingest(cible)
    store.register_document(
        "demo_reglement", "DEMO · Règlement (UE) 2024/1000 (fictif)",
        "Démonstration", store.file_sha256(cible), n=len(res.segments),
        kind="legal_text", n_segments=len(res.segments),
        version_kind="publie", version_date="2024-03-14", fichier=cible.name)
    store.save_segments("demo_reglement", res.segments)
    print(f"  règlement cible      : {len(res.segments)} segments")

    # --- the amending act ---------------------------------------------------
    acte = _pdf(CORPUS_DIR / "demo_omnibus_com_2026_100.pdf",
                "COM(2026) 100 (fictif)", OMNIBUS)
    res = ingest(acte)
    store.register_document(
        "demo_omnibus", "DEMO · Règlement omnibus · COM(2026) 100 (fictif)",
        "Démonstration", store.file_sha256(acte), n=len(res.segments),
        kind="legal_text", n_segments=len(res.segments),
        version_kind="proposition", version_date="2026-01-20",
        fichier=acte.name)
    store.save_segments("demo_omnibus", res.segments)
    print(f"  acte modificatif     : {len(res.segments)} segments")

    # --- the comments table -------------------------------------------------
    # Written straight to the store rather than through a PDF: the layout of a
    # real WK table is not public, and inventing one would demonstrate nothing.
    sections = {t: (f"art_{i}", i)
                for i, t in enumerate(ARTICLES_WK, start=1)}
    contributions = []
    for label, code, nature, texte in POSITIONS:
        sid, rang = sections[label]
        contributions.append(Contribution(
            document="DEMO · Commentaires consolidés (fictif)",
            section_id=sid, section_label=label, section_kind="article",
            ms_code=code, ms_name=ETATS[code], kind=nature, text=texte,
            page_start=rang, page_end=rang))
    store.register_document(
        "demo_wk", "DEMO · Commentaires consolidés des États membres (fictif)",
        "Démonstration",
        hashlib.sha256(b"demo_wk").hexdigest(), n=len(contributions),
        kind="wk_table", n_segments=len(contributions),
        version_kind="autre", version_date="2026-02-10")
    store.save_contributions("demo_wk", contributions)
    print(f"  commentaires         : {len(contributions)} contributions "
          f"· {len({c.ms_code for c in contributions})} États membres")

    # --- offline classification --------------------------------------------
    # No model, no key: the lexical classifier recognises the standard
    # formulas of working party comments. The matrix fills up, and every cell
    # is marked as heuristically derived on screen.
    lignes = store.load_contributions("demo_wk")
    cibles = lignes[lignes["ms_code"] != "FR"].to_dict("records")
    sortie = analyse_batch(
        cibles, {}, use_llm=False,
        save=lambda cid, a, m, mod: store.save_analysis(cid, a, m, mod))
    print(f"  classement hors ligne: {sortie.analysed} contributions, "
          f"{sortie.fallback} par heuristique lexicale")


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--reset", action="store_true",
                         help="empty the database first")
    args = parseur.parse_args()

    print("Fabrication du corpus de démonstration (entièrement fictif)")
    construire(reset=args.reset)
    print("\nTerminé. Lancez maintenant :  streamlit run app.py")
    print("Rien de ce corpus ne correspond à un texte, une délégation ou une "
          "position réels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
