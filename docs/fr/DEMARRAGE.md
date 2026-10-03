# Démarrer MARI(a)SOL

Ce guide part du principe que rien n'est installé sur le poste.
Compter **quinze minutes** jusqu'au premier résultat à l'écran.

---

## Étape 1 — Vérifier que Python est installé

Ouvrez un terminal :

- **Windows** — touche Windows, taper `powershell`, Entrée.
- **macOS** — Cmd+Espace, taper `terminal`, Entrée.

Puis tapez :

```
python --version
```

Si une version s'affiche (3.11 ou plus récente), passez à l'étape 2.
Si la commande est introuvable, installez Python depuis
<https://www.python.org/downloads/>. **Sur Windows, cochez impérativement
« Add Python to PATH »** pendant l'installation — sans cela rien ne marchera.

---

## Étape 2 — Lancer l'application

Décompressez `regwatch.zip` où vous voulez, par exemple dans vos Documents.
Puis, dans le dossier obtenu :

- **Windows** — double-cliquez sur **`demarrer.bat`**
- **macOS / Linux** — dans le terminal, placez-vous dans le dossier et tapez :

```
chmod +x demarrer.sh
./demarrer.sh
```

Le premier lancement installe les dépendances : deux à trois minutes, une seule
fois. Ensuite l'application s'ouvre dans votre navigateur, à l'adresse
`http://localhost:8501`.

Une fenêtre de terminal reste ouverte pendant l'utilisation : c'est normal,
c'est le serveur. Pour arrêter l'application, Ctrl+C dans cette fenêtre.

> Si vous préférez la ligne de commande classique :
> `pip install -r requirements.txt` puis `streamlit run app.py`.

---

## Étape 3 — Enregistrer la clé Albert

Dans l'application, page **Administration**, onglet **Modèle** :

1. Collez la clé dans le champ **Clé API**, cliquez sur **Enregistrer la clé**.
2. Cliquez sur **Interroger l'endpoint** : la liste des modèles disponibles
   s'affiche. Choisissez-en un, puis **Enregistrer le modèle**.
   L'identifiant exact change au fil des mises à jour d'Albert — c'est pour ça
   qu'on le demande à l'endpoint plutôt que de le deviner.
3. **Tester la connexion** pour confirmer.

La clé est écrite dans un fichier `.env` à la racine de l'application, avec des
permissions restreintes à votre compte. Elle transite uniquement vers
`localhost` : le serveur n'écoute que sur votre machine.

Sur un poste partagé, décochez « conserver la clé pour les prochains
démarrages » : elle ne vivra qu'en mémoire et disparaîtra à l'arrêt.

**Avant de copier le dossier de l'application ailleurs, ou de le transmettre :**
supprimez la clé (Administration → « Retirer la clé de ce poste »). Le `.env`
voyage avec le dossier.

**Si l'étape 2 échoue** — connexion impossible, liste vide : c'est presque
toujours un problème de réseau depuis le poste, ou une clé qui n'est pas encore
active. Vérifiez le point d'accès affiché et, le cas échéant, demandez à la
DINUM si la clé est bien ouverte sur cet environnement.

**Vous n'êtes pas bloquée sans clé.** L'import, l'indexation, la recherche
plein texte, la comparaison de versions et tous les calculs de coalition
fonctionnent sans aucun appel réseau.

---

## Étape 4 — Charger vos premiers documents

Page **Bibliothèque**, onglet **Importer**.

**Pour commencer, chargez vos deux WK CSA2.** Renseignez le dossier — par
exemple `CSA2` — et laissez la détection automatique. Vous devez obtenir
environ 550 et 730 contributions.

Puis, page **Positions des États membres** :

1. Sélectionnez le document.
2. Ouvrez **Position française de référence** et cliquez sur **Dériver les
   positions explicites**. Les articles où la France ne s'est pas exprimée sont
   traités par la règle du silence — ne pas amender vaut acceptation.
3. **Lancer l'analyse**. Comptez plusieurs minutes : chaque contribution fait
   l'objet d'un appel au modèle. Vous pouvez suivre l'avancement.
4. La matrice, le classement des alliés et les articles clivants s'affichent.

---

## Étape 5 — Le premier test qui compte vraiment

**Comparez le résultat automatique à votre matrice Excel faite à la main.**
C'est la seule vérité terrain disponible et vous l'avez déjà.

Ouvrez l'onglet **Export**, téléchargez le classeur, et mettez-le côte à côte
avec `CSA2_suivi_EM_MAJ_TitreIII`. Regardez article par article où les scores
divergent, et pourquoi. C'est ce test qui vous dira si l'outil est utilisable
en note, et sur quels types d'articles il faut se méfier.

Ne sautez pas cette étape. Un outil dont on ne connaît pas le taux d'erreur
n'est pas un outil, c'est un pari.

---

## Ensuite, dans l'ordre d'utilité

**Chargez les textes de référence** pour la page Régimes d'accès : RGPD, Data
Governance Act, Data Act, directive Open Data, AI Act. Versions consolidées,
en PDF ou Word, depuis EUR-Lex. Choisissez le type **Texte réglementaire** à
l'import. Tant qu'ils ne sont pas chargés, la page reste vide — c'est voulu :
l'outil ne répond que sur ce qu'il a lu.

**Chargez deux versions d'un même texte** pour essayer la comparaison. Deux
compromis de présidence successifs, ou la proposition initiale et le texte
post-omnibus. Renseignez le repère de version à l'import, il sert à les
ordonner.

**Corrigez les chiffres de population** — page Administration, onglet Données
de référence — avant d'utiliser les calculs de minorité de blocage dans une
note. Ceux livrés sont approchés.

---

## Problèmes courants

| Symptôme | Cause probable |
|---|---|
| `python` introuvable sur Windows | « Add Python to PATH » n'a pas été coché à l'installation. Réinstallez en cochant. |
| La page reste blanche au lancement | Le navigateur s'est ouvert avant le serveur. Rechargez `http://localhost:8501`. |
| « Aucune contribution détectée » à l'import | Le document ne suit pas la structure tabulaire attendue. Forcez le type à l'import. |
| L'analyse est très lente | Normal : un appel par contribution. Cochez « ne traiter que les non analysées » pour reprendre où vous en étiez. |
| Des affirmations « retirées » dans la recherche | Le garde-fou a joué : la citation n'était pas retrouvable dans le corpus. C'est le comportement attendu. |
| `database disk image is malformed` | Défaut corrigé le 12 août 2026 : le ré-import d'un document déjà présent corrompait l'index de recherche. Mettez l'application à jour, puis Administration → Index → **Réparer la base**. Aucun document n'est perdu. |

---

## Sécurité — ce qui est réglé, ce qui reste à vous

L'application **n'écoute que sur `localhost`** (`.streamlit/config.toml` et les
scripts de démarrage). Par défaut, Streamlit écoute sur toutes les interfaces
réseau : sans ce réglage, n'importe quel poste du réseau pourrait ouvrir
l'application, sans mot de passe, et lire le corpus.

**Le corpus est plus sensible que la clé API.** Une clé se révoque en un appel ;
des documents LIMITE qui ont fuité, non. Si un jour vous voulez ouvrir l'outil
à des collègues, il faut d'abord mettre une authentification devant — ne
changez pas `server.address` sans cela.

Trois réflexes :

- supprimer la clé avant de transmettre ou copier le dossier ;
- décocher la conservation de la clé sur un poste partagé ;
- ne pas verser `data/` dans un partage réseau ouvert — c'est là que vivent les
  documents importés.
