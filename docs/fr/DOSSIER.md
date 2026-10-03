# Lisez-moi d'abord

Ce dossier accompagne **MARI(a)SOL**, outil interne d'aide à la négociation
européenne et d'orientation sur les régimes d'accès aux données, développé au
sein de la direction de projets « économie de la donnée » de la Direction
générale des entreprises.

Il contient tout ce qu'il faut pour installer l'outil, l'essayer, en juger, et
décider de sa mise à disposition. Ce document dit simplement **qui lit quoi**.

---

## Ce qu'il y a dans ce dossier

| Fichier | Pour qui | Combien de temps |
|---|---|---|
| **1. Présentation générale** | Tout le monde. Ce que fait l'outil, ce qu'il garantit, ce qu'il ne garantit pas. | 10 min |
| **2. Guide d'installation** | La personne qui installe l'outil sur un poste. Aucun prérequis supposé. | 15 min, montre en main |
| **3. Test d'usage en trente minutes** | L'agent à qui l'on demande d'essayer l'outil. Trois manipulations, et ses impressions. | 30 min |
| **4. Note de cadrage** | Le responsable qui décide. Ce que l'outil est, pour qui, et ce qu'il n'est pas. | 15 min |
| **5. Architecture du code** | La personne qui doit reprendre, auditer ou héberger l'application. Fichier par fichier. | 20 min |
| **6. Déploiement d'une instance partagée** | Le service qui hébergerait l'outil. Options, précautions, ce qui reste à trancher. | 10 min |
| **7. Protocole de recette** | La personne qui vérifie avant la mise en service. Dix étapes, avec le résultat attendu à chaque étape. | 45 min |
| **8. Journal des versions** | Pour mémoire. Ce qui a changé, version par version, et pourquoi. | à la demande |

Le reste du dossier est le **code de l'application**, prêt à être lancé. Le
guide d'installation (document 2) suffit à le faire tourner : sur Windows, un
double-clic sur `demarrer.bat`.

---

## Si vous n'avez que dix minutes

Lisez la **présentation générale** (document 1), puis lancez l'application et
ouvrez sa page **Mode d'emploi** : elle contient le même contenu que ces
guides, à jour, et un assistant qui répond aux questions sur le fonctionnement
de l'outil.

## Si vous devez décider de l'hébergement

Lisez la **note de cadrage** (4) et le **déploiement d'une instance partagée**
(6). Trois options y sont exposées, de l'installation poste par poste à
l'hébergement sur serveur applicatif, avec ce que chacune suppose. La question
sur laquelle un arbitrage est attendu y est posée explicitement.

## Si vous devez auditer le code

Lisez l'**architecture du code** (5). Elle dit ce que fait chaque fichier et
pourquoi il existe. Les trois propriétés à vérifier en priorité y sont
nommées : le calcul est déterministe et le modèle ne fait que qualifier ;
aucune affirmation n'est produite sans citation vérifiée littéralement dans le
document source ; le seul appel réseau sortant est celui adressé à l'API
Albert de la DINUM, hébergée en SecNumCloud.

---

## Les trois points à connaître avant toute discussion

**Les calculs sont faits par le programme.** Matrices d'alignement, taux
d'accord, blocs de coalition, majorité qualifiée, écarts entre versions,
lecture d'un acte modificatif : tout cela est de l'arithmétique et de
l'analyse de texte déterministe, refaisable à la main. Le modèle de langage
n'intervient que pour qualifier une position ou résumer un passage, jamais
pour calculer ni pour décider.

**Aucune affirmation sans citation vérifiée.** Toute phrase produite par le
modèle porte une citation, et le programme la recherche littéralement dans le
document source. Si elle ne s'y trouve pas, l'affirmation est retirée — elle
n'est pas montrée assortie d'un avertissement. C'est le garde-fou principal,
et il est vérifié automatiquement à chaque version.

**Rien ne sort du poste, sauf vers Albert.** Les documents restent dans le
dossier `data/` de la machine. Seuls les extraits nécessaires à une analyse
sont transmis à l'API Albert de la DINUM. Aucun texte n'est envoyé à un
service d'indexation ou de vectorisation tiers : la recherche plein texte est
locale. Un mode entièrement hors ligne est disponible, dans lequel l'import,
l'indexation, la recherche et les calculs de coalition restent opérationnels.

---

## Ce que l'outil ne fait pas

Il ne dit pas le droit. Il ne prédit pas l'issue d'une négociation : des
positions écrites en groupe de travail ne sont pas des votes. Il ne remplace
pas la lecture des documents — il indique où lire, et cite ce sur quoi il se
fonde. Un classement se conteste : la contribution, la citation retenue et le
texte intégral sont accessibles en deux clics, et la position française de
référence se corrige à la main.
