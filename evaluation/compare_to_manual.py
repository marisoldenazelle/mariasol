"""Agreement between the tool's classification and a hand-coded matrix.

Why this script exists. The automated tests verify that the classification rules
are applied as specified. They say nothing about whether the specification
produces correct answers. The reference standard for that is an analyst coding
the same consolidated comments table by hand, and the only honest way to report
accuracy is to compare the two on the same corpus and publish the shape of the
disagreements.

Expected input: a CSV of the manual coding, one row per (article, member state)
cell that the analyst actually coded. Cells left blank are ignored rather than
counted as agreement — an analyst who did not code a cell has not agreed with
anything.

    section_label,ms_code,stance
    Article 5,DE,aligned
    Article 5,NL,divergent
    Article 14,SE,partial

Accepted spellings for `stance`, case-insensitive: aligned / aligné / 2,
partial / partiel / 1, divergent / opposé / opposed / 0.

    python evaluation/compare_to_manual.py --manual coded_by_hand.csv --doc-id wk_2026_01

What to read in the output. The headline agreement rate is the least interesting
number. What matters is the confusion matrix — which direction the errors go —
and the file of disagreeing cells, which is where the error analysis starts:
long contributions carrying several demands at once, oppositions expressed
without a marker, scrutiny reservations read as positions of substance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from core import store                                  # noqa: E402

# The tool stores stances as integers; the manual coding is written in words.
ECHELLE = {
    "aligned": 2, "aligne": 2, "aligné": 2, "2": 2,
    "partial": 1, "partiel": 1, "partially aligned": 1, "1": 1,
    "divergent": 0, "opposed": 0, "oppose": 0, "opposé": 0, "0": 0,
}
NOM = {2: "aligned", 1: "partial", 0: "divergent"}


def _normaliser(valeur) -> int | None:
    cle = str(valeur).strip().lower()
    return ECHELLE.get(cle)


def charger_manuel(chemin: Path) -> pd.DataFrame:
    df = pd.read_csv(chemin)
    manquantes = {"section_label", "ms_code", "stance"} - set(df.columns)
    if manquantes:
        raise SystemExit(f"colonnes absentes du fichier manuel : {manquantes}")
    df["code_manuel"] = df["stance"].map(_normaliser)
    inconnues = df[df["code_manuel"].isna()]["stance"].unique()
    if len(inconnues):
        raise SystemExit(f"valeurs de stance non reconnues : {list(inconnues)}")
    return df[["section_label", "ms_code", "code_manuel"]]


def charger_outil(doc_id: str, referentiel: str) -> pd.DataFrame:
    """The tool's matrix, flattened to one row per cell."""
    matrice = store.score_matrix(doc_id, referentiel=referentiel)
    if matrice is None or matrice.empty:
        raise SystemExit(f"aucune analyse enregistrée pour le document {doc_id}")
    plat = matrice.stack(future_stack=True).reset_index()
    plat.columns = ["section_label", "ms_code", "code_outil"]
    return plat.dropna(subset=["code_outil"])


def kappa(a: pd.Series, b: pd.Series) -> float:
    """Cohen's kappa — agreement corrected for chance.

    A raw agreement rate flatters any classifier facing an unbalanced
    distribution, and positions in a working party are unbalanced: most
    contributions align. Kappa is reported alongside it for that reason.
    """
    categories = sorted(set(a) | set(b))
    observe = (a.values == b.values).mean()
    attendu = sum((a == c).mean() * (b == c).mean() for c in categories)
    if attendu == 1:
        return float("nan")
    return (observe - attendu) / (1 - attendu)


def comparer(manuel: pd.DataFrame, outil: pd.DataFrame) -> pd.DataFrame:
    fusion = manuel.merge(outil, on=["section_label", "ms_code"], how="inner")
    fusion["code_outil"] = fusion["code_outil"].astype(int)
    fusion["code_manuel"] = fusion["code_manuel"].astype(int)
    fusion["accord"] = fusion["code_manuel"] == fusion["code_outil"]
    return fusion


def rapport(fusion: pd.DataFrame, manuel: pd.DataFrame,
            outil: pd.DataFrame) -> None:
    n = len(fusion)
    if not n:
        raise SystemExit("aucune cellule commune entre le codage manuel et "
                         "la sortie de l'outil : vérifiez les intitulés "
                         "d'article et les codes pays.")

    print(f"\nCellules codées à la main      : {len(manuel)}")
    print(f"Cellules produites par l'outil : {len(outil)}")
    print(f"Cellules comparables           : {n}")
    if len(manuel) > n:
        print(f"  ({len(manuel) - n} cellule(s) codée(s) à la main sans "
              "classement de l'outil : couverture incomplète, et c'est en "
              "soi un résultat)")

    accord = fusion["accord"].mean()
    k = kappa(fusion["code_manuel"], fusion["code_outil"])
    print(f"\nAccord brut                    : {accord:.1%}")
    print(f"Kappa de Cohen                 : {k:.3f}")

    print("\nAccord par classe (du point de vue du codage manuel)")
    for code in (2, 1, 0):
        lot = fusion[fusion["code_manuel"] == code]
        if len(lot):
            print(f"  {NOM[code]:<10} n={len(lot):4}   "
                  f"accord {lot['accord'].mean():.1%}")

    print("\nMatrice de confusion (lignes : manuel, colonnes : outil)")
    confusion = pd.crosstab(
        fusion["code_manuel"].map(NOM), fusion["code_outil"].map(NOM),
        rownames=["manuel"], colnames=["outil"], dropna=False)
    print(confusion.to_string())

    desaccords = fusion[~fusion["accord"]].copy()
    if len(desaccords):
        desaccords["manuel"] = desaccords["code_manuel"].map(NOM)
        desaccords["outil"] = desaccords["code_outil"].map(NOM)
        sortie = RACINE / "evaluation" / "disagreements.csv"
        desaccords[["section_label", "ms_code", "manuel", "outil"]].to_csv(
            sortie, index=False)
        print(f"\n{len(desaccords)} désaccord(s) écrits dans "
              f"{sortie.relative_to(RACINE)}")
        print("C'est ce fichier qu'il faut lire : le taux global ne dit pas "
              "où l'outil se trompe.")

        print("\nArticles les plus en désaccord")
        par_article = (desaccords.groupby("section_label").size()
                       .sort_values(ascending=False).head(8))
        for article, compte in par_article.items():
            total = (fusion["section_label"] == article).sum()
            print(f"  {article:<28} {compte}/{total}")


def main() -> int:
    parseur = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--manual", required=True, type=Path,
                         help="CSV of the hand-coded matrix")
    parseur.add_argument("--doc-id", required=True,
                         help="document identifier in the local store")
    parseur.add_argument("--reference", default="fr",
                         choices=("fr", "texte"),
                         help="reference frame the manual coding used")
    args = parseur.parse_args()

    manuel = charger_manuel(args.manual)
    outil = charger_outil(args.doc_id, args.reference)
    rapport(comparer(manuel, outil), manuel, outil)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
