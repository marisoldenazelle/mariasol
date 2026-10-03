"""
Mode d'emploi — ce que fait l'outil, dans quel ordre s'en servir, ce qu'il
garantit et ce qu'il ne garantit pas.

Cette page est une page comme les autres : elle ne fait rien, elle explique.
Elle est écrite pour être lue par quelqu'un qui ouvre l'application pour la
première fois, sans formation préalable et sans avoir lu le README.
"""

from __future__ import annotations

import streamlit as st

from core.config import APP_NOM_LONG, VERSION_DATE, __version__
from core.aide import guide_complet, repondre
from core.ui import entete_module, nom_marque


entete_module(
    f"Comment se servir de {nom_marque()} ?",
    f"*{APP_NOM_LONG}* · version {__version__}, {VERSION_DATE}. Posez votre "
    "question dans le premier onglet, ou lisez le guide complet dans le "
    "dernier.")

t0, t1, t2, t3, t4 = st.tabs(
    ["Poser une question", "Par où commencer", "Les outils, un par un",
     "Ce que l'outil garantit", "Guide complet"])

# --------------------------------------------------------------------------
with t0:
    st.markdown(
        f"### Demandez à {nom_marque()} comment elle fonctionne\n\n"
        "« Comment les scores sont-ils calculés ? », « puis-je comparer un "
        "compromis qui n'est pas publié ? », « qu'est-ce qui est sauvegardé "
        "quand je ferme ? »", unsafe_allow_html=True)
    st.caption(
        "L'assistant répond **uniquement sur le fonctionnement de "
        "l'application**, à partir de fiches écrites à la main. Il ne connaît "
        "ni le droit européen, ni vos documents : pour cela, c'est l'outil "
        "**Recherche**, qui cite ses sources. Cette séparation est "
        "délibérée, un assistant qui mélange les deux produit des réponses "
        "dont on ne sait plus laquelle on lit.")

    exemples = [
        "Quelle formule calcule les coalitions ?",
        "Comment les scores d'alignement sont-ils calculés ?",
        "Que veut dire « le silence vaut acceptation » ?",
        "Est-ce sauvegardé si je ferme l'application ?",
        "Quelles bibliothèques Python sont utilisées ?",
    ]
    colonnes = st.columns(len(exemples))
    for col, exemple in zip(colonnes, exemples):
        if col.button(exemple[:28] + "…", key=f"ex_{exemple[:12]}",
                      width="stretch"):
            st.session_state["question_aide"] = exemple

    question = st.text_input(
        "Votre question", value=st.session_state.get("question_aide", ""),
        placeholder="Comment l'outil décide-t-il qu'un État membre est opposé ?")

    if question.strip():
        reponse = repondre(question)
        if not reponse.couverte:
            st.warning(reponse.reponse)
        else:
            st.markdown(reponse.reponse)
            if reponse.redigee:
                st.caption(
                    "Réponse rédigée à partir des fiches ci-dessous, et de "
                    "rien d'autre.")
        if reponse.technique:
            st.caption(
                "Question de calcul : la réponse et les fiches ci-dessous "
                "incluent le détail d'implémentation, formules, seuils, "
                "bibliothèques employées.")
        for fiche in reponse.fiches:
            with st.expander(f"Fiche complète · {fiche.question}"):
                st.markdown(fiche.texte_complet() if reponse.technique
                            else fiche.reponse)
                if fiche.technique and not reponse.technique:
                    with st.popover("Le détail du calcul"):
                        st.markdown(fiche.technique)

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
with t1:
    st.markdown("""
### En trois étapes

**1. Charger vos documents.** Page **Bibliothèque**. Tous les outils
travaillent sur ces documents et sur rien d'autre : l'application ne connaît
pas le droit européen, elle connaît vos fichiers. Trois familles de documents
sont reconnues, commentaires consolidés du Conseil (les « WK »), textes
réglementaires, textes libres (non-papers, comptes rendus). Le type est
détecté automatiquement, **et il se corrige** : c'est lui qui décide des pages
où le document apparaît.

**2. Analyser.** Page **Positions des États membres**, encadré « Lancer
l'analyse ». Commencez par un dixième des contributions pour juger la qualité
du classement, puis lancez tout. Comptez trois secondes par contribution ;
l'estimation de durée est affichée avant le lancement, et ce qui est traité
est enregistré au fur et à mesure, une interruption ne fait rien perdre.

**3. Restituer.** Onglet **Export** de la même page : note Word avec le texte
de détail, classeur Excel avec des graphiques liés aux cellules, images PNG
article par article.

### L'ordre qui fait gagner du temps

| Vous voulez… | Allez à |
|---|---|
| Savoir qui pense quoi sur un article | **Positions des États membres** |
| Établir la liste des États à appeler | **Coalitions → Qui aller chercher** |
| Savoir si votre coalition suffit | **Coalitions → Arithmétique du Conseil** |
| Suivre un texte de version en version | **Comparaison de versions → Fil du texte** |
| Retrouver qui a dit quoi, où | **Recherche** |
| Répondre à une entreprise | **Régimes d'accès aux données** |
""")

