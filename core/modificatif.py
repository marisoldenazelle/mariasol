"""
Lecture d'un **acte modificatif** — un omnibus, un règlement « portant
modification de… ».

Pourquoi ce module existe. Un omnibus n'est pas une nouvelle version du Data
Act : c'est un texte qui *dit* ce qu'il faut y changer — « à l'article 5 du
règlement (UE) 2023/2854, le paragraphe 2 est remplacé par le texte
suivant… ». Son article premier ne correspond à rien dans le Data Act. Le
comparer article par article au Data Act, comme on compare deux compromis
successifs, apparie l'article 1 de l'un avec l'article 1 de l'autre et produit
un résultat qui n'a aucun sens — c'est le défaut que cette page corrige.

Ce que fait ce module, et ce qu'il ne fait pas. Il lit les instructions de
modification et les range par **texte cible** puis par **article cible** :
quel règlement, quel article, quelle opération, et le texte nouveau entre
guillemets. Tout est déterministe — expressions régulières et découpage — et
tout est vérifiable : chaque modification porte l'instruction verbatim et sa
page. Aucun modèle n'intervient, et rien n'est deviné : une instruction que
les motifs ne reconnaissent pas est conservée telle quelle, marquée
« non analysée », plutôt qu'écartée en silence.

La forme lue est celle de la rédaction législative européenne, stable depuis
des décennies :

    Article premier
    Modifications du règlement (UE) 2023/2854

    Le règlement (UE) 2023/2854 est modifié comme suit:
    1. L'article 1er est modifié comme suit:
       (a) au paragraphe 1, les points suivants sont ajoutés:
           «e bis) l'enregistrement volontaire…»;
       (b) le paragraphe 7 est supprimé;
    2. L'article 5, paragraphe 1, point b), est remplacé par le texte suivant:
       «…»
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.eurlex import NOMS_USAGE

# ---------------------------------------------------------------------------
# Repérage
# ---------------------------------------------------------------------------

# Fin de l'exposé des motifs et des considérants : le dispositif commence ici.
_DISPOSITIF = re.compile(
    r"ONT\s+ADOPT[ÉE]\s+(?:LE\s+PR[ÉE]SENT\s+R[ÈE]GLEMENT|"
    r"LA\s+PR[ÉE]SENTE\s+(?:DIRECTIVE|D[ÉE]CISION))",
    re.IGNORECASE)

# En-tête d'article de l'acte modificatif, seul sur sa ligne, suivi de son
# intitulé sur la ligne suivante — « Article 3 » / « Modifications du
# règlement (UE) 2016/679 (RGPD) ».
_ARTICLE_OMNIBUS = re.compile(
    r"(?m)^[ \t]*(?P<tete>Article\s+(?:premier|\d+))[ \t]*$")

# « règlement (UE) 2023/2854 », « directive 2002/58/CE »,
# « règlement (UE) nº 910/2014 », « directive (UE) 2022/2555 »
_ACTE = re.compile(
    r"(?P<nature>r[èe]glement|directive|d[ée]cision)\s*"
    r"(?:\((?P<espace>UE|CE|CEE|EU)\)\s*)?"
    r"(?:n[°ºo]\s*)?"
    # Les deux écritures : « 2023/2854 » (année/numéro) et « nº 910/2014 »
    # (numéro/année). C'est la place de l'année qui les distingue.
    r"(?P<a>\d{1,4})/(?P<b>\d{1,4})"
    r"(?:/(?P<espace2>CE|UE|CEE))?",
    re.IGNORECASE)

_MODIFIE_COMME_SUIT = re.compile(
    r"est\s+modifi[ée]e?\s+comme\s+suit", re.IGNORECASE)

# Instruction de premier niveau : « 12. À l'article 64, … »
_ITEM = re.compile(r"^[ \t]*(?P<num>\d{1,3})\.\s+(?P<corps>\S.*)$")
# Sous-instruction : « (a) au paragraphe 1, … »
_SOUS_ITEM = re.compile(r"^[ \t]*\((?P<lettre>[a-z]{1,2})\)\s+(?P<corps>\S.*)$")

# Article visé dans le texte cible. Les ordinaux latins vont bien au-delà de
# « quater » dans un omnibus : l'article 32 novovicies existe réellement.
_ORDINAUX = (
    "bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies|undecies|"
    "duodecies|terdecies|quaterdecies|quindecies|sexdecies|septdecies|"
    "octodecies|novodecies|vicies|unvicies|duovicies|tervicies|quatervicies|"
    "quinvicies|sexvicies|septvicies|octovicies|novovicies")
# Le numéro ne doit pas absorber l'espace qui le suit : avec `\d{1,3}\s?`, le
# groupe `num` avalait « 18 » ET l'espace, si bien que l'ordinal qui venait
# ensuite ne trouvait plus l'espace qu'il exigeait. « L'article 18 bis suivant
# est inséré » était alors rattaché à l'article 18, c'est-à-dire à un article
# existant plutôt qu'à celui que l'acte crée.
_ARTICLE_CIBLE = re.compile(
    r"article\s+(?P<num>\d{1,3}(?:\s?er)?|premier)"
    r"(?:\s*(?P<ordinal>" + _ORDINAUX + r"))?",
    re.IGNORECASE)

# Opérations, dans l'ordre où on les cherche : la première qui correspond
# gagne, et l'ordre compte — « est remplacé » doit être testé avant
# « est modifié comme suit », qui est le cas générique.
# `[ée]{1,2}s?` couvre les quatre accords : supprimé, supprimée, supprimés,
# supprimées. Sans le pluriel féminin, « les phrases suivantes sont ajoutées »
# n'était reconnue comme aucune opération.
_OPERATIONS = (
    ("suppression", re.compile(
        r"\b(?:est|sont)\s+supprim[ée]{1,2}s?\b", re.IGNORECASE)),
    ("remplacement", re.compile(
        r"\b(?:est|sont)\s+remplac[ée]{1,2}s?\b", re.IGNORECASE)),
    ("insertion", re.compile(
        r"\b(?:est|sont)\s+ins[ée]r[ée]{1,2}s?\b", re.IGNORECASE)),
    ("ajout", re.compile(
        r"\b(?:est|sont)\s+ajout[ée]{1,2}s?\b", re.IGNORECASE)),
    ("abrogation", re.compile(r"\b(?:est|sont)\s+abrog[ée]{1,2}s?\b",
                              re.IGNORECASE)),
    # Après une abrogation, l'acte énumère les dispositions qui survivent le
    # temps de la transition. Ce ne sont pas des modifications, mais les
    # laisser « non analysées » donnait huit lignes muettes dans la liste.
    ("maintien", re.compile(
        r"continuent?\s+(?:de|à)\s+s[’\']appliquer|restent?\s+"
        r"(?:temporairement\s+)?(?:en\s+vigueur|applicables?)|"
        r"par\s+d[ée]rogation\s+au\s+paragraphe", re.IGNORECASE)),
    ("modification", _MODIFIE_COMME_SUIT),
)

OPERATION_LABEL = {
    "remplacement": "Remplacé",
    "insertion": "Inséré",
    "ajout": "Ajouté",
    "suppression": "Supprimé",
    "abrogation": "Abrogé",
    "modification": "Modifié",
    "maintien": "Maintien transitoire",
    "": "Non analysée",
}


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

@dataclass
class Modification:
    """Une instruction de modification, telle qu'elle est écrite."""

    numero: str                  # « 12 » ou « 12 (b) »
    article_cible: str           # « Article 5 » — intitulé normalisé
    section_id: str              # « art_5 », pour rapprocher du texte cible
    operation: str               # remplacement | insertion | ajout | …
    instruction: str             # la phrase, verbatim
    texte_nouveau: str = ""      # ce qui figure entre guillemets
    page: int = 0
    portee: str = ""             # « paragraphe 1, point b) » quand c'est dit
    # Cette instruction a-t-elle été reportée dans le texte reconstitué ?
    # None tant que la reconstitution n'a pas été tentée (texte cible non
    # chargé). C'est ce qui permet de dire à l'écran, instruction par
    # instruction, ce que le « avant / après » montre et ce qu'il ne montre
    # pas — plutôt que de laisser croire que tout y figure.
    appliquee: bool | None = None

    @property
    def libelle_operation(self) -> str:
        return OPERATION_LABEL.get(self.operation, OPERATION_LABEL[""])

    @property
    def vise_l_article_entier(self) -> bool:
        """« L'article 4 est supprimé » — et non « le point a) est supprimé ».

        La distinction décide de ce qu'on affiche : sans elle, l'article 64 du
        RGPD, dont l'omnibus retire un seul point, était étiqueté
        « Supprimé ». L'article survit, et l'écran disait le contraire.
        """
        return bool(_ARTICLE_ENTIER.match(self.instruction))


