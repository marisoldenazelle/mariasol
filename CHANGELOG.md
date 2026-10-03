# Journal des versions

La version qui tourne réellement est affichée en bas du bandeau latéral de
l'application. Les dates des fichiers ne l'indiquent pas : un fichier garde la
date de sa dernière modification, pas celle de l'archive.

---

## 1.5.3 — 9 septembre 2026

Version de remise, allégée pour l'envoi.

Le dossier remis ne porte plus les sources Markdown des guides : elles font
double emploi avec les PDF de `documentation/`, et une même explication en
deux exemplaires finit toujours par diverger. Un `LISEZ-MOI.txt` en texte
brut, à la racine, renvoie vers `documentation/0. Lisez-moi d'abord.pdf` et
donne les trois lignes nécessaires pour lancer l'application.

Les sources Markdown et `outils/documentation.py` restent dans la copie de
développement : c'est là qu'on corrige un guide, et c'est de là qu'on
refabrique les PDF.

L'écran Administration ne renvoie plus à `POUR_LES_TESTEURS.md`, absent du
dossier remis, mais au dossier `documentation/`.

---

## 1.5.2 — 9 septembre 2026

Deux défauts vus à l'écran sur l'article premier du Data Act, tous deux du
même genre : l'outil montrait moins que ce qu'il avait, sans le dire.

### Le rendu mot à mot ne coupait plus la fin des articles longs

Le rendu « Le texte, avant et après » s'arrêtait à 900 mots. L'article premier
du Data Act en fait plusieurs milliers, et les paragraphes que l'omnibus y
ajoute arrivent à la fin : le rendu n'affichait donc **aucune modification**.
C'est le pire résultat possible, parce qu'il ressemble à un résultat — l'agent
en concluait que l'article n'était pas touché, alors que six instructions
portent sur lui.

Le rendu de l'onglet Omnibus ne plafonne plus du tout. Ailleurs, le plafond
passe de 900 à 4 000 mots, et **la coupure, quand elle survient, est écrite à
l'écran** au lieu de passer pour un texte inchangé.

### Un article long se lit maintenant en condensé

Trois passages modifiés dans dix mille mots ne se voient pas. Une bascule
« Ne montrer que les passages modifiés » remplace les longs passages inchangés
par « […] », en gardant vingt-cinq mots de contexte de part et d'autre. Elle
est active d'office dès que l'article dépasse le plafond ordinaire. Le compte
des mots ajoutés et retirés s'affiche sous le rendu : « +425 mots · −6 mots »
dit en une ligne s'il y a quelque chose à chercher.

### L'instruction et le texte qu'elle introduit ne sont plus séparés

Dans « Par où commencer », une instruction du type « au paragraphe 1, les
points suivants sont ajoutés: » s'affichait seule — deux points, puis rien.
Le texte cité entre guillemets figure désormais sous chaque instruction, à
l'écran comme dans la note de synthèse Word.

### Recette

116 tests. Quatre nouveaux portent précisément sur ces cas : une modification
placée au-delà du plafond doit rester visible, le rendu condensé doit élider
sans perdre le changement, une coupure doit s'écrire, et chaque instruction
doit porter le texte qu'elle cite.

---

## 1.5.1 — 9 septembre 2026

Version de remise. Quatre corrections tirées de la lecture des écrans, et la
documentation en PDF.

### Le pied de page du Journal officiel ne pollue plus les instructions

Le PDF d'un document COM porte en bas de chaque page « FR FR » et le numéro.
L'extraction le collait à la dernière phrase de la page, et cette phrase est
souvent une instruction de modification : l'écran affichait « au paragraphe 2,
les points suivants sont ajoutés: FR FR 23 ». Le pied part maintenant à la
lecture, pour tous les modules à la fois.

### « nul » ne s'affiche plus sur un article modifié

L'étiquette voulait dire deux choses à deux lignes d'écart : « cet article
n'est pas touché » et « le modèle juge que rien ne change en droit ». La
seconde se dit désormais « rédactionnel », qui est la case prévue pour cela.

### La qualification de portée est resserrée

Sur la proposition d'omnibus numérique, 30 articles sur 36 ressortaient
« majeurs ». Une liste de points durs qui reprend presque tout ne hiérarchise
plus rien. La consigne donnée au modèle exige maintenant que la modification
**crée, supprime ou déplace** une obligation, un droit, un seuil, une
compétence ou un délai, et qu'il puisse nommer ce qui change pour qui ; le fait
qu'une disposition mentionne un délai ne suffit plus. Elle lui demande aussi,
quand une valeur chiffrée change, de donner la valeur avant et après et de dire
si elle augmente ou diminue.

L'écran ne fait pas confiance à cette consigne pour autant : si les articles
majeurs dépassent 60 % des articles caractérisés, un avertissement le dit et
renvoie aux instructions verbatim.

### Détails d'affichage

Les résumés tronqués dans les intitulés se coupent sur un mot entier. La
colonne « Texte » de la charge par texte est élargie.

### La documentation est fournie en PDF

Neuf documents dans `documentation/`, produits par `outils/documentation.py`
depuis les sources Markdown : « Lisez-moi d'abord », présentation générale,
guide d'installation, test d'usage, note de cadrage, **architecture du code**,
déploiement, protocole de recette, journal des versions. Charte graphique de
l'application, couverture, pagination et numéro de version en pied de page.

**« Architecture du code » est nouveau.** Il dit ce que fait chaque fichier de
`core/` et de `pages/`, pourquoi il existe, quelles dépendances sont employées
et pour quelle raison, et ce qu'il faut savoir avant d'y toucher. Il s'adresse
à qui doit reprendre, auditer ou héberger l'application.

La source reste en Markdown : un diff de Markdown se lit, un diff de .docx
non. Le PDF est ce qu'on envoie.

