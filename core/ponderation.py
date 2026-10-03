"""
Pondération d'un critère choisi par l'agent.

Le besoin, formulé en réunion : « je veux donner plus de poids aux positions
qui demandent aussi de supprimer l'intervention de la Commission dans tel
processus ». Autrement dit : toutes les divergences ne se valent pas, et
l'agent sait, lui, laquelle compte pour la négociation en cours.

Ce que fait ce module : l'agent écrit son critère **en français**, le modèle
dit pour chaque contribution si elle y correspond, et cette correspondance
devient un poids. Le poids ne change jamais le classement d'une position — DE
reste opposé sur l'article 100 — il change la manière dont les positions se
totalisent : proximité moyenne, cohésion d'un bloc, ordre des alliés.

Trois précautions, qui sont ce qui distingue une pondération défendable d'un
réglage arbitraire :

1. **Elle est optionnelle et explicite.** Rien n'est pondéré tant que l'agent
   n'a pas écrit un critère et lancé l'évaluation. Le résultat non pondéré
   reste consultable à côté.
2. **Chaque correspondance est justifiée par une citation vérifiée** dans le
   texte de la contribution, exactement comme un classement de position. Une
   correspondance dont la citation est introuvable est refusée.
3. **Le facteur est affiché**, et les livrables portent la mention du critère
   employé : une note produite sous pondération doit dire laquelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pydantic import BaseModel, Field

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .qa import quote_matches

SYSTEM = """Tu examines UNE contribution écrite d'un État membre et tu dis si elle
correspond à un critère donné par l'utilisateur.

Règles impératives :
1. Tu réponds UNIQUEMENT sur la base du texte fourni. Aucune connaissance
   extérieure, aucune supposition sur ce que l'État membre pense par ailleurs.
2. Si la contribution correspond au critère, tu recopies MOT POUR MOT le passage
   qui le montre. Une citation reformulée est une erreur.
3. Si elle n'y correspond pas, tu réponds correspond = false et tu laisses la
   citation vide. C'est une réponse fréquente et attendue.
4. Tu ne juges ni la pertinence ni la justesse du critère : tu constates."""


class Correspondance(BaseModel):
    correspond: bool = Field(description="La contribution correspond-elle au critère ?")
    quote: str = Field("", max_length=600,
                       description="Passage recopié mot pour mot, si elle correspond")


@dataclass
class ResultatPonderation:
    critere: str = ""
    facteur: float = 2.0
    correspondances: dict[int, str] = field(default_factory=dict)  # id → citation
    examinees: int = 0
    refusees: int = 0          # correspondance annoncée, citation introuvable
    erreurs: list[str] = field(default_factory=list)

    @property
    def retenues(self) -> int:
        return len(self.correspondances)

    def poids(self, contribution_id: int) -> float:
        return self.facteur if contribution_id in self.correspondances else 1.0


def evaluer(contributions: pd.DataFrame, critere: str, facteur: float = 2.0,
            on_progress=None) -> ResultatPonderation:
    """Évalue le critère sur chaque contribution, une par une.

    Un appel de modèle par contribution : c'est le même choix que pour le
    classement des positions, et pour la même raison — un modèle à qui l'on
    donne trente contributions d'un coup en oublie.
    """
    res = ResultatPonderation(critere=critere.strip(), facteur=float(facteur))
    if contributions is None or contributions.empty or not res.critere:
        return res

    client = get_client()
    if not client.available:
        res.erreurs.append(
            "Aucun modèle configuré : la pondération par critère en français "
            "demande le modèle. Le classement des positions, lui, reste "
            "disponible.")
        return res

    total = len(contributions)
    for i, (_, row) in enumerate(contributions.iterrows(), start=1):
        if on_progress:
            on_progress(i, total, f"{row.get('ms_code', '')} · "
                                  f"{row.get('section_label', '')}")
        texte = str(row.get("text") or "")
        if not texte.strip():
            continue
        user = (f"Critère : {res.critere}\n\n"
                f"Contribution de {row.get('ms_code', '?')} sur "
                f"{row.get('section_label', '?')} :\n\"\"\"{texte[:5000]}\"\"\"")
        try:
            verdict = client.structured(Correspondance, SYSTEM, user,
                                        max_tokens=500)
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            res.erreurs.append(f"{row.get('ms_code', '?')} · {type(exc).__name__}")
            continue
        res.examinees += 1
        if not verdict.correspond:
            continue
        citation = verdict.quote.strip()
        if not quote_matches(citation, texte):
            # Même exigence que partout ailleurs : sans citation retrouvée,
            # la correspondance n'est pas retenue.
            res.refusees += 1
            continue
        res.correspondances[int(row["id"])] = citation
    return res


def matrice_ponderee(contributions: pd.DataFrame,
                     resultat: ResultatPonderation) -> pd.DataFrame:
    """Matrice article × État membre pondérée par le critère.

    Le score d'une case reste 0, 1 ou 2 — la position ne change pas. Ce qui
    change, c'est le poids de cette case dans les moyennes : une contribution
    qui correspond au critère compte pour `facteur` contributions.
    """
    if contributions is None or contributions.empty:
        return pd.DataFrame()
    df = contributions[contributions["score"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    df["_poids"] = [resultat.poids(int(i)) for i in df["id"]]
    df["_pondere"] = df["score"] * df["_poids"]

    somme = df.pivot_table(index=["section_order", "section_label"],
                           columns="ms_code", values="_pondere", aggfunc="sum")
    poids = df.pivot_table(index=["section_order", "section_label"],
                           columns="ms_code", values="_poids", aggfunc="sum")
    matrice = somme / poids
    matrice.index = matrice.index.droplevel(0)
    return matrice


def classement_pondere(contributions: pd.DataFrame,
                       resultat: ResultatPonderation) -> pd.DataFrame:
    """Proximité moyenne avec la référence, pondérée — et l'écart au brut.

    La colonne « Écart » est celle qu'il faut regarder : elle dit ce que la
    pondération change, État membre par État membre. Un écart nul signifie que
    le critère ne discrimine pas cet État — l'information est utile.
    """
    if contributions is None or contributions.empty:
        return pd.DataFrame()
    df = contributions[contributions["score"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    df["_poids"] = [resultat.poids(int(i)) for i in df["id"]]
    lignes = []
    for code, groupe in df.groupby("ms_code"):
        brut = float(groupe["score"].mean())
        poids_total = float(groupe["_poids"].sum())
        pondere = (float((groupe["score"] * groupe["_poids"]).sum()) / poids_total
                   if poids_total else brut)
        touchees = int((groupe["_poids"] > 1).sum())
        lignes.append({
            "EM": code,
            "Score pondéré": round(pondere, 2),
            "Score brut": round(brut, 2),
            "Écart": round(pondere - brut, 2),
            "Contributions": len(groupe),
            "Dont retenues par le critère": touchees,
        })
    return (pd.DataFrame(lignes)
            .sort_values("Score pondéré", ascending=False)
            .reset_index(drop=True))