@dataclass
class BlocCible:
    """Tout ce qu'un article de l'omnibus change dans UN texte."""

    article_omnibus: str          # « Article premier »
    intitule: str                 # « Modifications du règlement (UE) 2023/2854 »
    acte_cible: str               # « règlement (UE) 2023/2854 »
    celex: str = ""               # « 32023R2854 » quand il se déduit
    nom_cible: str = ""           # « Data Act » quand le catalogue le connaît
    modifications: list[Modification] = field(default_factory=list)
    texte: str = ""               # le bloc entier, pour relecture

    @property
    def articles_touches(self) -> list[str]:
        return list(dict.fromkeys(
            m.article_cible for m in self.modifications if m.article_cible))

    @property
    def libelle(self) -> str:
        """Le nom sous lequel on désigne ce texte en réunion.

        « règlement (UE) 2016/679 » est exact et illisible : personne ne le
        reconnaît d'un coup d'œil dans un menu déroulant. On affiche le nom
        d'usage quand le catalogue le connaît, la référence formelle sinon —
        et les deux ensemble, parce que c'est la référence qui figure dans
        l'omnibus et qu'il faut pouvoir la retrouver.
        """
        if self.nom_cible:
            return f"{self.nom_cible} · {self.acte_cible}"
        return self.acte_cible