---

## 1.5.0 — 9 septembre 2026

L'onglet Omnibus devient utilisable par quelqu'un qui reçoit le dossier et
doit en rendre compte, et non plus seulement par quelqu'un qui sait déjà quoi
y chercher.

### Trois vues au lieu d'une liste

Jusqu'ici l'onglet posait une seule question : « que fait cet acte au texte
que vous avez choisi ». C'est la question de la deuxième heure de travail, pas
de la première. L'onglet se lit maintenant en trois vues, sur un seul niveau,
sans menu replié.

**Vue d'ensemble.** La *carte de l'acte* tient dans un écran : une ligne par
texte modifié, une case par article touché, colorée par portée quand la
caractérisation a tourné, par opération sinon. L'exposant donne le nombre
d'instructions, l'infobulle le résumé et la page. À côté, la charge par texte
et le compte des opérations : combien de suppressions, d'insertions, de
remplacements, et dans quel règlement.

**Par où commencer.** La liste des articles dont la modification touche une
obligation, un champ d'application, un seuil, une compétence, une sanction ou
un délai, chacun avec ses instructions verbatim. C'est la liste qu'on porte
dans une note.

**Ce qui revient d'un texte à l'autre.** Les notions modifiées dans plusieurs
textes à la fois. C'est la lecture propre à un omnibus, et elle n'existait
nulle part : elle dit quels dossiers, tenus par des bureaux différents, sont
touchés par la même idée.

**Toutes les modifications**, dans un tableau filtrable par texte, par portée,
et par recherche libre dans les instructions.

### Une seule passe de caractérisation

Il fallait ouvrir les dix textes cibles l'un après l'autre et cliquer dix
fois. Un bouton « Caractériser tout l'omnibus » traite l'acte entier, en
retrouvant tout seul le texte consolidé de chaque cible quand il est au
corpus. Ce qui est caractérisé sert partout : la carte, la note, le classeur,
la lecture texte par texte.

### La note de synthèse Word

Ce que l'agent produit à la fin n'est pas un écran, c'est une note. Elle
s'obtient en un bouton : ce que fait l'acte, le tableau des textes modifiés,
les modifications de fond avec leur instruction verbatim, les notions
transverses, puis le détail article par article. De vrais tableaux Word,
modifiables, pas des captures.

### Les tirets longs deviennent des virgules

Dans les textes affichés par l'application, le tiret long est remplacé par une
virgule quand il articule une phrase, et par un point médian quand il sépare
deux valeurs d'un intitulé — forme déjà employée partout ailleurs dans
l'interface. Deux cent cinquante-sept passages sont concernés. Les
commentaires du code ne sont pas touchés : ce ne sont pas des textes de
l'application.

### Recette

110 tests, dont quatre nouveaux qui exercent l'écran lui-même, sans
navigateur : la vue d'ensemble compte bien ses textes, la carte se dessine,
les deux livrables se construisent, les trois vues se rendent sans exception.
C'est ce type de test qui aurait attrapé le plantage de l'export corrigé en
1.4.2.

---

## 1.4.2 — 9 septembre 2026

Correction des quatre points relevés au protocole de recette.

### L'export de l'onglet Omnibus ne plante plus

Le tableau récapitulatif « quels textes cet omnibus modifie-t-il » et une
variable de boucle portaient le même nom : le second écrasait le premier, et
le classeur Excel échouait sur `'str' object has no attribute 'to_excel'`. Le
bouton de téléchargement s'affichait donc en rouge dès que la caractérisation
avait été lancée. Les deux noms sont désormais distincts, et l'export porte
une colonne de plus.

### Le menu « Texte à examiner » dit le nom du texte

« règlement (UE) 2016/679 — 12 article(s) touché(s) » est exact et illisible.
Le catalogue des noms d'usage est étendu aux dix textes que l'omnibus
numérique modifie, et le menu affiche « RGPD — règlement (UE) 2016/679 —
12 article(s) touché(s), 25 modification(s) ». Le nom d'usage figure aussi
dans le tableau récapitulatif et dans l'export.

### Les suppressions apparaissent barrées

« Le point c) est supprimé », « le paragraphe 2 est supprimé » : ces
instructions n'étaient pas reportées dans la reconstitution, et le texte
« après » sortait identique au texte « avant ». Rien n'apparaissait barré,
alors que l'omnibus supprime bel et bien quelque chose. Le point et le
paragraphe sont désormais localisés — à condition que leur repère soit unique
dans l'article, faute de quoi l'instruction est laissée de côté plutôt
qu'appliquée au hasard — puis retirés du texte, où ils s'affichent barrés. Le
remplacement d'un point est traité de même, et un paragraphe inséré
(« 2 bis. ») se range après le paragraphe 2 au lieu d'aller en fin d'article.

Surtout, chaque instruction porte à l'écran la mention **« reportée »** ou
**« non reportée dans le texte ci-dessous »**. Une modification qui vise un
membre de phrase — « les mots “dans un délai raisonnable” sont supprimés » —
n'est toujours pas reportée, parce que la localiser mécaniquement expose au
contresens ; mais le lecteur sait désormais laquelle, au lieu de croire le
rendu complet.

### Les contributions françaises ne sont plus comptées comme non analysées

« 70 contribution(s) non analysée(s) sur 725 » s'affichait sur une analyse
pourtant complète : les contributions françaises **sont** le référentiel, elles
ne sont jamais classées. Elles sortent du dénominateur, et l'alerte le dit.
L'encadré de lancement affiche par ailleurs le détail du calcul — 725 dans le
document, −70 françaises, − les déjà analysées = le nombre à traiter — parce
que l'écart se demandait à chaque lancement.

