"""
Récupération des textes publics depuis EUR-Lex.

Pourquoi le HTML plutôt que le PDF — c'est la seule décision technique qui
compte ici, et elle a des conséquences sur toute la chaîne.

Le PDF du Journal officiel est une mise en page : deux colonnes, des césures
en fin de ligne, des en-têtes et des numéros de page insérés au milieu du
texte, parfois un ordre de lecture qui ne suit pas l'ordre visuel. L'extraction
produit un texte qu'il faut recoudre, et le recousage introduit des écarts qui
ne sont pas dans le texte officiel. Sur une comparaison de versions, ces écarts
se comptent comme des modifications : on compare alors deux extractions, pas
deux textes.

Le HTML du même document porte la structure : un article est un bloc, un
paragraphe est un bloc, il n'y a ni césure ni colonne. Le texte obtenu est
stable d'une version à l'autre, ce qui est exactement la propriété requise
pour un diff. C'est donc le HTML qui est récupéré ici.

Ce que cela coûte : la pagination du Journal officiel est perdue. Les numéros
de page affichés dans les citations d'un document récupéré ainsi sont des
repères internes, pas les pages du JO — le module le signale explicitement
pour que personne ne cite « p. 14 » dans une note en croyant citer le JO.

Aucune dépendance nouvelle : `urllib` et `html.parser` sont dans la
bibliothèque standard, et respectent les variables d'environnement de proxy —
ce qui compte sur un poste d'administration.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

BASE = "https://eur-lex.europa.eu/legal-content/{langue}/TXT/HTML/?uri=CELEX:{celex}"
TIMEOUT = 40

# EUR-Lex ne sert pas toujours le document à la première adresse : selon le
# texte, la langue et l'état de la session, il répond une page d'accueil, une
# page de consentement aux cookies, ou une page « document non disponible ».
# On essaie donc plusieurs formes d'adresse, de la plus directe à la plus
# officielle, et on garde la première qui rend un texte exploitable.
#
# La dernière est l'endpoint de l'Office des publications : c'est l'adresse
# prévue pour les machines, elle ignore l'interface web et ses redirections.
# C'est souvent la seule qui passe derrière un proxy filtrant.
GABARITS = [
    ("page HTML directe",
     "https://eur-lex.europa.eu/legal-content/{langue}/TXT/HTML/?uri=CELEX:{celex}"),
    ("page HTML, langue forcée",
     "https://eur-lex.europa.eu/legal-content/{langue}/TXT/HTML/"
     "?uri=CELEX:{celex}&from={langue}"),
    ("page complète",
     "https://eur-lex.europa.eu/legal-content/{langue}/TXT/?uri=CELEX:{celex}"),
    ("Office des publications (CELLAR)",
     "http://publications.europa.eu/resource/celex/{celex}"),
]

GABARIT_PDF = ("https://eur-lex.europa.eu/legal-content/{langue}/TXT/PDF/"
               "?uri=CELEX:{celex}")

# Signes qu'EUR-Lex a répondu autre chose que le document demandé.
_PAGES_INUTILES = (
    "the requested document does not exist",
    "document n'existe pas",
    "no documents matching",
    "sorry, the requested document",
    "veuillez accepter les cookies",
    "this site uses cookies",
    "javascript is disabled",
)
TAILLE_MINIMALE = 1200

# Un poste d'administration sort par un proxy et rejette les clients sans
# en-tête d'agent. On se présente pour ce qu'on est.
ENTETES = {
    "User-Agent": "MARIaSOL/1.0 (outil interne d'administration ; urllib)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr,en",
}

# Catalogue de départ : les textes que la page « Régimes d'accès » suppose
# chargés. Les identifiants CELEX sont stables et vérifiables sur EUR-Lex.
CATALOGUE = {
    "RGPD, règlement (UE) 2016/679": "32016R0679",
    "Data Governance Act, règlement (UE) 2022/868": "32022R0868",
    "Data Act, règlement (UE) 2023/2854": "32023R2854",
    "Directive Open Data, directive (UE) 2019/1024": "32019L1024",
    "Règlement sur l'intelligence artificielle, règlement (UE) 2024/1689":
        "32024R1689",
    "Règlement sur les marchés numériques (DMA), règlement (UE) 2022/1925":
        "32022R1925",
    "Règlement sur les services numériques (DSA), règlement (UE) 2022/2065":
        "32022R2065",
}

_CELEX = re.compile(r"\b([13]\d{4}[A-Z]{1,2}\d{4})\b", re.IGNORECASE)
# « règlement (UE) 2023/2854 », « directive (UE) 2019/1024 », « 2016/679 »
_REFERENCE = re.compile(
    r"(?P<nature>r[eè]glement|directive|decision|décision)?\s*"
    r"(?:\(UE\)\s*)?(?P<annee>(?:19|20)\d{2})\s*/\s*(?P<numero>\d{1,4})",
    re.IGNORECASE)

_LETTRE = {"reglement": "R", "règlement": "R", "directive": "L",
           "decision": "D", "décision": "D"}


def to_celex(reference: str) -> str:
    """Traduit une référence usuelle en identifiant CELEX.

    Accepte un CELEX, une URL EUR-Lex, ou une référence en clair. Renvoie une
    chaîne vide si rien n'est reconnu — la page appelante le signale plutôt
    que de tenter une requête au hasard.
    """
    texte = (reference or "").strip()
    if not texte:
        return ""

    direct = _CELEX.search(texte.replace(" ", ""))
    if direct:
        return direct.group(1).upper()

    m = _REFERENCE.search(texte)
    if not m:
        return ""
    nature = (m.group("nature") or "règlement").lower()
    lettre = _LETTRE.get(nature, "R")
    annee, numero = m.group("annee"), int(m.group("numero"))
    # Un règlement porte son numéro avant l'année (2023/2854 → 32023R2854) ;
    # une directive l'inverse dans l'usage courant mais pas dans le CELEX,
    # qui reste année puis numéro sur quatre chiffres.
    return f"3{annee}{lettre}{numero:04d}"


def url(celex: str, langue: str = "FR") -> str:
    return BASE.format(langue=langue.upper(), celex=celex.upper())


class _Extracteur(HTMLParser):
    """Transforme le HTML du Journal officiel en texte à blocs.

    On ne cherche pas à interpréter les classes CSS d'EUR-Lex : elles ont
    changé plusieurs fois. On garde le texte et les frontières de blocs, et le
    découpage en articles est fait ensuite par le même code que pour un PDF —
    un seul découpeur à maintenir, un seul comportement à vérifier.
    """

    IGNORE = {"script", "style", "head", "noscript"}
    BLOCS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self._ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORE:
            self._ignore += 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORE:
            self._ignore = max(0, self._ignore - 1)
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data):
        if self._ignore:
            return
        texte = data.strip()
        if texte:
            self.morceaux.append(texte + " ")


def html_vers_texte(html: str) -> str:
    """Texte lisible, un bloc par paragraphe."""
    parseur = _Extracteur()
    parseur.feed(html)
    texte = "".join(parseur.morceaux)
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\n\s*\n\s*", "\n\n", texte)
    return texte.strip()


def en_pages(texte: str, taille: int = 2600) -> list[str]:
    """Découpe en pseudo-pages, sans jamais couper un paragraphe.

    La pagination du JO n'existe pas dans le HTML. Ces repères servent aux
    citations internes de l'outil ; ils ne correspondent pas aux pages du
    Journal officiel, et le document importé le dit.
    """
    pages, courante = [], []
    total = 0
    for bloc in texte.split("\n\n"):
        if total + len(bloc) > taille and courante:
            pages.append("\n\n".join(courante))
            courante, total = [], 0
        courante.append(bloc)
        total += len(bloc) + 2
    if courante:
        pages.append("\n\n".join(courante))
    return pages or [texte]


@dataclass
class Recuperation:
    celex: str = ""
    langue: str = "FR"
    url: str = ""
    titre: str = ""          # nom d'usage, lisible : « Data Act »
    texte: str = ""
    pages: list[str] = field(default_factory=list)
    erreur: str = ""
    avertissements: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.pages) and not self.erreur


_TITRE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _ouvrir(adresse: str, timeout: int) -> tuple[str, str]:
    """Télécharge une page. Renvoie (contenu, erreur) — jamais d'exception.

    Un opener avec gestion des cookies : EUR-Lex pose un cookie de session et
    redirige tant qu'il n'est pas accepté, ce qui donne une page d'accueil au
    lieu du document.
    """
    import http.cookiejar

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    requete = urllib.request.Request(adresse, headers=ENTETES)
    try:
        with opener.open(requete, timeout=timeout) as reponse:
            brut = reponse.read()
            encodage = reponse.headers.get_content_charset() or "utf-8"
        return brut.decode(encodage, errors="replace"), ""
    except urllib.error.HTTPError as exc:
        return "", f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raison = getattr(exc, "reason", exc)
        return "", f"réseau : {raison}"


def _exploitable(texte: str) -> str:
    """Diagnostic d'une page récupérée. Chaîne vide si elle convient."""
    if len(texte) < TAILLE_MINIMALE:
        return "page trop courte"
    bas = texte[:4000].lower()
    for motif in _PAGES_INUTILES:
        if motif in bas:
            return "page d'accueil ou d'avertissement"
    if not re.search(r"\b(?:article|artikel|considérant|recital)\b", texte,
                     re.IGNORECASE):
        return "aucun article reconnaissable"
    return ""