@dataclass
class ResultatModificatif:
    est_modificatif: bool = False
    blocs: list[BlocCible] = field(default_factory=list)
    remarques: list[str] = field(default_factory=list)

    @property
    def actes_cibles(self) -> list[str]:
        return [b.acte_cible for b in self.blocs]

    def bloc(self, acte_cible: str) -> BlocCible | None:
        for b in self.blocs:
            if b.acte_cible == acte_cible:
                return b
        return None


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def _joindre(pages: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Texte complet, et table des positions → numéro de page."""
    morceaux: list[str] = []
    reperes: list[tuple[int, int]] = []
    curseur = 0
    for i, page in enumerate(pages, start=1):
        reperes.append((curseur, i))
        morceaux.append(page or "")
        curseur += len(page or "") + 1
    return "\n".join(morceaux), reperes


def _page_de(position: int, reperes: list[tuple[int, int]]) -> int:
    page = 1
    for debut, numero in reperes:
        if debut > position:
            break
        page = numero
    return page


def celex_de(acte: str) -> str:
    """« règlement (UE) 2023/2854 » → « 32023R2854 ».

    Deux écritures coexistent : la moderne « 2023/2854 » (année/numéro) et
    l'ancienne « nº 910/2014 » (numéro/année). On les distingue par la place
    de l'année — celle des quatre chiffres qui ressemble à une année.
    """
    m = _ACTE.search(acte or "")
    if not m:
        return ""
    lettre = {"r": "R", "d": "L"}.get(m.group("nature")[0].lower(), "R")
    if m.group("nature").lower().startswith("déc") or \
            m.group("nature").lower().startswith("dec"):
        lettre = "D"
    a, b = m.group("a"), m.group("b")
    annee, numero = (a, b) if len(a) == 4 and a.startswith(("19", "20")) else (b, a)
    return f"3{annee}{lettre}{int(numero):04d}"


def _normaliser_article(num: str, ordinal: str = "") -> tuple[str, str]:
    """« 1er » → (« Article 1 », « art_1 ») ; « 32 bis » → « art_32bis »."""
    brut = (num or "").strip().lower().replace("er", "").strip()
    if brut in ("premier", ""):
        brut = "1"
    chiffres = "".join(c for c in brut if c.isdigit())
    if not chiffres:
        return "", ""
    suffixe = (ordinal or "").strip().lower()
    label = f"Article {int(chiffres)}" + (f" {suffixe}" if suffixe else "")
    sid = f"art_{int(chiffres)}" + (suffixe if suffixe else "")
    return label, sid


def _operation(texte: str) -> str:
    for nom, motif in _OPERATIONS:
        if motif.search(texte):
            return nom
    return ""


def _portee(texte: str) -> str:
    """« au paragraphe 1, point b) » — la précision, quand elle est donnée."""
    bouts = []
    m = re.search(r"paragraphes?\s+[\d\s,ete]+", texte, re.IGNORECASE)
    if m:
        bouts.append(m.group(0).strip(" ,"))
    m = re.search(r"points?\s+[\w\)\s,]{1,20}", texte, re.IGNORECASE)
    if m:
        bouts.append(m.group(0).strip(" ,"))
    return ", ".join(bouts)


def _texte_cite(bloc: str) -> str:
    """Le contenu entre guillemets français qui suit l'instruction.

    C'est le texte nouveau : celui qui remplace, ou celui qui est inséré. On
    prend du premier « au » de même niveau, en tenant compte des guillemets
    imbriqués, qui existent.
    """
    debut = bloc.find("«")
    if debut < 0:
        return ""
    profondeur = 0
    for i in range(debut, len(bloc)):
        if bloc[i] == "«":
            profondeur += 1
        elif bloc[i] == "»":
            profondeur -= 1
            if profondeur == 0:
                return re.sub(r"\s*\n\s*", " ", bloc[debut + 1:i]).strip()
    return re.sub(r"\s*\n\s*", " ", bloc[debut + 1:]).strip()


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def est_acte_modificatif(pages: list[str] | str) -> bool:
    """Ce document dit-il comment modifier d'autres textes ?

    Deux marqueurs concordants sont exigés : la formule « est modifié comme
    suit » et un intitulé d'article annonçant des modifications. Un texte
    ordinaire qui cite un règlement en passant ne coche pas les deux.
    """
    texte = pages if isinstance(pages, str) else "\n".join(pages or [])
    if not texte:
        return False
    chapeaux = len(_MODIFIE_COMME_SUIT.findall(texte))
    intitules = len(re.findall(
        r"(?im)^\s*Modifications?\s+(?:du|de la|des)\s+"
        r"(?:r[èe]glement|directive|d[ée]cision)", texte))
    return chapeaux >= 1 and (intitules >= 1 or chapeaux >= 3)


def entetes_dispositif(pages: list[str] | str) -> list[str]:
    """Numéros des articles de l'acte modificatif lui-même, normalisés.

    Sert à distinguer les articles DE l'omnibus des articles qu'il **cite** :
    un omnibus contient le texte intégral des articles qu'il insère —
    « Article 32 bis », « Article 88 ter »), et rien ne les distingue
    typographiquement de ses propres en-têtes, sinon que ceux-ci sont
    numérotés sans ordinal latin et se suivent.
    """
    if isinstance(pages, str):
        pages = [pages]
    joint = "\n".join(pages)
    depart = _DISPOSITIF.search(joint)
    dispositif = joint[depart.end():] if depart else joint
    labels = []
    for m in _ARTICLE_OMNIBUS.finditer(dispositif):
        tete = re.sub(r"\s+", " ", m.group("tete")).strip().lower()
        labels.append("article 1" if "premier" in tete else tete)
    return list(dict.fromkeys(labels))


def lire(pages: list[str] | str) -> ResultatModificatif:
    """Range les modifications par texte cible, puis par article cible."""
    if isinstance(pages, str):
        pages = [pages]
    joint, reperes = _joindre(list(pages))
    res = ResultatModificatif(est_modificatif=est_acte_modificatif(joint))
    if not res.est_modificatif:
        return res

    # Le dispositif seul : l'exposé des motifs cite les mêmes règlements et
    # produirait des modifications imaginaires.
    depart = _DISPOSITIF.search(joint)
    if depart:
        decalage = depart.end()
    else:
        decalage = 0
        res.remarques.append(
            "La formule « ONT ADOPTÉ LE PRÉSENT RÈGLEMENT » n'a pas été "
            "trouvée : l'exposé des motifs n'a pas pu être écarté, vérifiez "
            "les premières modifications listées.")
    dispositif = joint[decalage:]

    # Découpage par article de l'acte modificatif.
    entetes = list(_ARTICLE_OMNIBUS.finditer(dispositif))
    if not entetes:
        res.remarques.append("Aucun en-tête d'article n'a été reconnu.")
        return res

    for i, m in enumerate(entetes):
        fin = entetes[i + 1].start() if i + 1 < len(entetes) else len(dispositif)
        corps = dispositif[m.end():fin]
        lignes = corps.lstrip("\n").split("\n")
        intitule = lignes[0].strip() if lignes else ""

        acte = ""
        cherche = _ACTE.search(intitule)
        if not cherche:
            # L'intitulé peut tenir sur deux lignes, ou l'acte n'être nommé
            # que dans le chapeau « Le règlement (UE) … est modifié comme
            # suit ».
            chapeau = _MODIFIE_COMME_SUIT.search(corps[:1200])
            zone = corps[:chapeau.end()] if chapeau else corps[:400]
            cherche = _ACTE.search(zone)
        if cherche:
            acte = re.sub(r"\s+", " ", cherche.group(0)).strip()
        if not acte:
            # Article de dispositions finales, d'abrogation, d'entrée en
            # vigueur : il ne modifie aucun texte, on ne le retient pas.
            continue

        celex = celex_de(acte)
        bloc = BlocCible(
            article_omnibus=m.group("tete").strip(),
            intitule=re.sub(r"\s+", " ", intitule)[:160],
            acte_cible=acte,
            celex=celex,
            nom_cible=NOMS_USAGE.get(celex, ""),
            texte=corps,
        )
        # « L'article 19 du règlement (UE) 2022/2554 est modifié comme
        # suit » : l'article visé est nommé une fois, dans le chapeau, et les
        # instructions qui suivent disent seulement « au paragraphe 1… ».
        article_chapeau = ("", "")
        chapeau = _MODIFIE_COMME_SUIT.search(corps[:1200])
        if chapeau:
            vise = _ARTICLE_CIBLE.search(corps[:chapeau.start()])
            if vise:
                article_chapeau = _normaliser_article(
                    vise.group("num"), vise.group("ordinal") or "")

        bloc.modifications = _lire_instructions(
            corps, decalage + m.end(), reperes, defaut=article_chapeau)
        if not bloc.modifications:
            # Certains articles ne portent qu'une instruction, sans numéro :
            # « Dans le tableau figurant à l'annexe II du règlement (UE)
            # 2018/1724, la rubrique “…” est remplacée par le texte suivant ».
            # Sans ce rattrapage, tout un texte cible disparaissait de la
            # liste.
            unique = _instruction_unique(corps, decalage + m.end(), reperes)
            if unique is not None:
                bloc.modifications = [unique]
        if bloc.modifications:
            res.blocs.append(bloc)

    if not res.blocs:
        res.remarques.append(
            "Aucune instruction de modification n'a pu être rattachée à un "
            "texte cible.")
    return res


_ANNEXE = re.compile(r"annexes?\s+(?P<num>[IVXLC]+|\d{1,2})", re.IGNORECASE)


def _instruction_unique(corps: str, position_absolue: int,
                        reperes: list[tuple[int, int]]) -> Modification | None:
    """Un article qui ne porte qu'une instruction, écrite d'un seul tenant."""
    lignes = corps.lstrip("\n").split("\n")
    texte = "\n".join(lignes[1:])          # l'intitulé est déjà lu par ailleurs
    # L'instruction va jusqu'aux deux-points qui annoncent le texte nouveau.
    # Couper au premier guillemet ne marche pas : l'instruction elle-même cite
    # souvent l'intitulé qu'elle remplace — « la rubrique “…” est remplacée ».
    fin = re.search(r"^(.{20,700}?:)\s*$", texte, re.S | re.M)
    tete = (fin.group(1) if fin else texte.split("«", 1)[0]).strip()
    tete = re.sub(r"\s*\n\s*", " ", tete)
    if not tete or not _operation(tete):
        return None

    cible = _ARTICLE_CIBLE.search(tete)
    if cible:
        label, sid = _normaliser_article(
            cible.group("num"), cible.group("ordinal") or "")
    else:
        annexe = _ANNEXE.search(tete)
        label = f"Annexe {annexe.group('num').upper()}" if annexe else ""
        sid = f"ann_{annexe.group('num').lower()}" if annexe else ""
    return Modification(
        numero="1.", article_cible=label, section_id=sid,
        operation=_operation(tete), instruction=tete[:400],
        texte_nouveau=_texte_cite(texte),
        page=_page_de(position_absolue, reperes), portee=_portee(tete))


def _lire_instructions(corps: str, position_absolue: int,
                       reperes: list[tuple[int, int]],
                       defaut: tuple[str, str] = ("", "")) -> list[Modification]:
    """Instructions de premier niveau, et leurs sous-points.

    La difficulté tient au **texte cité** : il contient lui aussi des
    paragraphes numérotés « 7. », qui ressemblent trait pour trait à des
    instructions. On suit donc la profondeur des guillemets et on n'ouvre une
    instruction qu'à l'extérieur de toute citation — sans quoi le paragraphe 7
    d'un article inséré deviendrait la septième modification du règlement.
    """
    modifications: list[Modification] = []
    profondeur = 0
    courant: dict | None = None
    debut_ligne = 0

    def cloturer(fin: int) -> None:
        if courant is None:
            return
        bloc = corps[courant["debut"]:fin]
        instruction = re.sub(r"\s*\n\s*", " ", courant["tete"]).strip()
        cible = _ARTICLE_CIBLE.search(instruction)
        label, sid = ("", "")
        if cible:
            label, sid = _normaliser_article(
                cible.group("num"), cible.group("ordinal") or "")
        modifications.append(Modification(
            numero=courant["numero"],
            article_cible=label,
            section_id=sid,
            operation=_operation(instruction),
            instruction=instruction[:400],
            texte_nouveau=_texte_cite(bloc),
            page=_page_de(position_absolue + courant["debut"], reperes),
            portee=_portee(instruction),
        ))

    for ligne in corps.split("\n"):
        fin_ligne = debut_ligne + len(ligne)
        if profondeur == 0:
            item = _ITEM.match(ligne)
            sous = _SOUS_ITEM.match(ligne)
            if item or sous:
                cloturer(debut_ligne)
                if item:
                    numero = item.group("num") + "."
                    tete = item.group("corps")
                else:
                    prefixe = modifications[-1].numero.split()[0] \
                        if modifications else ""
                    numero = f"{prefixe} ({sous.group('lettre')})".strip()
                    tete = sous.group("corps")
                courant = {"numero": numero, "tete": tete, "debut": debut_ligne}
            elif courant is not None and not courant.get("figee"):
                # La suite immédiate de l'instruction, avant la citation.
                if "«" in ligne:
                    courant["figee"] = True
                else:
                    courant["tete"] += " " + ligne.strip()
        profondeur += ligne.count("«") - ligne.count("»")
        profondeur = max(profondeur, 0)
        debut_ligne = fin_ligne + 1

    cloturer(len(corps))

    # Un sous-point hérite de l'article visé par son instruction parente :
    # « (b) le paragraphe 7 est supprimé » ne nomme pas l'article, il
    # continue le « 1. L'article 1er est modifié comme suit ».
    dernier_article = defaut
    derniere_operation = ""
    for mod in modifications:
        if "(" not in mod.numero:          # instruction de premier niveau
            derniere_operation = mod.operation
        if mod.article_cible:
            dernier_article = (mod.article_cible, mod.section_id)
        elif dernier_article[0]:
            mod.article_cible, mod.section_id = dernier_article
        # « (a) article 2, point 1); » n'énonce aucun verbe : c'est une
        # énumération sous l'instruction parente, dont elle reprend la nature.
        if not mod.operation and "(" in mod.numero and derniere_operation:
            mod.operation = derniere_operation
    return modifications


# ---------------------------------------------------------------------------
# Rapprochement avec le texte cible chargé
# ---------------------------------------------------------------------------

def par_article(bloc: BlocCible) -> dict[str, list[Modification]]:
    """Modifications regroupées par article du texte cible."""
    groupes: dict[str, list[Modification]] = {}
    for mod in bloc.modifications:
        groupes.setdefault(mod.article_cible or "— non rattaché —",
                           []).append(mod)
    return groupes


def documents_candidats(bloc: BlocCible, documents) -> list[str]:
    """Identifiants des documents du corpus qui pourraient être la cible.

    On rapproche d'abord par CELEX, qui est sans ambiguïté, puis par le
    numéro de l'acte tel qu'il s'écrit dans un nom de fichier.
    """
    if documents is None or getattr(documents, "empty", True):
        return []
    m = _ACTE.search(bloc.acte_cible)
    numero = f"{m.group('a')}/{m.group('b')}" if m else ""
    candidats: list[str] = []
    for _, row in documents.iterrows():
        nom = str(row.get("name") or "")
        if bloc.celex and bloc.celex in nom:
            candidats.insert(0, row["id"])
        elif numero and numero in nom:
            candidats.append(row["id"])
    return list(dict.fromkeys(candidats))


# ---------------------------------------------------------------------------
# Reconstitution du texte cible
# ---------------------------------------------------------------------------
#
# Appliquer une instruction, c'est réécrire un article. On ne le fait que
# lorsque l'instruction dit exactement quoi remplacer et par quoi ; sinon on
# affiche la modification à côté de l'article sans toucher au texte, et on le
# dit. Une reconstitution approximative présentée comme le droit en vigueur
# serait pire que pas de reconstitution du tout.

@dataclass
class ArticleReconstitue:
    """Un article du texte cible, avant et après l'acte modificatif."""

    article: str
    section_id: str
    texte_avant: str = ""
    texte_apres: str = ""
    modifications: list[Modification] = field(default_factory=list)
    fiabilite: str = "inchange"   # exacte | approchee | non_appliquee | inchange
    note: str = ""
    # Renseignés par `qualifier()`, et par lui seul : ce sont les deux seuls
    # champs de ce module qui viennent d'un modèle.
    resume: str = ""
    impact: str = ""              # majeur | mineur | redactionnel | nul
    concepts: list[str] = field(default_factory=list)
    # Le texte cible est-il chargé ? Sans lui, on ne peut pas dire si un
    # article est inséré ou seulement modifié : l'absence de texte « avant »
    # ne prouve rien, elle dit seulement qu'on ne l'a pas.
    cible_chargee: bool = False

    @property
    def touche(self) -> bool:
        return bool(self.modifications)

    @property
    def statut(self) -> str:
        """Ce que l'omnibus fait de cet article, d'après ce qu'il écrit.

        L'opération est lue dans l'instruction, jamais déduite de l'absence
        du texte : sans le texte cible chargé, tout article aurait été
        déclaré « inséré », ce qui est faux et se voyait à l'écran.
        """
        if not self.modifications:
            return "Inchangé"
        operations = {m.operation for m in self.modifications}
        if operations <= {"suppression", "abrogation"}:
            # Encore faut-il que ce soit l'article qui disparaisse, et non un
            # point à l'intérieur de l'article.
            if any(m.vise_l_article_entier for m in self.modifications):
                return "Supprimé"
            return "Modifié"
        if operations <= {"insertion"}:
            return "Inséré"
        if operations <= {"maintien"}:
            return "Maintenu"
        if self.cible_chargee and self.texte_avant and not self.texte_apres:
            return "Supprimé"
        # Un article absent du texte de référence n'est pas pour autant
        # inséré : le texte chargé peut être incomplet — c'est signalé à
        # l'écran, mais on ne transforme pas cette lacune en verdict.
        return "Modifié"