L'onglet « Position française de référence » rappelle qu'un article sans
position explicite n'est pas un article bloqué : la règle du silence s'y
applique, et l'analyse peut être lancée sans avoir tout dérivé.

---

## 1.4.1 — 9 septembre 2026

Un article dont l'omnibus retire **un point** n'est plus annoncé comme
supprimé. L'article 64 du RGPD, dont seul le point a) du paragraphe 1
disparaît, s'affichait « Supprimé » : l'article survit, et l'écran disait le
contraire. La suppression n'est retenue que lorsque l'instruction vise
l'article entier — « L'article 4 est supprimé ».

---

## 1.4.0 — 9 septembre 2026

Version de déploiement : les cinq points relevés après la lecture des omnibus
sont traités.

### Un acte modificatif est découpé instruction par instruction

L'article premier d'un omnibus fait trente mille caractères et énumère
quarante modifications de textes différents. Gardé d'un bloc, il rendait trois
choses mauvaises : la recherche ramenait ce pavé entier, la comparaison de
deux versions affichait un diff illisible, et le fil du texte ne proposait que
« Article 1 ».

Chaque instruction devient donc une section à part entière, dont
l'identifiant porte le texte cible et l'article visé —
`mod_32016R0679_art_33_8`, intitulé « Article 3 · 8. — RGPD, Article 33 ».
Deux versions du même omnibus s'apparient alors **instruction par
instruction** : c'est ce qui permettra de voir ce qu'un compromis de
présidence change à la proposition de la Commission, dans la comparaison
ordinaire comme dans l'onglet dédié.

Sur la proposition d'omnibus numérique, le découpage passe de 174 segments
dont un préambule de 182 000 caractères à 251 segments lisibles : 70
instructions, les considérants, l'exposé des motifs et les annexes séparés.

### L'exposé des motifs n'est plus confondu avec le droit

Une proposition de la Commission commence par cent pages d'exposé des motifs
et de fiche financière. Elles atterrissaient dans le même segment que les
considérants, remontaient en recherche, et un résumé pouvait présenter un
tableau budgétaire comme une disposition — c'est exactement ce qu'on lisait
dans l'export de la version 0.8. Trois sections distinctes désormais :
**exposé des motifs et fiche financière**, **préambule et considérants**,
**annexes et pièces jointes**, cette dernière recueillant ce qui suit la
formule de clôture au lieu d'être avalé par le dernier article.

Les articles insérés par l'omnibus — « Article 32 bis », « Article 88 ter » —
ne sont plus indexés comme des articles de l'omnibus : ce sont des textes
cités, déjà portés par l'instruction qui les insère.

### Les fichiers EUR-Lex prennent le nom du texte

« cellar_ebf17714-c56e-11f0-8da2-01aa75ed71a1.0010.02_DOC_1 » n'apprend rien
à personne, et c'est ce nom qu'on relit dans toutes les listes. À l'import,
un fichier au nom de machine est renommé d'après son propre contenu :
**« Règlement omnibus numérique — COM(2025) 837 »**, ou « RGPD —
32016R0679 » pour un acte publié. Le nom se corrige à tout moment dans
Bibliothèque → Corpus, et le fichier d'origine est désormais mémorisé à part —
renommer un document ne le rend plus illisible pour l'onglet omnibus.

### La page Positions ne s'ouvre plus sur trois bandes de réglages

Position française de référence, lancement de l'analyse, regroupement par
titre : trois encadrés empilés avant le premier tableau. Ils sont réunis dans
un seul encadré à trois onglets. **Aucune fonction n'a été retirée** ; le
« Comment ça marche ? » descend en bas de page, comme dans les autres modules.

### Corrections

- **Un article n'est plus déclaré « inséré » parce qu'on ne l'a pas.** Sans
  texte de référence chargé, tous les articles s'affichaient « Inséré » — y
  compris l'article 1 du Data Act. Le statut vient maintenant de l'opération
  écrite dans l'instruction ; quand un article touché manque au texte chargé,
  l'écran le dit au lieu d'en tirer un verdict.
- Les **dispositions maintenues en vigueur** après une abrogation sont
  reconnues comme telles (« maintien transitoire ») au lieu de rester huit
  lignes muettes marquées « non analysée ».
- Un article de l'acte modificatif portant **une seule instruction non
  numérotée** — la modification d'une annexe — n'était pas lu du tout : tout
  un texte cible disparaissait de la liste.
- Les **accords féminins pluriels** (« les phrases suivantes sont ajoutées »)
  et l'écriture ancienne des références (« règlement (UE) nº 910/2014 ») sont
  reconnus.
- L'**ordre des sections** place l'exposé des motifs en tête et les annexes en
  fin, fragments compris.

---

## 1.3.0 — 9 septembre 2026

### La portée des modifications d'un omnibus est caractérisée

L'onglet « Omnibus et actes modificatifs » donnait l'instruction verbatim et
le texte avant/après. Il dit maintenant aussi **ce que la modification
change** et **si elle pèse** — majeure lorsqu'elle touche une obligation, un
champ d'application, un seuil, une compétence, une sanction ou un délai ;
mineure ; rédactionnelle. Un tableau récapitulatif range les articles par
portée décroissante, un filtre permet de ne garder que les modifications
majeures, et l'export les emporte.

**Pourquoi c'est juste cette fois.** Dans la version 0.8, le modèle résumait
des écarts calculés entre deux textes qui n'avaient rien à voir : le RGPD
d'un côté, l'omnibus de l'autre, appariés par numéro d'article. Les résumés
étaient fluides, confiants et faux — « l'article 33 a été supprimé » quand
l'omnibus le modifie, la fiche financière de la proposition présentée comme
un ajout à l'article 11 du RGPD, et un « impact rédactionnel » sur un
préambule intégralement remplacé. Ce n'était pas une défaillance du modèle
mais du rapprochement qu'on lui soumettait, et aucun garde-fou ne pouvait le
rattraper : la citation existait, le résumé était fidèle au diff, seul
l'appariement était absurde.

