"""
Couleurs de l'application — une seule source, deux conventions.

Deux publics, deux besoins qui se contredisent :

- une **note de direction** se lit en vert / jaune / rouge, parce que c'est la
  convention interne et qu'un lecteur pressé la déchiffre sans légende ;
- un **écran** doit rester lisible pour les 8 % d'hommes et 0,5 % de femmes
  qui distinguent mal le rouge du vert. Sur une matrice de vingt-sept
  colonnes, l'erreur n'est pas rattrapable par le contexte.

D'où deux palettes, et un choix qui vaut pour toute l'application — écrans,
images PNG, note Word et classeur Excel. Le défaut est la palette accessible :
c'est celle qui n'exclut personne, et la convention de la direction reste à
un clic.

La forme reste porteuse d'information dans les deux cas : les symboles
+ / ~ / − doublent la couleur, de sorte qu'une impression en noir et blanc
garde son sens.
"""

from __future__ import annotations

PALETTES = {
    "accessible": {
        "nom": "Bleu / rouge, lisible en vision daltonienne",
        "aligne": "#1c5cab", "partiel": "#f0efec", "oppose": "#d03b3b",
        "absent": "#e8e7e2", "texte_fonce": True,
        # nuance intermédiaire, pour les empilements et les dégradés
        "aligne_clair": "#86b6ef", "partiel_ecran": "#9db8dc",
        # en-tête de tableau et colonne de référence, dans les classeurs
        "entete": "#1f3864", "entete_ms": "#2e4c7e", "reference": "#d6dce5",
    },
    # Reprise exacte des teintes du suivi tenu à la main : le classeur produit
    # par l'outil doit pouvoir se poser à côté du fichier existant sans que
    # l'œil ait à réapprendre le code couleur.
    "note": {
        "nom": "Vert / jaune / rouge, convention des notes de la direction",
        "aligne": "#63be7b", "partiel": "#ffeb84", "oppose": "#f8696b",
        "absent": "#d9d9d9", "texte_fonce": False,
        "aligne_clair": "#8fd08f", "partiel_ecran": "#f2df8a",
        "entete": "#1f3864", "entete_ms": "#2e4c7e", "reference": "#d6dce5",
    },
}

SYMBOLES = {2: "+", 1: "~", 0: "−"}

# Palette active pour le processus en cours. `app.py` la fixe au démarrage
# depuis le choix de l'utilisateur ; les modules de restitution la lisent au
# moment de dessiner, jamais à l'import — sans quoi le changement ne
# prendrait effet qu'au redémarrage.
_ACTIVE = "accessible"


def utiliser(nom: str) -> None:
    global _ACTIVE
    if nom in PALETTES:
        _ACTIVE = nom


def actif() -> str:
    return _ACTIVE


def couleurs(nom: str | None = None) -> dict:
    return PALETTES.get(nom or _ACTIVE, PALETTES["accessible"])


def diverging(nom: str | None = None) -> list[list]:
    """Échelle continue 0 → 2 pour les cartes de chaleur."""
    p = couleurs(nom)
    return [
        [0.0, p["oppose"]],
        [0.25, "#e88b8b" if _ACTIVE == "accessible" else "#f4a5a5"],
        [0.5, p["partiel"]],
        [0.75, p["aligne_clair"]],
        [1.0, p["aligne"]],
    ]
