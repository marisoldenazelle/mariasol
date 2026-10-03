# Protocole de test

Six manches, de la plus rapide à la plus exigeante. Chacune indique **ce que
vous devez obtenir** : si le chiffre ne tombe pas, quelque chose ne va pas, et
ça vaut mieux que de le découvrir dans une note.

Compter deux heures pour tout faire, dont beaucoup d'attente machine.

---

## Manche 1 — Import (5 min, aucun appel au modèle)

**Documents :** vos deux WK CSA2.

Bibliothèque → Importer. Dossier `CSA2`, détection automatique.

| Fichier | Attendu |
|---|---|
| `Commentaires consolidés EM 3 70 ENISA.pdf` | type « Commentaires consolidés », **728 segments**, 21 États membres |
| `Commentaires consolidés EM 71 97 ECCF.pdf` | type « Commentaires consolidés », **550 segments**, 18 États membres |

**Si le compte est très différent :** le format du document a changé, ou la
détection s'est trompée. Réimportez en forçant le type.

---

## Manche 2 — Recherche (10 min, premier vrai test du modèle)

**Rien à charger de plus.** C'est le test le plus rentable : une question, une
réponse, et vous voyez immédiatement si le modèle tient ses promesses.

Essayez, page Recherche, en mode **Réponse sourcée** :

1. `Qui a posé une réserve d'examen sur la certification de posture ?`
   → doit citer au moins DE, IT, ES. La FR figure dans les commentaires
   généraux.
2. `"cyber posture"` (avec les guillemets) en mode **Extraits bruts**
   → l'expression exacte, avec pages. Aucun appel au modèle.
3. `Quels États membres demandent la suppression de l'article 100 ?`
   → l'article 100 est dans le WK ENISA (art. 3-70)… il n'y est pas.
   **La bonne réponse est que le corpus ne permet pas de répondre.** Si le
   modèle invente une liste d'États, le garde-fou a échoué — dites-le-moi.

**Ce qu'il faut regarder :** sous chaque affirmation, la citation et sa
référence de page. Ouvrez le PDF à cette page et vérifiez que la phrase y est
vraiment. Faites-le trois fois. C'est le test qui décide si l'outil est
utilisable.

Regardez aussi l'avertissement « n affirmations retirées » s'il apparaît :
c'est le garde-fou qui travaille.

---

## Manche 3 — Positions et visualisations (30 min)

**Étape A — la référence française.** Page Positions → « Position française de
référence » → **Dériver les positions explicites**. Une minute. Vous devez
obtenir une dizaine d'articles marqués « ✓ explicite » sur le Titre III, le
reste en « · silence = accord ».

**Étape B — un échantillon d'abord.** Dans « Lancer l'analyse », limitez à
**3 articles** (par exemple Art. 73, 74, 86) et laissez le plafond à 40.
Comptez deux minutes.

Vérifiez tout de suite, onglet **Détail** : prenez trois lignes au hasard,
lisez le résumé et la citation, ouvrez le texte intégral. Le classement
aligné / partiel / opposé vous paraît-il juste ? Si non, arrêtez et
dites-le-moi : c'est une question de consigne, ça se corrige.

**Étape C — le lot complet.** Retirez les filtres, montez le plafond à 550.
Comptez 25 à 30 minutes. Vous pouvez fermer l'onglet du navigateur, le serveur
continue ; rouvrez `http://localhost:8501`.

**Étape D — les cinq visualisations.**

| Onglet | Ce que vous voyez | Ce qu'il faut y lire |
|---|---|---|
| Matrice d'alignement | Heatmap articles × États | Bleu = aligné, rouge = opposé. Une colonne très rouge = un adversaire constant |
| Alliés | Barres + répartition empilée | Le classement de proximité, et qui s'exprime beaucoup vs peu |
| Articles clivants | Nuage score × dispersion | En haut = article qui divise. **C'est là que se jouent les compromis** |
| Détail | Fiches filtrables | La preuve derrière chaque case |
| Export | Classeur xlsx + volume par EM | Ce qui part en note |

Les graphiques sont interactifs : survolez une case, une barre, un point.

---

## Manche 4 — Coalitions (10 min)

**Rien à charger.** Page Coalitions, une fois la manche 3 finie.

- **Blocs** : commencez au seuil 0,75, articles communs 3. Bougez le seuil et
  regardez les blocs se former et se défaire. Un seul gros bloc = seuil trop
  bas, l'app vous le dit.
- **Accords deux à deux** : la heatmap de toutes les paires. Cherchez les
  paires les plus proches — elles ne passent pas forcément par la France.
- **Arithmétique du Conseil** : sélectionnez un article dans « Pré-remplir
  depuis un article ». Les deux jauges montrent où vous en êtes des seuils
  55 % / 65 %, et le tableau des pivots dit quel ralliement ferait basculer un
  blocage.

