"""
« Nos amendements ont-ils été retenus ? »

C'est la question qui suit toute publication d'un nouveau compromis, et elle
se pose article par article : la présidence a-t-elle repris la demande
française sur l'article 100 ? l'a-t-elle reprise à moitié ? l'a-t-elle
ignorée ? Et, plus largement : quelles délégations ont obtenu quelque chose
dans ce texte ?

Le calcul se fait en deux temps, et la séparation est le cœur du module.

**Premier temps, déterministe.** Certaines réponses ne demandent aucun
modèle : une délégation qui demandait la suppression d'un article qui a
effectivement disparu a obtenu gain de cause ; celle qui la demandait sur un
article toujours présent, non. Ces cas sont tranchés par comparaison des
structures, et ils sont marqués comme tels.

**Second temps, par le modèle.** Pour le reste — « clarifier le champ »,
« ajouter une condition de proportionnalité » — il faut lire le nouveau texte
et juger. Le modèle le fait sous la même contrainte que partout ailleurs :
**il doit recopier le passage du NOUVEAU texte qui fonde son verdict**, et ce
passage est vérifié par le programme. Sans citation retrouvée, le verdict
bascule en « indéterminé » plutôt que d'être affiché comme acquis.

Ce que le module ne prétend pas faire : dire *pourquoi* une demande a été
écartée, ni si la rédaction retenue satisfait juridiquement la délégation.
Cela reste le travail de l'agent — l'outil lui dit où regarder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
from pydantic import BaseModel, Field

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .qa import quote_matches

VERDICTS = {
    "retenue": "Reprise",
    "partielle": "Reprise partiellement",
    "ecartee": "Écartée",
    "indetermine": "Indéterminé",
}

VERDICT_COULEUR = {
    "retenue": "aligne", "partielle": "partiel",
    "ecartee": "oppose", "indetermine": "absent",
}

SYSTEM = """Tu compares UNE demande écrite d'un État membre au texte finalement retenu
pour l'article concerné, et tu dis ce qu'il en est advenu.

Barème :
- « retenue »     : la demande figure dans le nouveau texte, dans sa substance.
- « partielle »   : le nouveau texte va dans le sens de la demande sans
                    l'accueillir entièrement (condition ajoutée, portée réduite,
                    formulation atténuée).
- « ecartee »     : le nouveau texte ne comporte rien qui réponde à la demande,
                    ou retient la solution inverse.
- « indetermine » : le nouveau texte ne permet pas de trancher.

Règles impératives :
1. Tu juges UNIQUEMENT sur les deux textes fournis. Aucune connaissance
   extérieure, aucune supposition sur les intentions de la présidence.
2. Tu recopies MOT POUR MOT, depuis le NOUVEAU TEXTE, le passage qui fonde ton
   verdict. Si le verdict est « ecartee », recopie le passage du nouveau texte
   qui montre que la demande n'y est pas satisfaite.
3. Une citation reformulée est une erreur. Si aucun passage du nouveau texte ne
   fonde ton verdict, réponds « indetermine » et laisse la citation vide.
