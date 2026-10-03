"""
Base de connaissance de l'application — et l'assistant qui y répond.

Ce fichier est la source unique de toute explication affichée : la page Mode
d'emploi, les fenêtres « Comment ça marche ? » de chaque module, et
l'assistant qui répond aux questions posées en français. Écrire l'explication
à un seul endroit évite qu'une page dise une chose et une autre le contraire
après un changement de calcul.

**Ce que l'assistant sait, et ce qu'il ne sait pas.** Il répond uniquement à
partir des fiches ci-dessous, qui décrivent le fonctionnement de l'outil. Il
ne connaît ni le droit européen, ni les documents chargés, ni le dossier en
cours : ces questions-là relèvent de l'outil Recherche, qui travaille sur le
corpus et cite ses sources. Cette séparation est délibérée — un assistant qui
mélange « comment l'outil calcule » et « ce que dit le Data Act » produit des
réponses dont on ne sait plus laquelle des deux on lit.

La recherche dans les fiches est lexicale et locale : aucune requête réseau
n'est nécessaire pour obtenir une réponse. Le modèle, quand il est disponible,
ne sert qu'à rédiger la réponse à partir des fiches retenues.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .llm import LLMInvalidOutput, LLMUnavailable, get_client


@dataclass
class Fiche:
    """Une réponse à une question de fonctionnement.

    `technique` porte le détail que personne ne veut lire par défaut mais que
    quelqu'un finit toujours par demander : la formule exacte, la fonction et
    la bibliothèque Python qui l'exécutent, les seuils en dur. Il est séparé
    de `reponse` pour que la réponse ordinaire reste courte, et donné au
    modèle — ou affiché tel quel — dès que la question porte sur le calcul.
    """

    cle: str
    module: str            # bibliotheque | recherche | positions | coalitions
    #                        versions | regimes | amendements | general
    question: str
    reponse: str
    mots_cles: list[str] = field(default_factory=list)
    technique: str = ""

    def texte_complet(self) -> str:
        """Fiche + détail technique, pour le guide et pour l'assistant."""
        if not self.technique:
            return self.reponse
        return f"{self.reponse}\n\n**Sous le capot**\n\n{self.technique}"


# ---------------------------------------------------------------------------
# Les fiches
# ---------------------------------------------------------------------------