_PARAGRAPHE_VISE = re.compile(
    r"paragraphe\s+(?P<num>\d{1,2})", re.IGNORECASE)
_POINT_VISE = re.compile(
    r"point\s+(?P<ref>[a-z]{1,2}\s?(?:bis|ter|quater)?|\d{1,2})\s*\)",
    re.IGNORECASE)
_ARTICLE_ENTIER = re.compile(
    r"^\s*(?:l[’']\s*)?article\s+[\w\s]{1,20}?\s+est\s+"
    r"(?:remplac|supprim|abrog)", re.IGNORECASE)


# Début d'un point : « a) », « (a) », « h bis) », ou le retour au numérotage
# de paragraphe « 3. » qui clôt la liste.
_DEBUT_DE_POINT = re.compile(
    r"(?m)^[ \t]*(?:\(\s*[a-z]{1,2}\s?(?:bis|ter|quater|quinquies)?\s*\)"
    r"|[a-z]{1,2}\s?(?:bis|ter|quater|quinquies)?\s*\)"
    r"|\d{1,2}\.\s)")


def _bornes_paragraphe(texte: str, numero: str) -> tuple[int, int] | None:
    """Où commence et où finit le paragraphe « 3. … » dans un article."""
    motif = re.compile(rf"(?m)^\s*{re.escape(numero)}\.\s")
    debuts = [m.start() for m in motif.finditer(texte)]
    if not debuts:
        return None
    debut = debuts[0]
    suivant = re.compile(rf"(?m)^\s*{int(numero) + 1}\.\s").search(texte, debut + 1)
    return debut, (suivant.start() if suivant else len(texte))