def _depuis_pdf(celex: str, langue: str, timeout: int) -> tuple[str, str]:
    """Repli sur le PDF du Journal officiel, quand le HTML ne vient pas.

    Moins bon que le HTML — la mise en page en deux colonnes laisse des traces
    dans le texte extrait — mais très supérieur à rien. Le document importé le
    signale, pour que personne ne fonde une comparaison de versions dessus
    sans le savoir.
    """
    adresse = GABARIT_PDF.format(langue=langue.upper(), celex=celex)
    requete = urllib.request.Request(adresse, headers={
        **ENTETES, "Accept": "application/pdf"})
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            donnees = reponse.read()
    except Exception as exc:                      # noqa: BLE001
        return "", f"PDF indisponible ({exc})"
    if not donnees[:5].startswith(b"%PDF"):
        return "", "la réponse n'est pas un PDF"

    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(donnees)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
    except Exception as exc:                      # noqa: BLE001
        return "", f"lecture du PDF impossible ({exc})"
    return "\n\n".join(pages).strip(), ""


def recuperer(reference: str, langue: str = "FR",
              timeout: int = TIMEOUT, autoriser_pdf: bool = True) -> Recuperation:
    """Télécharge un texte depuis EUR-Lex et le prépare pour l'import.

    Ne lève jamais : les erreurs réseau d'un poste d'administration — proxy,
    filtrage, absence de sortie — sont la règle et non l'exception, et
    l'utilisateur doit lire un message utile, pas une trace d'exception.

    Chaque adresse tentée est consignée avec son résultat : quand rien ne
    passe, c'est ce journal qui permet de dire si le réseau bloque, si le
    document n'existe pas dans cette langue, ou si EUR-Lex a changé de format.
    """
    celex = to_celex(reference)
    if not celex:
        return Recuperation(
            erreur="Référence non reconnue. Donnez un identifiant CELEX "
                   "(32023R2854), une adresse EUR-Lex, ou une référence du "
                   "type « règlement (UE) 2023/2854 ».")

    journal: list[str] = []
    for nom, gabarit in GABARITS:
        adresse = gabarit.format(langue=langue.upper(), celex=celex)
        html, erreur = _ouvrir(adresse, timeout)
        if erreur:
            journal.append(f"{nom} · {erreur}")
            continue

        texte = html_vers_texte(html)
        probleme = _exploitable(texte)
        if probleme:
            journal.append(f"{nom} · {probleme} ({len(texte)} caractères)")
            continue

        titre_html = ""
        m = _TITRE.search(html)
        if m:
            titre_html = re.sub(r"\s+", " ", m.group(1)).strip()

        res = Recuperation(celex=celex, langue=langue.upper(), url=adresse,
                           titre=nom_usuel(celex, texte, titre_html),
                           texte=texte, pages=en_pages(texte))
        res.avertissements.append(
            "Version HTML : la structure des articles est fiable, mais la "
            "pagination affichée dans les citations est interne à l'outil et "
            "ne correspond pas aux pages du Journal officiel.")
        if len(journal) > 0:
            res.avertissements.append(
                "Adresse retenue : « " + nom + " ». Les précédentes ont "
                "échoué, " + " ; ".join(journal) + ".")
        return res

    # --- repli sur le PDF --------------------------------------------------
    if autoriser_pdf:
        texte, erreur_pdf = _depuis_pdf(celex, langue, timeout)
        if texte and len(texte) >= TAILLE_MINIMALE:
            res = Recuperation(
                celex=celex, langue=langue.upper(),
                url=GABARIT_PDF.format(langue=langue.upper(), celex=celex),
                titre=nom_usuel(celex, texte), texte=texte,
                pages=en_pages(texte))
            res.avertissements.append(
                "Récupéré en PDF, faute de HTML disponible. La mise en page "
                "en deux colonnes laisse des traces dans le texte extrait : "
                "utilisable pour la recherche, à vérifier avant d'en tirer "
                "une comparaison de versions.")
            res.avertissements.append("Tentatives HTML : " + " ; ".join(journal) + ".")
            return res
        journal.append(f"PDF · {erreur_pdf or 'texte trop court'}")

    reseau = all("réseau" in ligne or "HTTP" in ligne for ligne in journal)
    conseil = (
        "Le réseau de l'administration bloque probablement les sorties "
        "directes. Ouvrez l'adresse dans le navigateur, enregistrez la page "
        "ou le PDF, puis chargez le fichier depuis l'onglet « Importer »."
        if reseau else
        "EUR-Lex répond, mais pas avec le document attendu. Vérifiez "
        "l'identifiant CELEX, essayez l'autre langue, ou passez par le "
        "navigateur puis l'onglet « Importer »."
    )
    return Recuperation(
        celex=celex, langue=langue.upper(),
        url=GABARITS[0][1].format(langue=langue.upper(), celex=celex),
        erreur=conseil, avertissements=journal)