# --------------------------------------------------------------------------
with t2:
    st.markdown("""
### Bibliothèque
Import des documents, récupération directe des textes publics depuis EUR-Lex,
correction du type et du repère de version. **Le repère de version**, nature
du document dans la procédure et date, est détecté à l'import et modifiable :
c'est lui qui ordonne les versions dans le fil du texte.

### Recherche
Une question en français, une réponse dont chaque affirmation cite un passage
retrouvé littéralement dans vos documents. Deux modes : *réponse sourcée*, qui
examine chaque passage séparément et appelle le modèle ; *extraits bruts*, qui
n'appelle rien et se contente de l'index plein texte.

Réglez le nombre de passages examinés selon l'enjeu : vingt pour une question
précise, cent ou deux cents pour une question du type « qui a posé une réserve
d'examen ? », où l'exhaustivité compte plus que la vitesse.

### Positions des États membres
Le cœur de l'outil. Chaque contribution écrite est classée : alignée,
partiellement alignée, divergente. **Deux référentiels au choix**, et ils ne
répondent pas à la même question :

- *par rapport à la position française*, qui est avec nous ;
- *par rapport au texte initial*, qui veut le changer, France comprise.

Sur un article que la France n'a pas amendé, les deux coïncident : ne pas
amender vaut acceptation. Sur un article où elle demande une réécriture, ils
divergent, et c'est là que la bascule est utile.

### Coalitions
Quatre onglets : qui aller chercher, quels blocs se forment sans nous, le
détail paire par paire, et l'arithmétique du Conseil, c'est-à-dire si le
groupe envisagé atteint la majorité qualifiée ou constitue une minorité de
blocage. Les chiffres de population ne servent qu'à cette dernière question.

### Comparaison de versions
Le fil complet d'un texte, l'évolution d'un article à travers toutes les
versions chargées, les changements majeurs triés, et le détail mot à mot.
L'appariement et le calcul des écarts sont déterministes ; le modèle
n'intervient que pour qualifier la portée d'un écart déjà constaté.

**Un omnibus ne se lit pas là.** Un acte modificatif ne récrit pas le Data
Act : il dit ce qu'il faut y changer. L'onglet **Omnibus et actes
modificatifs** lit ces instructions et se lit en trois vues.

*Vue d'ensemble* : la carte de l'acte, une ligne par texte modifié et une case
par article touché, colorée par portée ; la charge par texte ; la liste des
points durs, ceux qui touchent une obligation, un seuil, un délai ; les
notions qui reviennent d'un texte à l'autre, la lecture propre à un omnibus ;
un tableau filtrable de toutes les modifications. On y produit la **note de
synthèse Word**, qui est le livrable.

*Texte par texte* : la lecture de travail, article par article, avec
l'instruction verbatim, sa page, et le texte avant et après quand le texte
consolidé est chargé.

*Comparer deux versions* : ce qu'un compromis de présidence change à la
proposition de la Commission, instruction par instruction.

### Régimes d'accès aux données
Une situation d'entreprise décrite par un formulaire, et ce que les textes
chargés en disent, disposition par disposition. Produit une fiche
d'orientation Word modifiable.

### Administration
Clé API, modèle, état de la base, reconstruction de l'index, journal d'audit.
""")