def _bornes_point(texte: str, ref: str) -> tuple[int, int] | None:
    """Où commence et où finit le point « h) … » dans un article.

    Le repère est exigé **en début de ligne** et doit être unique dans
    l'article : « le point h) » cité au fil d'une phrase ne doit pas être pris
    pour le point lui-même, et un article qui numérote deux fois « h) » — ce
    qui arrive quand plusieurs paragraphes portent chacun leur liste — se
    traite à l'œil, pas au hasard.
    """
    ref = re.sub(r"\s+", "", (ref or "")).lower()
    if not ref:
        return None
    motif = re.compile(
        rf"(?m)^[ \t]*\(?\s*{re.escape(ref[0])}\s?{re.escape(ref[1:])}\s*\)\s"
        if len(ref) > 1 else rf"(?m)^[ \t]*\(?\s*{re.escape(ref)}\s*\)\s")
    trouves = list(motif.finditer(texte))
    if len(trouves) != 1:
        return None
    debut = trouves[0].start()
    prochain = _DEBUT_DE_POINT.search(texte, trouves[0].end())
    return debut, (prochain.start() if prochain else len(texte))


# « 2 bis. Les détenteurs… » : le numéro que porte le texte inséré.
_NUMERO_PORTE = re.compile(
    r"^[\s«\"]*(?P<num>\d{1,2})\s*(?P<ordinal>bis|ter|quater|quinquies)?\s*\.")


def _inserer_paragraphe(texte: str, nouveau: str) -> tuple[str, bool]:
    """Insère un paragraphe à sa place quand son numéro permet de la trouver.

    « 2 bis. » se range après le paragraphe 2 ; « 3. » inséré dans un article
    qui a déjà un paragraphe 3 se range avant lui — c'est une renumérotation.
    À défaut, le texte est ajouté à la fin et l'appelant en est informé.
    """
    nouveau = (nouveau or "").strip()
    if not nouveau:
        return texte, False
    if not texte.strip():
        return nouveau, True
    m = _NUMERO_PORTE.match(nouveau)
    if not m:
        return (texte.rstrip() + "\n" + nouveau).strip(), False
    bornes = _bornes_paragraphe(texte, m.group("num"))
    if bornes is None:
        return (texte.rstrip() + "\n" + nouveau).strip(), False
    debut, fin = bornes
    coupe = fin if m.group("ordinal") else debut
    return (texte[:coupe].rstrip() + "\n" + nouveau + "\n"
            + texte[coupe:].lstrip()).strip(), True


def _remplacer_paragraphe(texte: str, numero: str, nouveau: str) -> tuple[str, bool]:
    """Remplace le paragraphe « 3. … » d'un article. Signale s'il l'a trouvé."""
    bornes = _bornes_paragraphe(texte, numero)
    if bornes is None:
        return texte, False
    debut, fin = bornes
    corps = nouveau if nouveau.lstrip().startswith(f"{numero}.") \
        else f"{numero}. {nouveau}"
    return texte[:debut] + corps + "\n" + texte[fin:], True