4. Tu expliques en une phrase, en français, factuelle, sans recommandation."""


class VerdictAmendement(BaseModel):
    verdict: str = Field(description="retenue | partielle | ecartee | indetermine")
    explication: str = Field("", max_length=400,
                             description="Une phrase factuelle, en français")
    quote: str = Field("", max_length=600,
                       description="Passage recopié depuis le NOUVEAU texte")


@dataclass
class Suivi:
    ms_code: str
    section_label: str
    demande: str                    # ce que la délégation demandait
    verdict: str = "indetermine"
    explication: str = ""
    citation: str = ""
    methode: str = "modèle"         # structure | modèle
    article_present: bool = True
    demandait_suppression: bool = False

    @property
    def verdict_fr(self) -> str:
        return VERDICTS.get(self.verdict, self.verdict)


@dataclass
class ResultatSuivi:
    suivis: list[Suivi] = field(default_factory=list)
    examines: int = 0
    sans_citation: int = 0
    erreurs: list[str] = field(default_factory=list)
    document_cible: str = ""

    def table(self) -> pd.DataFrame:
        if not self.suivis:
            return pd.DataFrame()
        return pd.DataFrame([{
            "EM": s.ms_code,
            "Article": s.section_label,
            "Ce qui était demandé": s.demande,
            "Sort de la demande": s.verdict_fr,
            "Pourquoi": s.explication,
            "Passage du nouveau texte": s.citation,
            "Méthode": s.methode,
        } for s in self.suivis])

    def taux(self) -> pd.DataFrame:
        """Taux de reprise par État membre — la lecture politique du texte."""
        if not self.suivis:
            return pd.DataFrame()
        lignes = []
        for code, groupe in pd.DataFrame(
                [s.__dict__ for s in self.suivis]).groupby("ms_code"):
            total = len(groupe)
            retenues = int((groupe["verdict"] == "retenue").sum())
            partielles = int((groupe["verdict"] == "partielle").sum())
            ecartees = int((groupe["verdict"] == "ecartee").sum())
            indetermines = int((groupe["verdict"] == "indetermine").sum())
            tranchees = total - indetermines
            lignes.append({
                "EM": code,
                "Demandes suivies": total,
                "Reprises": retenues,
                "Reprises partiellement": partielles,
                "Écartées": ecartees,
                "Indéterminées": indetermines,
                "Taux de reprise": round(
                    (retenues + 0.5 * partielles) / tranchees, 2)
                if tranchees else None,
            })
        return (pd.DataFrame(lignes)
                .sort_values("Taux de reprise", ascending=False,
                             na_position="last")
                .reset_index(drop=True))


_NUM = re.compile(r"(\d+)")
_SUPPRESSION = re.compile(
    r"\b(delet|suppress|supprim|should be removed|remove this article)",
    re.IGNORECASE)


# Nature de la section, lue dans l'intitulé. Sans elle, « Considérant 79 » et
# « Article 79 » donnaient la même clé « 79 » : une demande portant sur le
# considérant était jugée sur le texte de l'article, et une demande de
# suppression de considérant était tranchée « écartée — l'article est toujours
# présent » en citant un article sans rapport. Verdict faux, présenté comme
# déterministe : c'est le pire cas possible pour cet outil.
_NATURES = (
    ("rec", re.compile(r"\b(consid[ée]rant|recital)\b", re.IGNORECASE)),
    ("ann", re.compile(r"\b(annexe|annex)\b", re.IGNORECASE)),
    ("art", re.compile(r"\b(article|art\.)\b", re.IGNORECASE)),
)


def _cle_article(label: str) -> str:
    """Clé d'appariement entre deux documents : nature + numéro de section."""
    texte = str(label or "")
    nature = "art"
    for code, motif in _NATURES:
        if motif.search(texte):
            nature = code
            break
    m = _NUM.search(texte)
    if not m:
        return texte.strip().lower()
    return f"{nature}_{m.group(1)}"


def articles_cibles(segments: pd.DataFrame) -> dict[str, str]:
    """Texte du nouveau document, indexé par numéro d'article."""
    if segments is None or segments.empty:
        return {}
    cible: dict[str, str] = {}
    for _, row in segments.iterrows():
        cle = _cle_article(row.get("section_label"))
        texte = str(row.get("text") or "")
        if not cle:
            continue
        # Un article découpé en plusieurs fragments se recolle ici : le
        # verdict doit porter sur l'article entier, pas sur un morceau.
        cible[cle] = (cible.get(cle, "") + "\n" + texte).strip()
    return cible