Ici, le rapprochement est établi par le texte lui-même — l'omnibus écrit
« l'article 33 est modifié comme suit ». Le modèle reçoit l'instruction, le
texte nouveau cité et l'article dans sa version actuelle, et il ne décide de
rien : l'opération (remplacement, suppression, ajout) est lue dans
l'instruction, pas devinée. Sans modèle configuré, rien n'est inventé : les
instructions verbatim restent affichées.

---

## 1.2.0 — 21 août 2026

### Les omnibus se lisent enfin pour ce qu'ils sont

Le défaut était de conception, pas de format. Un omnibus **n'est pas une
version du Data Act** : c'est un texte qui dit ce qu'il faut y changer — « à
l'article 5 du règlement (UE) 2023/2854, le paragraphe 2 est remplacé par le
texte suivant… ». Son article premier ne correspond à rien dans le Data Act.
La comparaison de versions appariant les articles par leur numéro, elle
mettait en regard l'article 1 de l'omnibus et l'article 1 du RGPD, qui ne
traitent pas du même sujet : des chiffres qui ressemblaient à une comparaison
sans en être une, et aucun article modifié détecté.

Un onglet **Omnibus et actes modificatifs** répond à la vraie question — que
change l'omnibus dans le Data Act, puis dans le RGPD :

- les **instructions de modification** sont extraites et rangées par texte
  modifié, puis par article visé, avec l'opération, la portée, le texte
  nouveau entre guillemets, et la page où l'instruction figure ;
- quand le texte consolidé est chargé, chaque article est **reconstitué avant
  et après**, avec le mot à mot — barré ce qui disparaît, souligné ce qui
  arrive. Les articles que l'omnibus ne touche pas restent affichés, marqués
  « inchangé » : un article absent laisserait croire à un oubli ;
- la reconstitution affiche sa **fiabilité** : exacte lorsque l'instruction
  remplace, supprime ou insère un article entier ou un paragraphe repérable ;
  partielle ; ou non appliquée lorsque l'instruction vise une phrase à
  l'intérieur d'un article. Une reconstitution approximative présentée comme
  le droit en vigueur serait pire que pas de reconstitution du tout ;
- le texte cible est retrouvé tout seul dans le corpus par son **CELEX**,
  déduit de « règlement (UE) 2023/2854 » comme de « règlement (UE) nº
  910/2014 » ;
- toutes les modifications s'exportent en un classeur, une ligne par
  instruction.

**Deux versions d'un même omnibus se comparent instruction par instruction.**
Un compromis de présidence ressemble à la proposition, avec des passages
changés, et il ne dit pas lesquels. Comparer les deux textes mot à mot noierait
le lecteur — l'article premier d'un omnibus fait trente mille caractères. La
comparaison porte donc sur les instructions, regroupées par article visé, et
répond à la question de négociation : sur quels articles du Data Act la
présidence a-t-elle changé ce que la Commission proposait ? Statuts :
inchangée, modifiée, nouvelle, abandonnée.

Tout est déterministe — expressions régulières, découpage, `difflib`. Aucun
appel de modèle, et donc rien à vérifier a posteriori : chaque modification
porte son instruction verbatim.

### Deux garde-fous contre le même piège

- La **comparaison ordinaire** prévient quand l'un des deux documents
  désignés est un acte modificatif, et renvoie vers le bon onglet.
- Le **suivi des amendements** refuse un texte d'arrivée de cette nature : il
  apparie lui aussi par numéro d'article, et aurait rendu des verdicts faux
  sans que rien ne le signale.

### Corrections venues de la revue de code

- Un **article scindé à l'import** (au-delà de 2 500 caractères) apparaissait
  comme supprimé puis ajouté dans la comparaison de versions, sans mot à mot.
  Les fragments sont désormais recollés avant l'appariement.
- L'**ordre des sections** rangeait ces mêmes fragments entre l'article 50 et
  l'article 53, et renvoyait le préambule en dernier. La règle est corrigée et
  les bases existantes sont migrées au premier démarrage.
- Un **considérant** et un **article** de même numéro partageaient une clé
  dans le suivi des amendements : « Considérant 79 » était jugé sur le texte
  de l'article 79, avec un verdict présenté comme déterministe.
- L'alerte « **classé sans le modèle** » ne se déclenchait jamais : en mode
  hors ligne, toute la matrice était lexicale et rien ne le disait.
- Un **PDF illisible** dans un lot d'import faisait tomber l'import entier, y
  compris les fichiers suivants. Chaque document est désormais traité pour
  lui-même, et l'échec est expliqué.
- Le **second appel au modèle** — celui de repli, quand l'endpoint refuse
  `response_format` — n'était pas protégé : une coupure réseau à cet instant
  arrêtait une analyse de trois cents contributions sur une trace Python.
- La **dispersion** d'un article commenté par un seul État membre était
  affichée comme nulle, plaçant une opinion isolée dans la zone que la légende
  décrit comme un consensus.
- Les **couleurs du mot à mot** suivent désormais la palette active.

### Installation et reprise

- `requirements.txt` **fige les versions** validées au lieu de poser des
  planchers. Un `pip install` résolvant vers Streamlit 1.38 produisait une
  application qui plante à la première page ; sans plafond, une installation
  faite dans six mois reproduisait l'incident `st.logo`.
