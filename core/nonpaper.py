"""
Mettre à jour les positions depuis un non-paper, un papier blanc ou une note.

Toutes les positions n'arrivent pas dans un tableau à trois colonnes. Une
délégation diffuse un non-paper, une autre un papier blanc ; le bureau rédige
une note ministre ; un compte rendu de réunion rapporte qui a dit quoi. Ces
documents portent des positions aussi réelles que celles du tableau, et rien
ne permettait de les faire entrer dans la matrice.

**La méthode est en deux temps, et c'est délibéré.** L'outil lit le document,
en extrait les positions qu'il croit y voir, et propose pour chacune un
rattachement à un article — avec la citation du passage correspondant. Rien
n'entre dans la matrice avant validation par l'agent.

C'est plus lent qu'un enregistrement automatique. C'est le prix de la
fiabilité : une position mal rattachée fausse silencieusement toutes les
coalitions qui en dépendent, et personne ne s'en aperçoit avant la réunion.

Trois garde-fous, les mêmes que partout ailleurs :

- chaque position proposée porte une **citation vérifiée** dans le document ;
- l'article visé est celui que le texte cite explicitement quand il le fait ;
  sinon la proposition est marquée « rattachement incertain » ;
- la position enregistrée garde la **trace de sa source** — nom du document et
  type — pour être distinguable d'une contribution issue d'un tableau du
  Conseil.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pydantic import BaseModel, Field

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .qa import quote_matches
from .schemas import PositionAnalysis, Stance
from .wk_parser import MS_CODES, MS_NAMES

SYSTEM = """Tu lis un extrait d'un document de position, non-paper d'un État membre,
papier blanc, note interne, compte rendu de réunion, et tu en extrais les
positions exprimées sur des articles précis d'un texte européen en négociation.

Règles impératives :
1. Tu n'extrais QUE ce qui est écrit. Aucune interprétation, aucune déduction
   sur ce que l'auteur pense par ailleurs.
2. Pour chaque position : l'article visé tel que le texte le nomme (« Article
   100 », « art. 99(3) ») ou une chaîne vide si le texte ne le dit pas ; ce que
   l'auteur demande, en une phrase française factuelle ; et la citation
   LITTÉRALE du passage, recopiée mot pour mot.
3. Une citation reformulée est une erreur. Si tu ne peux pas recopier, n'extrais
   pas la position.
4. Tu qualifies la position : « demande de suppression », « demande de
   modification », « soutien », « réserve », « question ». Rien d'autre.
5. Un extrait qui n'exprime aucune position, contexte, formule de politesse,
   rappel de procédure, ne produit AUCUNE position. C'est fréquent et attendu."""

NATURES = {
    "suppression": ("demande de suppression", Stance.OPPOSE),
    "modification": ("demande de modification", Stance.PARTIEL),
    "soutien": ("soutien", Stance.ALIGNE),
    "reserve": ("réserve", Stance.OPPOSE),
    "question": ("question", Stance.NEUTRE),
}


class PositionExtraite(BaseModel):
    article: str = Field("", max_length=60,
                         description="Article visé, tel que le texte le nomme")
    nature: str = Field(
        "modification",
        description="suppression | modification | soutien | reserve | question")
    demande: str = Field(max_length=400,
                         description="Ce que l'auteur demande, en français")
    quote: str = Field(max_length=600,
                       description="Citation recopiée mot pour mot")


class Extraction(BaseModel):
    positions: list[PositionExtraite] = Field(default_factory=list,
                                              max_length=12)


@dataclass
class Proposition:
    """Une position proposée à la validation de l'agent."""

    ms_code: str
    article: str
    nature: str
    demande: str
    citation: str
    source: str = ""
    page: int = 0
    rattachement_sur: bool = True
    retenue: bool = True            # coché par défaut, décochable

    @property
    def stance(self) -> Stance:
        return NATURES.get(self.nature, ("", Stance.PARTIEL))[1]


@dataclass
class ResultatExtraction:
    propositions: list[Proposition] = field(default_factory=list)
    examines: int = 0
    sans_citation: int = 0
    erreurs: list[str] = field(default_factory=list)

    def table(self) -> pd.DataFrame:
        if not self.propositions:
            return pd.DataFrame()
        return pd.DataFrame([{
            "Retenir": p.retenue,
            "EM": p.ms_code,
            "Article": p.article,
            "Nature": NATURES.get(p.nature, (p.nature, None))[0],
            "Ce qui est demandé": p.demande,
            "Citation": p.citation,
            "Rattachement sûr": p.rattachement_sur,
        } for p in self.propositions])


# Les non-papers sont rédigés en anglais : chercher « Allemagne » dans un
# document intitulé « Non-paper from Germany » ne donne rien.
NOMS_ANGLAIS = {
    "Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES",
    "Netherlands": "NL", "Belgium": "BE", "Poland": "PL", "Sweden": "SE",
    "Denmark": "DK", "Austria": "AT", "Finland": "FI", "Ireland": "IE",
    "Portugal": "PT", "Greece": "EL", "Czechia": "CZ", "Czech Republic": "CZ",
    "Hungary": "HU", "Romania": "RO", "Bulgaria": "BG", "Croatia": "HR",
    "Slovakia": "SK", "Slovenia": "SI", "Estonia": "EE", "Latvia": "LV",
    "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT", "Cyprus": "CY",
}