def suivre(demandes: pd.DataFrame, segments_cible: pd.DataFrame,
           nom_cible: str = "", on_progress=None,
           max_demandes: int = 400) -> ResultatSuivi:
    """Confronte des demandes écrites au texte finalement retenu.

    `demandes` est une table de contributions — celles du tableau de suivi ou
    du tableau à trois colonnes. `segments_cible` sont les segments du texte
    de compromis publié ensuite.
    """
    res = ResultatSuivi(document_cible=nom_cible)
    if demandes is None or demandes.empty:
        return res

    cible = articles_cibles(segments_cible)
    if not cible:
        res.erreurs.append(
            "Le document d'arrivée ne contient aucun article exploitable.")
        return res

    client = get_client()
    modele_dispo = client.available
    if not modele_dispo:
        res.erreurs.append(
            "Aucun modèle configuré : seuls les cas tranchables par "
            "comparaison de structure (demandes de suppression) sont traités.")

    travail = demandes.head(max_demandes)
    total = len(travail)
    for i, (_, row) in enumerate(travail.iterrows(), start=1):
        label = str(row.get("section_label") or "")
        ms = str(row.get("ms_code") or "?")
        if on_progress:
            on_progress(i, total, f"{ms} · {label}")

        texte_demande = str(row.get("text") or "")
        resume = str(row.get("summary_fr") or "").replace(
            "[Classement lexical, non validé] ", "").strip()
        demande_lisible = (resume or texte_demande)[:300]

        cle = _cle_article(label)
        nouveau = cible.get(cle, "")
        suppression = bool(_SUPPRESSION.search(texte_demande[:400])) or bool(
            row.get("deletion"))

        suivi = Suivi(ms_code=ms, section_label=label,
                      demande=demande_lisible,
                      article_present=bool(nouveau),
                      demandait_suppression=suppression)

        # --- premier temps : ce que la structure suffit à trancher --------
        if suppression:
            suivi.methode = "structure"
            if not nouveau:
                suivi.verdict = "retenue"
                suivi.explication = (
                    "L'article demandé en suppression ne figure plus dans le "
                    "texte d'arrivée.")
            else:
                suivi.verdict = "ecartee"
                suivi.explication = (
                    "L'article est toujours présent dans le texte d'arrivée "
                    "alors que sa suppression était demandée.")
                suivi.citation = nouveau[:300]
            res.suivis.append(suivi)
            continue

        if not nouveau:
            suivi.methode = "structure"
            suivi.verdict = "indetermine"
            suivi.explication = (
                "Aucun article correspondant dans le texte d'arrivée, "
                "renumérotation probable, à vérifier à la main.")
            res.suivis.append(suivi)
            continue

        if not modele_dispo:
            suivi.verdict = "indetermine"
            suivi.explication = "Non évalué : modèle indisponible."
            res.suivis.append(suivi)
            continue

        # --- second temps : lecture du nouveau texte ----------------------
        user = (
            f"Article : {label}\n\n"
            f"DEMANDE ÉCRITE DE {ms} :\n\"\"\"{texte_demande[:3000]}\"\"\"\n\n"
            f"NOUVEAU TEXTE DE L'ARTICLE :\n\"\"\"{nouveau[:6000]}\"\"\"\n\n"
            "Qu'est devenue cette demande ?")
        try:
            verdict = client.structured(VerdictAmendement, SYSTEM, user,
                                        max_tokens=800)
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            res.erreurs.append(f"{ms} · {label} · {type(exc).__name__}")
            res.suivis.append(suivi)
            continue

        res.examines += 1
        citation = verdict.quote.strip()
        rendu = verdict.verdict.strip().lower()
        if rendu not in VERDICTS:
            rendu = "indetermine"

        if rendu != "indetermine" and not quote_matches(citation, nouveau):
            # Le verdict n'est pas adossé au texte d'arrivée : on ne l'affiche
            # pas comme acquis. C'est la même règle que pour les positions.
            res.sans_citation += 1
            suivi.verdict = "indetermine"
            suivi.explication = (
                "Verdict écarté : la justification n'a pas été retrouvée dans "
                "le texte d'arrivée. " + verdict.explication.strip())[:400]
        else:
            suivi.verdict = rendu
            suivi.explication = verdict.explication.strip()
            suivi.citation = citation
        res.suivis.append(suivi)

    return res
