# MARI(a)SOL — note de cadrage v3

**11 août 2026** · Direction de projets « économie de la donnée », DGE
Remplace la v2 du même jour. Fait suite à la fiche méthodologique
« Appli Streamlit — cartographie accès données ».

---

## 1. Ce que l'outil est devenu

Un **outil de négociation européenne** pour les agents de la direction, et un
**outil d'orientation des entreprises** sur les régimes d'accès aux données.
Deux publics, un socle technique commun : une bibliothèque de documents et un
index, sur lesquels six outils travaillent.

L'application ne connaît que les documents qu'on y charge. C'est la propriété
structurante : elle ne complète jamais avec des connaissances extérieures et,
quand le corpus ne permet pas de répondre, elle le dit.

| Outil | Ce qu'il fait gagner |
|---|---|
| Bibliothèque | Charger n'importe quel document de négociation : WK du Conseil, texte de compromis, non-paper, compte rendu. |
| Recherche | « Qui a dit quoi sur tel sujet, dans tout le corpus ? » avec citation et page. |
| Positions des États membres | La matrice d'alignement CSA2, produite automatiquement au lieu d'être faite à la main. |
| Coalitions | Qui pense comme qui, indépendamment de la France ; majorité qualifiée et minorités de blocage. |
| Comparaison de versions | Deux versions d'un texte, article par article, mot à mot — le suivi des omnibus. |
| Régimes d'accès | Une situation d'entreprise, et ce que disent les textes chargés. |

---

## 2. Trois décisions d'architecture, et ce qu'elles coûtent

### 2.1 Le graphe de règles est abandonné

**Décision.** Le module « régimes d'accès » ne repose plus sur un graphe de
règles écrit à la main, mais sur une réponse sourcée à partir des textes
chargés dans l'application.

**Pourquoi.** Le graphe suppose qu'un juriste écrive et valide chaque règle.
Cette ressource n'est pas disponible. Un graphe non validé produit des réponses
fausses avec l'apparence de la rigueur — c'est pire qu'une réponse sourcée dont
on voit la source.

**Ce que ça coûte, et il faut le dire clairement.** L'argument central du pitch
DINUM était le déterminisme : « le droit est restitué de façon strictement
déterministe », « pas de risque d'hallucination ». Cet argument-là ne tient plus
sous cette forme. Deux exécutions sur la même question peuvent formuler la
réponse différemment.

**Ce qui le remplace, et qui est défendable.** La garantie n'est plus le
déterminisme mais la **vérifiabilité imposée par le programme** :

> aucune affirmation n'est affichée sans une citation littérale, rattachée à un
> segment précis d'un document chargé, et vérifiée par le code contre le texte
> de ce segment. Une affirmation dont la citation est introuvable n'est pas
> signalée : elle est **retirée** avant affichage, et l'interface indique
> combien d'affirmations ont été écartées.

Ce n'est pas une consigne donnée au modèle — c'est un contrôle exécuté après
lui, testé, et que le modèle ne peut pas contourner. La formulation à retenir
pour la DINUM : *le modèle ne peut pas produire une assertion juridique qui ne
soit pas adossée à un passage réellement présent dans un document de la
direction.*

Le moteur de graphe reste dans le dépôt, sous `attic/`, avec ses 14 régimes et
ses tests. Le jour où du temps de juriste est dégagé — même sur un périmètre
restreint, par exemple les seuls régimes du Data Act — il se rebranche comme
page sans réécriture.

### 2.2 Pas d'embeddings, un index plein texte local

La recherche repose sur SQLite FTS5, pas sur une base vectorielle. Trois
raisons : aucun texte ne sort pour être vectorisé, ce qui compte sur des
documents LIMITE ; un résultat lexical s'explique, on voit quel terme l'a fait
remonter ; et sur un corpus juridique les recherches portent souvent sur des
termes exacts — « cyber posture », « art. 100 », « scrutiny reservation » —
cas où le lexical vaut le vectoriel.

Le point d'extension existe si le besoin apparaît : la fonction de reclassement
est isolée et peut appeler un service de rerank sans toucher au reste.

### 2.3 Le silence français vaut accord

