"""
Schémas Pydantic : contrat de sortie imposé au LLM.

Principe méthodologique du projet : le modèle de langage n'est jamais
décisionnaire. Il ne produit que des structures typées et validées ; toute
sortie non conforme est rejetée, jamais interprétée.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Module 1 — Accès aux données
# ---------------------------------------------------------------------------

class ActorType(str, Enum):
    STARTUP_PME = "startup_pme"
    ETI_GE = "eti_grande_entreprise"
    CLOUD_PROVIDER = "fournisseur_cloud"
    INTERMEDIAIRE = "intermediaire_de_donnees"
    ORG_ALTRUISME = "organisation_altruisme_donnees"
    ORG_RECHERCHE = "organisme_recherche"
    ORGANISME_PUBLIC = "organisme_public"


class DataType(str, Enum):
    PERSONNELLE = "donnee_personnelle"
    PERSONNELLE_SENSIBLE = "donnee_personnelle_sensible"
    NON_PERSONNELLE = "donnee_non_personnelle"
    MIXTE = "jeu_mixte"
    PRODUIT_CONNECTE = "donnee_produit_connecte"


class Sector(str, Enum):
    SANTE = "sante"
    TRANSPORTS = "transports"
    ENERGIE = "energie"
    FINANCE = "finance"
    INDUSTRIE = "industrie"
    PUBLIC = "secteur_public"
    AUTRE = "autre"


class UseCase(str, Enum):
    REUTILISATION_PUBLIQUE = "reutilisation_donnees_publiques"
    ACCES_PRODUIT_CONNECTE = "acces_donnees_produit_connecte"
    PARTAGE_B2B = "partage_b2b"
    TRANSFERT_HORS_UE = "transfert_hors_ue"
    ENTRAINEMENT_IA = "entrainement_modele_ia"
    CHANGEMENT_FOURNISSEUR_CLOUD = "changement_fournisseur_cloud"


class QueryProfile(BaseModel):
    """Variables extraites d'une question en langage naturel.

    C'est l'unique sortie attendue du LLM dans le module 1 : une traduction,
    pas un raisonnement. Le régime juridique est ensuite déroulé par le graphe.
    """

    actor: ActorType | None = Field(None, description="Type d'acteur concerné")
    data_type: DataType | None = Field(None, description="Typologie de données")
    sector: Sector | None = Field(None, description="Secteur d'activité")
    use_case: UseCase | None = Field(None, description="Cas d'usage principal")
    third_country: bool = Field(
        False, description="Un transfert hors UE/EEE est-il en jeu ?"
    )
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Confiance du parseur sur l'extraction"
    )
    unresolved: list[str] = Field(
        default_factory=list,
        description="Variables que la question ne permet pas de trancher",
    )

    def missing(self) -> list[str]:
        return [
            name
            for name in ("actor", "data_type", "sector", "use_case")
            if getattr(self, name) is None
        ]


# ---------------------------------------------------------------------------
# Module 2 — Suivi des positions des États membres
# ---------------------------------------------------------------------------

class Stance(str, Enum):
    """Position d'un EM relativement à la position française de référence."""

    ALIGNE = "aligne"            # 2
    PARTIEL = "partiel"          # 1
    OPPOSE = "oppose"            # 0
    NEUTRE = "neutre"            # commentaire sans portée d'alignement
    ABSENT = "absent"            # pas de contribution


STANCE_SCORE: dict[str, int | None] = {
    Stance.ALIGNE.value: 2,
    Stance.PARTIEL.value: 1,
    Stance.OPPOSE.value: 0,
    Stance.NEUTRE.value: None,
    Stance.ABSENT.value: None,
}

STANCE_LABEL_FR = {
    Stance.ALIGNE.value: "Aligné",
    Stance.PARTIEL.value: "Partiel",
    Stance.OPPOSE.value: "Opposé",
    Stance.NEUTRE.value: "Neutre",
    Stance.ABSENT.value: "Sans contribution",
}


class PositionAnalysis(BaseModel):
    """Analyse structurée d'une contribution d'État membre.

    Le LLM ne « juge » pas : il remplit un formulaire dont chaque champ est
    contraint, et cite obligatoirement le passage qui fonde son classement.
    Sans citation vérifiable dans le texte source, l'analyse est rejetée.
    """

    stance: Stance = Field(description="Position relative à la référence française")
    summary_fr: str = Field(
        max_length=400, description="Résumé en français, 1 à 2 phrases, factuel"
    )
    evidence: str = Field(
        max_length=600,
        description="Citation littérale extraite du texte source justifiant le classement",
    )
    themes: list[str] = Field(
        default_factory=list, max_length=4, description="Enjeux abordés"
    )
    is_scrutiny_reservation: bool = Field(
        False, description="La contribution pose-t-elle une réserve d'examen ?"
    )
    proposes_deletion: bool = Field(
        False, description="La contribution demande-t-elle la suppression de l'article ?"
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("summary_fr", "evidence")
    @classmethod
    def _non_vide(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("champ obligatoire vide")
        return v.strip()

    @property
    def score(self) -> int | None:
        return STANCE_SCORE[self.stance.value]


class FrenchReference(BaseModel):
    """Position française de référence sur un article, déduite des contributions FR.

    La limite de longueur est large et le dépassement est tronqué plutôt que
    rejeté : sur un article où la France a beaucoup écrit, un résumé un peu
    long est un désagrément, pas une raison d'interrompre le traitement de
    tous les autres articles.
    """

    section_id: str
    summary_fr: str = Field(max_length=4000)
    key_asks: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("summary_fr", mode="before")
    @classmethod
    def _tronquer(cls, v):
        if isinstance(v, str) and len(v) > 4000:
            return v[:3997] + "…"
        return v


class DeltaAnalysis(BaseModel):
    """Comparaison de deux versions d'un même article (suivi omnibus / compromis)."""

    change_type: Literal["ajout", "suppression", "reformulation", "inchange"]
    summary_fr: str = Field(max_length=400)
    impact: Literal["majeur", "mineur", "redactionnel", "nul"]
    affected_concepts: list[str] = Field(default_factory=list, max_length=6)