FICHES: list[Fiche] = [

    # --- général ----------------------------------------------------------
    Fiche(
        "garantie", "general",
        "Qu'est-ce que l'outil garantit exactement ?",
        "Trois choses, et pas davantage.\n\n"
        "**1. Aucune affirmation sans citation vérifiée.** Toute phrase "
        "produite par le modèle est accompagnée d'une citation, et cette "
        "citation est recherchée *littéralement* dans le document source par "
        "le programme, pas par le modèle. Si elle ne s'y trouve pas, une "
        "seconde recopie exacte est demandée ; si elle échoue encore, "
        "l'affirmation est **retirée** de la réponse. Elle n'est pas signalée, "
        "elle disparaît.\n\n"
        "**2. Aucun calcul confié au modèle.** Matrice d'alignement, taux "
        "d'accord, blocs, majorité qualifiée, écarts entre versions : tout "
        "cela est de l'arithmétique faite par le programme. Le modèle ne "
        "calcule rien.\n\n"
        "**3. Aucune donnée hors du poste, sauf vers Albert.** Les documents "
        "restent sur votre machine. Seuls les extraits nécessaires à une "
        "analyse partent vers l'API Albert de la DINUM, hébergée en "
        "SecNumCloud.\n\n"
        "Ce qui n'est **pas** garanti : la justesse juridique d'un classement, "
        "l'exhaustivité d'une extraction sur un PDF mal structuré, et le "
        "résultat de la négociation.",
        ["garantie", "fiable", "confiance", "hallucination", "vérification",
         "citation", "sûr", "erreur"]),

    Fiche(
        "sauvegarde", "general",
        "Si je ferme l'application, faut-il tout refaire ?",
        "Non. Tout est enregistré au fur et à mesure dans une base locale "
        "(`data/regwatch.sqlite3`) : documents importés, découpage en "
        "articles, classement de chaque contribution, position française de "
        "référence, index de recherche. Fermer la fenêtre, éteindre le poste, "
        "revenir trois semaines plus tard : les analyses sont là.\n\n"
        "Ce qui repart à zéro, ce sont seulement les réglages d'affichage, "
        "filtres, onglet ouvert, périmètre sélectionné.\n\n"
        "Une interruption en cours d'analyse ne fait rien perdre non plus : "
        "chaque contribution est enregistrée dès qu'elle est traitée. "
        "Relancer reprend là où l'on s'était arrêté, à condition de laisser "
        "cochée l'option « Ne traiter que les contributions non analysées ».\n\n"
        "**Une réserve importante** : ne placez pas le dossier `data/` dans "
        "OneDrive ou SharePoint. La synchronisation copie le fichier de base "
        "de données pendant qu'il est en cours d'écriture et le corrompt.",
        ["sauvegarde", "fermer", "perdre", "refaire", "enregistré", "quitter",
         "persistant", "base"],
        technique="""SQLite, en un seul fichier, via le module standard `sqlite3` (aucun ORM). Les
tables : `documents`, `segments`, `contributions`, `analyses`, `fr_reference`,
`llm_audit`, plus l'index `segments_fts` (FTS5). Chaque contribution analysée
est écrite dans sa propre transaction, ce qui est la raison pour laquelle une
interruption ne perd que la contribution en cours.

`check_integrity()` exécute `PRAGMA integrity_check` et compare le nombre de
segments à celui de l'index ; `repair()` reconstruit l'index à partir des
segments. L'index est une donnée dérivée : le reconstruire ne peut rien
perdre."""),

    Fiche(
        "plusieurs", "general",
        "Plusieurs personnes peuvent-elles travailler dessus en même temps ?",
        "Pas sur la même installation. Chaque agent lance l'application sur "
        "son poste, avec sa propre base et ses propres documents : ce que vous "
        "chargez n'est pas visible par votre collègue.\n\n"
        "Un usage collectif suppose un hébergement sur un serveur interne, "
        "qui est une décision d'administration et non un développement, "
        "c'est l'un des points listés dans la note d'arbitrage.",
        ["plusieurs", "collègue", "partager", "équipe", "simultané",
         "collaboratif", "ensemble"]),

    Fiche(
        "limite", "general",
        "Dans quels cas l'outil se trompe-t-il le plus souvent ?",
        "Quatre situations, connues et documentées :\n\n"
        "- **Une contribution longue qui porte plusieurs demandes de sens "
        "contraire.** La ramener à une seule position perd de l'information. "
        "Le panneau de fiabilité les signale.\n"
        "- **Une renumérotation entre deux versions.** Un article déplacé "
        "apparaît comme supprimé d'un côté et ajouté de l'autre.\n"
        "- **Un PDF mal structuré**, dont l'extraction perd des lignes ou "
        "colle deux colonnes. Vérifiez les compteurs à l'import.\n"
        "- **Une opposition exprimée sans marqueur** (« nous nous "
        "interrogeons sur l'opportunité… ») : le classement lexical la rate, "
        "et le modèle peut l'adoucir.\n\n"
        "Dans tous les cas, la contribution intégrale reste consultable dans "
        "l'onglet Détail : un classement se conteste en trente secondes.",
        ["erreur", "faux", "trompe", "limite", "risque", "défaut", "rate"]),

    # --- bibliothèque -----------------------------------------------------
    Fiche(
        "types", "bibliotheque",
        "Comment l'outil sait-il à quel type de document il a affaire ?",
        "Il lit les premières pages et cherche des signatures : un tableau à "
        "deux ou trois colonnes avec des codes pays en tête de cellule est un "
        "document de commentaires consolidés ; une suite d'« Article premier, "
        "Article 2… » précédée de considérants est un texte réglementaire ; "
        "le reste est traité comme texte libre.\n\n"
        "**La détection se trompe régulièrement** sur les textes consolidés et "
        "les documents mixtes. Le type est donc corrigeable après coup dans "
        "**Bibliothèque → Corpus → Type de document**, sans réimport : c'est "
        "lui qui décide des pages où le document apparaît.\n\n"
        "Le découpage, lui, n'est pas refait par cette correction. Si le "
        "document a été mal découpé, supprimez-le et réimportez-le en forçant "
        "le bon type.",
        ["type", "détection", "wk", "tableau", "texte réglementaire",
         "classement du document", "import"]),

    Fiche(
        "eurlex", "bibliotheque",
        "Pourquoi l'outil récupère-t-il le HTML d'EUR-Lex et non le PDF ?",
        "Parce que le PDF du Journal officiel est une **mise en page**, pas un "
        "texte : deux colonnes, des césures en fin de ligne, des en-têtes et "
        "des numéros de page insérés au milieu des phrases. L'extraction "
        "produit un texte qu'il faut recoudre, et le recousage introduit des "
        "écarts qui ne sont pas dans le texte officiel. Dans une comparaison "
        "de versions, ces écarts se comptent comme des modifications : on "
        "comparerait deux extractions, pas deux textes.\n\n"
        "Le HTML porte la structure, un article est un bloc, et donne un "
        "texte stable d'une version à l'autre.\n\n"
        "**Ce que cela coûte** : la pagination du JO est perdue. Les numéros "
        "de page affichés dans les citations d'un texte récupéré ainsi sont "
        "des repères internes à l'outil, pas les pages du Journal officiel.\n\n"
        "Si le réseau bloque la sortie, quatre adresses sont essayées, dont "
        "l'endpoint machine de l'Office des publications, puis le PDF en "
        "repli. En dernier recours, ouvrez l'adresse dans le navigateur, "
        "enregistrez la page et chargez le fichier depuis l'onglet Importer.",
        ["eurlex", "html", "pdf", "télécharger", "celex", "journal officiel",
         "récupérer"]),

    Fiche(
        "titres", "bibliotheque",
        "Comment regrouper les articles par titre du règlement ?",
        "Deux voies, dans cet ordre :\n\n"
        "**1. Depuis le texte réglementaire lui-même.** S'il est chargé, "
        "l'outil lit les en-têtes « TITRE IV, … » au fil du document : tout "
        "article rencontré ensuite appartient à ce titre jusqu'au suivant. "
        "C'est la voie fiable, parce qu'elle recopie la structure officielle.\n\n"
        "**2. À la main, par bornes.** Vous saisissez « Titre IV : articles 98 "
        "à 118 » et l'outil range les articles dans l'intervalle.\n\n"
        "Le rattachement n'est jamais deviné à partir du seul numéro : deux "
        "règlements numérotent différemment, et une erreur de titre fausserait "
        "tous les regroupements qui en dépendent.",
        ["titre", "regrouper", "chapitre", "section", "titre iv", "grouper"]),

    # --- positions --------------------------------------------------------
    Fiche(
        "scores", "positions",
        "Comment les scores d'alignement sont-ils calculés ?",
        "En trois étapes séparées, dont une seule mobilise le modèle.\n\n"
        "**1. La position française de référence est établie**, article par "
        "article. Soit la France a déposé un amendement ou un commentaire, et "
        "cette contribution est résumée ; soit elle n'a rien déposé, et la "
        "référence est le maintien du texte initial en l'état, c'est la "
        "règle du silence, posée par la direction : ne pas amender vaut "
        "acceptation.\n\n"
        "**2. Chaque contribution d'un État membre est classée** par rapport à "
        "cette référence, sur un barème à trois valeurs : **2 = aligné** "
        "(même objectif, même mécanisme, ou soutien explicite), **1 = "
        "partiel** (convergence sur l'objectif mais divergence sur les "
        "moyens, ou accord assorti de conditions), **0 = divergent** (la "
        "contribution contredit la demande française, ou défend la solution "
        "que la France cherche à écarter). Une quatrième valeur, **neutre**, "
        "laisse la case vide : elle marque une contribution qui n'exprime "
        "aucune demande, une question de compréhension, une remarque de "
        "procédure. Une absence de position n'est jamais comptée comme un "
        "accord.\n\n"
        "**3. Les agrégats sont calculés par le programme.** La moyenne d'un "
        "État membre est la moyenne arithmétique de ses scores sur les "
        "articles où il s'est exprimé, les cases vides n'entrent pas dans le "
        "calcul. Quand un État s'exprime plusieurs fois sur le même article, "
        "**la position la plus défavorable est retenue** : une objection ne "
        "s'annule pas par un commentaire de soutien exprimé ailleurs.\n\n"
        "Le classement de l'étape 2 est le seul endroit où le modèle "
        "intervient, et il doit citer le passage qui fonde son verdict.",
        ["score", "calcul", "note", "alignement", "matrice", "moyenne",
         "barème", "2 1 0", "comment sont calculés"],
        technique="""**Où c'est écrit** : `core/scoring.py` (classement), `core/store.py`
(`score_matrix`), `core/analysis.py` (agrégats). Bibliothèques : `pandas`
pour toute l'arithmétique, `pydantic` pour contraindre la sortie du modèle.

**Le classement d'une contribution.** Le modèle reçoit la position française
de référence et le texte de la contribution, et répond selon un schéma
Pydantic figé : `stance ∈ {aligne, partiel, divergent, neutre}`, `confidence
∈ [0,1]`, `quote` (recopie littérale). La citation est cherchée dans le texte
source par `quote_matches()`, normalisation des espaces et des apostrophes,
minimum 4 mots ; sans correspondance, une seconde recopie est demandée, puis
la contribution passe en `neutre`. Correspondance des valeurs :
`aligne → 2`, `partiel → 1`, `divergent → 0`, `neutre → NaN`.

**La matrice.** `score_matrix()` construit un tableau croisé articles × EM :

```python
matrix = (df.pivot_table(index="section_label", columns="ms_code",
                         values="score", aggfunc="min")
            .reindex(ordre_des_articles))
```

`aggfunc="min"` est la règle « la position la plus défavorable l'emporte » :
sur un article où un EM s'est exprimé deux fois, 0 et 2 donnent 0. Les cases
`NaN` ne sont **jamais** remplies par 0, c'est la distinction entre « opposé »
et « ne s'est pas exprimé ».

**Les agrégats**, avec `s_i,a` le score de l'EM *i* sur l'article *a* et
`A_i` l'ensemble des articles où il s'est exprimé :

- proximité moyenne : `moyenne_i = (1/|A_i|) · Σ_{a∈A_i} s_i,a`, soit
  `matrix.mean(axis=0, skipna=True)` ;
- dispersion d'un article : `matrix.std(axis=1)` (écart-type d'échantillon,
  `ddof=1`, convention `pandas`) ;
- articles clivants : tri croissant sur la moyenne par article, départage par
  dispersion décroissante ;
- couverture : `matrix.notna().sum()`.

`skipna=True` est le défaut `pandas` et il est ici structurant : une absence
de position ne tire aucune moyenne ni vers le haut ni vers le bas."""),

    Fiche(
        "silence", "positions",
        "Que veut dire « le silence vaut acceptation » ?",
        "C'est la règle métier posée par la direction, et elle change tout le "
        "calcul.\n\n"
        "Sur un article où la France n'a déposé ni amendement ni commentaire, "
        "on considère qu'elle accepte le texte initial dans sa rédaction "
        "actuelle. La position de référence devient donc « maintien de "
        "l'article tel quel ». Un État membre qui en demande la suppression ou "
        "la réécriture s'en écarte ; celui qui l'accepte s'y aligne.\n\n"
        "Sans cette règle, l'outil ne pourrait rien dire des articles que la "
        "France n'a pas amendés, soit, sur un document type, les deux tiers "
        "du texte. Avec elle, la couverture passe d'une dizaine d'articles à "
        "l'ensemble du document.\n\n"
        "**La limite à connaître** : si ni la France ni l'État membre n'ont "
        "amendé l'article, on ne sait rien de la position de cet État. La case "
        "reste vide. Un silence partagé n'est pas un accord, c'est une absence "
        "d'information.\n\n"
        "La règle se désactive article par article : saisissez une position "
        "française explicite dans l'encadré « Position française de "
        "référence », elle prend le pas sur le silence.",
        ["silence", "acceptation", "amendement", "règle", "france", "vide",
         "pas amendé"],
        technique="""Implémentation : `core/scoring.py`, constante `FR_SILENCE_REFERENCE` et bloc
`SILENCE_RULE` du prompt. La référence utilisée pour un article sans
contribution française n'est pas une chaîne vide, c'est un texte explicite
(« la France accepte le texte dans sa rédaction actuelle et ne demande aucune
modification ») injecté dans le prompt à la place de la position française.
Le modèle ne sait donc pas qu'il traite un cas de silence : il classe par
rapport à une position, comme partout ailleurs.

Une position française saisie à la main est enregistrée dans la table
`fr_reference` (`document_id`, `section_id`, `text`, `origin`) et prend le pas
sur le silence : `load_fr_reference()` est consultée avant d'appliquer la
règle."""),

    Fiche(
        "referentiels", "positions",
        "Quelle différence entre les deux référentiels de comparaison ?",
        "Ils répondent à deux questions différentes.\n\n"
        "**Par rapport à la position française** · « qui est avec nous ? ». "
        "L'écart mesuré est l'écart à ce que demande la France, règle du "
        "silence comprise. C'est le référentiel de la négociation : il sert à "
        "établir une liste d'alliés.\n\n"
        "**Par rapport au texte initial** · « qui veut le changer ? ». "
        "L'écart mesuré est la demande de modification du texte lui-même, quel "
        "que soit l'avis français, France comprise. C'est le référentiel de "
        "lecture du dossier : il montre la pression qui s'exerce sur le texte.\n\n"
        "Sur un article que la France n'a pas amendé, **les deux coïncident**, "
        "c'est mécanique, puisque la référence française est alors le texte "
        "lui-même. Ils divergent sur les articles où la France demande une "
        "réécriture, et ce sont précisément ceux qui comptent.\n\n"
        "Le second référentiel est entièrement déterministe : il applique la "
        "règle du silence au texte de chaque contribution, sans appeler le "
        "modèle. Il est donc disponible immédiatement, même avant toute "
        "analyse.",
        ["référentiel", "comparé", "bascule", "texte initial",
         "position française", "deux lectures"]),

    Fiche(
        "echantillon", "positions",
        "Que traite l'outil quand je choisis « un dixième » des contributions ?",
        "Un échantillon **réparti sur tous les articles**, et non les "
        "premières contributions du document.\n\n"
        "Concrètement : l'outil fait un tour de table article par article, "
        "une contribution sur chaque article, puis une deuxième sur chacun, et "
        "ainsi de suite jusqu'au plafond. Sans cette précaution, un dixième "
        "d'un document de cent articles ne couvrirait que les dix premiers, et "
        "la matrice n'afficherait que le début du texte. C'est un défaut qui a "
        "été constaté en test et corrigé.\n\n"
        "L'usage recommandé : un dixième pour juger la qualité du classement "
        "sur un échantillon lisible, puis la totalité. Les contributions déjà "
        "analysées ne sont pas retraitées si l'option correspondante est "
        "cochée.",
        ["échantillon", "dixième", "moitié", "partiel", "combien",
         "toutes les contributions", "volume"],
        technique="""L'échantillonnage est stratifié par article, pas séquentiel :

```python
df["rang"] = df.groupby("section_id").cumcount()
echantillon = df.sort_values(["rang", "section_order"]).head(plafond)
```

Trier sur `rang` avant `section_order` revient à faire un tour de table : tous
les rangs 0 (une contribution par article) passent avant le premier rang 1. Un
`head(n)` naïf sur le document couvrirait 2 articles là où celui-ci en couvre
`n`. C'est ce que vérifie le test `test_echantillon_couvre_tous_les_articles`."""),

    Fiche(
        "ponderation", "positions",
        "À quoi sert la pondération par critère, et comment fonctionne-t-elle ?",
        "Elle répond à un constat : toutes les divergences ne pèsent pas "
        "pareil dans une négociation. Une opposition sur une virgule et une "
        "opposition sur le rôle de la Commission comptent autant dans une "
        "moyenne, ce qui est faux politiquement.\n\n"
        "**Fonctionnement.** Vous écrivez un critère en français, par "
        "exemple « les positions qui demandent de supprimer l'intervention de "
        "la Commission dans la désignation ». Le modèle examine chaque "
        "contribution et dit si elle y correspond, en recopiant le passage qui "
        "le montre ; ce passage est vérifié dans le texte source, comme "
        "partout ailleurs. Les contributions retenues comptent alors pour le "
        "facteur choisi (2 par défaut) dans les moyennes.\n\n"
        "**Ce que la pondération ne change pas** : le classement d'une "
        "position. DE reste divergent sur l'article 100. Ce qui change, c'est "
        "le poids de cette divergence dans la proximité moyenne, dans le "
        "classement des alliés et dans la cohésion d'un bloc.\n\n"
        "**Trois précautions.** Elle est optionnelle et doit être lancée "
        "explicitement ; le résultat non pondéré reste affiché à côté, avec "
        "l'écart ; et le critère employé figure dans les livrables produits "
        "sous pondération. Une note pondérée doit dire par quoi elle l'est.",
        ["pondération", "poids", "critère", "pondérer", "importance",
         "facteur", "priorité"],
        technique="""`core/ponderation.py`. Le modèle ne produit qu'un booléen par contribution
(`correspond`, plus la citation vérifiée) ; la pondération elle-même est une
moyenne pondérée classique, avec `w_i,a = f` (facteur choisi, 2 par défaut) si
la contribution est retenue par le critère et `w_i,a = 1` sinon :

```
score_pondéré_i = Σ_a w_i,a · s_i,a / Σ_a w_i,a
écart_i        = score_pondéré_i − score_brut_i
```

L'écart est affiché tel quel, signé : c'est lui qui dit si le critère
avantage ou désavantage un État membre. Un EM dont aucune contribution n'est
retenue a un écart nul par construction, le critère ne le discrimine pas, et
il vaut mieux le voir que le deviner. La matrice, elle, n'est pas modifiée :
`matrice_ponderee()` renvoie les mêmes 0/1/2, seuls les agrégats bougent."""),

    Fiche(
        "nonpaper", "positions",
        "Puis-je mettre à jour les positions depuis un non-paper ou une note ?",
        "Oui, et c'est fait pour : toutes les positions n'arrivent pas sous "
        "forme de tableau à trois colonnes. Un non-paper d'une délégation, un "
        "papier blanc, un compte rendu de réunion ou une note que vous avez "
        "rédigée peuvent alimenter la matrice.\n\n"
        "**La méthode est en deux temps, volontairement.** L'outil lit le "
        "document, en extrait les positions qu'il croit y voir, et propose un "
        "rattachement article par article, avec, pour chacune, la citation du "
        "passage correspondant. **Rien n'entre dans la matrice avant que vous "
        "ayez validé.** Vous cochez ce qui est juste, corrigez l'article "
        "quand le rattachement se trompe, écartez le reste.\n\n"
        "C'est plus lent qu'un enregistrement automatique, et c'est le prix de "
        "la fiabilité de la matrice : une position mal rattachée fausse "
        "silencieusement toutes les coalitions qui en dépendent.\n\n"
        "Les positions ainsi ajoutées portent la mention de leur source, et "
        "restent distinguables de celles issues des tableaux du Conseil.",
        ["non-paper", "nonpaper", "papier blanc", "note", "mettre à jour",
         "ajouter position", "compte rendu"]),

    Fiche(
        "plusieurs_tableaux", "positions",
        "Puis-je analyser plusieurs tableaux de commentaires ensemble ?",
        "Oui. Sélectionnez-en plusieurs dans la liste de documents en haut de "
        "la page : les contributions sont réunies et la matrice porte sur "
        "l'ensemble.\n\n"
        "C'est l'usage prévu quand les titres d'un même règlement ont été "
        "traités dans des documents de travail distincts, le Titre III dans "
        "un tableau, le Titre IV dans un autre. Combinés au regroupement par "
        "titre, ils donnent la vue d'ensemble du règlement.\n\n"
        "**Attention à une chose** : la position française de référence est "
        "enregistrée par document. Si le même article figure dans deux "
        "tableaux, la référence du premier document trouvé est utilisée. "
        "Vérifiez-la dans l'encadré « Position française de référence ».",
        ["plusieurs tableaux", "fusionner", "combiner", "deux wk",
         "titre iii", "ensemble", "regrouper documents"]),

    # --- coalitions -------------------------------------------------------
    Fiche(
        "accord", "coalitions",
        "Comment le taux d'accord entre deux États membres est-il calculé ?",
        "C'est la proportion des articles sur lesquels les deux tiennent la "
        "même position, **calculée sur les seuls articles où les deux se sont "
        "exprimés**.\n\n"
        "Exemple : DE et NL se sont tous deux exprimés sur douze articles ; "
        "ils tiennent la même position sur neuf. Leur taux d'accord est de "
        "75 %. Les articles où l'un des deux s'est tu n'entrent pas dans le "
        "calcul, un silence ne vaut ni accord ni désaccord.\n\n"
        "**La limite qui compte** : un taux calculé sur deux articles communs "
        "ne signifie rien. Deux coïncidences suffisent à afficher 100 %. Le "
        "réglage « Articles communs minimum » sert exactement à écarter ces "
        "faux couples, et le panneau de fiabilité compte les paires "
        "concernées.",
        ["accord", "taux", "paire", "deux à deux", "similarité entre états"],
        technique="""`core/coalition.py`, fonction `agreement_matrix()`. Pour deux EM *i* et *j*,
avec `C_ij` l'ensemble des articles où **les deux** se sont exprimés :

```
accord(i,j) = |{ a ∈ C_ij : s_i,a = s_j,a }| / |C_ij|      si |C_ij| ≥ n_min
            = NaN                                          sinon
```

En code, sur la matrice articles × EM :

```python
commun = matrix[[i, j]].dropna()
accord = (commun[i] == commun[j]).mean() if len(commun) >= n_min else np.nan
```

Trois propriétés à connaître : l'égalité est stricte (2 contre 1 compte comme
un désaccord, pas comme un demi-accord) ; le dénominateur est le nombre
d'articles communs, jamais le nombre total d'articles ; et une paire sous le
seuil `n_min` renvoie `NaN` et disparaît du graphe au lieu d'afficher un
100 % obtenu sur deux coïncidences."""),

    Fiche(
        "blocs", "coalitions",
        "Comment les blocs sont-ils détectés ?",
        "Par un graphe, et volontairement par une méthode simple.\n\n"
        "Chaque État membre est un nœud. Deux États sont reliés par une arête "
        "quand leur taux d'accord dépasse le seuil que vous fixez, sur un "
        "nombre suffisant d'articles communs. Un bloc est ensuite une "
        "**composante connexe** de ce graphe : un groupe d'États reliés de "
        "proche en proche.\n\n"
        "La cohésion affichée est la moyenne des taux d'accord des arêtes "
        "internes au bloc.\n\n"
        "**Pourquoi cette méthode plutôt qu'un regroupement statistique plus "
        "savant** : parce qu'un agent doit pouvoir refaire le calcul à la main "
        "sur un cas et contester le résultat. Un regroupement que personne ne "
        "peut vérifier n'a pas sa place dans une note.\n\n"
        "Deux effets de bord à connaître : un seuil trop bas relie tout le "
        "monde en un seul bloc ; un seuil trop haut isole tout le monde. "
        "L'outil vous avertit dans le premier cas.",
        ["bloc", "graphe", "coalition", "seuil", "composante", "grouper états"],
        technique="""`core/coalition.py`, fonction `detect_blocs()`. Bibliothèque : `networkx`.

```python
G = nx.Graph()
for i, j in itertools.combinations(codes, 2):
    a = accord(i, j)
    if not np.isnan(a) and a >= seuil:
        G.add_edge(i, j, weight=a)
blocs = [c for c in nx.connected_components(G) if len(c) >= 2]
```

Un bloc est donc une **composante connexe** : la relation « accord ≥ seuil »
est étendue par transitivité de proche en proche. Cohésion affichée :

```
cohésion(B) = moyenne des poids des arêtes internes à B
            = (1/|E_B|) · Σ_{(i,j)∈E_B} accord(i,j)
```

**Ce que ce choix implique, et pourquoi il est assumé.** Une composante
connexe n'est pas une clique : A–B et B–C suffisent à mettre A et C dans le
même bloc, même si A et C ne s'accordent pas. Un algorithme de communautés
(Louvain, `nx.community.greedy_modularity_communities`) donnerait des groupes
plus fins, mais dépendant d'une optimisation de modularité que personne ne
peut refaire à la main. Ici, un agent qui conteste un bloc n'a qu'à demander
la liste des arêtes : chaque arête est un taux d'accord recalculable sur les
articles communs. Le critère de vérifiabilité l'a emporté sur la finesse.

Deux régimes limites, mécaniques : sous un seuil bas le graphe devient
complet et ne donne qu'un bloc de 27 ; au-dessus du taux d'accord maximal
observé, le graphe est vide. L'outil signale le premier cas.

Les États **pivots** sortent du même graphe : ce sont les nœuds de plus fort
degré pondéré hors bloc français, c'est-à-dire ceux qui relieraient deux
composantes."""),

    Fiche(
        "qmv", "coalitions",
        "Comment la majorité qualifiée et la minorité de blocage sont-elles calculées ?",
        "Selon l'article 16(4) du traité sur l'Union européenne.\n\n"
        "**Majorité qualifiée** : 55 % des États membres, soit 15 sur 27, "
        "représentant au moins 65 % de la population de l'Union. Les deux "
        "conditions sont cumulatives.\n\n"
        "**Minorité de blocage** : au moins **4 États membres** représentant "
        "plus de 35 % de la population. Le seuil des quatre États est ce qui "
        "explique qu'un groupe de trois grands pays, même à 46 % de la "
        "population, ne bloque rien.\n\n"
        "C'est à cela, et à cela seulement, que servent les chiffres de "
        "population dans l'outil : savoir si un groupe suffit. Ils servent "
        "aussi à hiérarchiser un démarchage à proximité égale.\n\n"
        "**Deux avertissements.** Les chiffres viennent d'un fichier local "
        "modifiable et doivent être remplacés par ceux de l'annexe en vigueur "
        "du règlement intérieur du Conseil avant tout usage en négociation. Et "
        "surtout : les positions écrites d'un groupe de travail ne sont pas "
        "des votes. Ce calcul dit ce que donnerait cette répartition si elle "
        "se transposait en vote, ce qui n'arrive jamais tel quel.",
        ["majorité qualifiée", "qmv", "blocage", "minorité", "population",
         "vote", "conseil", "55", "65"],
        technique="""`core/coalition.py`, fonction `qualified_majority()`. Aucun modèle, aucune
subtilité : deux comparaisons et un seuil d'arrondi.

```python
n_requis  = math.ceil(0.55 * 27)               # 15 États membres
pop_totale = populations["population"].sum()
pop_groupe = populations.loc[groupe, "population"].sum()

majorite = len(groupe) >= n_requis and pop_groupe >= 0.65 * pop_totale
blocage  = len(groupe) >= 4       and pop_groupe >  0.35 * pop_totale
```

Formellement, avec *G* le groupe et *p(·)* la population :

```
QMV(G)     ⟺ |G| ≥ ⌈0,55 × 27⌉ = 15   ∧   p(G) ≥ 0,65 × p(UE)
Blocage(G) ⟺ |G| ≥ 4                  ∧   p(G) > 0,35 × p(UE)
```

Le `⌈·⌉` compte : 0,55 × 27 = 14,85, et 14 États ne font pas une majorité
qualifiée. L'inégalité stricte sur le blocage vient de la rédaction du traité
(« plus de 35 % »). Les populations sont lues dans `data/rules/populations.csv`,
modifiable dans Administration, ce sont les seuls chiffres de l'outil qui
viennent d'ailleurs que de vos documents."""),

    # --- versions ---------------------------------------------------------
    Fiche(
        "diff", "versions",
        "Comment la comparaison entre deux versions fonctionne-t-elle ?",
        "En deux étapes, dont la première est entièrement déterministe.\n\n"
        "**1. Appariement.** Les articles des deux versions sont rapprochés "
        "par leur identifiant de section, `art_5`, `rec_12`, et non par "
        "leur position dans le document : insérer un article ne décale donc "
        "pas toute la comparaison.\n\n"
        "**2. Écarts.** Comparaison mot à mot par `difflib`, qui donne la "
        "similarité, le nombre de mots ajoutés et retirés, et le rendu "
        "souligné / barré. Deux exécutions donnent exactement le même "
        "résultat.\n\n"
        "**3. Qualification**, la seule étape où le modèle parle. On lui "
        "donne un écart *déjà constaté* et on lui demande d'en dire la portée "
        "(majeure, mineure, rédactionnelle). Il ne peut ni inventer un "
        "changement, ni en masquer un.\n\n"
        "**Le faux positif à connaître** : un article renuméroté apparaît "
        "comme une suppression suivie d'un ajout. Le panneau de fiabilité le "
        "signale quand les deux se produisent ensemble, et le fil du texte "
        "permet de le vérifier.",
        ["comparaison", "diff", "versions", "changement", "difflib",
         "mot à mot", "similarité"],
        technique="""`core/versions.py`. Bibliothèque : `difflib` (bibliothèque standard), sur des
listes de mots et non de caractères.

```python
sm = difflib.SequenceMatcher(None, mots_a, mots_b, autojunk=False)
similarite = sm.ratio()
for tag, i1, i2, j1, j2 in sm.get_opcodes():   # equal | replace | delete | insert
    ...
```

`ratio()` vaut `2·M / T` où *M* est le nombre de mots appariés et *T* le
nombre total de mots des deux versions, pas une distance d'édition
normalisée : deux textes de longueurs très différentes plafonnent bas même
sans réécriture. Les mots ajoutés et retirés sont comptés sur les opcodes
`insert` / `replace` et `delete` / `replace`, et le rendu souligné / barré est
produit à partir des mêmes opcodes. `autojunk=False` est indispensable :
l'heuristique par défaut de `difflib` traite comme du bruit tout élément
présent dans plus de 1 % d'une séquence longue, soit, sur un règlement, les
mots « article », « paragraphe », « Commission ».

**L'appariement** se fait par identifiant de section (`art_5`, `rec_12`),
extrait par expression régulière à l'import, jamais par la position dans le
document : un article inséré ne décale pas la comparaison. Corollaire connu :
une renumérotation apparaît comme une suppression plus un ajout."""),

    Fiche(
        "fil", "versions",
        "À quoi sert le « fil du texte » ?",
        "À suivre un texte sur **toute sa trajectoire**, et pas seulement "
        "entre deux versions.\n\n"
        "Il affiche toutes les versions chargées dans l'ordre, proposition "
        "de la Commission, compromis 1, compromis 2…, puis, pour un article "
        "que vous choisissez, son évolution à travers chacune : présent ou "
        "absent, similarité avec l'étape précédente, mots ajoutés et retirés, "
        "et le diff mot à mot de chaque étape.\n\n"
        "C'est ce qui manquait pour suivre un omnibus : un texte qui passe par "
        "cinq compromis ne se lit pas deux versions à la fois.\n\n"
        "L'ordre repose sur la date de version, détectée à l'import dans "
        "l'en-tête du document et corrigeable dans Bibliothèque → Corpus. "
        "Sans date, l'ordre est celui de l'import.",
        ["fil", "trajectoire", "omnibus", "chronologie", "toutes les versions",
         "évolution"]),

    Fiche(
        "omnibus", "versions",
        "Comment comparer un omnibus au Data Act ou au RGPD ?",
        "Pas avec la comparaison de versions, et c'est la distinction la plus "
        "importante de ce module.\n\n"
        "**Un omnibus n'est pas une version du Data Act.** C'est un texte qui "
        "*dit* ce qu'il faut y changer : « à l'article 5 du règlement (UE) "
        "2023/2854, le paragraphe 2 est remplacé par le texte suivant… ». Son "
        "article premier ne correspond à rien dans le Data Act, il énumère "
        "des modifications. Les apparier par numéro, comme on apparie deux "
        "compromis successifs, met en regard des articles qui ne traitent pas "
        "du même sujet.\n\n"
        "**L'onglet « Omnibus et actes modificatifs »** fait le travail juste : "
        "il lit les instructions de modification, les range par texte modifié "
        "puis par article visé, et, si vous avez chargé le texte consolidé, "
        "reconstitue chaque article avant et après, avec le mot à mot. Les "
        "articles que l'omnibus ne touche pas restent affichés, marqués "
        "« inchangé ».\n\n"
        "**Pour comparer deux versions d'un même omnibus**, la proposition de "
        "la Commission et un compromis de présidence, le même onglet compare "
        "les instructions elles-mêmes, article visé par article visé. C'est la "
        "question de négociation : sur quels articles du Data Act la "
        "présidence a-t-elle changé ce que la Commission proposait ?\n\n"
        "**La portée de chaque modification se caractérise** : un bouton, et "
        "le modèle dit ce que la modification change et si elle pèse, "
        "majeure, mineure, rédactionnelle. Ce qu'il qualifie est une "
        "modification écrite par le législateur, pas un rapprochement "
        "calculé entre deux textes.\n\n"
        "**Trois vues, dans cet ordre.** La *vue d'ensemble* répond à la "
        "question qu'on se pose quand le dossier arrive : où ce texte "
        "frappe-t-il, et fort ? Elle donne la carte de l'acte (une ligne par "
        "texte modifié, une case par article, colorée par portée), la charge "
        "par texte, la liste des points durs, les notions qui reviennent d'un "
        "texte à l'autre, un tableau filtrable de toutes les modifications, "
        "et les deux livrables. Le *texte par texte* est la lecture de "
        "travail : article par article, l'instruction verbatim et le texte "
        "avant/après. La troisième vue compare deux versions du même "
        "omnibus.\n\n"
        "**Dans quel ordre s'en servir.** (1) Chargez l'omnibus *et* les "
        "textes consolidés qu'il modifie, sans eux, l'écran affiche les "
        "instructions mais pas l'article avant/après. (2) Vue d'ensemble, "
        "bouton « Caractériser tout l'omnibus » : une seule passe du modèle "
        "sur l'ensemble des textes cibles, comptez trois secondes par "
        "article. (3) Lisez la carte, puis « Par où commencer » : c'est la "
        "liste à porter dans une note. (4) Pour chaque point dur, passez au "
        "texte par texte pour voir l'article avant et après. (5) Basculez sur "
        "« Tout le texte, inchangés compris » pour vérifier qu'un article "
        "n'a pas été oublié. (6) Emportez la note Word et le classeur.\n\n"
        "**La note de synthèse Word** reprend ce que fait l'acte, les "
        "modifications de fond avec leur instruction verbatim, les notions "
        "transverses et le détail article par article, en tableaux "
        "modifiables. C'est le livrable, l'écran n'en est que la "
        "préparation.\n\n"
        "**Ce que le avant/après ne montre pas.** Une instruction qui vise un "
        "membre de phrase · « les mots “dans un délai raisonnable” sont "
        "supprimés », n'est pas reportée dans le texte reconstitué : la "
        "localiser sans risque de contresens n'est pas possible "
        "mécaniquement. Elle est alors marquée « non reportée dans le texte "
        "ci-dessous », et le libellé exact reste affiché. Les suppressions "
        "d'un point ou d'un paragraphe entier, elles, sont bien reportées et "
        "apparaissent barrées.\n\n"
        "À l'import, un acte modificatif est **découpé instruction par "
        "instruction** plutôt qu'article par article, et son exposé des "
        "motifs est séparé des considérants. L'outil prévient quand vous "
        "désignez un acte modificatif dans la comparaison ordinaire, et le "
        "suivi des amendements refuse un texte d'arrivée de cette nature "
        "plutôt que de rendre des verdicts faux.",
        ["omnibus", "acte modificatif", "modifie", "data act", "rgpd",
         "portant modification", "amendant", "plusieurs textes"],
        technique=r"""`core/modificatif.py`, entièrement déterministe, aucun appel de modèle.

**Découpage.** Le dispositif est isolé sur la formule « ONT ADOPTÉ LE PRÉSENT
RÈGLEMENT » (l'exposé des motifs cite les mêmes règlements et produirait des
modifications imaginaires), puis découpé sur les en-têtes d'articles de l'acte
modificatif. Le texte cible vient de l'intitulé (« Modifications du règlement
(UE) 2016/679 ») ou du chapeau (« Le règlement … est modifié comme suit »).

**Instructions.** Les items « 1. », « 2. » et les sous-points « (a) », « (b) »
sont lus **hors des guillemets uniquement** : on suit la profondeur des
`«` et `»`, parce que le texte cité contient lui aussi des paragraphes
numérotés, qui ressemblent trait pour trait à des instructions. L'article visé
est repéré par `article\s+(\d+)(\s+ordinal)?`, avec les ordinaux latins
jusqu'à `novovicies`, l'article 32 novovicies existe réellement. Un sous-point
qui ne nomme pas d'article hérite de celui de son instruction parente.

**Opération** : suppression, remplacement, insertion, ajout, abrogation,
modification, détectées sur `est|sont` + participe accordé, les quatre
accords compris.

**CELEX** : `règlement (UE) 2023/2854` → `32023R2854`, `directive 2002/58/CE` →
`32002L0058`, `règlement (UE) nº 910/2014` → `32014R0910`. C'est ce qui permet
de retrouver automatiquement le texte cible dans le corpus.

**Reconstitution** (`appliquer`). Trois niveaux de fiabilité, affichés :
*exacte*, toutes les instructions ont été reportées ; *approchée*, une partie
seulement ; *non appliquée*, aucune, et le texte affiché reste celui d'avant.
Sont reportables : l'article entier (remplacé, supprimé, inséré), un paragraphe
repéré par `^\s*(\d+)\.\s` et borné par le paragraphe suivant, et un point
repéré par `^\s*\(?[a-z]{1,2}(bis|ter|quater|quinquies)?\)`, à condition que
le repère soit **unique** dans l'article, faute de quoi l'instruction est
laissée de côté plutôt qu'appliquée au hasard. Chaque instruction porte un
booléen `appliquee`, affiché à l'écran en regard de son libellé : le lecteur
sait ce que le avant/après contient et ce qu'il ne contient pas. Une reconstitution approximative présentée
comme le droit en vigueur serait pire que pas de reconstitution du tout.

**Découpage à l'import** (`ingest._decouper_par_modification`). Chaque
instruction devient un segment dont l'identifiant porte le texte cible et
l'article visé, `mod_32016R0679_art_33_8`. Deux versions du même omnibus
s'apparient donc instruction par instruction. Les articles que l'omnibus
insère (« Article 32 bis ») ne sont pas indexés comme des articles de
l'omnibus : ce sont des textes cités, déjà portés par l'instruction qui les
insère. L'exposé des motifs, les considérants et les annexes forment trois
sections distinctes.

**Caractérisation** (`qualifier`) : sortie Pydantic `DeltaAnalysis`
(`summary_fr`, `impact`, `affected_concepts`). Le modèle reçoit l'instruction,
le texte nouveau cité et l'article dans sa version actuelle ; l'opération,
elle, est lue dans l'instruction, jamais devinée.

**Comparaison de deux versions de l'omnibus** (`comparer`) : les instructions
sont regroupées par (texte cible, article visé), puis comparées par
`difflib.SequenceMatcher` sur la concaténation instruction + texte nouveau.
Statuts : identique, modifiée, nouvelle, abandonnée. On ne compare pas les
deux textes mot à mot, l'article premier d'un omnibus fait trente mille
caractères et le lecteur s'y noierait."""),

    Fiche(
        "compromis_non_publies", "versions",
        "Puis-je comparer des textes qui ne sont pas publiés sur EUR-Lex ?",
        "Oui, et c'est l'usage principal. Un compromis de présidence, un "
        "document de travail, une version de travail interne : chargez le PDF "
        "ou le Word depuis l'onglet Importer, en type « Texte réglementaire », "
        "et il devient comparable à n'importe quel autre document du corpus.\n\n"
        "Les deux listes de sélection portent sur **tout le corpus**, sans "
        "restriction de dossier ni de type : le texte de départ et le texte "
        "d'arrivée d'un omnibus n'appartiennent pas toujours au même dossier, "
        "et un dossier n'est qu'un confort de tri.\n\n"
        "Le seul prérequis est que le document soit découpé par article, ce "
        "qui suppose que ses en-têtes « Article 5 » soient reconnaissables. "
        "Vérifiez le nombre de segments après import.",
        ["compromis", "non publié", "interne", "présidence", "document de "
         "travail", "comparer n'importe quoi"]),

    # --- amendements ------------------------------------------------------
    Fiche(
        "amendements", "amendements",
        "Comment l'outil détermine-t-il si un amendement a été retenu ?",
        "En confrontant chaque demande écrite au texte finalement publié, en "
        "deux temps.\n\n"
        "**Premier temps, déterministe.** Certaines réponses ne demandent "
        "aucun modèle : une délégation qui demandait la suppression d'un "
        "article qui a effectivement disparu a obtenu gain de cause ; celle "
        "qui la demandait sur un article toujours présent, non. Ces verdicts "
        "sont marqués « structure ».\n\n"
        "**Second temps, par le modèle.** Pour les demandes de fond, "
        "« clarifier le champ », « ajouter une condition de "
        "proportionnalité », le modèle lit la demande et le nouveau texte de "
        "l'article, et rend un verdict : reprise, reprise partiellement, "
        "écartée, indéterminé. **Il doit recopier le passage du nouveau texte "
        "qui fonde son verdict**, et ce passage est vérifié par le programme. "
        "Sans citation retrouvée, le verdict bascule en « indéterminé » plutôt "
        "que d'être affiché comme acquis.\n\n"
        "Le taux de reprise par État membre se calcule sur les seules demandes "
        "tranchées : une reprise partielle compte pour une demi-reprise, les "
        "indéterminées sont exclues du dénominateur.\n\n"
        "**Ce que l'outil ne dit pas** : pourquoi une demande a été écartée, "
        "ni si la rédaction retenue satisfait juridiquement la délégation.",
        ["amendement", "retenu", "repris", "écarté", "obtenu", "compromis "
         "final", "taux de reprise"],
        technique="""`core/amendements.py`, fonction `suivre()`. Deux étages :

1. **Étage structurel, sans modèle** : une demande marquée `deletion=1`
   (détectée à l'analyse par « requests the deletion », « should be deleted »,
   « supprimer ») est tranchée en comparant les identifiants de section
   présents dans le texte cible, article absent ⇒ `retenue`, présent ⇒
   `ecartee`. Verdict marqué `methode="structure"`, entièrement reproductible.
2. **Étage modèle**, pour les demandes de fond, avec sortie Pydantic
   (`verdict`, `justification`, `quote`) et la même vérification de citation
   que partout. Citation non retrouvée ⇒ `indetermine`.

Le taux de reprise pondère la reprise partielle à un demi et exclut les
indéterminés du dénominateur :

```
taux_i = (n_retenues + 0,5 · n_partielles) / (n_retenues + n_partielles + n_ecartees)
```

Si aucune demande d'un EM n'a pu être tranchée, le taux est `NaN` et affiché
comme tel, pas 0 %. Un taux inventé sur trois demandes indéterminées
raconterait l'inverse de la réalité."""),

    # --- recherche et régimes d'accès ------------------------------------
    Fiche(
        "passages", "recherche",
        "Comment les passages examinés sont-ils choisis, et comment être sûr de ne rien rater ?",
        "**La sélection se fait en trois temps.**\n\n"
        "1. Votre question est traduite en termes de recherche, en français "
        "**et en anglais**, les documents de négociation sont rédigés en "
        "anglais, et chercher « réserve d'examen » sans « scrutiny "
        "reservation » ne trouve rien.\n"
        "2. L'index plein texte classe tous les passages du périmètre par "
        "pertinence, selon l'algorithme BM25 : un passage remonte d'autant "
        "plus haut qu'il contient les termes cherchés, qu'ils y sont rares "
        "ailleurs dans le corpus, et que le passage est court. Si vous nommez "
        "un article, ses passages passent devant.\n"
        "3. Les N premiers, le plafond que vous fixez, sont examinés **un "
        "par un** par le modèle. Un modèle à qui l'on donne quinze passages "
        "d'un coup répond sur le premier et oublie les autres ; un appel par "
        "passage rend l'oubli impossible.\n\n"
        "**Le risque réel, et comment le traiter.** Ce ne sont pas les "
        "passages examinés qui posent problème, ce sont ceux qui ne l'ont pas "
        "été. Si l'index remonte autant de passages que le plafond, il en "
        "existe probablement d'autres. Le panneau de fiabilité vous le dit "
        "explicitement · « le plafond a été atteint », et c'est le signal "
        "qu'il faut relancer avec un plafond plus élevé.\n\n"
        "Trois réflexes pour une réponse exhaustive : montez le plafond (200 "
        "coûte dix minutes, pas dix heures) ; restreignez le périmètre "
        "documentaire pour concentrer la recherche ; et posez la question en "
        "citant l'article quand vous le connaissez.",
        ["passages", "30", "plafond", "exhaustif", "rater", "complet",
         "sélection", "bm25", "pertinence", "comment choisit"],
        technique="""`core/retrieval.py`. Index : SQLite **FTS5**, table autonome (pas de table
externe, pas de déclencheurs), reconstruite par `rebuild_index()`. Le
classement est la fonction `bm25()` intégrée à FTS5 :

```sql
SELECT segment_id, bm25(segments_fts, 4.0, 1.0) AS rank
FROM segments_fts WHERE segments_fts MATCH ? ORDER BY rank LIMIT ?
```

BM25, pour un passage *d* et une requête *Q* :

```
score(d,Q) = Σ_{t∈Q} IDF(t) · ( tf(t,d) · (k1+1) ) / ( tf(t,d) + k1·(1 − b + b·|d|/avgdl) )
IDF(t)     = ln( 1 + (N − n_t + 0,5) / (n_t + 0,5) )
```

avec `k1 = 1,2` et `b = 0,75` (valeurs fixées par FTS5), `|d|` la longueur du
passage, `avgdl` la longueur moyenne, `N` le nombre de passages et `n_t` le
nombre de passages contenant le terme. FTS5 renvoie un score **négatif**,
plus il est bas, plus le passage est pertinent, d'où le `ORDER BY rank` sans
`DESC`. Les arguments `4.0, 1.0` pondèrent les colonnes de l'index : un terme
trouvé dans l'intitulé de l'article pèse quatre fois un terme du corps.

**Construction de la requête** (`build_query()`) : la question est traduite en
termes français et anglais, les termes sont assemblés en `OR` avec des
préfixes (`scrutiny*`), et une mention d'article ajoute une clause sur la
colonne d'intitulé. Aucune vectorisation, aucun plongement : rien ne sort du
poste pour être indexé, ce qui est la propriété qui compte sur des documents
LIMITE.

**Puis un appel de modèle par passage**, jamais un lot : `qa.py` boucle sur
les `hits`, extrait les affirmations d'un passage à la fois, puis lance une
seconde passe inclusive sur les passages sans affirmation retenue."""),

    Fiche(
        "recherche_vs_llm", "recherche",
        "Quelle différence avec un assistant conversationnel classique ?",
        "Trois différences, et elles décident de l'usage qu'on peut en faire.\n\n"
        "**Il ne connaît que vos documents.** Aucune réponse ne vient d'une "
        "connaissance générale du droit européen : tout sort des fichiers "
        "chargés, y compris ceux qui ne sont pas publics.\n\n"
        "**Chaque affirmation est vérifiée par le programme**, pas par le "
        "modèle : la citation est recherchée littéralement dans le segment "
        "source, et l'affirmation est retirée si elle ne s'y trouve pas.\n\n"
        "**Il est exhaustif par construction** : chaque passage est examiné "
        "séparément, ce qui coûte du temps et supprime l'oubli.\n\n"
        "En contrepartie, il ne sait pas répondre à une question générale de "
        "droit, ne raisonne pas au-delà des textes chargés, et est plus lent.",
        ["différence", "chatgpt", "assistant", "llm", "pourquoi cet outil",
         "plus value"]),

    Fiche(
        "regimes", "regimes",
        "Comment fonctionne la page Régimes d'accès aux données ?",
        "Vous décrivez une situation d'entreprise, acteur, typologie de "
        "données, secteur, cas d'usage, transfert hors UE, et cette "
        "description est traduite en requête documentaire. L'outil cherche "
        "ensuite dans **les seuls documents que vous avez cochés** en haut de "
        "page, examine les passages un par un, et rapporte ce qu'ils disent "
        "avec citation vérifiée.\n\n"
        "**Un point qui prête à confusion** : l'encadré « Textes où regarder "
        "en priorité » est une liste de méthode, écrite d'avance pour chaque "
        "cas d'usage. **Ce n'est pas un résultat de recherche.** Un texte cité "
        "là mais absent de votre corpus ne sera pas lu, l'outil vous indique "
        "d'ailleurs lesquels sont effectivement chargés.\n\n"
        "La fiche d'orientation Word reprend la situation examinée, les "
        "dispositions citées avec leurs références, les points non tranchés "
        "et la liste des textes interrogés. Elle est modifiable : complétez-la "
        "avant de l'envoyer.",
        ["régime", "entreprise", "accès aux données", "fiche", "orientation",
         "rgpd", "data act"]),

    # --- livrables --------------------------------------------------------
    Fiche(
        "livrables", "general",
        "Que contiennent exactement les documents exportés ?",
        "**Le classeur Excel**, en neuf feuilles : mode de lecture et méthode ; "
        "position française de référence article par article, avec l'origine "
        "de cette référence ; synthèse thématique ; détail article par article "
        "à la forme du suivi tenu à la main (France en première colonne, "
        "couleur de compatibilité, référence de disposition dans chaque case) ; "
        "matrice numérique ; classement des États membres ; articles clivants ; "
        "couverture ; détail contribution par contribution. Les graphiques du "
        "classement, des articles clivants et de la couverture sont des "
        "graphiques Excel **liés aux cellules** : corriger une valeur met le "
        "graphique à jour.\n\n"
        "**La note Word** : de vrais tableaux, pas des captures, les "
        "figures, et le texte de détail article par article, avec la position "
        "française rappelée en tête de chaque article, puis ce que dit chaque "
        "État membre, la citation qui le fonde et sa page.\n\n"
        "**Les images PNG**, sélectionnables par article, pour insertion dans "
        "une note existante.\n\n"
        "Les livrables ne portent **pas** les alertes de fiabilité : une note "
        "de direction n'a pas à porter les doutes de l'outil. Ces alertes "
        "vivent dans le panneau dédié, à l'écran.",
        ["export", "excel", "word", "png", "livrable", "télécharger",
         "classeur", "note"]),

    Fiche(
        "fiabilite", "general",
        "Que contient le panneau « Fiabilité et points d'attention » ?",
        "La liste de ce qui, dans le résultat affiché, demande votre œil, et "
        "pour chaque point, quoi faire.\n\n"
        "Par exemple : les contributions dont la citation n'a pas été "
        "retrouvée ; celles classées sans le modèle ; celles de plus de 2 500 "
        "caractères, qui portent souvent plusieurs demandes contradictoires ; "
        "les articles documentés par moins de trois États membres ; les paires "
        "d'États dont le taux d'accord repose sur moins de trois articles "
        "communs ; les réserves d'examen, qui ne sont pas des positions de "
        "fond ; et, en recherche, le fait que le plafond de passages ait été "
        "atteint.\n\n"
        "Les seuils sont grossiers et affichés : ils servent à attirer "
        "l'attention, pas à produire un score de confiance qui ferait "
        "autorité.\n\n"
        "Ce panneau est **à l'écran uniquement**. Il ne part ni dans le Word "
        "ni dans l'Excel.",
        ["fiabilité", "alerte", "attention", "vigilance", "qualité",
         "points d'attention"],
        technique="""`core/fiabilite.py`. Les seuils sont des constantes de module, lisibles et
modifiables en un endroit :

```python
CONFIANCE_BASSE       = 0.45   # confidence renvoyée par le modèle
CONTRIBUTION_LONGUE   = 2500   # caractères
ARTICLES_COMMUNS_MINI = 3      # pour qu'un taux d'accord veuille dire quelque chose
EM_MINI_PAR_ARTICLE   = 3      # en deçà, l'article est mal documenté
```

Chaque contrôle est une expression `pandas` sur la table des contributions ou
sur la matrice, `(df["confidence"] < CONFIANCE_BASSE).sum()`,
`matrix.notna().sum(axis=1) < EM_MINI_PAR_ARTICLE`, etc., et produit une
`Alerte(niveau, titre, detail, quoi_faire)`. Aucun score global n'est
calculé : agréger ces contrôles en un « indice de confiance » donnerait un
chiffre qui aurait l'air d'une mesure sans en être une."""),

    Fiche(
        "architecture", "general",
        "Sur quoi l'application est-elle construite ?",
        "Python, une base SQLite locale, et rien qui tourne ailleurs que sur "
        "le poste, hormis les appels au modèle.\n\n"
        "L'interface est **Streamlit** ; le stockage et l'index de recherche "
        "sont **SQLite** avec son extension plein texte FTS5 ; tous les "
        "calculs passent par **pandas** et **networkx** ; les documents sont "
        "lus par **pdfplumber** et **python-docx**, produits par "
        "**python-docx** et **openpyxl** ; les comparaisons de versions par "
        "**difflib**, de la bibliothèque standard.\n\n"
        "Les sorties du modèle sont contraintes par des schémas **Pydantic** "
        "et appelées via le client **OpenAI**, l'API Albert suit les mêmes "
        "conventions, le même client sert donc pour Albert, pour un endpoint "
        "interne, ou pour un modèle exécuté en local.\n\n"
        "Aucune bibliothèque de vectorisation, aucun service externe, aucune "
        "télémétrie : la seule connexion sortante est celle du fournisseur de "
        "modèle configuré.",
        ["architecture", "technique", "bibliothèques", "python", "stack",
         "code", "librairies", "dépendances", "comment c'est fait",
         "streamlit", "sqlite", "pandas", "networkx"],
        technique="""Dépendances directes, et ce que chacune fait :

| Bibliothèque | Rôle | Où |
|---|---|---|
| `streamlit` | interface, navigation multipage (`st.navigation`), état de session | `app.py`, `pages/` |
| `sqlite3` (standard) | stockage, index FTS5, journal d'audit | `core/store.py`, `core/retrieval.py` |
| `pandas` | matrices, agrégats, classements, tous les calculs | partout |
| `networkx` | graphe d'accord, composantes connexes, degrés | `core/coalition.py` |
| `difflib` (standard) | comparaison mot à mot, `SequenceMatcher` | `core/versions.py` |
| `pdfplumber` | extraction du texte et des tableaux des PDF | `core/ingest.py` |
| `python-docx` | lecture des .docx, production des notes Word | `core/ingest.py`, `core/docx.py` |
| `openpyxl` | classeur Excel, mises en forme conditionnelles, graphiques natifs | `core/excel.py` |
| `pydantic` | schémas contraignant chaque sortie de modèle | `core/llm.py` et appelants |
| `openai` | client HTTP vers Albert ou tout endpoint compatible | `core/llm.py` |
| `plotly` | figures interactives à l'écran | `pages/` |
| `matplotlib` | figures PNG exportables | `core/figures.py` |
| `requests` | récupération EUR-Lex, uniquement sur demande explicite | `core/eurlex.py` |

Le découpage en modules suit la même règle que le reste : `core/` ne contient
aucun appel Streamlit, ce qui rend chaque calcul testable sans interface,
c'est ce que fait la suite `pytest` du dossier `tests/`."""),
]