**Votre remarque, et elle change la portée de l'outil.** Sur un article que la
France n'a pas amendé, la référence est le maintien du texte initial en
l'état. Un État membre qui en demande la suppression ou la réécriture s'en
écarte ; celui qui l'accepte s'y aligne.

Effet mesuré sur le CSA2 Titre III : la matrice passe de **10 articles
renseignés à 28**. Auparavant l'outil ne calculait rien là où la France
n'écrivait pas — c'était honnête mais inutilisable. La règle est
surchargeable article par article depuis l'interface.

---

## 3. Ce qui est livré

- Application Streamlit à sept pages, organisée par outil. Zéro exception sur
  l'ensemble des écrans, corpus vide comme corpus chargé.
- **Ingestion universelle** : PDF et Word, trois familles de documents
  détectées automatiquement et corrigibles à l'import.
- **Parser WK validé** sur les deux documents CSA2 de juillet 2026 :
  1 278 contributions, articles 3-70 et 71-97, 21 États membres.
- **Index et recherche plein texte** sur l'ensemble du corpus, tous types
  confondus.
- **Réponse sourcée** avec retrait effectif des affirmations non vérifiables.
- **Comparaison de versions** article par article, diff mot à mot, avec
  qualification de l'impact.
- **Coalitions** : taux d'accord entre toutes les paires, détection de blocs,
  majorité qualifiée, minorités de blocage, États pivots.
- **14 tests automatiques** sur les garde-fous — ils ont trouvé deux failles
  réelles pendant le développement : une citation d'un seul mot passait la
  vérification, et « should be deleted » n'était pas reconnu comme une demande
  de suppression. Les deux sont corrigées.

## 4. Ce qui reste

**Charger les textes de référence.** Le module « régimes d'accès » ne répond
que sur ce qui est chargé. Il faut y mettre le RGPD, le Data Governance Act,
le Data Act, la directive Open Data et l'AI Act — en version consolidée, en
PDF ou Word, depuis EUR-Lex. Sans cela la page reste vide, et c'est voulu.

**Brancher la clé Albert** et relever l'identifiant exact du modèle exposé,
depuis l'écran Administration.

**Mesurer la qualité de qualification** contre les matrices CSA2 faites à la
main. C'est la seule vérité terrain disponible et elle est déjà là. Objectif :
savoir sur quels types d'articles le classement automatique diverge, et de
combien. À faire avant tout usage en note.

**Remplacer les chiffres de population** par ceux de l'annexe en vigueur du
règlement intérieur du Conseil. Ceux livrés sont approchés ; l'écran
Administration permet de les éditer sans toucher au code.

---

## 5. Risques

| Risque | Portée | Traitement |
|---|---|---|
| Qualité de qualification du LLM inconnue | Une lecture diplomatique faussée | Comparaison chiffrée aux matrices manuelles, à faire avant tout usage |
| Réponse sourcée mais incomplète | Le corpus ne contient pas la disposition pertinente | La page liste ce que le corpus ne permet pas d'établir, plutôt que de combler |
| Chiffres de population approchés | Calcul de blocage faux | Avertissement affiché, fichier éditable, source documentée |
| Confusion positions écrites / votes | Conclusion politique erronée | Avertissement permanent sur la page Coalitions |
| Format WK non stable | Import cassé sur un futur document | Bascule automatique sur un autre découpage, avec avertissement — jamais d'extraction silencieusement partielle |
| Documents LIMITE transmis à Albert | Conformité | Décision prise : Albert sur tout. Le mode `offline` reste disponible ; l'import, l'index, la recherche et le diff n'appellent jamais le réseau |

---

## 6. Question ouverte

**Faut-il rouvrir le graphe de règles sur un périmètre restreint ?** Modéliser
à la main les seuls régimes du Data Act représente peut-être deux jours de
travail juridique. En échange, le module « régimes d'accès » redeviendrait
déterministe sur le texte qui concentre l'essentiel des sollicitations
d'entreprises, et l'argument tenu à la DINUM redeviendrait exact. Le code est
prêt et testé. C'est un arbitrage de disponibilité, pas de technique.