- Les scripts de démarrage vérifient que l'installation a **réellement
  réussi** : un `pip install` échoué laissait un environnement vide, et tous
  les lancements suivants sautaient l'installation — l'application ne
  démarrait plus jamais, sans message. Ils gèrent aussi les lecteurs réseau,
  le faux `python.exe` du Microsoft Store, et une installation **sans accès à
  PyPI** depuis un dossier `wheelhouse`.
- `headless` est retiré de la configuration de poste : le navigateur ne
  s'ouvrait jamais, alors que les quatre documents le promettaient.
- `requirements-dev.txt` et la mention des 90 tests, pour qui reprend le code.

### Guide

La question « est-ce que ça coûte de l'argent à l'État ? » est retirée du
guide d'utilisation.

---

## 1.1.2 — 21 août 2026

**Mise en page seulement — aucun calcul, aucune règle n'a bougé.**

Le nom de l'application s'écrit désormais partout au lettrage du logo :
« mar », le « i » et le « a » en rouge Marianne — l'intelligence
artificielle —, le « a » en exposant pour que le mot se lise « marisol », puis
« sol » en bleu France. Titre d'accueil, titre du mode d'emploi, intitulé de
l'assistant, pied du bandeau latéral. Le lettrage est un composant unique
(`core.ui.nom_marque`), stylé en ligne pour qu'une page ouverte seule le rende
correctement.

La charte entre aussi dans l'habillage : titres de page en bleu France,
chiffres clés des indicateurs au même bleu, onglet actif souligné de ce bleu,
traits de séparation en bleu très clair. Le corps de texte reste noir — un
écran de travail entièrement bleu se lit moins bien — et les visualisations
gardent leur palette lisible en vision daltonienne.

---

## 1.1.1 — 21 août 2026

**Correctif de démarrage.** Sur les postes équipés d'une version de Streamlit
qui refuse un chemin de fichier SVG, `st.logo` levait une exception avant même
l'affichage de la navigation : l'application ne démarrait pas du tout. La
marque du bandeau est désormais un PNG, l'appel est enveloppé — un habillage
que Streamlit refuse ne doit jamais empêcher l'outil de s'ouvrir — et deux
tests couvrent le cas : le point d'entrée `app.py` est exercé comme les autres
pages, et aucun SVG ne doit y être référencé. Les fichiers SVG restent dans
`assets/` pour les notes, présentations et impressions.

---

## 1.1.0 — 21 août 2026

Version de finition : la charte graphique entre dans l'application, et six
points relevés à l'usage sont corrigés.

### Le tableau de suivi revient à l'écran

Il n'existait plus que dans le classeur exporté, et sans couleur à l'écran.
Un onglet **Tableau de suivi** s'ajoute donc dans *Positions des États
membres*, **après la matrice** : une ligne par article avec son sujet, la
position française de référence en première colonne — sans elle « opposé » ne
veut rien dire —, puis un État membre par colonne, chaque case portant le
résumé de la contribution et la référence de la disposition citée.

La couleur est celle de la palette active : le tableau à l'écran et la feuille
« Détail par article » du classeur sont la même chose, aux mêmes teintes.
Contenu des cases et couleur sont d'ailleurs calculés par les mêmes fonctions
— les réécrire pour l'écran les aurait fait diverger au premier changement de
règle.

### L'assistant répond enfin aux questions de calcul

« Comment sont calculées les coalitions ? » recevait une réponse d'usage en
cinq phrases. Chaque fiche porte désormais un bloc **« Sous le capot »** :
la formule, la fonction, la bibliothèque, les seuils chiffrés — accord entre
deux États, composantes connexes de `networkx`, majorité qualifiée et son
arrondi, BM25 et ses constantes, `SequenceMatcher` et son `autojunk`, taux de
reprise des amendements, seuils de fiabilité, échantillonnage stratifié.

L'assistant reconnaît une question de calcul à sa formulation, bascule sur une
consigne qui exige le détail plutôt que la brièveté, et reçoit ces blocs en
contexte. Une fiche **Architecture** liste par ailleurs toutes les
bibliothèques et ce que chacune fait. Le guide complet a une bascule
« Afficher le détail d'implémentation ».

La recherche dans les fiches rabat aussi les pluriels sur le singulier :
« comment tu calcules les coalitions » ne rencontrait pas le mot-clé
« coalition » et répondait à côté.

### La comparaison de versions ne compare plus au hasard

Elle ouvrait sur les deux premiers documents du corpus et affichait des
chiffres qui ne répondaient à aucune question posée. Les deux listes
démarrent maintenant vides, la sélection est remontée **avant** les onglets,
et les onglets de comparaison disent ce qu'ils attendent tant que les deux
textes ne sont pas désignés. Le fil du texte, lui, continue de fonctionner
sans ce choix.

### Une carte lisible plutôt que trois illisibles

Les trois vues concurrentes laissent place à **une seule carte, grande**, dont
les tuiles portent des étiquettes lisibles : les articles les plus lourdement
modifiés d'abord, en nombre réglable, un clic ouvrant le texte modifié juste
en dessous. Le nombre d'articles non représentés est affiché — une coupe
silencieuse aurait laissé croire à une carte exhaustive. Les deux autres
représentations restent disponibles, repliées.

### Charte graphique

Logo et marque intégrés à l'en-tête et au bandeau latéral, couleurs
d'interface alignées sur le bleu France. Les visualisations gardent leur
palette lisible en vision daltonienne, et la convention vert / jaune / rouge
de la direction reste à un clic.

### Corrections de détail

- « Demandez à mariasol comment **elle** fonctionne » — l'application porte un
  nom féminin.
- Le second référentiel s'appelle désormais **« comparé au texte initial »**,
  partout : écrans, fiches, classeur, note Word, documentation.
- Le panneau **Fiabilité et points d'attention** reste replié, y compris quand
  une alerte est bloquante : le résumé est déjà dans l'intitulé, et un encadré
  qui s'ouvre seul déplace tout ce qui est en dessous.