FICHES_PAR_CLE = {f.cle: f for f in FICHES}


def fiches_du_module(module: str) -> list[Fiche]:
    """Fiches à afficher dans le « Comment ça marche ? » d'un module."""
    return [f for f in FICHES if f.module == module]


# ---------------------------------------------------------------------------
# Recherche dans les fiches — lexicale, locale, sans réseau
# ---------------------------------------------------------------------------

_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "que",
          "qui", "quoi", "est", "sont", "ce", "cette", "ces", "comment",
          "pourquoi", "quel", "quelle", "dans", "pour", "sur", "avec", "je",
          "il", "elle", "on", "en", "au", "aux", "a", "à", "se", "sa", "son",
          "mes", "mon", "ma", "vous", "nous", "faire", "fait", "peux", "peut",
          "puis", "veux", "veut", "ça", "cela", "y", "par", "plus", "pas"}


def _tronquer(mot: str) -> str:
    """Pluriel rabattu sur le singulier, grossièrement mais des deux côtés.

    Sans cela, « comment tu calcules les coalitions ? » ne rencontrait pas le
    mot-clé « coalition » et l'assistant répondait à côté. La troncature est
    volontairement bête : elle s'applique identiquement à la question et aux
    fiches, donc une déformation ne fait perdre aucune correspondance.
    """
    return mot[:-1] if len(mot) > 3 and mot[-1] in "sx" else mot


