"""
Mesures de fiabilité — ce qui, dans un résultat, demande l'œil de l'agent.

Un outil qui présente tous ses résultats avec la même assurance est un outil
dangereux. Certaines cases de la matrice reposent sur une contribution longue
et ambiguë, d'autres sur une phrase sans équivoque ; certains taux d'accord se
calculent sur deux articles communs, d'autres sur trente. Rien ne distingue
les deux à l'écran, et c'est ce que ce module corrige.

Deux principes de conception :

- **Les alertes vivent dans une fenêtre à part, jamais dans le livrable.** Une
  note de direction n'a pas à porter les doutes de l'outil ; l'analyste, si.
  C'est pourquoi ces indicateurs s'affichent dans un panneau dédié et ne
  partent ni dans le Word ni dans l'Excel.
- **Chaque alerte dit quoi faire.** « 14 contributions classées par
  heuristique » n'aide personne ; « 14 contributions classées sans le modèle,
  relisez-les en priorité — filtre Méthode = heuristique dans l'onglet
  Détail » se traite.

Les seuils sont volontairement grossiers et explicites : ils servent à
attirer l'attention, pas à produire un score de confiance qui ferait autorité.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Seuils. Ils se règlent ici, en un seul endroit, et sont affichés à l'écran.
CONFIANCE_BASSE = 0.45        # en dessous, le classement est fragile
CONTRIBUTION_LONGUE = 2500    # caractères : au-delà, un résumé peut écraser
ARTICLES_COMMUNS_MINI = 3     # sous ce seuil, un taux d'accord ne veut rien dire
EM_MINI_PAR_ARTICLE = 3       # un article vu par deux États n'est pas cartographié

NIVEAUX = {"bloquant": 0, "attention": 1, "information": 2}


@dataclass
class Alerte:
    niveau: str          # bloquant | attention | information
    titre: str
    detail: str
    quoi_faire: str = ""

    @property
    def icone(self) -> str:
        return {"bloquant": "🔴", "attention": "🟠"}.get(self.niveau, "🔵")


def _trier(alertes: list[Alerte]) -> list[Alerte]:
    return sorted(alertes, key=lambda a: NIVEAUX.get(a.niveau, 3))


# ---------------------------------------------------------------------------
# Positions des États membres
# ---------------------------------------------------------------------------

def positions(df: pd.DataFrame, matrix: pd.DataFrame) -> list[Alerte]:
    """Ce qui, dans une cartographie de positions, mérite une relecture."""
    alertes: list[Alerte] = []
    if df is None or df.empty:
        return alertes

    # Les contributions françaises ne sont pas classées : elles *sont* le
    # référentiel auquel les autres sont comparées. Les compter parmi les
    # « non analysées » affichait « 70 contributions non analysées sur 725 »
    # sur une analyse pourtant complète — l'alerte la plus inquiétante de
    # l'écran désignait le fonctionnement normal de l'outil.
    classables = df[df["ms_code"] != "FR"] if "ms_code" in df.columns else df
    n_reference = len(df) - len(classables)

    analysees = (classables[classables["stance"].notna()]
                 if "stance" in classables.columns else classables.iloc[0:0])
    if analysees.empty:
        return [Alerte("bloquant", "Aucune contribution analysée",
                       "La matrice ne peut rien montrer.",
                       "Lancez l'analyse depuis l'encadré « Lancer l'analyse ».")]

    # --- couverture -------------------------------------------------------
    part = len(analysees) / max(len(classables), 1)
    if part < 0.95:
        alertes.append(Alerte(
            "attention" if part > 0.5 else "bloquant",
            f"{len(classables) - len(analysees)} contribution(s) non "
            f"analysée(s) sur {len(classables)}",
            f"Seules {part:.0%} des contributions à classer ont été traitées : "
            "la matrice est partielle, et les moyennes portent sur un "
            "échantillon."
            + (f" Les {n_reference} contribution(s) françaises ne sont pas "
               "comptées ici : elles servent de référence et ne sont jamais "
               "classées." if n_reference else ""),
            "Relancez l'analyse avec « Toutes les contributions » pour une "
            "cartographie complète."))

    # --- citations non retrouvées ----------------------------------------
    if "confidence" in analysees.columns:
        fragiles = analysees[analysees["confidence"].fillna(0) <= 0.0]
        if len(fragiles):
            alertes.append(Alerte(
                "attention",
                f"{len(fragiles)} classement(s) dont la citation n'a pas été "
                "retrouvée",
                "Le modèle a produit une justification introuvable dans le "
                "texte source ; la confiance a été ramenée à zéro et le "
                "classement conservé, mais il n'est pas adossé à une preuve.",
                "Filtrez sur ces contributions dans l'onglet Détail et "
                "vérifiez-les à la main avant tout usage en négociation."))

        basses = analysees[
            (analysees["confidence"].fillna(1) > 0)
            & (analysees["confidence"].fillna(1) < CONFIANCE_BASSE)]
        if len(basses):
            alertes.append(Alerte(
                "information",
                f"{len(basses)} classement(s) à confiance faible "
                f"(< {CONFIANCE_BASSE:.2f})",
                "Contributions ambiguës, ou traitées par classement lexical "
                "faute de modèle disponible.",
                "Onglet Détail, filtre « Méthode » : commencez par celles-là."))

    # --- méthode ----------------------------------------------------------
    if "method" in analysees.columns:
        # `scoring` enregistre « heuristique (silence) » ou « heuristique
        # (explicite) », jamais « heuristique » tout court : l'égalité stricte
        # ne trouvait donc rien, et l'alerte la plus utile de l'outil — vous
        # travaillez sans modèle — ne s'affichait jamais.
        heuristiques = analysees[
            analysees["method"].fillna("").str.startswith("heuristique")]
        if len(heuristiques):
            alertes.append(Alerte(
                "attention" if len(heuristiques) > 0.2 * len(analysees)
                else "information",
                f"{len(heuristiques)} contribution(s) classée(s) sans le modèle",
                "Le classement lexical repère les formules types (« we do not "
                "support », « should be deleted ») mais rate une opposition "
                "exprimée sans marqueur.",
                "Relancez l'analyse avec le modèle activé sur ces "
                "contributions."))

    # --- contributions longues -------------------------------------------
    if "text" in analysees.columns:
        longues = analysees[analysees["text"].fillna("").str.len()
                            > CONTRIBUTION_LONGUE]
        if len(longues):
            alertes.append(Alerte(
                "attention",
                f"{len(longues)} contribution(s) de plus de "
                f"{CONTRIBUTION_LONGUE} caractères",
                "Une contribution longue porte souvent plusieurs demandes de "
                "sens contraire ; la réduire à une seule position perd de "
                "l'information.",
                "Ouvrez-les dans l'onglet Détail : le texte intégral y est, et "
                "vous pouvez corriger la position française de référence si "
                "l'article le justifie."))

    # --- articles trop peu couverts ---------------------------------------
    if matrix is not None and not matrix.empty:
        exprimes = matrix.notna().sum(axis=1)
        maigres = exprimes[exprimes < EM_MINI_PAR_ARTICLE]
        if len(maigres):
            alertes.append(Alerte(
                "information",
                f"{len(maigres)} article(s) documenté(s) par moins de "
                f"{EM_MINI_PAR_ARTICLE} États membres",
                "Sur ces articles, le « consensus » affiché repose sur une ou "
                "deux prises de position : " +
                ", ".join(str(i) for i in list(maigres.index)[:6]) +
                ("…" if len(maigres) > 6 else ""),
                "Ne tirez pas de conclusion de coalition sur ces articles."))

        # États membres presque muets
        colonnes = matrix.notna().sum(axis=0)
        rares = colonnes[colonnes <= 1]
        if len(rares):
            alertes.append(Alerte(
                "information",
                f"{len(rares)} État(s) membre(s) présent(s) sur un seul article",
                "Leur position moyenne est calculée sur une contribution : " +
                ", ".join(str(c) for c in list(rares.index)[:10]),
                "Traitez leur score comme indicatif, pas comme une tendance."))

    # --- réserves d'examen -------------------------------------------------
    if "scrutiny" in analysees.columns:
        reserves = analysees[analysees["scrutiny"].fillna(0).astype(bool)]
        if len(reserves):
            etats = sorted({str(m) for m in reserves["ms_code"]})
            alertes.append(Alerte(
                "information",
                f"{len(reserves)} réserve(s) d'examen relevée(s)",
                "Une réserve d'examen n'est pas une position de fond : elle "
                "suspend l'accord sans dire dans quel sens. États concernés : "
                + ", ".join(etats[:12]),
                "Ces positions peuvent basculer ; ne les comptez pas comme "
                "acquises dans une coalition."))

    return _trier(alertes)


def desaccord_referentiels(matrice_fr: pd.DataFrame,
                           matrice_texte: pd.DataFrame) -> list[Alerte]:
    """Là où « écart à la France » et « écart au texte » divergent.

    Ces cases sont les plus intéressantes du dossier : elles marquent les
    articles où la France demande elle-même une modification. Elles sont aussi
    celles où une lecture pressée se trompe le plus.
    """
    if (matrice_fr is None or matrice_fr.empty
            or matrice_texte is None or matrice_texte.empty):
        return []
    communs = matrice_fr.index.intersection(matrice_texte.index)
    colonnes = matrice_fr.columns.intersection(matrice_texte.columns)
    if not len(communs) or not len(colonnes):
        return []

    a = matrice_fr.loc[communs, colonnes]
    b = matrice_texte.loc[communs, colonnes]
    ecarts = (a - b).abs()
    divergents = ecarts[(ecarts >= 1)].dropna(how="all")
    if divergents.empty:
        return []

    articles = list(divergents.index)[:8]
    return [Alerte(
        "information",
        f"{int((ecarts >= 1).sum().sum())} case(s) où les deux référentiels "
        "divergent",
        "Sur ces articles, être proche de la France et vouloir garder le texte "
        "en l'état ne sont pas la même chose, la France y demande une "
        "modification. Articles : " + ", ".join(str(x) for x in articles)
        + ("…" if len(divergents) > 8 else ""),
        "Basculez le référentiel en haut de page pour lire les deux lectures.")]


# ---------------------------------------------------------------------------
# Coalitions
# ---------------------------------------------------------------------------

def coalitions(agree: pd.DataFrame, shared: pd.DataFrame,
               population_disponible: bool) -> list[Alerte]:
    alertes: list[Alerte] = []
    if agree is None or agree.empty:
        return alertes

    if not population_disponible:
        alertes.append(Alerte(
            "bloquant", "Chiffres de population absents",
            "Sans eux, ni majorité qualifiée ni minorité de blocage ne se "
            "calculent.",
            "Renseignez `data/reference/populations.csv` depuis la page "
            "Administration."))

    if shared is not None and not shared.empty:
        maigres = 0
        total = 0
        for i, a in enumerate(shared.index):
            for b in list(shared.columns)[i + 1:]:
                total += 1
                if shared.loc[a, b] < ARTICLES_COMMUNS_MINI:
                    maigres += 1
        if maigres:
            alertes.append(Alerte(
                "attention",
                f"{maigres} paire(s) d'États sur {total} partagent moins de "
                f"{ARTICLES_COMMUNS_MINI} articles",
                "Leur taux d'accord se calcule sur une base trop mince pour "
                "signifier quoi que ce soit, deux coïncidences suffisent à "
                "afficher 100 %.",
                "Montez « Articles communs minimum » dans l'onglet Blocs et "
                "dans le tableau des paires."))

    alertes.append(Alerte(
        "information", "Des positions écrites ne sont pas des votes",
        "L'arithmétique du Conseil dit ce que donnerait cette répartition si "
        "elle se transposait en vote. Une délégation qui écrit une réserve "
        "peut voter pour ; une qui se tait peut voter contre.",
        "Utilisez ces chiffres pour hiérarchiser un démarchage, pas pour "
        "annoncer un résultat."))
    return _trier(alertes)


# ---------------------------------------------------------------------------
# Comparaison de versions
# ---------------------------------------------------------------------------

def versions(deltas: list) -> list[Alerte]:
    alertes: list[Alerte] = []
    if not deltas:
        return alertes

    ajouts = [d for d in deltas if d.status == "ajout"]
    suppressions = [d for d in deltas if d.status == "suppression"]
    if ajouts and suppressions:
        alertes.append(Alerte(
            "attention",
            f"{len(suppressions)} suppression(s) et {len(ajouts)} ajout(s) "
            "simultanés",
            "C'est la signature d'une renumérotation : un article déplacé "
            "apparaît comme supprimé d'un côté et ajouté de l'autre, alors "
            "que son contenu n'a pas changé. C'est le faux positif le plus "
            "fréquent de la comparaison.",
            "Vérifiez dans « Fil du texte » si le contenu se retrouve sous un "
            "autre numéro."))

    non_qualifies = [d for d in deltas
                     if d.status != "inchange" and not d.impact]
    if non_qualifies:
        alertes.append(Alerte(
            "information",
            f"{len(non_qualifies)} changement(s) non qualifié(s)",
            "Leur portée, majeure, mineure, rédactionnelle, n'a pas encore "
            "été évaluée.",
            "Bouton « Tout qualifier » dans l'onglet Changements majeurs."))

    reecrits = [d for d in deltas
                if d.status == "reformulation" and d.similarity < 0.4]
    if reecrits:
        alertes.append(Alerte(
            "attention",
            f"{len(reecrits)} article(s) réécrit(s) à plus de 60 %",
            "Une similarité aussi basse peut signaler une refonte de fond, ou "
            "un mauvais appariement entre deux articles qui n'ont que leur "
            "numéro en commun.",
            "Ouvrez-les dans « Article par article » pour trancher."))
    return _trier(alertes)


# ---------------------------------------------------------------------------
# Réponses sourcées (recherche, régimes d'accès)
# ---------------------------------------------------------------------------

def reponse_sourcee(res, limite_demandee: int, corpus_segments: int = 0) -> list[Alerte]:
    """Ce qui limite la confiance qu'on peut accorder à une réponse sourcée."""
    alertes: list[Alerte] = []
    if res is None:
        return alertes

    if getattr(res, "dropped", 0):
        alertes.append(Alerte(
            "attention",
            f"{res.dropped} affirmation(s) retirée(s)",
            "Le modèle a produit des affirmations dont la citation était "
            "introuvable dans le corpus, même après une demande de recopie "
            "exacte. Elles ont été supprimées, vous ne les voyez pas, mais "
            "leur nombre indique un sujet sur lequel il extrapole.",
            "Reformulez la question, ou vérifiez que le texte pertinent est "
            "bien chargé."))

    hits = len(getattr(res, "hits", []) or [])
    if hits >= limite_demandee:
        alertes.append(Alerte(
            "attention",
            f"Le plafond de {limite_demandee} passages a été atteint",
            "L'index a remonté au moins autant de passages que le plafond : "
            "il en existe probablement d'autres, non examinés. **C'est le "
            "principal risque de réponse incomplète.**",
            f"Relancez avec un plafond plus élevé, {limite_demandee * 3} par "
            "exemple, ou restreignez le périmètre documentaire."))

    claims = len(getattr(res, "claims", []) or [])
    indirect = len(getattr(res, "indirect", []) or [])
    if not claims and indirect:
        alertes.append(Alerte(
            "information",
            "Aucun passage ne répond directement",
            "Les éléments affichés viennent de la seconde lecture, plus "
            "inclusive : ils éclairent la question sans y répondre.",
            "Traitez-les comme du contexte, pas comme une réponse."))

    if claims:
        documents = {c.hit.document_name for c in res.claims}
        if len(documents) == 1:
            alertes.append(Alerte(
                "information",
                "Toute la réponse vient d'un seul document",
                f"Document : {list(documents)[0][:60]}. Ce n'est pas anormal, "
                "mais une réponse mono-source ne recoupe rien.",
                "Élargissez le périmètre si d'autres textes sont pertinents."))
    return _trier(alertes)


def resume(alertes: list[Alerte]) -> str:
    """Phrase d'en-tête du panneau, pour savoir s'il faut l'ouvrir."""
    if not alertes:
        return "Aucun point d'attention détecté."
    compte: dict[str, int] = {}
    for a in alertes:
        compte[a.niveau] = compte.get(a.niveau, 0) + 1
    morceaux = [f"{n} {libelle}" for libelle, n in
                (("bloquant(s)", compte.get("bloquant", 0)),
                 ("point(s) d'attention", compte.get("attention", 0)),
                 ("remarque(s)", compte.get("information", 0))) if n]
    return " · ".join(morceaux)
