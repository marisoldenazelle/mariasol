"""
Estimation et affichage des durées.

Un traitement qui dure trois minutes est acceptable ; le même traitement sans
indication de durée ne l'est pas, parce que l'utilisateur ne sait pas s'il doit
attendre, relancer, ou fermer la fenêtre. C'est vrai partout dans l'outil :
analyse d'un lot de contributions, qualification d'un texte entier, examen des
passages d'une recherche.

Deux fonctions, volontairement pauvres :

- `duree_estimee` avant de lancer — ce que ça va coûter en temps ;
- `avancement` pendant — où on en est, et combien il reste, calculé sur le
  rythme réellement observé et non sur l'estimation initiale.

Les cadences par défaut sont des ordres de grandeur mesurés sur l'API Albert
avec un modèle de 24 milliards de paramètres. Elles dépendent de la charge du
service : l'estimation initiale peut se tromper d'un facteur deux, l'affichage
pendant le traitement se corrige tout seul.
"""

from __future__ import annotations

import time

# Secondes par unité traitée, mesurées sur Albert (mistral-small 24B).
CADENCE_ANALYSE = 3.0        # une contribution classée
CADENCE_QUALIFICATION = 4.0  # un article de texte qualifié (prompt plus long)
CADENCE_EXTRAIT = 3.0        # un passage examiné en recherche sourcée


def formater(secondes: float) -> str:
    """Durée en français, arrondie à ce que l'utilisateur peut utiliser."""
    if secondes < 45:
        return "moins d'une minute"
    minutes = secondes / 60
    if minutes < 60:
        return f"environ {round(minutes)} minute" + ("s" if round(minutes) > 1 else "")
    heures = minutes / 60
    if heures < 10:
        reste = round((heures - int(heures)) * 60)
        base = f"environ {int(heures)} h"
        return f"{base} {reste:02d}" if reste else base
    return f"environ {round(heures)} heures"


def duree_estimee(nombre: int, cadence: float = CADENCE_ANALYSE,
                  quoi: str = "") -> str:
    """Phrase d'annonce avant de lancer un traitement."""
    if nombre <= 0:
        return "Rien à traiter."
    total = nombre * cadence
    debut = f"**{quoi}**, " if quoi else ""
    if total < 45:
        return f"{debut}quelques secondes."
    return (f"{debut}{formater(total)}. Vous pouvez laisser la fenêtre "
            "ouverte et faire autre chose ; fermer l'onglet interrompt le "
            "traitement, mais tout ce qui a déjà été traité est enregistré.")


def avancement(fait: int, total: int, depart: float) -> str:
    """Texte de barre de progression, avec temps restant observé.

    Le rythme est recalculé à chaque pas : une estimation fondée sur ce qui
    vient de se passer vaut mieux qu'une moyenne théorique, surtout quand le
    service est chargé.
    """
    if total <= 0:
        return ""
    ecoule = max(time.time() - depart, 0.001)
    if fait <= 0:
        return f"0 / {total}"
    restant = (ecoule / fait) * (total - fait)
    if fait >= total:
        return f"{total} / {total} · terminé en {formater(ecoule)}"
    return f"{fait} / {total} · il reste {formater(restant)}"