**Avant d'en tirer quoi que ce soit :** Administration → Données de référence →
remplacez les populations par celles de l'annexe en vigueur du règlement
intérieur du Conseil. Celles livrées sont approchées.

---

## Manche 5 — Comparaison de versions (20 min)

**Documents à trouver.** Il vous faut deux versions du même texte. Deux
options, par ordre de facilité :

1. **Vos propres documents CSA2** — la proposition initiale de la Commission
   (5611/26) et le texte de compromis de la présidence. Si vous les avez sous
   la main, c'est le meilleur test : vous connaissez déjà les réponses.
2. **Data Act avant / après omnibus** — la proposition de novembre 2025 et le
   règlement (UE) 2023/2854 consolidé, tous deux sur EUR-Lex.

À l'import, choisissez le type **Texte réglementaire** et remplissez le
**repère de version** (« Compromis 1 — juin 2026 »). Sans ça vous ne saurez
plus lequel est lequel.

Puis page Comparaison : sélectionnez les deux, regardez le tableau, ouvrez
**Article par article** sur un article modifié. Le diff mot à mot montre en
rouge barré ce qui disparaît, en vert souligné ce qui arrive.

Enfin, **Qualifier** : le modèle dit si le changement est majeur, mineur ou
rédactionnel. Vérifiez son verdict sur deux ou trois articles dont vous
connaissez l'enjeu.

---

## Manche 6 — Régimes d'accès (20 min)

**Chargez les textes depuis EUR-Lex, sans quitter l'application** :
Bibliothèque → onglet **Depuis EUR-Lex** → choisissez un texte du catalogue →
*Récupérer*. C'est la version HTML qui est récupérée ; le découpage en articles
est meilleur qu'avec le PDF, et la comparaison de versions y gagne.

| Texte | CELEX |
|---|---|
| RGPD | `32016R0679` |
| Data Governance Act | `32022R0868` |
| Data Act | `32023R2854` |
| Directive Open Data | `32019L1024` |
| Règlement IA | `32024R1689` |

Si le réseau du ministère bloque la sortie directe, l'outil le dit et donne la
marche à suivre : ouvrir l'adresse dans le navigateur, enregistrer la page,
charger le fichier depuis l'onglet **Importer** en type « Texte réglementaire ».

**Vérifiez le découpage.** Dans l'onglet Corpus, le nombre de segments doit
correspondre à peu près au nombre d'articles du texte. Trois segments pour le
RGPD, c'est un échec de découpage — signalez-le.

**Si un texte n'apparaît pas là où vous l'attendez**, ce n'est plus bloquant :
la page Régimes d'accès propose désormais *tous* les documents du corpus, et
le type se corrige dans Bibliothèque → Corpus → *Type de document*.

Testez ensuite une situation réelle — startup, données non personnelles,
transports, réutilisation de données publiques — puis une situation que les
textes ne tranchent pas.

**Ce qu'il faut regarder :**

- les **dispositions applicables** citent-elles les bons articles ?
- quand aucune ne répond directement, les **éléments de contexte** sont-ils
  utiles, ou du remplissage ? C'est le point à me signaler en priorité : le
  seuil de pertinence de cette seconde lecture est réglable ;
- la **fiche d'orientation Word** est-elle envoyable telle quelle à une
  entreprise, après relecture ?

---

## Manche 7 — Livrables (15 min)

Depuis **Positions des États membres** → onglet **Export**, avec un périmètre
d'articles restreint (trois ou quatre articles, cinq États membres) :

1. **Classeur Excel.** Ouvrez-le dans Excel, pas dans l'aperçu. Vérifiez que
   les feuilles « Classement EM », « Articles clivants » et « Couverture »
   portent un graphique, et que modifier une valeur dans le tableau met le
   graphique à jour. La feuille « Détail » doit porter le texte de chaque
   contribution avec sa citation.
2. **Note Word.** Case *Inclure le texte de détail* cochée : la note doit se
   terminer par une partie en portrait, article par article, avec les
   citations et les pages.
3. **PNG.** Un fichier par figure, à insérer dans une note existante.

Le test qui compte : la note Word part-elle à votre chef de bureau sans
retouche de mise en forme ?

---

## Ce que ce protocole ne teste pas

**La justesse juridique du classement sur l'ensemble du corpus.** Pour ça, une
seule méthode : l'export xlsx de la manche 3, côte à côte avec votre
`CSA2_suivi_EM_MAJ_TitreIII`, article par article. Comptez les écarts,
regardez s'ils se concentrent sur un type d'article.

C'est fastidieux et c'est le seul test qui compte vraiment. Tant qu'il n'est
pas fait, l'outil sert à explorer, pas à conclure.

---

## Journal des anomalies

Notez ce qui cloche au fil de l'eau : la page, ce que vous attendiez, ce que
vous avez obtenu. Le journal d'audit (Administration → Journal d'audit) donne
le taux de conformité des appels et la latence médiane — utile si quelque chose
échoue en silence.