def deviner_auteur(texte: str, defaut: str = "") -> str:
    """Code pays de l'auteur, deviné dans l'en-tête du document."""
    import re

    tete = (texte or "")[:800]
    for nom, code in NOMS_ANGLAIS.items():
        if re.search(rf"\b{re.escape(nom)}\b", tete, re.IGNORECASE):
            return code
    for code in MS_CODES:
        nom = MS_NAMES.get(code, "")
        if nom and nom.lower() in tete.lower():
            return code
    for code in MS_CODES:
        if re.search(rf"\b{code}\b", tete):
            return code
    return defaut


def extraire(segments: pd.DataFrame, ms_code: str, source: str = "",
             articles_connus: list[str] | None = None,
             on_progress=None, max_segments: int = 60) -> ResultatExtraction:
    """Propose des positions à partir des segments d'un document libre.

    Rien n'est enregistré ici : la fonction ne fait que proposer. C'est la
    page qui, après validation par l'agent, écrit dans la base.
    """
    res = ResultatExtraction()
    if segments is None or segments.empty:
        res.erreurs.append("Document vide ou non découpé.")
        return res

    client = get_client()
    if not client.available:
        res.erreurs.append(
            "Aucun modèle configuré : l'extraction depuis un texte libre "
            "demande le modèle. Vous pouvez saisir les positions à la main "
            "dans le tableau ci-dessous.")
        return res

    connus = {str(a).strip().lower() for a in (articles_connus or [])}
    travail = segments.head(max_segments)
    total = len(travail)

    for i, (_, row) in enumerate(travail.iterrows(), start=1):
        texte = str(row.get("text") or "")
        if on_progress:
            on_progress(i, total, str(row.get("section_label") or "")[:60])
        if len(texte.strip()) < 120:
            continue
        try:
            sortie = client.structured(
                Extraction, SYSTEM,
                f"Extrait du document « {source} » :\n\"\"\"{texte[:5000]}\"\"\"",
                max_tokens=1600)
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            res.erreurs.append(f"segment {i} · {type(exc).__name__}")
            continue
        res.examines += 1

        for pos in sortie.positions:
            citation = pos.quote.strip()
            if not quote_matches(citation, texte):
                # Sans citation retrouvée, la position n'est pas proposée :
                # elle ne serait pas vérifiable au moment de la validation.
                res.sans_citation += 1
                continue

            article = _normaliser_article(pos.article, pos.quote, texte)
            sur = bool(article) and (not connus or article.lower() in connus)
            res.propositions.append(Proposition(
                ms_code=ms_code,
                article=article or "Commentaires généraux",
                nature=(pos.nature or "modification").strip().lower(),
                demande=pos.demande.strip(),
                citation=citation,
                source=source,
                page=int(row.get("page_start") or 0),
                rattachement_sur=sur,
            ))
    return res


def _normaliser_article(brut: str, citation: str, texte: str) -> str:
    """« art. 100(2) » → « Article 100 ». Chaîne vide si rien de fiable."""
    import re

    for candidat in (brut, citation, texte[:300]):
        m = re.search(r"\bart(?:icle)?s?\.?\s*(\d+\s*(?:bis|ter|quater)?)",
                      str(candidat or ""), re.IGNORECASE)
        if m:
            return f"Article {m.group(1).strip()}"
    return ""


def en_contributions(propositions: list[Proposition], document: str):
    """Transforme les propositions validées en contributions enregistrables."""
    from .wk_parser import Contribution

    retenues = [p for p in propositions if p.retenue]
    contributions = []
    analyses = []
    for p in retenues:
        section_id = _section_id(p.article)
        contributions.append(Contribution(
            document=document, section_id=section_id,
            section_label=p.article, section_kind="article",
            ms_code=p.ms_code, ms_name=MS_NAMES.get(p.ms_code, p.ms_code),
            # Le type de contribution garde la trace de la source : une
            # position tirée d'un non-paper ne doit pas se confondre avec une
            # ligne d'un tableau du Conseil.
            kind="non-paper",
            text=f"[{p.source}] {p.citation}",
            page_start=p.page or 1, page_end=p.page or 1))
        analyses.append(PositionAnalysis(
            stance=p.stance,
            summary_fr=p.demande,
            evidence=p.citation,
            themes=[],
            is_scrutiny_reservation=(p.nature == "reserve"),
            proposes_deletion=(p.nature == "suppression"),
            confidence=0.7,
        ))
    return contributions, analyses


def _section_id(label: str) -> str:
    import re

    m = re.search(r"(\d+)\s*(bis|ter|quater)?", str(label or ""))
    if not m:
        return "general"
    suffixe = f"_{m.group(2)}" if m.group(2) else ""
    return f"art_{m.group(1)}{suffixe}"
