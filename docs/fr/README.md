# MARI(a)SOL

*Mapping d'Alignement Réglementaire par Intelligence Albert pour le Suivi
des Orientations Législatives* — Direction générale des entreprises.

Outil interne DGE de **négociation européenne** et de **cartographie des
régimes d'accès aux données**.

L'application ne connaît que les documents que vous y chargez. Elle ne complète
jamais avec des connaissances extérieures : si le corpus ne permet pas de
répondre, elle le dit.

Les guides de ce dossier existent aussi **en PDF**, dans `documentation/` :
présentation, installation, test d'usage, cadrage, architecture du code,
déploiement, recette, journal des versions. Commencez par
`0. Lisez-moi d'abord.pdf`, qui dit qui lit quoi.

Pour les régénérer après avoir modifié un fichier Markdown :

```bash
pip install -r requirements-dev.txt
python tools/build_docs.py
```

---

## Démarrage

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # y renseigner ALBERT_API_KEY
streamlit run app.py
```

Sans clé API, l'import, l'indexation, la recherche plein texte, la comparaison
de versions et tous les calculs de coalition restent pleinement fonctionnels.
Seules la rédaction des synthèses et la qualification fine des positions
demandent un modèle.

### Premier parcours

1. **Administration › Modèle** — tester la connexion, relever l'identifiant
   exact du modèle exposé et le reporter dans `.env`.
2. **Bibliothèque** — charger les documents. Le type est détecté, corrigible.
3. Puis l'outil qui correspond au besoin.

---

## Les huit outils

| Page | Ce qu'elle fait |
|---|---|
| **Mode d'emploi** | Par où commencer, les outils un par un, ce qui est garanti et ce qui ne l'est pas, questions fréquentes. |
| **Bibliothèque** | Import et gestion du corpus, récupération directe des textes publics depuis EUR-Lex. Découpage déterministe, indexation immédiate. |
| **Recherche** | « Qui a dit quoi sur tel sujet ? » Réponse rédigée dont chaque affirmation cite un passage vérifié, et répartition des occurrences par État membre. |
| **Positions des États membres** | Matrice d'alignement article par article avec la position française, classement des alliés, articles clivants — et les livrables Word et Excel. |
| **Coalitions** | Qui aller chercher pour ouvrir la négociation, blocs indépendants de la France, majorité qualifiée, minorités de blocage. |
| **Suivi des amendements** | Chaque demande écrite confrontée au texte publié : reprise, reprise partiellement, écartée — et le taux de reprise par délégation. |
| **Comparaison de versions** | Deux versions d'un texte, article par article : ce qui a changé mot à mot, la portée du changement, et trois cartes cliquables pour savoir par où commencer. |
| **Régimes d'accès** | Une situation d'entreprise, ce que disent les textes chargés disposition par disposition, et une fiche d'orientation Word. |

---

## Types de documents

| Type | Découpage | Attribution |
|---|---|---|
| Commentaires consolidés (WK, tableau à 2 ou 3 colonnes) | par article, puis par État membre | code pays lu dans le tableau |
| Texte réglementaire (proposition, compromis, règlement) | par article, préambule à part | aucune |
| Texte libre (non-paper, note de position, compte rendu) | par paragraphe, courts regroupés | auteur deviné depuis l'en-tête, corrigeable |

PDF et Word, plus la récupération HTML depuis EUR-Lex. Le découpage ne coupe
jamais au milieu d'un paragraphe : un extrait cité doit pouvoir être retrouvé
tel quel dans le document source.

Le type détecté à l'import est **corrigeable après coup** depuis l'onglet
Corpus : il conditionne les pages où le document apparaît, et la détection se
trompe régulièrement sur les textes consolidés.

**EUR-Lex : HTML, pas PDF.** Le PDF du Journal officiel est une mise en page —
deux colonnes, césures, en-têtes insérés dans le texte. Son extraction
introduit des écarts qui se comptent ensuite comme des modifications dans une
comparaison de versions : on compare alors deux extractions, pas deux textes.
Le HTML porte la structure des articles et donne un texte stable d'une version
à l'autre. En contrepartie, la pagination du JO est perdue — les numéros de
page des citations sont des repères internes, et le document importé le dit.

Le parser WK est validé sur les deux documents CSA2 de juillet 2026 :
1 278 contributions extraites, articles 3-70 et 71-97, 21 États membres.

---

## Ce qui est déterministe, ce qui ne l'est pas

| Étape | Nature | Composant |
|---|---|---|
| Découpage des documents | déterministe | `pdfplumber`, `python-docx`, expressions régulières |
| Index et recherche | déterministe | SQLite FTS5, local |
| Comparaison de versions | déterministe | `difflib`, mot à mot |
| Scores, matrices, coalitions, majorité qualifiée | déterministe | `pandas`, `networkx` |
| Synthèse d'une réponse | modèle contraint | schéma Pydantic, chaque affirmation citée et vérifiée |
| Qualification d'une position ou d'un changement | modèle contraint | schéma Pydantic, citation vérifiée dans la source |

Trois garde-fous, tous exécutés par le programme et non demandés au modèle :

- **Validation de schéma** — toute sortie non conforme est réinjectée avec
  l'erreur de validation, puis rejetée après épuisement des essais.
- **Vérification de citation** — une affirmation dont la citation ne se
  retrouve pas dans le texte source **n'est pas affichée**. L'interface
  indique combien d'affirmations ont été retirées.
- **Journal d'audit** — horodatage, modèle, empreinte SHA-256 du prompt,
  latence, conformité. Le contenu des prompts n'est jamais stocké.

### Pourquoi pas d'embeddings

La recherche repose sur un index plein texte local (SQLite FTS5), pas sur une
base vectorielle. Trois raisons : aucun texte ne sort pour être vectorisé — ce
qui compte sur des documents LIMITE ; un résultat lexical s'explique, on voit
quel terme l'a fait remonter ; et sur un corpus juridique, les recherches
portent souvent sur des termes exacts (« cyber posture », « art. 100 »,
« scrutiny reservation »), cas où le lexical vaut le vectoriel.

---

## Règles métier notables

**Le silence français vaut accord.** Sur un article que la France n'a pas
amendé, la référence est le maintien du texte initial en l'état. Un État
membre qui en demande la suppression ou la réécriture s'en écarte ; celui qui
l'accepte s'y aligne. Cette règle est ce qui permet de renseigner la matrice
sur l'ensemble des articles, et pas seulement sur ceux où la France s'est
exprimée par écrit. Elle est surchargeable article par article.

**Position la plus défavorable retenue.** Quand un État s'exprime plusieurs
fois sur le même article, c'est sa position la plus éloignée qui compte : une
objection ne s'annule pas par un commentaire de soutien ailleurs.

**Un silence n'est pas un accord entre deux États.** Le taux d'accord d'une
paire ne se calcule que sur les articles où les deux se sont exprimés.

---

## Structure

```
app.py                       point d'entrée : déclare la navigation
accueil.py                   page d'accueil
pages/                       les huit outils, un fichier par page
assets/                      marque et logo de l'application
core/
  config.py                  configuration par variables d'environnement
  schemas.py                 contrats Pydantic imposés au modèle
  llm.py                     client LLM sous contrainte + journal d'audit
  ingest.py                  ingestion universelle (3 familles de documents)
  wk_parser.py               extraction des tableaux WK du Conseil
  retrieval.py               index et recherche plein texte
  qa.py                      réponse sourcée, avec vérification des citations
  scoring.py                 qualification des positions, agrégations
  coalition.py               blocs, majorité qualifiée, minorités de blocage
  diff.py                    comparaison de versions
  eurlex.py                  récupération des textes publics (HTML, sans dépendance)
  labels.py                  intitulés précis : disposition visée, aperçu
  titres.py                  regroupement des articles par titre du règlement
  ponderation.py             pondération optionnelle d'un critère métier
  fiabilite.py               points d'attention, à l'écran seulement
  amendements.py             « nos amendements ont-ils été retenus ? »
  nonpaper.py                positions extraites d'un non-paper, à valider
  aide.py                    base de connaissance et assistant de l'outil
  duree.py                   estimation et affichage des durées
  palette.py                 les deux conventions de couleur, source unique
  ui.py                      explication en haut, méthode en bas
  store.py                   persistance SQLite
  viz.py                     restitutions Plotly interactives
  report.py                  figures PNG et documents Word
  excel.py                   classeur Excel : graphiques natifs et texte de détail
  modificatif.py             lecture d'un omnibus : instructions, reconstitution, synthèse
