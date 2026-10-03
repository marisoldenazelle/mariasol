# Déployer l'instance de démonstration

Objectif : un lien que vos collègues ouvrent dans leur navigateur, sans rien
installer, pour recueillir des retours d'ergonomie.

**Ce que cette instance est** : une vitrine publique, en mode dégradé, sur des
documents publics uniquement.
**Ce qu'elle n'est pas** : un espace de travail. Le corpus est partagé entre
tous les utilisateurs et effacé à chaque redémarrage.

Comptez 20 minutes.

---

## Ce qui est verrouillé, et pourquoi

| Verrou | Raison |
|---|---|
| **Aucune saisie de clé API possible** | L'instance est un processus unique partagé : une clé saisie par une personne deviendrait active pour toutes les autres, qui consommeraient son quota à son insu. Le verrou est posé dans la configuration, pas seulement dans l'interface. |
| **Synthèses rédigées désactivées** | Elles nécessitent un modèle, donc une clé. |
| **Bannière permanente** | Rappelle à chaque écran que le corpus est public et partagé. |

**Ce qui fonctionne quand même :** l'import, la recherche par mots-clés avec
extraits et numéros de page, la comparaison de deux versions d'un texte mot à
mot, et les visualisations. La comparaison de versions est entièrement
déterministe — c'est la partie qui ne perd rien à tourner sans modèle.

---

## Étape 1 — Préparer le dépôt GitHub

Créez un dépôt, par exemple `regwatch`. **Privé convient** : Community Cloud
sait déployer depuis un dépôt privé, il demandera l'autorisation d'y accéder.

Deux façons d'y mettre le code :

**Par l'interface web**, sans ligne de commande : sur la page du dépôt vide,
« uploading an existing file », puis glissez-déposez le contenu du dossier
`regwatch`. Attention, GitHub n'accepte pas le glisser-déposer d'un dossier
vide ni des fichiers commençant par un point — vous devrez créer `.streamlit`
et son `config.toml` à la main via « Create new file » en tapant
`.streamlit/config.toml` comme nom.

**Par la ligne de commande**, plus simple pour les fichiers cachés :

```
cd chemin\vers\regwatch
git init
git add .
git commit -m "MARI(a)SOL 0.6.0"
git branch -M main
git remote add origin https://github.com/VOTRE-COMPTE/regwatch.git
git push -u origin main
```

**Avant de pousser, vérifiez trois choses :**

1. Le fichier `.env` **ne doit pas** partir — il est dans `.gitignore`, mais
   confirmez avec `git status` qu'il n'apparaît pas.
2. Le dossier `data/corpus/` ne doit contenir aucun document de travail.
   Videz-le.
3. Le fichier `data/regwatch.sqlite3` ne doit pas partir non plus. Il est
   également ignoré.

---

## Étape 2 — Adapter la configuration pour l'hébergement

Dans `.streamlit/config.toml`, **commentez la ligne `address`** et **ajoutez
`headless`** :

```toml
[server]
# address = "localhost"
headless = true
```

`headless = true` empêche le serveur d'essayer d'ouvrir un navigateur sur la
machine hôte — ce qui n'a aucun sens sur un hébergeur, et fait perdre deux
secondes au démarrage. Ce réglage ne doit **pas** figurer dans la version
distribuée aux postes de travail : là, il empêcherait le navigateur de
l'utilisateur de s'ouvrir tout seul.

Ce sont les deux seuls changements nécessaires. Sur votre poste cette ligne est ce qui
empêche un autre ordinateur d'ouvrir votre corpus ; sur un hébergeur, elle
empêche la plateforme de joindre l'application.

> Gardez donc deux versions du dépôt à l'esprit : celle que vous distribuez à
> vos collègues pour installation locale garde la ligne, celle qui est
> déployée la commente. Le plus simple est de ne pas repousser ce changement
> dans l'archive que vous envoyez par Tchap.

---

## Étape 3 — Déployer

1. Allez sur <https://share.streamlit.io>, connectez-vous avec votre compte
   GitHub.
2. « Create app » → sélectionnez votre dépôt, la branche `main`, et le fichier
   principal **`app.py`**.
3. Avant de valider, ouvrez **« Advanced settings » → « Secrets »** et collez :

```toml
REGWATCH_DEMO = "1"
REGWATCH_LLM_PROVIDER = "offline"
```

**Rien d'autre. Surtout aucune clé API.**

4. Déployez. Le premier démarrage prend quelques minutes, le temps
   d'installer les dépendances.

Vous obtenez une URL du type `https://regwatch-xxxx.streamlit.app`.

---

## Étape 4 — Restreindre l'accès et charger le corpus

**Restreindre.** Dans les paramètres de l'application, section « Sharing »,
passez l'application en privé et ajoutez les adresses de vos collègues. Sans
cela l'URL est ouverte à quiconque la connaît.

**Charger.** Ouvrez l'instance et importez vous-même quelques textes publics
depuis EUR-Lex, pour que vos collègues trouvent quelque chose en arrivant :

- Data Act — CELEX `32023R2854`
- Data Governance Act — CELEX `32022R0868`
- pour votre collègue omnibus : le règlement en vigueur **et** la proposition
  de novembre 2025, importés tous deux en type « Texte réglementaire », avec
  un repère de version distinct. C'est ce qui rend la comparaison possible.

URL de téléchargement :
`https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:` + le numéro.

Rechargez le corpus après chaque redémarrage de l'instance — Community Cloud
ne conserve pas les fichiers.

---

## Étape 5 — Vérifier avant d'envoyer le lien

Ouvrez l'instance dans une fenêtre de navigation privée et contrôlez :

- [ ] la bannière orange « instance de démonstration » s'affiche ;
- [ ] page Administration → onglet Modèle : aucun champ de saisie de clé,
      seulement le message de verrouillage ;
- [ ] le bandeau latéral affiche « Démonstration — modèle désactivé » ;
- [ ] la recherche en mode « extraits bruts » renvoie des résultats ;
- [ ] la comparaison de versions fonctionne sur les deux textes chargés.

---

## Ce qu'il faut dire à vos collègues

> Voici un lien pour tester l'outil, sans rien installer :
> [URL]
>
> Attention, c'est une **démonstration publique et partagée** : ne chargez
> aucun document de travail ni marqué LIMITE. Ce que vous chargez est visible
> par les autres et effacé régulièrement.
>
> Les synthèses rédigées par l'IA sont désactivées sur cette instance. En
> revanche, la recherche dans les documents et la **comparaison de deux
> versions d'un texte, article par article**, fonctionnent entièrement.
>
> Si vous voulez tester sur vos propres dossiers, dites-le-moi : je vous
> envoie la version à installer sur votre poste.

---

## Limites à connaître

- **Ressources** : l'offre gratuite est limitée en mémoire. Un règlement
  consolidé de 400 pages passe ; plusieurs simultanément peuvent faire
  redémarrer l'instance.
- **Mise en veille** : une application inactive plusieurs jours s'endort et
  demande un clic pour redémarrer. Prévenez vos collègues.
- **Base partagée** : deux personnes qui importent en même temps se marchent
  dessus. Acceptable pour une démonstration, disqualifiant pour un usage réel.
- **Hébergement hors UE** : c'est pour cela que rien de sensible ne doit y
  aller. Un usage réel suppose un déploiement interne, avec authentification.