# ---------------------------------------------------------------------------
# Nom d'usage du texte récupéré
# ---------------------------------------------------------------------------
#
# La balise <title> d'EUR-Lex porte souvent le nom du fichier XML source —
# « L_2022152FR.01000101.xml » — qui ne dit rien à personne. Le nom affiché
# dans la bibliothèque doit permettre de reconnaître le texte au premier
# coup d'œil : « Data Governance Act », pas un identifiant de fichier.
#
# Trois sources, dans l'ordre de préférence :
#   1. le catalogue, qui porte les noms d'usage (« Data Act », « RGPD ») ;
#   2. l'intitulé officiel lu en tête du texte lui-même ;
#   3. l'identifiant CELEX, en dernier recours.

# Noms d'usage, indexés par CELEX. Ce sont les noms sous lesquels ces textes
# se désignent en réunion — personne ne dit « le règlement 2022/868 ».
NOMS_USAGE = {
    "32016R0679": "RGPD",
    "32022R0868": "Data Governance Act",
    "32023R2854": "Data Act",
    "32019L1024": "Directive Open Data",
    "32024R1689": "Règlement sur l'intelligence artificielle",
    "32022R1925": "Règlement sur les marchés numériques (DMA)",
    "32022R2065": "Règlement sur les services numériques (DSA)",
    "32022L2555": "Directive NIS 2",
    "32019R0881": "Cybersecurity Act",
    "32024R2847": "Cyber Resilience Act",
    "32022R2554": "DORA",
    # Les textes que l'omnibus numérique modifie : sans leur nom d'usage, le
    # menu « texte à examiner » n'affiche que des numéros, et personne ne
    # reconnaît « règlement (UE) 2018/1725 » d'un coup d'œil.
    "32014R0910": "eIDAS",
    "32018R1724": "Règlement portail numérique unique",
    "32018R1725": "Règlement protection des données des institutions de l'UE",
    "32002L0058": "Directive vie privée et communications électroniques",
    "32022L2557": "Directive résilience des entités critiques (REC)",
    "32019R1150": "Règlement plateformes-entreprises (P2B)",
}

