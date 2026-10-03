"""
Regroupement des articles par titre du règlement.

Un texte européen se négocie titre par titre autant qu'article par article :
le Titre IV du CSA2 porte les chaînes d'approvisionnement, le Titre III la
certification, et ce sont deux discussions différentes, souvent traitées dans
des documents de travail distincts. L'agent doit pouvoir dire « montre-moi le
Titre IV » sans énumérer trente articles à la main.

Deux sources, dans cet ordre :

1. **Le texte réglementaire lui-même**, quand il est chargé : les en-têtes
   « TITRE IV — SÉCURITÉ DE LA CHAÎNE D'APPROVISIONNEMENT » y figurent entre
   les articles, et tout article qui suit appartient à ce titre jusqu'au
   suivant.
2. **La saisie manuelle**, sinon : l'agent renseigne les bornes (« Titre IV :
   articles 98 à 118 ») et l'outil range les articles dans l'intervalle.

Le rattachement n'est jamais deviné à partir du seul numéro d'article : deux
règlements différents numérotent différemment, et une erreur de titre fausse
tous les regroupements qui en dépendent.
"""

from __future__ import annotations

import re

import pandas as pd

# « TITRE IV », « TITLE IV », « CHAPITRE II », « CHAPTER II », suivis ou non
# d'un intitulé sur la même ligne ou la suivante.
# `[^\S\n]` = une espace qui n'est pas un saut de ligne : sans cette
# précaution, le séparateur avale le retour à la ligne et l'intitulé du titre
# happe la première ligne de l'article suivant.
_ENTETE_TITRE = re.compile(
    r"^[^\S\n]*(?P<mot>TITRE|TITLE|CHAPITRE|CHAPTER)[^\S\n]+"
    r"(?P<num>[IVXLC]+|\d+|premier|first)\b"
    r"[^\S\n]*[—\-–:.]?[^\S\n]*(?P<suite>[^\n]{0,90})?$",
    re.IGNORECASE | re.MULTILINE)

_NUM_ARTICLE = re.compile(r"(\d+)")


def _numero(label: str) -> int | None:
    """Numéro d'article contenu dans un intitulé, ou None."""
    m = _NUM_ARTICLE.search(str(label or ""))
    return int(m.group(1)) if m else None


def titres_depuis_texte(segments: pd.DataFrame) -> dict[str, str]:
    """Rattache chaque article au titre qui le précède dans le texte.

    `segments` est la table des segments d'un texte réglementaire, dans
    l'ordre du document. On lit les en-têtes de titre au fil du texte : tout
    article rencontré ensuite appartient au dernier titre vu.
    """
    if segments is None or segments.empty:
        return {}

    ordonnes = (segments.sort_values("section_order")
                if "section_order" in segments.columns else segments)

    rattachement: dict[str, str] = {}
    courant = ""
    for _, row in ordonnes.iterrows():
        texte = str(row.get("text") or "")
        # L'en-tête peut se trouver au début du segment d'article, parce que
        # le découpage attache l'en-tête à l'article qui le suit.
        for m in _ENTETE_TITRE.finditer(texte[:600]):
            mot = m.group("mot").upper()
            mot = "Titre" if mot in ("TITRE", "TITLE") else "Chapitre"
            suite = (m.group("suite") or "").strip(" —-–:.")
            courant = f"{mot} {m.group('num').upper()}"
            if suite and len(suite) > 3:
                courant += f", {suite.capitalize()}"
        label = str(row.get("section_label") or "")
        if courant and label:
            rattachement.setdefault(label, courant)
    return rattachement


def titres_depuis_bornes(bornes: dict[str, tuple[int, int]],
                         labels: list[str]) -> dict[str, str]:
    """Rattache par intervalles saisis à la main : {« Titre IV »: (98, 118)}."""
    rattachement: dict[str, str] = {}
    for label in labels:
        numero = _numero(label)
        if numero is None:
            continue
        for titre, (debut, fin) in bornes.items():
            if debut <= numero <= fin:
                rattachement[label] = titre
                break
    return rattachement


def bornes_depuis_rattachement(rattachement: dict[str, str]) -> dict[str, tuple]:
    """Bornes d'articles par titre — pour afficher « Titre IV : art. 98 à 118 »."""
    par_titre: dict[str, list[int]] = {}
    for label, titre in rattachement.items():
        numero = _numero(label)
        if numero is not None:
            par_titre.setdefault(titre, []).append(numero)
    return {t: (min(n), max(n)) for t, n in par_titre.items() if n}


def appliquer(df: pd.DataFrame, rattachement: dict[str, str],
              colonne: str = "section_label",
              defaut: str = "Titre non renseigné") -> pd.DataFrame:
    """Ajoute une colonne « Titre » à une table de contributions ou de scores."""
    if df is None or df.empty:
        return df
    sortie = df.copy()
    sortie["Titre"] = [rattachement.get(str(v), defaut) for v in sortie[colonne]]
    return sortie


def ordre_des_titres(titres: list[str]) -> list[str]:
    """Trie « Titre I, II, IV, X » dans l'ordre romain, pas alphabétique."""
    romains = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
               "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
               "XIV": 14, "XV": 15}

    def cle(titre: str) -> tuple:
        m = re.search(r"\b(TITRE|CHAPITRE)\s+([IVXLC]+|\d+)", titre, re.IGNORECASE)
        if not m:
            return (9, 999, titre)
        valeur = m.group(2).upper()
        rang = romains.get(valeur, int(valeur) if valeur.isdigit() else 999)
        return (0 if m.group(1).upper() == "TITRE" else 1, rang, titre)

    return sorted(dict.fromkeys(titres), key=cle)