def appliquer(bloc: BlocCible, segments=None) -> list[ArticleReconstitue]:
    """Le texte cible, article par article, avant et après l'omnibus.

    `segments` est le texte cible tel qu'il est chargé dans le corpus (un
    DataFrame de segments). Sans lui, on rend seulement les articles touchés,
    avec leurs instructions : c'est la lecture « liste des modifications ».
    Avec lui, **tous** les articles sont rendus, y compris ceux que l'omnibus
    ne touche pas, marqués « inchangé » — un article absent de la liste ne
    doit pas laisser croire qu'on a oublié de le regarder.
    """
    par_art = par_article(bloc)
    cible_chargee = segments is not None and not getattr(segments, "empty", True)

    articles: list[ArticleReconstitue] = []
    connus: set[str] = set()

    if cible_chargee:
        for _, row in segments.iterrows():
            label = str(row.get("section_label") or "")
            sid = str(row.get("section_id") or "")
            # Les fragments d'un article long sont recollés : la
            # reconstitution porte sur l'article entier. Le motif exige DEUX
            # groupes de chiffres — « art_5_2 » est un fragment, « art_5 » est
            # un article, et les confondre vidait tous les articles cibles.
            racine = re.sub(r"^([a-z]+_\d+[a-z]*)_\d+$", r"\1", sid)
            propre = re.sub(r"\s*\(\d+/\d+\)\s*$", "", label).strip()
            existant = next((a for a in articles if a.section_id == racine), None)
            if existant is not None:
                existant.texte_avant += "\n" + str(row.get("text") or "")
                continue
            articles.append(ArticleReconstitue(
                article=propre, section_id=racine,
                texte_avant=str(row.get("text") or "")))
            connus.add(propre)

    # Les articles insérés par l'omnibus n'existent pas encore dans la cible.
    for label, mods in par_art.items():
        if label in connus or not label or label.startswith("—"):
            continue
        articles.append(ArticleReconstitue(
            article=label, section_id=mods[0].section_id))

    # Ordre du texte cible : article 5 avant article 12, et un article inséré
    # à sa place plutôt qu'à la fin de la liste.
    def _rang(art: ArticleReconstitue) -> tuple:
        chiffres = "".join(c for c in art.section_id if c.isdigit())
        suffixe = art.section_id.split("_")[-1] if "_" in art.section_id else ""
        lettres = "".join(c for c in suffixe if c.isalpha())
        return (int(chiffres) if chiffres else 9999, lettres)

    articles.sort(key=_rang)

    for art in articles:
        art.cible_chargee = cible_chargee
        mods = par_art.get(art.article, [])
        art.modifications = mods
        if not mods:
            art.texte_apres = art.texte_avant
            art.fiabilite = "inchange"
            continue
        art.texte_apres, art.fiabilite, art.note = _appliquer_a(
            art.texte_avant, mods)

    return articles


def _appliquer_a(texte: str, mods: list[Modification]) -> tuple[str, str, str]:
    """Applique ce qui peut l'être, et dit ce qui ne l'a pas été."""
    resultat = texte
    exactes, laissees = 0, []
    # Reportées, mais à un emplacement que le programme n'a pas su déduire :
    # le contenu est juste, sa place dans l'article ne l'est peut-être pas.
    approximatifs: list[Modification] = []

    for mod in mods:
        instruction = mod.instruction
        if mod.operation == "maintien":
            # Une disposition maintenue en vigueur ne change pas le texte :
            # elle est signalée à côté, elle n'entre pas dans la
            # reconstitution.
            exactes += 1
            continue
        entier = bool(_ARTICLE_ENTIER.match(instruction))

        if mod.operation in ("suppression", "abrogation") and entier:
            resultat, exactes = "", exactes + 1
            continue

        if mod.operation == "remplacement" and entier and mod.texte_nouveau:
            resultat, exactes = mod.texte_nouveau, exactes + 1
            continue

        if mod.operation in ("insertion", "ajout") and not texte \
                and mod.texte_nouveau:
            resultat, exactes = mod.texte_nouveau, exactes + 1
            continue

        # --- suppression d'une partie de l'article -------------------------
        # « le point h) est supprimé », « le paragraphe 3 est supprimé » :
        # sans ce traitement, le texte « après » était identique au texte
        # « avant » et rien n'apparaissait barré à l'écran — alors que
        # l'omnibus supprime bel et bien quelque chose.
        if mod.operation in ("suppression", "abrogation"):
            points = [m.group("ref") for m in _POINT_VISE.finditer(instruction)]
            para = _PARAGRAPHE_VISE.search(instruction)
            if points:
                bornes = [_bornes_point(resultat, r) for r in points]
                if all(b is not None for b in bornes):
                    for debut, fin in sorted(bornes, reverse=True):
                        resultat = resultat[:debut] + resultat[fin:]
                    exactes += 1
                    continue
            elif para:
                bornes = _bornes_paragraphe(resultat, para.group("num"))
                if bornes is not None:
                    resultat = resultat[:bornes[0]] + resultat[bornes[1]:]
                    exactes += 1
                    continue
            laissees.append(mod)
            continue

        if mod.operation == "remplacement" and mod.texte_nouveau:
            para = _PARAGRAPHE_VISE.search(instruction)
            point = _POINT_VISE.search(instruction)
            if para and not point:
                resultat, trouve = _remplacer_paragraphe(
                    resultat, para.group("num"), mod.texte_nouveau)
                if trouve:
                    exactes += 1
                    continue
            if point and not para:
                bornes = _bornes_point(resultat, point.group("ref"))
                if bornes is not None:
                    debut, fin = bornes
                    resultat = (resultat[:debut] + mod.texte_nouveau.strip()
                                + "\n" + resultat[fin:])
                    exactes += 1
                    continue
            laissees.append(mod)
            continue

        if mod.operation in ("ajout", "insertion") and mod.texte_nouveau:
            # Le texte inséré porte presque toujours son propre numéro —
            # « 2 bis. Les détenteurs… ». On le place à sa place quand ce
            # numéro se rattache à un paragraphe existant ; sinon on l'ajoute
            # à la fin, et on le dit : un paragraphe correct au mauvais
            # endroit se lit mal, mais silencieusement mal serait pire.
            resultat, place = _inserer_paragraphe(resultat, mod.texte_nouveau)
            exactes += 1
            if not place:
                approximatifs.append(mod)
            continue

        laissees.append(mod)

    # Identité et non égalité : deux instructions peuvent avoir exactement les
    # mêmes champs (« le paragraphe 2 est supprimé » revient dans plusieurs
    # articles) et `in` les confondrait.
    non_reportees = {id(m) for m in laissees}
    for mod in mods:
        mod.appliquee = id(mod) not in non_reportees

    note_place = ""
    if approximatifs:
        numeros = ", ".join(m.numero for m in approximatifs if m.numero)
        note_place = (
            f" {len(approximatifs)} texte(s) inséré(s)"
            + (f" (instruction(s) {numeros}" if numeros else "")
            + " figurent en fin d'article : leur contenu est exact, leur "
            "emplacement exact dans l'article reste à vérifier.")

    if not mods:
        return texte, "inchange", ""
    if not laissees:
        return resultat, ("approchee" if approximatifs else "exacte"), note_place
    if exactes:
        numeros = ", ".join(m.numero for m in laissees if m.numero)
        return resultat, "approchee", (
            f"{len(laissees)} modification(s) sur {len(mods)} ne sont pas "
            "reportées dans le texte ci-dessous"
            + (f" (instruction(s) {numeros}" if numeros else "")
            + " : elles visent une phrase ou un membre de phrase que le "
            "programme ne sait pas localiser sans risque de contresens. Le "
            "texte affiché est donc incomplet de ces changements-là ; leur "
            "libellé exact figure dans « Ce que dit l'omnibus »." + note_place)
    return texte, "non_appliquee", (
        "L'instruction vise une partie de l'article que le programme ne sait "
        "pas localiser sans risque de contresens. Le texte affiché est donc "
        "celui d'avant, et la modification est donnée à côté, verbatim.")


