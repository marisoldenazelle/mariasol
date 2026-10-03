# mariasol

**Un instrument d'analyse de la négociation législative européenne, conçu sous
contrainte institutionnelle.**

Cartographier la position de vingt-sept États membres sur un projet de
règlement, article par article, se fait à la main : un analyste, un classeur,
plusieurs jours par tableau de commentaires consolidés. Quand la carte est
terminée, la présidence a diffusé un nouveau compromis.

Cet outil construit cette carte à partir des documents primaires, et rend
chaque case contestable sur pièce. Il a été écrit au sein d'une direction
ministérielle française pour ses propres négociateurs, sous des contraintes qui
sont la partie intéressante du problème : les documents ne quittent pas la
machine, l'arithmétique doit être refaisable à la main, et aucune affirmation
d'un modèle de langage ne tient sans une citation qu'un programme — et non le
modèle — a retrouvée dans la source.

**La présentation complète du projet est en anglais : [README.md](README.md).**

## La documentation d'origine, en français

Elle est dans [`docs/fr/`](docs/fr), et les neuf PDF de
[`docs/fr/pdf/`](docs/fr/pdf) sont les documents effectivement remis au service
avec l'application :

| Document | Pour qui |
|---|---|
| [Présentation générale](docs/fr/README.md) | Tout le monde |
| [Guide d'installation](docs/fr/DEMARRAGE.md) | Qui installe sur un poste |
| [Test d'usage en trente minutes](docs/fr/POUR_LES_TESTEURS.md) | L'agent qui essaie |
| [Note de cadrage](docs/fr/CADRAGE.md) | Qui décide |
| [Architecture du code](docs/fr/ARCHITECTURE.md) | Qui reprend, audite ou héberge |
| [Déploiement d'une instance partagée](docs/fr/DEPLOIEMENT_DEMO.md) | Le service hébergeur |
| [Protocole de recette](docs/fr/TEST.md) | Qui vérifie avant mise en service |
| [Journal des versions](CHANGELOG.md) | Ce qui a changé, et pourquoi |

## Lancer l'application

```bash
pip install -r requirements.txt
python examples/make_demo_corpus.py      # corpus de démonstration, entièrement fictif
streamlit run app.py
```

Sous Windows, un double-clic sur `demarrer.bat` suffit.
