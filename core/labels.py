"""
Intitulés lisibles pour les contributions et les fragments d'article.

Le problème que ce module règle : « Article 5 » répété quatre fois dans une
liste, ou « Article 24 (2/12) », ne dit rien. L'agent doit déplier chaque ligne
pour savoir de quoi elle parle, et le numéro d'ordre du fragment — le (2/12) —
est un artefact du découpage, sans rapport avec la structure du texte.

Trois sources de précision, dans l'ordre de fiabilité :

1. **La référence écrite par la délégation elle-même.** Les commentaires du
   Conseil commencent presque toujours par la disposition visée : « Art. 5(2) »,
   « Article 5(2)(a) », « Recital 12 », « paragraph 3 ». C'est la source la plus
   sûre : c'est l'État membre qui la donne.
2. **Le sous-titre de l'article** dans un texte réglementaire.
3. **Les premiers mots du texte**, à défaut. Ce n'est pas une référence, mais
   cela suffit à distinguer quatre lignes les unes des autres — ce qui est le
   besoin réel.

Aucune de ces extractions n'invente : elles recopient ce qui est écrit.
"""

from __future__ import annotations

import re

# « Art. 5(2)(a) », « Article 5 (2) », « Art 5.2 », « Article 5(2) to (4) »
_PARAGRAPHE = re.compile(
    r"\bart(?:icle)?s?\.?\s*(\d+\s*(?:bis|ter|quater)?)\s*"
    r"[\(§]\s*(\d+[a-z]?)\s*\)?"
    r"(?:\s*\(\s*([a-z])\s*\))?",
    re.IGNORECASE)

# « Recital 12 », « recitals 12 and 13 », « considérant 12 »
_CONSIDERANT = re.compile(
    r"\b(?:recital|consid[ée]rant)s?\s*\(?(\d+[a-z]?)\)?", re.IGNORECASE)

# « paragraph 3 », « paragraphe 3 », « point (b) »
_PARAGRAPHE_SEUL = re.compile(
    r"\bparagraph[e]?\s*\(?(\d+[a-z]?)\)?", re.IGNORECASE)
_POINT = re.compile(r"\bpoint\s*\(?([a-z])\)?\b", re.IGNORECASE)

# Fragment produit par le découpage automatique : « Article 24 (2/12) ».
# Ce numéro d'ordre ne renvoie à rien dans le texte officiel.
_FRAGMENT = re.compile(r"\s*\((\d+)\s*/\s*(\d+)\)\s*$")

# Formules d'ouverture sans intérêt pour distinguer deux commentaires.
_BRUIT = re.compile(
    r"^(?:[-–•\s]*)(?:we\s+|our\s+delegation\s+|the\s+delegation\s+)?"
    r"(?:would\s+like\s+to\s+)?", re.IGNORECASE)


def reference_dans_texte(texte: str) -> str:
    """Référence de disposition citée par la délégation, si elle en donne une.

    Renvoie une chaîne courte — « § 2 », « § 2 (a) », « considérant 12 » — ou
    une chaîne vide. On ne regarde que le début du commentaire : une référence
    citée au milieu d'une phrase renvoie le plus souvent à un *autre* article.
    """
    tete = (texte or "")[:220]

    m = _PARAGRAPHE.search(tete)
    if m:
        lettre = f" ({m.group(3)})" if m.group(3) else ""
        return f"§ {m.group(2)}{lettre}"

    m = _CONSIDERANT.search(tete)
    if m:
        return f"considérant {m.group(1)}"

    m = _PARAGRAPHE_SEUL.search(tete)
    if m:
        return f"§ {m.group(1)}"

    m = _POINT.search(tete)
    if m:
        return f"point ({m.group(1)})"
    return ""


def apercu(texte: str, mots: int = 9) -> str:
    """Premiers mots du texte, nettoyés — de quoi distinguer deux lignes."""
    corps = _BRUIT.sub("", (texte or "").strip())
    corps = re.sub(r"\s+", " ", corps)
    decoupe = corps.split(" ")
    apercu_ = " ".join(decoupe[:mots])
    return apercu_ + ("…" if len(decoupe) > mots else "")


def preciser(section_label: str, texte: str, avec_apercu: bool = True) -> str:
    """Intitulé complet d'une contribution : article, disposition, aperçu.

    « Article 5 » devient « Article 5 § 2 » quand la délégation vise le
    paragraphe 2, et « Article 5 — "the scope should be limited…" » quand elle
    ne vise rien de précis.
    """
    base = label_fragment(section_label, texte)
    if avec_apercu and " : « " in base:
        # `label_fragment` a déjà mis l'aperçu dans l'intitulé : ne pas le
        # répéter une seconde fois à la fin.
        return base
    reference = reference_dans_texte(texte)
    if reference.startswith("considérant"):
        # Un commentaire qui vise un considérant ne vise pas l'article : on
        # remplace l'intitulé au lieu de l'accoler, sinon on lit « Article 5
        # considérant 12 », qui ne désigne rien.
        base = f"{base.split(' · ')[0]} → {reference}"
    elif reference and " à partir du " not in base:
        base = f"{base} {reference}"
    if avec_apercu:
        extrait = apercu(texte)
        if extrait:
            return f"{base} · « {extrait} »"
    return base


def label_fragment(section_label: str, texte: str) -> str:
    """Intitulé d'un fragment d'article produit par le découpage automatique.

    Remplace « Article 24 (2/12) », qui ne renvoie à rien, par la première
    disposition réellement contenue dans le fragment — « Article 24, à partir
    du § 3 » — et, à défaut, garde le numéro d'ordre en le disant clairement.
    """
    base = (section_label or "").strip()
    m = _FRAGMENT.search(base)
    if not m:
        return base
    racine = _FRAGMENT.sub("", base)
    rang, total = m.group(1), m.group(2)

    reference = reference_dans_texte(texte)
    if reference:
        return f"{racine}, à partir du {reference}"
    extrait = apercu(texte, mots=7)
    if extrait:
        return f"{racine} · extrait {rang}/{total} : « {extrait} »"
    return f"{racine} · extrait {rang}/{total}"


# Un intitulé d'article dans un texte réglementaire : la ligne qui suit
# « Article 5 », courte, sans point final, souvent en gras dans le PDF.
_SUJET_INTERDIT = re.compile(
    r"\b(shall|means|the commission|il est|le présent|for the purposes)\b",
    re.IGNORECASE)


def sujet_article(texte: str, maxi: int = 90) -> str:
    """Intitulé d'un article, lu dans le texte réglementaire lui-même.

    « Art. 111 » ne dit rien ; « Art. 111 — Interdictions réseaux de
    communication » se lit en réunion. Le sujet est la ligne qui suit
    immédiatement l'en-tête de l'article : courte, sans verbe conjugué, sans
    point final. Au moindre doute, on ne renvoie rien : un faux intitulé est
    pire que pas d'intitulé.
    """
    lignes = [ligne.strip() for ligne in (texte or "").split("\n") if ligne.strip()]
    for ligne in lignes[:3]:
        if re.match(r"^article\s+", ligne, re.IGNORECASE):
            continue
        if len(ligne) > maxi or ligne.endswith("."):
            continue
        if _SUJET_INTERDIT.search(ligne):
            continue
        if sum(c.isdigit() for c in ligne) > len(ligne) / 3:
            continue
        return ligne
    return ""