def _normaliser(texte: str) -> list[str]:
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFKD", (texte or "").lower())
        if not unicodedata.combining(c))
    mots = re.findall(r"[a-z0-9]+", sans_accent)
    return [_tronquer(m) for m in mots if len(m) > 2 and m not in _VIDES]


# Une question qui contient l'un de ces mots ne demande pas une explication
# d'usage mais le détail du calcul : formule, seuil, bibliothèque. On lui
# répond alors avec les blocs techniques des fiches, et sans plafond de
# longueur — c'est exactement le cas d'usage « ma chef veut savoir comment
# les coalitions sont calculées ».
_MOTS_TECHNIQUES = {_tronquer(m) for m in {
    "formule", "formules", "algorithme", "algorithmes", "calcul", "calcule",
    "calcules", "calculs", "calculee", "calculees", "bibliotheque",
    "bibliotheques", "librairie", "librairies", "python", "code", "fonction",
    "mathematique", "mathematiques", "equation", "seuil", "seuils",
    "parametre", "parametres", "implementation", "implemente", "technique",
    "techniquement", "precisement", "detail", "details", "exactement",
    "pandas", "networkx", "difflib", "sqlite", "bm25", "sequencematcher",
    "moyenne", "ponderee", "coefficient", "arithmetique",
}}