_TITRE_INUTILE = re.compile(
    r"(\.xml$|^L_\d|^EUR-Lex|^\s*$|celex|publications\.europa)", re.IGNORECASE)

# « RÈGLEMENT (UE) 2022/868 DU PARLEMENT EUROPÉEN ET DU CONSEIL du 30 mai 2022
#   relatif à la gouvernance européenne des données … »
_INTITULE = re.compile(
    r"((?:R[ÈE]GLEMENT|DIRECTIVE|D[ÉE]CISION)\s*\((?:UE|EU)\)[^\n]{0,400})",
    re.IGNORECASE)
# La partie qui dit de quoi le texte traite, après « relatif à » / « on ».
_OBJET = re.compile(
    r"\b(?:relati(?:f|ve)s?\s+(?:à|au|aux)|concernant|sur\s+l|établissant|on)\s+(.{10,140})",
    re.IGNORECASE)


# Noms de fichiers que le téléchargement d'EUR-Lex produit et qui ne disent
# rien : « cellar_ebf17714-c56e-11f0-8da2-01aa75ed71a1.0010.02_DOC_1.pdf »,
# « CELEX_32016R0679_FR_TXT.pdf », « L_2022152FR.01000101.xml ».
_NOM_DE_MACHINE = re.compile(
    r"^(cellar[_-]|celex[_-]|l_\d|c_\d|st\d{4,}|sn\d{4,}|"
    r"[0-9a-f]{8}-[0-9a-f]{4})", re.IGNORECASE)


