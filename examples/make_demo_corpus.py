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
    "Article 9": (
        "Obligations des fabricants\n"
        "1. Le fabricant conçoit le capteur connecté de manière que les "
        "données produites soient accessibles par défaut à l'utilisateur.\n"
        "2. Le fabricant informe l'utilisateur, avant la conclusion du "
        "contrat, de la nature et du volume des données produites.\n"),
    "Article 14": (
        "Notification des incidents\n"
        "1. Le détenteur de données notifie à l'autorité compétente tout "
        "incident affectant l'intégrité des données dans les meilleurs "
        "délais et, lorsque cela est possible, 72 heures au plus tard après "
        "en avoir pris connaissance.\n"
        "2. La notification précise la nature de l'incident, les catégories "
        "de données concernées et les mesures prises.\n"),
    "Article 18": (
        "Autorités compétentes\n"
        "1. Chaque État membre désigne une ou plusieurs autorités "
        "compétentes chargées de l'application du présent règlement.\n"
        "2. Les autorités compétentes coopèrent entre elles et avec la "
        "Commission.\n"),
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
    "FR": "France", "DE": "Allemagne", "NL": "Pays-Bas", "IT": "Italie",
    "ES": "Espagne", "PL": "Pologne", "SE": "Suède", "DK": "Danemark",
    "IE": "Irlande", "AT": "Autriche", "BE": "Belgique", "FI": "Finlande",
}

# (article, code État, nature, texte)
POSITIONS = [
    ("Article 5", "FR", "drafting",
     "FR considers that point (c) should be maintained. Aggregation is a "
     "safeguard for commercially sensitive data and its deletion is not "
     "acceptable as drafted."),
    ("Article 5", "DE", "comments",
     "DE supports the deletion of point (c) and welcomes the machine-readable "
     "format requirement."),
    ("Article 5", "NL", "comments",
     "NL supports the Commission proposal on this article."),
    ("Article 5", "IT", "drafting",
     "IT cannot support the deletion of point (c) and would prefer to keep "
     "the current wording."),
    ("Article 5", "ES", "comments",
     "ES can accept the proposal, subject to clarification of the term "
     "'machine-readable'."),
    ("Article 5", "PL", "comments",
     "PL does not support this amendment. The obligation to publish general "
     "conditions creates a disproportionate burden for SMEs."),
    ("Article 5", "SE", "comments",
     "SE welcomes the simplification and supports the text as drafted."),
    ("Article 5", "DK", "comments",
     "DK supports the proposal."),
    ("Article 5", "IE", "comments",
     "IE enters a scrutiny reservation on this article."),
    ("Article 5", "AT", "comments",
     "AT shares the concerns expressed by other delegations on the deletion "
     "of point (c) and cannot support it."),

    ("Article 14", "FR", "drafting",
     "FR proposes to retain the 72-hour deadline. Extending it to 96 hours "
     "weakens the supervision regime without demonstrated benefit."),
    ("Article 14", "DE", "comments",
     "DE supports the extension to 96 hours."),
    ("Article 14", "NL", "comments",
     "NL supports the extension, which aligns the deadline with other "
     "reporting obligations."),
    ("Article 14", "IT", "comments",
     "IT can accept the proposal."),
    ("Article 14", "ES", "drafting",
     "ES would prefer to keep 72 hours and does not support the extension."),
    ("Article 14", "PL", "comments",
     "PL supports the extension to 96 hours."),
    ("Article 14", "SE", "comments",
     "SE does not support the extension. The current deadline should be "
     "maintained."),
    ("Article 14", "DK", "comments",
     "DK enters a scrutiny reservation."),
    ("Article 14", "FI", "comments",
     "FI supports the Commission proposal."),
    ("Article 14", "BE", "comments",
     "BE can support the extension provided the content of the notification "
     "is unchanged."),

    ("Article 18", "FR", "comments",
     "FR welcomes the creation of the European data board and considers it "
     "essential to the consistent application of the Regulation."),
    ("Article 18", "DE", "comments",
     "DE supports the creation of the board."),
    ("Article 18", "NL", "comments",
     "NL questions the added value of a new body and would prefer to rely on "
     "existing cooperation structures. NL cannot support this article."),
    ("Article 18", "SE", "comments",
     "SE does not support the creation of an additional body."),
    ("Article 18", "DK", "comments",
     "DK shares the concerns of NL and SE on the proliferation of bodies."),
    ("Article 18", "IT", "comments",
     "IT supports the proposal."),
    ("Article 18", "ES", "comments",
     "ES supports the creation of the board."),
    ("Article 18", "PL", "comments",
     "PL enters a scrutiny reservation on the composition of the board."),

    ("Article 22", "FR", "drafting",
     "FR firmly opposes the deletion of Article 22. A regulation without a "
     "penalties regime cannot be enforced and this deletion should be "
     "withdrawn."),
    ("Article 22", "DE", "comments",
     "DE does not support the deletion of the penalties article."),
    ("Article 22", "IT", "comments",
     "IT opposes the deletion."),
    ("Article 22", "ES", "comments",
     "ES cannot accept the deletion of Article 22."),
    ("Article 22", "NL", "comments",
     "NL can accept the deletion, as penalties are governed by national law."),
    ("Article 22", "PL", "comments",
     "PL supports the deletion."),
    ("Article 22", "SE", "comments",
     "SE supports the simplification."),
    ("Article 22", "DK", "comments",
     "DK supports the deletion."),
    ("Article 22", "AT", "comments",
     "AT opposes the deletion of the penalties regime."),
    ("Article 22", "BE", "comments",
     "BE shares the concerns expressed by FR and DE and cannot support the "
     "deletion."),

    ("Article 9", "FR", "comments",
     "FR has no comment on this article."),
    ("Article 9", "DE", "comments",
     "DE supports the article as drafted."),
    ("Article 9", "FI", "comments",
     "FI supports the article."),
    ("Article 9", "IE", "comments",
     "IE can accept the article."),

    ("Article 2", "DE", "drafting",
     "DE proposes to clarify the definition of 'data holder' to exclude "
     "intermediaries acting on behalf of the user."),
    ("Article 2", "FR", "drafting",
     "FR proposes to align the definition of 'connected sensor' with the "
     "wording used in related instruments."),
    ("Article 2", "NL", "comments",
     "NL supports the definitions as drafted."),
    ("Article 2", "PL", "comments",
     "PL enters a scrutiny reservation on the definitions."),
]


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
    sections = {t: (f"art_{i}", i) for i, t in enumerate(
        ["Article 2", "Article 5", "Article 9", "Article 14",
         "Article 18", "Article 22"], start=1)}
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