def question_technique(question: str) -> bool:
    """La question porte-t-elle sur le calcul lui-même ?"""
    return bool(set(_normaliser(question)) & _MOTS_TECHNIQUES)


def chercher(question: str, limite: int = 3) -> list[tuple[Fiche, float]]:
    """Fiches les plus proches d'une question, par recouvrement de mots."""
    mots = set(_normaliser(question))
    if not mots:
        return []
    technique = question_technique(question)

    scores: list[tuple[Fiche, float]] = []
    for fiche in FICHES:
        mots_cles = set()
        for mc in fiche.mots_cles:
            mots_cles |= set(_normaliser(mc))
        mots_question = set(_normaliser(fiche.question))
        mots_reponse = set(_normaliser(fiche.reponse))
        mots_technique = set(_normaliser(fiche.technique))

        # Un mot-clé pèse plus qu'un mot du corps : il a été choisi pour ça.
        score = (3.0 * len(mots & mots_cles)
                 + 2.0 * len(mots & mots_question)
                 + 0.5 * len(mots & mots_reponse)
                 + 0.5 * len(mots & mots_technique))
        # Sur une question de calcul, une fiche qui porte le détail technique
        # passe devant une fiche qui n'a que l'explication d'usage. Le bonus
        # est multiplicatif et modeste : il départage, il ne renverse pas.
        if score > 0:
            if technique and fiche.technique:
                score *= 1.3
            scores.append((fiche, score))

    scores.sort(key=lambda x: -x[1])
    return scores[:limite]


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