def nom_de_machine(nom: str) -> bool:
    """Ce nom de fichier dit-il de quel texte il s'agit ?

    « CELEX_32016R0679_FR_TXT.pdf » identifie le texte pour un ordinateur,
    pas pour la personne qui ouvre la liste des documents — et c'est cette
    liste qu'on lit dix fois par jour.
    """
    base = re.sub(r"\.\w{2,5}$", "", (nom or "").strip())
    return bool(_NOM_DE_MACHINE.search(base))


def nom_depuis_le_document(pages: list[str], defaut: str = "") -> str:
    """Nom lisible tiré des premières pages du document lui-même.

    Sert à l'import d'un fichier téléchargé à la main sur EUR-Lex, dont le nom
    est celui que le site a donné. Trois cas, dans cet ordre :

    1. une **proposition de la Commission** : sa page de garde porte le numéro
       COM et, presque toujours, un titre court entre parenthèses — « (règlement
       omnibus numérique) ». C'est ce nom-là qu'on emploie en réunion ;
    2. un **acte publié** : son intitulé officiel ouvre le texte, et le numéro
       qu'il contient donne le CELEX, donc le nom d'usage du catalogue ;
    3. à défaut, le nom du fichier est conservé.

    L'ordre compte : sur une proposition, les premiers numéros de règlement
    rencontrés sont ceux des textes qu'elle modifie. Les prendre pour elle
    baptisait l'omnibus « Directive Open Data ».
    """
    tete = "\n".join((pages or [])[:3])[:6000]

    # --- 1. proposition de la Commission -----------------------------------
    if re.search(r"(?i)proposition\s+de\s*\n?\s*(r[èe]glement|directive)", tete):
        com = re.search(r"COM\s*\((\d{4})\)\s*(\d+)", tete)
        reference = f"COM({com.group(1)}) {com.group(2)}" if com else ""
        court = re.search(r"\(((?:r[èe]glement|directive|acte)[^)]{3,60})\)", tete,
                          re.IGNORECASE)
        if court:
            titre = court.group(1).strip()
            titre = titre[0].upper() + titre[1:]
        else:
            nature = "règlement" if re.search(r"(?i)proposition\s+de\s*\n?\s*r",
                                              tete) else "directive"
            titre = f"Proposition de {nature}"
        return f"{titre} · {reference}".strip(" ·")[:120]

    # --- 2. acte publié ----------------------------------------------------
    m = _INTITULE.search(tete)
    if m:
        intitule = re.sub(r"\s+", " ", m.group(1)).strip()
        num = re.search(r"\((?:UE|CE)\)\s*(?:n[°ºo]\s*)?(\d{4})/(\d{1,4})",
                        intitule, re.IGNORECASE)
        celex = ""
        if num:
            lettre = "R" if intitule.upper().startswith("R") else "L"
            annee, numero = num.group(1), num.group(2)
            if len(annee) == 4 and annee.startswith(("19", "20")):
                celex = f"3{annee}{lettre}{int(numero):04d}"
            else:
                celex = f"3{numero}{lettre}{int(annee):04d}"
        nom = nom_usuel(celex, texte=tete)
        if nom and not _TITRE_INUTILE.search(nom):
            return f"{nom} · {celex}" if celex and nom != celex else nom

    return defaut


def nom_usuel(celex: str, texte: str = "", titre_html: str = "") -> str:
    """Nom lisible d'un texte récupéré : « Data Act », pas un nom de fichier."""
    celex = (celex or "").upper()
    if celex in NOMS_USAGE:
        return NOMS_USAGE[celex]

    m = _INTITULE.search(texte or "")
    if m:
        intitule = re.sub(r"\s+", " ", m.group(1)).strip()
        objet = _OBJET.search(intitule)
        if objet:
            court = objet.group(1).strip().rstrip(",;.")
            # On garde la référence courte plus l'objet : « règlement (UE)
            # 2022/868 — gouvernance européenne des données ».
            reference = intitule.split("DU PARLEMENT")[0].strip()
            return f"{reference.capitalize()} · {court}"[:120]
        return intitule[:120]

    propre = re.sub(r"\s+", " ", (titre_html or "")).strip()
    if propre and not _TITRE_INUTILE.search(propre):
        return propre[:120]
    return celex or "Texte EUR-Lex"