- **Plus aucun chemin absolu affiché.** L'application est déployée sur des
  postes dont l'arborescence diffère ; un chemin absolu n'y veut rien dire, et
  donnait au passage le nom de session Windows du poste de préparation. Tous
  les chemins montrés sont relatifs au dossier de l'application.

---

## 1.0.0 — 20 août 2026

**L'application prend son nom : MARI(a)SOL** — *Mapping d'Alignement
Réglementaire par Intelligence Albert pour le Suivi des Orientations
Législatives*. Marque et logo aux couleurs de la charte de l'État (bleu
France, blanc, rouge Marianne), sans reprise du bloc-marque officiel. Les
variables d'environnement et le nom du dossier restent inchangés : une
installation existante continue de fonctionner sans rien toucher.

### Nouveau : suivi des amendements

Une page entière pour la question qui suit toute publication d'un compromis :
**nos amendements ont-ils été retenus ?** Chaque demande écrite est confrontée
au texte d'arrivée, avec un verdict par demande — reprise, reprise
partiellement, écartée, indéterminé — et le taux de reprise par délégation,
qui donne la lecture politique du texte.

Le calcul se fait en deux temps. Les demandes de suppression sont tranchées
**sans modèle**, par comparaison des structures : l'article a disparu, ou il
est toujours là. Le reste est lu par le modèle, qui doit recopier le passage
du nouveau texte fondant son verdict ; sans citation retrouvée, le verdict
bascule en « indéterminé » plutôt que d'être affiché comme acquis.

### Nouveau : mise à jour depuis les non-papers et les notes

Toutes les positions n'arrivent pas dans un tableau à trois colonnes. Un
non-paper, un papier blanc, une note ministre, un compte rendu : l'outil
dépouille le document, propose les positions qu'il y lit avec leur citation et
leur rattachement à un article — et **rien n'entre dans la matrice avant
validation par l'agent**. Les positions ainsi ajoutées gardent la trace de
leur source.

### Nouveau : assistant d'aide et guide complet

La page Mode d'emploi porte un assistant qui répond **uniquement sur le
fonctionnement de l'application**, à partir de vingt-sept fiches écrites à la
main : comment les scores sont calculés, comment les passages sont choisis, ce
qui est sauvegardé. Il ne connaît ni le droit européen ni les documents
chargés — cette séparation est délibérée.

Les mêmes fiches alimentent la fenêtre « Comment ça marche ? » de chaque
module et le guide complet, de sorte qu'une explication ne peut pas en
contredire une autre.

### Nouveau : panneau de fiabilité

Chaque module affiche, dans une fenêtre à part, ce qui demande l'œil de
l'agent : citations non retrouvées, contributions classées sans modèle,
contributions de plus de 2 500 caractères, articles documentés par moins de
trois États membres, paires d'États dont le taux d'accord repose sur moins de
trois articles communs, réserves d'examen, plafond de passages atteint en
recherche. Chaque alerte dit quoi faire. **Ces alertes ne partent pas dans les
livrables** : une note de direction n'a pas à porter les doutes de l'outil.

### Nouveau : regroupement par titre, et plusieurs tableaux à la fois

Les articles se regroupent par titre du règlement — rattachement lu dans le
texte réglementaire quand il est chargé, sinon saisi par bornes. Et la page
Positions accepte **plusieurs tableaux de commentaires simultanément**, pour
le cas où chaque titre a son propre document de travail.

### Nouveau : pondération d'un critère métier

Facultative, repliée, lancée à la main. L'agent écrit son critère en français
— « les positions qui demandent de supprimer l'intervention de la
Commission » — le modèle dit pour chaque contribution si elle y correspond,
citation vérifiée à l'appui, et les contributions retenues comptent double
dans les moyennes. Le classement brut reste affiché à côté, avec l'écart :
c'est lui qui dit ce que la pondération change.

### Corrections

- **Les textes récupérés depuis EUR-Lex portent enfin leur nom** : « Data
  Governance Act — 32022R0868 [FR] » au lieu de « L_2022152FR.01000101.xml ».
  Le nom vient d'un catalogue de noms d'usage, ou de l'intitulé officiel lu en
  tête du texte.
- **La comparaison de versions n'est plus bloquée par le dossier.** Les deux
  listes portent sur tout le corpus : un omnibus modifie plusieurs textes, et
  le texte de départ et le texte d'arrivée n'appartiennent pas au même
  dossier. Le dossier n'est plus qu'un confort de tri.
- **Un intitulé de titre ne happe plus la première ligne de l'article
  suivant** dans la détection des titres.

## 0.9.1 — 20 août 2026

**Le classeur reprend la forme du suivi tenu à la main.**

- **La position française est rappelée avant tout jugement.** Dans la matrice,
  dans le détail de chaque contribution, dans la note Word et dans le
  classeur : « opposé » ne veut rien dire tant qu'on ne sait pas opposé à
  quoi. Sur un article sans amendement français, la référence affichée est
  explicitement la règle du silence.
- **Nouvelle feuille « Détail par article »**, calquée sur le suivi existant :
  une ligne par article — numéro et sujet —, la France en première colonne,
  puis chaque État membre, la case portant sa position, sa référence de
  disposition, et la couleur de compatibilité.
- **Nouvelle feuille « Position FR »** : article, intitulé, position de
  référence, et l'origine de cette référence (amendement écrit ou règle du
  silence).
- **Nouvelle feuille « Synthèse thématique »**, placée avant le détail : les
  enjeux qui traversent plusieurs articles, État membre par État membre.
- **Le sujet de l'article** est lu automatiquement dans le texte réglementaire
  quand il est chargé — « Art. 111 · Interdictions réseaux de communication » —
  et reste modifiable avant export.