# ---------------------------------------------------------------------------
# Deux versions d'un même acte modificatif
# ---------------------------------------------------------------------------
#
# Un compromis de présidence sur un omnibus ressemble à l'omnibus, avec des
# passages changés — et il ne dit pas lesquels. Comparer les deux textes mot à
# mot noierait le lecteur : l'article premier d'un omnibus fait trente mille
# caractères. On compare donc **instruction par instruction**, regroupées par
# article visé : la question posée en négociation n'est pas « qu'est-ce qui a
# bougé dans le texte » mais « sur quels articles du Data Act la présidence
# a-t-elle changé ce que la Commission proposait ».

@dataclass
class EcartModification:
    acte_cible: str
    article: str
    statut: str                # identique | modifiee | ajoutee | retiree
    similarite: float = 1.0
    avant: str = ""
    apres: str = ""
    mods_avant: list[Modification] = field(default_factory=list)
    mods_apres: list[Modification] = field(default_factory=list)


def _texte_des_mods(mods: list[Modification]) -> str:
    return "\n".join(
        f"{m.instruction} {m.texte_nouveau}".strip()
        for m in sorted(mods, key=lambda x: x.numero))


def comparer(avant: ResultatModificatif, apres: ResultatModificatif,
             seuil: float = 0.995) -> list[EcartModification]:
    """Ce que la seconde version change à la première, article visé par article."""
    import difflib

    def indexer(res: ResultatModificatif) -> dict:
        table: dict[tuple[str, str], list[Modification]] = {}
        for bloc in res.blocs:
            for mod in bloc.modifications:
                table.setdefault(
                    (bloc.acte_cible, mod.article_cible or "— non rattaché —"),
                    []).append(mod)
        return table

    gauche, droite = indexer(avant), indexer(apres)
    ecarts: list[EcartModification] = []
    for cle in sorted(set(gauche) | set(droite)):
        acte, article = cle
        a_mods, b_mods = gauche.get(cle, []), droite.get(cle, [])
        a_txt, b_txt = _texte_des_mods(a_mods), _texte_des_mods(b_mods)
        if not a_mods:
            statut, sim = "ajoutee", 0.0
        elif not b_mods:
            statut, sim = "retiree", 0.0
        else:
            sim = difflib.SequenceMatcher(
                None, a_txt.split(), b_txt.split()).ratio()
            statut = "identique" if sim >= seuil else "modifiee"
        ecarts.append(EcartModification(
            acte_cible=acte, article=article, statut=statut, similarite=sim,
            avant=a_txt, apres=b_txt, mods_avant=a_mods, mods_apres=b_mods))
    return ecarts


STATUT_ECART = {
    "identique": "Inchangée",
    "modifiee": "Modifiée par la nouvelle version",
    "ajoutee": "Nouvelle modification",
    "retiree": "Modification abandonnée",
}


# ---------------------------------------------------------------------------
# Caractérisation de la portée — la seule étape où un modèle intervient
# ---------------------------------------------------------------------------
#
# La leçon de la version 0.8 est ici. Le modèle y résumait des écarts calculés
# entre deux textes qui n'avaient rien à voir : les résumés étaient fluides,
# confiants et faux — « l'article 33 a été supprimé » quand il était seulement
# modifié. Ce n'était pas une défaillance du modèle mais du rapprochement
# qu'on lui soumettait.
#
# Ici, le rapprochement est établi par le texte lui-même : l'omnibus dit
# « l'article 33 est modifié comme suit ». Le modèle ne qualifie donc plus un
# appariement fabriqué, mais une modification que le législateur a écrite. Il
# ne décide pas non plus de l'opération — remplacement, suppression, ajout
# sont lus dans l'instruction. Il ne fait qu'une chose : dire en français ce
# que ça change, et si ça pèse.

QUALIF_MODIFICATIF = """Tu qualifies UNE modification apportée par un acte
modificatif européen (un « omnibus ») à un article d'un règlement existant.

On te donne l'instruction de modification telle qu'elle est écrite, le texte
nouveau lorsqu'il est cité, et, quand il est disponible, l'article dans sa
version actuelle.

Règles impératives :
1. Tu décris ce que la modification change, en français, en trois phrases au
   plus. Tu ne récris pas l'instruction : tu dis son effet juridique.
2. Tu ne qualifies QUE ce qui est écrit dans ce qu'on te donne. Tu n'ajoutes
   aucune connaissance extérieure sur le règlement concerné, et tu ne
   supposes rien de ce que l'omnibus ferait par ailleurs.
3. `impact` se qualifie STRICTEMENT ainsi. « majeur » : la modification
   **crée, supprime ou déplace** une obligation, un droit, un champ
   d'application, un seuil chiffré, une compétence, une sanction ou un délai
   — quelqu'un devra faire autrement qu'avant, ou n'aura plus le droit de
   faire ce qu'il faisait. « mineur » : elle précise, encadre ou complète une
   règle qui existait déjà, sans déplacer l'équilibre entre les parties.
   « redactionnel » : formulation, terminologie, renvoi, coordination avec un
   autre texte. « nul » : rien ne change en droit.
   Étalonnage : dans un acte modificatif ordinaire, la plupart des
   modifications sont mineures ou rédactionnelles, et une minorité seulement
   est majeure. Ne mets « majeur » que si tu peux nommer, dans
   `summary_fr`, ce qui change pour qui. Le fait qu'une disposition
   *mentionne* une obligation ou un délai ne suffit pas.
3 bis. Si la modification change une valeur chiffrée — un délai, un seuil, un
   montant, un nombre de jours —, `summary_fr` donne la valeur avant et la
   valeur après, dans cet ordre, et dit si elle augmente ou diminue. Vérifie
   le sens : passer de 72 à 96 heures allonge le délai, passer de 96 à 72 le
   raccourcit.
4. `change_type` reprend l'opération annoncée par l'instruction : ajout,
   suppression, reformulation.
5. Si l'instruction ne permet pas de dire l'effet, parce qu'elle vise un
   point que tu ne vois pas), tu le dis dans `summary_fr` plutôt que de
   deviner."""


