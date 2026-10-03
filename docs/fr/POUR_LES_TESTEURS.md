# MARI(a)SOL — test d'usage, 30 minutes

Merci de tester cet outil interne. Il sert à deux choses : suivre les positions
des États membres sur un texte européen en négociation, et retrouver ce que
disent les textes chargés sur une question précise.

**Ce qu'on attend de vous :** trois manipulations, et vos impressions. Pas la
peine d'être exhaustif — ce qui coince chez vous nous intéresse plus que ce qui
marche.

---

## Installation — 10 minutes, une seule fois

1. **Python** doit être installé. Dans un terminal, tapez `python --version`.
   Si rien ne s'affiche : <https://www.python.org/downloads/>, et sur Windows
   **cochez « Add Python to PATH »**.
2. Décompressez le dossier reçu où vous voulez.
3. **Windows** : double-cliquez sur `demarrer.bat`.
   **Mac** : dans le terminal, `chmod +x demarrer.sh` puis `./demarrer.sh`.

La première fois, comptez deux à trois minutes d'installation. L'application
s'ouvre ensuite dans votre navigateur. Une fenêtre noire reste ouverte : c'est
le serveur, ne la fermez pas.

L'application tourne **entièrement sur votre poste**. Rien n'est envoyé nulle
part, sauf les appels au modèle si vous renseignez une clé.

**Avec ou sans clé API ?** Sans clé, l'import, la recherche par mots-clés et la
comparaison de textes fonctionnent déjà — c'est suffisant pour ce test. Si vous
avez une clé Albert, renseignez-la dans Administration → Modèle, et vous aurez
en plus les synthèses rédigées.

---

## Test 1 — Charger un document (5 min)

Page **Bibliothèque** → Importer. Prenez un document que vous connaissez bien :
un WK de commentaires consolidés, un texte de compromis, un non-paper. PDF ou
Word.

Vérifiez ensuite dans l'onglet **Corpus** que le nombre de segments est
cohérent avec le document.

> **À nous dire :** le type a-t-il été bien détecté ? Le découpage vous
> paraît-il juste ? Combien de temps a pris l'import ?

---

## Test 2 — Chercher quelque chose que vous savez déjà (10 min)

Page **Recherche**. Posez une question dont **vous connaissez la réponse** —
c'est tout l'intérêt : vous pouvez juger.

Exemples : « Qui s'oppose à tel mécanisme ? », « Quels États posent une réserve
d'examen sur tel sujet ? »

Deux modes :

- **Extraits bruts** — les passages, sans intervention du modèle. Mettez une
  expression entre guillemets pour une recherche exacte.
- **Réponse sourcée** — une synthèse rédigée, où chaque affirmation cite un
  passage vérifié dans le document. Une affirmation dont la citation est
  introuvable est retirée avant affichage : c'est le garde-fou de l'outil.

**Le point à vérifier :** ouvrez le document source à la page indiquée et
regardez si la phrase citée s'y trouve vraiment. Faites-le deux ou trois fois.

> **À nous dire :** l'outil a-t-il oublié un État membre que vous attendiez ?
> A-t-il affirmé quelque chose de faux ? Les citations sont-elles exactes ?

---

## Test 3 — Regarder les visualisations (10 min)

Si vous avez chargé un document de commentaires consolidés et une clé :
page **Positions des États membres** → dérivez la position française, puis
lancez l'analyse en la **limitant à deux ou trois articles** (les filtres sont
prévus pour ça).

Sinon, dites-le-nous et nous vous montrerons cette partie en direct.

Regardez la matrice d'alignement, le classement des alliés, les articles
clivants. Puis l'onglet **Export** : vous pouvez choisir les articles,
renommer les intitulés, et sortir une note Word modifiable.

> **À nous dire :** ces restitutions vous seraient-elles utiles dans une note ?
> Qu'est-ce qui manque ? Qu'est-ce qui est de trop ?

---

## Les questions qui nous intéressent le plus

1. **Sur quoi vous êtes-vous trompé de clic ?** Les endroits où l'interface
   n'est pas évidente comptent autant que les bugs.
2. **L'outil vous a-t-il fait gagner du temps**, ou avez-vous eu l'impression
   d'aller plus vite à la main ?
3. **Lui feriez-vous confiance pour une note ?** Si non, sur quel point
   précis ?
4. **Qu'est-ce qui manque** pour que vous l'utilisiez vraiment ?

En cas de message d'erreur, copiez-le en entier — c'est ce qui permet de
corriger vite.

---

## Deux précisions

**Vos données restent chez vous.** Chaque installation a sa propre base ; ce
que vous chargez n'est visible que par vous. L'application n'écoute que sur
votre machine et n'est accessible depuis aucun autre poste.

**Ce que l'outil ne fait pas :** il ne remplace pas une analyse juridique, et
il ne connaît que les documents que vous lui donnez. S'il ne peut pas répondre,
il le dit — c'est le comportement attendu, pas une panne.