documentation/               les guides en PDF, produits par tools/build_docs.py
tools/build_docs.py      fabrique les PDF à partir des .md (dépendance de développement)
data/
  reference/populations.csv  populations pour le calcul de majorité qualifiée
  corpus/                    documents importés
  regwatch.sqlite3           base locale
attic/                       code non branché — voir attic/README.md
```

---

## Points d'attention avant mise en service

- **Populations** : `data/reference/populations.csv` porte des chiffres
  approchés. Les valeurs officielles sont fixées chaque année par décision du
  Conseil modifiant son règlement intérieur ; remplacez-les avant tout usage
  en négociation. L'écran Administration permet de les éditer.
- **Les positions écrites ne sont pas des votes.** Le calcul de majorité
  qualifiée dit ce que donnerait cette répartition si elle se transposait en
  vote — pas ce qui se passera.
- **Qualité de qualification** : à mesurer contre les matrices CSA2 faites à
  la main avant tout usage en note. C'est la seule vérité terrain disponible.

---

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `REGWATCH_LLM_PROVIDER` | `albert` | `albert` \| `openai_compatible` \| `offline` |
| `ALBERT_BASE_URL` | `https://albert.api.etalab.gouv.fr/v1` | endpoint compatible OpenAI |
| `ALBERT_API_KEY` | — | jeton d'authentification |
| `REGWATCH_LLM_MODEL` | — | identifiant exact du modèle exposé |
| `REGWATCH_LLM_TEMPERATURE` | `0.0` | à laisser à zéro |
| `REGWATCH_DB` | `data/regwatch.sqlite3` | base locale |
| `REGWATCH_AUDIT` | `1` | journal des appels au modèle |

L'API Albert suit les conventions de l'API OpenAI : le même client sert pour un
LLM interne ou un modèle exécuté en local.