SYSTEM = """Tu es l'assistant d'aide d'une application interne d'administration.
Tu réponds UNIQUEMENT à partir des fiches de documentation qui te sont fournies.

Règles impératives :
1. Tu n'utilises AUCUNE connaissance extérieure aux fiches. Tu ne sais rien du
   droit européen, rien des documents chargés par l'utilisateur, rien de ce que
   l'application n'a pas documenté.
2. Si les fiches ne répondent pas à la question, tu le dis franchement et tu
   indiques la page de l'application où l'utilisateur trouvera l'information.
   C'est une réponse acceptable et attendue.
3. Tu réponds en français, brièvement, cinq phrases au maximum, et tu vas au
   fait. L'utilisateur peut lire la fiche complète juste en dessous.
4. Tu n'inventes aucun chiffre, aucun seuil, aucun nom de bouton qui ne
   figurerait pas dans les fiches.
5. Tu ne donnes ni conseil juridique, ni avis sur une négociation."""

# Deuxième régime : la question porte sur le calcul. Là, une réponse de cinq
# phrases est une mauvaise réponse — la personne veut la formule, le nom de la
# fonction et celui de la bibliothèque. Les fiches fournies contiennent alors
# leur bloc « Sous le capot », et la consigne change en conséquence.
SYSTEM_TECHNIQUE = """Tu es l'assistant d'aide d'une application interne
d'administration. Tu réponds UNIQUEMENT à partir des fiches de documentation
qui te sont fournies. La question posée porte sur le fonctionnement interne :
un calcul, une formule, un seuil, une bibliothèque.

Règles impératives :
1. Tu n'utilises AUCUNE connaissance extérieure aux fiches. Tu ne complètes
   jamais par ce que tu crois savoir d'une bibliothèque Python ou d'un
   algorithme : si la fiche ne donne pas la formule, tu dis qu'elle n'y est
   pas plutôt que de l'écrire de mémoire.
2. Tu réponds de façon DÉTAILLÉE et technique. Tu reprends les formules, les
   noms de fonctions, les noms de bibliothèques et les seuils chiffrés tels
   qu'ils figurent dans les fiches, en les recopiant exactement. Tu peux
   utiliser des blocs de code et des formules en Markdown.
3. Tu structures la réponse : ce que le programme calcule, comment, avec quoi,
   et ce que ce choix implique. Vingt lignes sont acceptables si la question
   les demande.
4. Tu n'inventes aucun chiffre, aucun seuil, aucun nom de fonction, aucune
   bibliothèque qui ne figurerait pas dans les fiches.
5. Si les fiches ne couvrent pas la question, tu le dis franchement et tu
   indiques où chercher dans l'application.
6. Tu ne donnes ni conseil juridique, ni avis sur une négociation."""