def qualifier(article: ArticleReconstitue, acte_cible: str = "") -> ArticleReconstitue:
    """Fait dire au modèle ce que la modification change, et si elle pèse.

    Sans modèle disponible, l'article est renvoyé tel quel : les instructions
    verbatim restent affichées, elles se lisent sans aide.
    """
    from .llm import LLMInvalidOutput, LLMUnavailable, get_client
    from .schemas import DeltaAnalysis

    if not article.modifications:
        article.impact, article.resume = "nul", "Article non modifié."
        return article

    client = get_client()
    if not client.available:
        return article

    instructions = "\n".join(
        f"- [{m.libelle_operation}] {m.instruction}"
        + (f"\n  Texte nouveau : « {m.texte_nouveau[:1200]} »"
           if m.texte_nouveau else "")
        for m in article.modifications[:8])

    user = (
        f"Texte modifié : {acte_cible or 'règlement européen'}\n"
        f"Article visé : {article.article}\n\n"
        f"INSTRUCTIONS DE L'OMNIBUS :\n{instructions[:6000]}\n\n"
        + (f"ARTICLE DANS SA VERSION ACTUELLE :\n"
           f"\"\"\"{article.texte_avant[:3500]}\"\"\"\n\n"
           if article.texte_avant else
           "L'article dans sa version actuelle n'est pas disponible.\n\n")
        + "Qualifie la portée de cette modification.")

    try:
        out = client.structured(DeltaAnalysis, QUALIF_MODIFICATIF, user,
                                max_tokens=700)
    except (LLMUnavailable, LLMInvalidOutput):
        return article

    article.resume = out.summary_fr
    # « nul » est réservé, dans cet écran, aux articles que l'acte ne touche
    # pas. Sur un article effectivement modifié, la même étiquette voulait
    # dire deux choses différentes à deux lignes d'écart : « rien à voir ici »
    # et « le modèle juge que rien ne change en droit ». La seconde se dit
    # « rédactionnel », qui est la case prévue pour cela.
    article.impact = "redactionnel" if out.impact == "nul" else out.impact
    article.concepts = list(out.affected_concepts)
    return article


IMPACT_ORDRE = {"majeur": 0, "mineur": 1, "redactionnel": 2, "nul": 3, "": 4}


# ---------------------------------------------------------------------------
# Synthèse d'un omnibus : la lecture transversale
# ---------------------------------------------------------------------------
#
# L'écran texte par texte répond à « qu'est-ce que cet omnibus fait au RGPD ».
# Il ne répond pas aux questions que se pose l'agent qui reçoit le dossier :
# par où commencer, quels bureaux consulter, qu'est-ce qui pèse. Un omnibus
# qui modifie dix textes se lit d'abord de haut : combien d'articles touchés
# où, de quelle portée, autour de quelles notions. Ces fonctions produisent
# cette lecture, une fois, pour l'écran comme pour la note Word, de sorte que
# les deux ne puissent pas se contredire.

@dataclass
class LigneSynthese:
    """Un article d'un texte cible, et tout ce que l'omnibus lui fait."""

    acte_cible: str
    nom_cible: str
    celex: str
    article_omnibus: str
    article: str
    section_id: str
    operations: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    # Le texte cité entre guillemets par chaque instruction, dans le même
    # ordre : « les points suivants sont ajoutés: » ne veut rien dire sans lui.
    textes_nouveaux: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    nb_modifications: int = 0
    impact: str = ""
    resume: str = ""
    concepts: list[str] = field(default_factory=list)

    @property
    def libelle_cible(self) -> str:
        return (f"{self.nom_cible} · {self.acte_cible}" if self.nom_cible
                else self.acte_cible)

    @property
    def page_min(self) -> int:
        return min(self.pages) if self.pages else 0


@dataclass
class SyntheseOmnibus:
    lignes: list[LigneSynthese] = field(default_factory=list)
    par_texte: dict[str, list[LigneSynthese]] = field(default_factory=dict)
    par_operation: dict[str, int] = field(default_factory=dict)
    par_impact: dict[str, int] = field(default_factory=dict)
    notions: list[tuple[str, list[LigneSynthese]]] = field(default_factory=list)

    @property
    def nb_textes(self) -> int:
        return len(self.par_texte)

    @property
    def nb_articles(self) -> int:
        return len(self.lignes)

    @property
    def nb_instructions(self) -> int:
        return sum(l.nb_modifications for l in self.lignes)

    @property
    def caracterises(self) -> int:
        return sum(1 for l in self.lignes if l.impact)

    @property
    def points_durs(self) -> list[LigneSynthese]:
        """Les articles de portée majeure, dans l'ordre des textes."""
        return [l for l in self.lignes if l.impact == "majeur"]


def _rang_article(section_id: str) -> tuple:
    chiffres = "".join(c for c in section_id if c.isdigit())
    lettres = "".join(c for c in section_id.split("_")[-1] if c.isalpha())
    return (int(chiffres) if chiffres else 9999, lettres)


def synthese(resultat: ResultatModificatif,
             caracterisation: dict | None = None) -> SyntheseOmnibus:
    """La lecture transversale d'un acte modificatif.

    `caracterisation` associe `(acte_cible, article)` au triplet
    `(resume, impact, concepts)` produit par le modèle. Il est facultatif :
    sans lui la synthèse existe quand même, elle dit ce que l'omnibus fait
    sans dire ce que cela pèse.
    """
    caracterisation = caracterisation or {}
    out = SyntheseOmnibus()

    for bloc in resultat.blocs:
        lignes_bloc: list[LigneSynthese] = []
        for article, mods in par_article(bloc).items():
            if not article or article.startswith("—"):
                continue
            resume_txt, impact, concepts = "", "", []
            trouve = caracterisation.get((bloc.acte_cible, article))
            if trouve:
                resume_txt, impact = trouve[0], trouve[1]
                concepts = list(trouve[2]) if len(trouve) > 2 and trouve[2] else []
            ligne = LigneSynthese(
                acte_cible=bloc.acte_cible, nom_cible=bloc.nom_cible,
                celex=bloc.celex, article_omnibus=bloc.article_omnibus,
                article=article, section_id=mods[0].section_id,
                operations=list(dict.fromkeys(m.libelle_operation for m in mods)),
                instructions=[m.instruction for m in mods],
                textes_nouveaux=[m.texte_nouveau for m in mods],
                pages=[m.page for m in mods if m.page],
                nb_modifications=len(mods),
                impact=impact, resume=resume_txt, concepts=concepts)
            lignes_bloc.append(ligne)
            for m in mods:
                out.par_operation[m.libelle_operation] = \
                    out.par_operation.get(m.libelle_operation, 0) + 1
            if impact:
                out.par_impact[impact] = out.par_impact.get(impact, 0) + 1

        lignes_bloc.sort(key=lambda l: _rang_article(l.section_id))
        if lignes_bloc:
            out.par_texte[bloc.acte_cible] = lignes_bloc
            out.lignes.extend(lignes_bloc)

    # Les notions qui reviennent d'un texte à l'autre : c'est la lecture
    # horizontale d'un omnibus, celle qui dit « les délais de notification
    # sont revus dans quatre règlements à la fois ».
    index: dict[str, list[LigneSynthese]] = {}
    for ligne in out.lignes:
        for notion in ligne.concepts:
            index.setdefault(notion.strip().lower(), []).append(ligne)
    out.notions = sorted(
        ((n, v) for n, v in index.items() if len(v) > 1),
        key=lambda kv: (-len(kv[1]), kv[0]))
    return out