# --------------------------------------------------------------------------
with t3:
    st.markdown("""
### Ce qui est garanti

**Aucune affirmation sans citation vérifiée.** Toute phrase produite par le
modèle est accompagnée d'une citation, et cette citation est recherchée
*littéralement* dans le document source par le programme, pas par le modèle.
Si elle ne s'y trouve pas, l'affirmation n'est pas signalée : elle est
**retirée**. C'est le garde-fou principal, et il est testé automatiquement à
chaque version.

**Aucune donnée hors du poste, sauf vers Albert.** Les documents restent dans
`data/` sur votre machine. Seuls les extraits nécessaires à une analyse
partent vers l'API Albert de la DINUM, hébergée en SecNumCloud. Aucun autre
service n'est appelé.

**Les calculs sont faits par le programme.** Matrice, taux d'accord, blocs,
majorité qualifiée, écarts entre versions : tout cela est arithmétique, pas
génératif. Le modèle ne calcule rien et ne décide rien.

**Tout est refaisable à la main.** Les méthodes ont été choisies pour rester
vérifiables : un agent doit pouvoir refaire un calcul sur un cas et contester
le résultat.

### Ce qui n'est pas garanti

**La justesse juridique du classement.** Le modèle qualifie une convergence, il
ne dit pas le droit. Un classement se conteste : ouvrez la contribution, lisez
la citation, corrigez.

**L'exhaustivité de l'extraction.** Le découpage d'un PDF mal structuré peut
perdre des contributions. Vérifiez les compteurs à l'import.

**Le résultat de la négociation.** Les positions écrites d'un groupe de
travail ne sont pas des votes. L'arithmétique du Conseil dit ce que donnerait
une répartition si elle se transposait en vote, ce qui n'arrive jamais tel
quel.
""")

# --------------------------------------------------------------------------
with t4:
    st.caption(
        "Toutes les fiches de l'application, dans l'ordre des modules. C'est "
        "le même contenu que les fenêtres « Comment ça marche ? » de chaque "
        "page, écrit à un seul endroit, pour qu'une explication ne puisse "
        "pas contredire une autre.")
    detail = st.toggle(
        "Afficher le détail d'implémentation",
        help="Ajoute à chaque fiche la formule exacte, les seuils chiffrés et "
             "les bibliothèques Python employées. C'est la version à lire "
             "pour vérifier un calcul ou le refaire à la main.")
    st.markdown(guide_complet(technique=detail))

with st.expander("Questions fréquentes sur l'installation et le poste"):
    st.markdown("""
### Plusieurs personnes peuvent-elles travailler dessus en même temps ?
Pas sur la même installation. Chaque personne lance l'application sur son
poste, avec sa base et ses documents : ce qui est chargé chez vous n'est pas
visible chez votre collègue. Un usage vraiment collectif suppose un
déploiement serveur, c'est un des points à arbitrer avant mise en service.

### Les documents restent-ils chargés quand je ferme l'application ?
Oui. Documents, découpage, analyses, positions françaises : tout est
enregistré dans `data/regwatch.sqlite3`, sur votre poste. Fermer la fenêtre ou
éteindre l'ordinateur ne perd rien. Seul l'état d'affichage, filtres, onglet
ouvert, repart à zéro.

Une réserve : ne placez pas `data/` dans un dossier synchronisé
(OneDrive, SharePoint). La synchronisation d'un fichier de base de données en
cours d'écriture le corrompt.

### Pourquoi l'analyse est-elle si longue ?
Parce que chaque contribution fait l'objet d'un appel distinct au modèle.
C'est un choix : un modèle à qui l'on donne quinze contributions d'un coup
répond sur la première et oublie les autres. Un appel par contribution rend
l'oubli impossible, au prix du temps.

### L'outil s'est trompé sur un classement. Que faire ?
Ouvrez la contribution dans l'onglet **Détail** : le résumé, la citation
retenue et le texte intégral y figurent. Si la citation ne soutient pas le
classement, c'est une erreur du modèle, signalez-la, elle sert à régler les
consignes. Vous pouvez aussi corriger la position française de référence, qui
change tout le classement de l'article.

### Puis-je charger des documents marqués LIMITE ?
Sur votre poste, oui : ils ne quittent pas la machine, sauf vers Albert, qui
est hébergé en SecNumCloud. **Sur une instance de démonstration partagée,
non** : la bannière d'avertissement le rappelle en permanence.
""")