class ReponseAide(BaseModel):
    reponse: str = Field(max_length=4000, description="Réponse en français")
    couverte: bool = Field(
        True, description="Les fiches permettent-elles de répondre ?")


@dataclass
class ResultatAide:
    question: str
    reponse: str = ""
    fiches: list[Fiche] = field(default_factory=list)
    redigee: bool = False        # rédigée par le modèle, ou fiches brutes
    couverte: bool = True
    technique: bool = False      # question de calcul → réponse détaillée


def repondre(question: str, limite: int = 3) -> ResultatAide:
    """Répond à une question de fonctionnement, sans jamais sortir des fiches.

    Deux régimes : une question d'usage appelle une réponse courte ; une
    question de calcul appelle le détail — formules, seuils, bibliothèques —
    et reçoit les blocs techniques des fiches.

    Sans modèle disponible, la réponse est la fiche la plus proche, affichée
    telle quelle : c'est moins agréable, ce n'est pas moins exact.
    """
    technique = question_technique(question)
    # Une question de calcul mérite un peu plus de matière : la formule est
    # souvent dans une fiche et son application dans une autre.
    if technique:
        limite = max(limite, 4)
    trouvees = chercher(question, limite=limite)
    res = ResultatAide(question=question, fiches=[f for f, _ in trouvees],
                       technique=technique)

    if not trouvees:
        res.couverte = False
        res.reponse = (
            "Je ne trouve pas de fiche sur ce point. L'assistant ne connaît "
            "que le fonctionnement de l'application, pas le droit européen, "
            "pas le contenu des documents chargés. Pour une question sur vos "
            "documents, utilisez l'outil **Recherche**, qui cite ses sources.")
        return res

    def _repli() -> str:
        fiche = trouvees[0][0]
        return fiche.texte_complet() if technique else fiche.reponse

    client = get_client()
    if not client.available:
        res.reponse = _repli()
        return res

    contexte = "\n\n".join(
        f"[Fiche « {f.question} »]\n"
        f"{f.texte_complet() if technique else f.reponse}"
        for f, _ in trouvees)
    try:
        sortie = client.structured(
            ReponseAide,
            SYSTEM_TECHNIQUE if technique else SYSTEM,
            f"Question de l'utilisateur : {question.strip()}\n\n"
            f"Fiches disponibles :\n{contexte}",
            max_tokens=2200 if technique else 900)
        res.reponse = sortie.reponse.strip()
        res.couverte = sortie.couverte
        res.redigee = True
    except (LLMUnavailable, LLMInvalidOutput):
        res.reponse = _repli()
    return res


def guide_complet(technique: bool = False) -> str:
    """Toutes les fiches, en Markdown — le guide d'utilisation exhaustif.

    `technique=True` ajoute les blocs « Sous le capot » : c'est la version à
    lire quand on veut vérifier un calcul plutôt que se servir de l'outil.
    """
    modules = {
        "general": "Général",
        "bibliotheque": "Bibliothèque",
        "recherche": "Recherche",
        "positions": "Positions des États membres",
        "coalitions": "Coalitions",
        "versions": "Comparaison de versions",
        "amendements": "Suivi des amendements",
        "regimes": "Régimes d'accès aux données",
    }
    morceaux = []
    for cle, titre in modules.items():
        fiches = fiches_du_module(cle)
        if not fiches:
            continue
        morceaux.append(f"## {titre}\n")
        for f in fiches:
            corps = f.texte_complet() if technique else f.reponse
            morceaux.append(f"### {f.question}\n\n{corps}\n")
    return "\n".join(morceaux)