- **La palette « convention des notes » reprend exactement les teintes du
  fichier existant** (vert 63BE7B, jaune FFEB84, rouge F8696B, gris D9D9D9) :
  le classeur produit peut se poser à côté du suivi sans que l'œil ait à
  réapprendre le code couleur.
- **Filtre thématique ajouté dans l'onglet Détail**, avant le filtre par
  article, et colonne « Thèmes » remontée dans la feuille Détail.

## 0.9.0 — 20 août 2026

**Deuxième retour de test : précision des repères, volumes, langage.**

### Ce qui bloquait

- **EUR-Lex refusait de répondre.** Une seule adresse était tentée, et EUR-Lex
  ne sert pas toujours le document à la première : selon le texte, la langue
  et l'état de la session, il renvoie une page d'accueil ou un avertissement.
  Quatre adresses sont désormais essayées, dont l'endpoint machine de l'Office
  des publications (CELLAR) — celui qui passe le plus souvent derrière un
  proxy — avec gestion des cookies, repli sur le PDF, et le journal des
  tentatives affiché quand tout échoue.
- **Plafond de 30 passages en recherche**, arbitraire et trop bas : porté à
  500, avec la durée estimée avant lancement.
- **« Article 24 (2/12) »** ne renvoyait à rien : ce numéro d'ordre est un
  artefact du découpage. Les intitulés reprennent maintenant la disposition
  réellement visée — « § 2 », « considérant 12 », « à partir du § 3 » — lue
  dans le commentaire de la délégation, et à défaut les premiers mots du
  texte, de sorte que quatre lignes « Article 5 » se distinguent enfin.
- **Une absence de position comptait comme un alignement.** Quand ni la France
  ni l'État membre n'ont amendé un article, on ne sait rien de sa position :
  la case reste vide. Corrigé dans l'heuristique et dans la consigne donnée au
  modèle, et couvert par un test.

### Deux référentiels au lieu d'un

La matrice, le classement des alliés et les articles clivants se calculent au
choix **par rapport à la position française** — qui est avec nous — ou **par
rapport au texte de compromis** — qui veut le changer, France comprise. Le
second est entièrement déterministe : il applique la règle du silence au texte
de chaque contribution, sans appeler le modèle. Sur un article que la France
n'a pas amendé, les deux coïncident ; sur un article où elle demande une
réécriture, ils divergent — et c'est là que la bascule sert.

### Volumes et durées

- L'analyse se lance sur **un dixième, la moitié ou toutes** les contributions,
  plutôt qu'un nombre absolu qui ne dit rien sans connaître le document.
- La qualification des changements se fait **en une fois**, avec le temps
  restant calculé sur le rythme observé, et non sur une moyenne théorique.
- Toute tâche longue annonce sa durée avant de commencer.

### Comparaison de versions, refondue

- Nouvel onglet **Fil du texte** : toutes les versions chargées d'un dossier
  dans l'ordre, et l'évolution d'un article à travers toutes ces versions —
  un omnibus ne se suit pas deux versions à la fois.
- Nouvel onglet **Changements majeurs** : ce qui a bougé, trié par portée, avec
  le diff mot à mot en un clic.
- **Nature et date de version** détectées à l'import depuis l'en-tête
  (proposition de la Commission, compromis de la présidence, orientation
  générale, position du Parlement, accord provisoire, texte publié au JO) et
  modifiables. Les listes déroulantes ne disent plus « version antérieure /
  nouvelle » mais nomment ce que sont les documents.

### Langage et repères

- **Page « Mode d'emploi »** dans le menu : par où commencer, les outils un par
  un, ce que l'outil garantit et ce qu'il ne garantit pas, questions
  fréquentes.
- Les titres de page sont posés **comme des questions** — « Qui est avec nous,
  article par article ? » plutôt que « Positions des États membres ».
- Chaque module s'ouvre sur **deux phrases d'explication**, et referme sur le
  **détail de méthode**, replié en bas de page.
- **Choix de palette rendu global** — bleu / rouge lisible en vision
  daltonienne, ou vert / jaune / rouge des notes de direction. Le choix vaut
  pour les écrans, les images, la note Word et le classeur.
- La page Régimes d'accès dit clairement que les « textes où regarder en
  priorité » sont une liste de méthode écrite d'avance, **pas un résultat de
  recherche**, et indique lesquels sont réellement au corpus.

## 0.8.0 — 18 août 2026

**Corrections et ajouts issus de la deuxième campagne de test.**

### Corrections

- **Régimes d'accès : plus aucun filtre sur le type de document.** La page ne
  regardait que les documents marqués « texte réglementaire ». Un texte mal
  classé à l'import — la détection automatique se trompe souvent sur les
  textes consolidés — devenait invisible, et l'outil répondait « les textes
  chargés ne tranchent pas » alors que le règlement était dans la base. Même
  correction sur la comparaison de versions.
- **Le type d'un document est corrigeable après import**, depuis l'onglet
  Corpus de la Bibliothèque. C'était la cause du point précédent.
- **L'outil ne déclare plus forfait trop vite.** Quand l'examen extrait par
  extrait ne retient rien, une seconde lecture d'ensemble reprend tous les
  passages avec un seuil de pertinence plus bas et les restitue comme
  « éléments de contexte ». La garantie ne change pas : chaque élément reste
  adossé à une citation vérifiée dans le texte source.
- **Seconde chance sur les citations.** Une citation approximative — recopie
  imparfaite plutôt qu'invention — donne lieu à une demande de recopie exacte
  avant retrait. Ce qui échoue deux fois n'est toujours pas affiché.
- **`build_query` n'était pas importé dans `core/qa.py`** : toute réponse
  sourcée levait une `NameError`. Corrigé, et un test de garde-fou couvre
  désormais le chemin complet.
- **Repli de recherche** : si la requête enrichie de termes anglais ne trouve
  rien, la recherche est refaite avec les seuls mots de la question.

### Livrables

- **Classeur Excel entièrement refait** (`core/excel.py`) : sept feuilles —
  mode de lecture et méthode, matrice en damier coloré, classement des États
  membres, articles clivants, couverture, détail texte, figures. Les
  graphiques du classement, des articles clivants et de la couverture sont
  des **graphiques Excel natifs, liés aux cellules** : corriger une valeur met
  le graphique à jour sans repasser par l'outil. Filtres, volets figés et mise
  en page d'impression posés sur chaque feuille.
- **Note Word enrichie du texte de détail** : article par article, ce que dit
  chaque État membre, la citation qui le fonde, la page. Cette partie bascule
  en portrait — une matrice se lit en largeur, un paragraphe sur une colonne
  étroite.
- **Fiche d'orientation Word** produite depuis la page Régimes d'accès :
  situation examinée, dispositions citées, points non tranchés, textes
  interrogés.

### Visualisations

- **Comparaison de versions** : trois vues d'ensemble **cliquables** — carte
  des changements (surface = mots touchés), barres divergentes ajouts/retraits,
  nuage ampleur × similarité. Cliquer un article l'ouvre avec ses différences
  mot à mot.
- **Coalitions** : nouvel onglet « Qui aller chercher », placé en premier.
  Proximité avec la France croisée avec le poids au Conseil, répartition des
  positions par État membre, et simulateur de coalition — c'est là, et
  seulement là, que servent les chiffres de population.
- **Recherche** : répartition des occurrences par État membre et par article,
  et marquage des passages retenus ou écartés.

### EUR-Lex

- **Récupération directe des textes publics** (`core/eurlex.py`), catalogue
  des sept règlements usuels, ou saisie d'un CELEX, d'une référence en clair
  ou d'une adresse. C'est la version **HTML** qui est récupérée, pas le PDF :
  le PDF du Journal officiel est une mise en page dont l'extraction introduit
  des écarts qui se comptent ensuite comme des modifications dans une
  comparaison de versions. Aucune dépendance nouvelle, proxy respecté, et un
  message explicite plus une marche à suivre manuelle si le réseau filtre la
  sortie.

## 0.7.0 — 18 août 2026

- **Mode démonstration** (`REGWATCH_DEMO=1`) pour une instance partagée :
  saisie de clé API impossible — verrou posé dans la configuration, pas
  seulement dans l'interface —, bannière permanente, modèle désactivé.
- `DEPLOIEMENT_DEMO.md` : marche à suivre pour Streamlit Community Cloud.

## 0.6.0 — 18 août 2026

**Corrections issues du premier test complet.**

- **Tableaux à trois colonnes.** Le parser lisait la deuxième colonne, qui
  contient le texte de compromis de la présidence sur les WK à trois colonnes :
  les contributions des États membres étaient perdues. Il lit désormais la
  dernière colonne, ce qui couvre les deux formats.
- **Aperçus de recherche illisibles.** Le mode « extraits bruts » affichait
  l'identifiant numérique du segment au lieu du passage. Régression introduite
  le 12 août avec le nouvel index.
- **Réponses incomplètes.** La synthèse s'arrêtait au premier extrait
  pertinent — un seul État membre cité alors que plusieurs figuraient dans les
  extraits. Consigne d'exhaustivité ajoutée, plafond porté de 12 à 24
  affirmations.
- **Plantage de la dérivation des positions françaises.** La limite de 600
  caractères sur le résumé faisait échouer l'appel après trois essais et
  interrompait tout le traitement. Limite portée à 4 000 caractères avec
  troncature, et un article en échec n'emporte plus les autres.

**Nouveautés.**

- Export **PNG** des trois figures et **note Word modifiable**, avec sélection
  des articles et des États membres, choix de palette (bleu accessible ou
  vert/jaune/rouge selon la convention des notes) et renommage des intitulés
  d'articles.
- Filtres et plafond sur le lot d'analyse, pour juger la qualité sur quelques
  contributions avant de lancer les 550.
- Mode d'emploi `POUR_LES_TESTEURS.md` à joindre pour un test d'usage.

---

## 0.5.0 — 12 août 2026 (après-midi)

- **Corruption de base au ré-import.** Les entrées d'index étaient supprimées
  deux fois — par le code et par un déclencheur SQLite — ce qui corrompait
  irréversiblement l'index FTS5 (« database disk image is malformed »). Index
  refait sans déclencheurs, plus détection et réparation dans Administration.
- Contrôle d'intégrité qui sonde réellement l'index : `PRAGMA integrity_check`
  seul déclarait saine une base qui ne l'était pas.

## 0.4.0 — 12 août 2026 (matin)

- Saisie de la clé API dans l'interface, avec option « ne pas conserver » et
  bouton de suppression.
- **Écoute restreinte à `localhost`.** Streamlit écoutait par défaut sur toutes
  les interfaces réseau : n'importe quel poste du réseau pouvait ouvrir
  l'application et lire le corpus.
- Navigation refondue : libellés accentués, icônes, bandeau d'état permanent.

## 0.3.0 — 11 août 2026

- Abandon du graphe de règles au profit de réponses sourcées sur les documents
  chargés. Le moteur de graphe reste dans `attic/`.
- Règle du silence français : ne pas amender vaut acceptation.
- Ingestion universelle (WK, textes réglementaires, textes libres), recherche
  plein texte, comparaison de versions, coalitions et majorité qualifiée.

## 0.2.0 — 11 août 2026

- Première application complète : parser WK, matrice d'alignement, graphe de
  règles, restitutions.
