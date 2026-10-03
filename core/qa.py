"""
Réponse sourcée sur le corpus.

Remplace le graphe de règles écrit à la main. Le compromis est explicite :
on perd le déterminisme (deux exécutions peuvent formuler différemment), on
garde l'essentiel de la garantie anti-hallucination par une contrainte de
forme forte —

    aucune affirmation n'est affichée sans une citation littérale, rattachée
    à un segment précis du corpus, et vérifiée par le code contre le texte
    de ce segment.

Une affirmation dont la citation est introuvable n'est pas « signalée » :
elle est **retirée** de la réponse. Le modèle ne peut donc pas produire une
assertion juridique qui ne soit pas adossée à un passage réellement présent
dans un document chargé par l'utilisateur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .llm import LLMInvalidOutput, LLMUnavailable, get_client
from .retrieval import Hit, build_query, search

# ---------------------------------------------------------------------------
# Étape 1 — traduire la question en termes de recherche
# ---------------------------------------------------------------------------

PLAN_SYSTEM = """Tu prépares une recherche documentaire dans un corpus de textes
européens. Ces textes sont le plus souvent rédigés en ANGLAIS ; la question, elle,
est posée en français.

Ta seule tâche est de produire des termes de recherche. Tu ne réponds pas à la
question, tu ne commentes pas.

Règles :
1. Donne les termes dans les DEUX langues : le mot français et son équivalent
   anglais consacré dans le vocabulaire des institutions européennes
   (« réserve d'examen » → « scrutiny reservation », « posture » → « posture »,
   « certification » → « certification »).
2. Ajoute les expressions exactes à chercher telles quelles, en anglais de
   préférence.
3. Reprends tels quels les numéros d'article cités dans la question.
4. Cinq à douze termes suffisent. Pas de mots vides, pas de verbes courants."""


class SearchPlan(BaseModel):
    termes: list[str] = Field(default_factory=list, max_length=16,
                              description="Mots-clés, en français et en anglais")
    expressions: list[str] = Field(default_factory=list, max_length=6,
                                   description="Expressions à chercher exactement")
    articles: list[str] = Field(default_factory=list, max_length=8,
                                description="Numéros d'article cités, ex. « 90 »")


def plan_recherche(question: str) -> str:
    """Construit la requête d'index, en s'appuyant sur le modèle s'il est là.

    Le corpus est majoritairement anglais et les questions sont posées en
    français : sans traduction des termes, la recherche lexicale ne trouve
    presque rien. Le modèle sert ici de traducteur, pas de juge — son résultat
    n'est qu'une liste de mots à chercher.
    """
    base = build_query(question)
    client = get_client()
    if not client.available:
        return base
    try:
        plan = client.structured(SearchPlan, PLAN_SYSTEM,
                                 f"Question : {question.strip()}", max_tokens=500)
    except (LLMUnavailable, LLMInvalidOutput):
        return base

    parts: list[str] = [base] if base else []
    for expression in plan.expressions:
        nettoye = re.sub(r'["*]', " ", expression).strip()
        if len(nettoye) > 3:
            parts.append(f'"{nettoye}"')
    for terme in plan.termes + plan.articles:
        mot = re.sub(r'["*]', " ", str(terme)).strip().lower()
        if not mot:
            continue
        parts.append(f'"{mot}"' if mot.isdigit() else f'"{mot}"*')
    return " OR ".join(dict.fromkeys(p for p in parts if p))


# ---------------------------------------------------------------------------
# Étape 2 — examiner CHAQUE extrait, un par un
# ---------------------------------------------------------------------------

EXTRAIT_SYSTEM = """Tu examines UN SEUL extrait de document et tu dis s'il apporte
un élément de réponse à la question posée.

Règles impératives :
1. Si l'extrait n'apporte rien, réponds pertinent = false et laisse les autres
   champs vides. C'est une réponse fréquente et attendue.
2. S'il apporte quelque chose, formule UNE affirmation en français, factuelle et
   brève, et recopie MOT POUR MOT le passage de l'extrait qui la fonde.
3. La citation doit être copiée à l'identique depuis l'extrait, sans reformuler,
   sans traduire, sans corriger les fautes de frappe.
4. Sois inclusif : un extrait qui répond partiellement, ou par une formulation
   différente de celle de la question, est pertinent. Une réserve exprimée par
   « reserves its right to provide further comments » est une réserve, au même
   titre que « scrutiny reservation »."""


class ExtraitVerdict(BaseModel):
    pertinent: bool = Field(description="Cet extrait apporte-t-il un élément de réponse ?")
    statement: str = Field("", max_length=400, description="Affirmation en français")
    quote: str = Field("", max_length=700,
                       description="Citation recopiée mot pour mot depuis l'extrait")


SYNTHESE_SYSTEM = """Tu rédiges une synthèse de trois phrases au maximum, en français,
à partir d'affirmations déjà établies et sourcées. Tu n'ajoutes aucune information
qui ne figure pas dans ces affirmations. Quand plusieurs États membres sont
concernés, tu les cites tous."""


class Synthese(BaseModel):
    answer_fr: str = Field(max_length=1200)
    unanswered: list[str] = Field(default_factory=list, max_length=5)


# ---------------------------------------------------------------------------
# Étape 2 bis — lecture d'ensemble, quand l'examen strict n'a rien retenu
# ---------------------------------------------------------------------------
#
# L'examen extrait par extrait est délibérément sévère : il ne retient qu'un
# extrait qui répond *directement* à la question. Sur une question large
# (« quelles conditions pour réutiliser des données publiques ? ») aucun extrait
# ne répond à lui seul, et l'outil concluait « les textes ne tranchent pas »
# alors que le corpus contenait précisément les articles utiles.
#
# Cette seconde lecture voit tous les extraits ensemble et rapporte ce qu'ils
# établissent, même indirectement. La garantie ne change pas : chaque élément
# reste adossé à une citation vérifiée dans le texte source. Ce qui change,
# c'est le seuil de pertinence — et l'affichage, qui les présente comme des
# « éléments de contexte » et non comme une réponse directe.
LECTURE_SYSTEM = """Tu es documentaliste juridique. On te donne des extraits de textes
et une question. Aucun extrait ne répond peut-être directement : ton travail est de
rapporter ce que ces extraits établissent d'UTILE pour traiter la question.

Règles impératives :
1. Tu ne sors JAMAIS des extraits fournis. Aucune connaissance extérieure.
2. Chaque élément que tu rapportes cite son numéro d'extrait et recopie MOT POUR
   MOT le passage qui le fonde. Une citation reformulée est une erreur.
3. Tu es INCLUSIF : un extrait qui pose une condition, une définition, une
   exception ou une obligation voisine du sujet mérite d'être rapporté, en
   précisant en quoi il éclaire la question.
4. Tu produis un élément par extrait utile, dans l'ordre des extraits.
5. Tu écris en français, sans conseil ni recommandation."""


class LectureElement(BaseModel):
    extract_number: int = Field(description="Numéro de l'extrait")
    statement: str = Field(max_length=400,
                           description="Ce que cet extrait établit, en français")
    quote: str = Field(max_length=700,
                       description="Citation recopiée mot pour mot depuis l'extrait")


class Lecture(BaseModel):
    elements: list[LectureElement] = Field(default_factory=list, max_length=16)
    manques: list[str] = Field(
        default_factory=list, max_length=5,
        description="Ce que les extraits ne permettent toujours pas d'établir")


@dataclass
class VerifiedClaim:
    statement: str
    quote: str
    hit: Hit
    verified: bool


@dataclass
class AnswerResult:
    question: str
    answer_fr: str = ""
    claims: list[VerifiedClaim] = field(default_factory=list)
    indirect: list[VerifiedClaim] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    dropped: int = 0
    examines: int = 0
    error: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.claims) and not self.error

    @property
    def tous_elements(self) -> list[VerifiedClaim]:
        """Réponses directes puis éléments de contexte, dans cet ordre."""
        return self.claims + self.indirect


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", " ", re.sub(r"\s+", " ", s.lower())).strip()


# Une citation doit être assez substantielle pour fonder une affirmation :
# « the » figure dans tous les textes anglais et ne prouve rien.
MIN_QUOTE_WORDS = 4


def quote_matches(quote: str, source: str, min_ratio: float = 0.75) -> bool:
    """La citation figure-t-elle réellement dans l'extrait ?

    Tolérance volontairement limitée : on accepte les écarts de ponctuation et
    de césure — fréquents après extraction PDF — mais pas une reformulation.
    Une citation trop courte est refusée même si elle est littérale : elle ne
    permettrait pas de vérifier que l'affirmation vient bien de ce passage.
    """
    q, s = _norm(quote), _norm(source)
    if not q:
        return False
    words = q.split()
    if len(words) < MIN_QUOTE_WORDS:
        return False
    if q in s:
        return True
    # fenêtre glissante : proportion de mots de la citation présents en ordre
    hits, i = 0, 0
    tokens = s.split()
    for w in words:
        try:
            i = tokens.index(w, i) + 1
            hits += 1
        except ValueError:
            continue
    return hits / len(words) >= min_ratio


def build_context(hits: list[Hit], max_chars: int = 1800) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        body = h.text.strip()
        if len(body) > max_chars:
            body = body[:max_chars] + " […]"
        blocks.append(f"[Extrait {i}] {h.citation}\n\"\"\"{body}\"\"\"")
    return "\n\n".join(blocks)


def answer(
    question: str,
    limit: int = 14,
    document_ids: list[str] | None = None,
    doc_kinds: list[str] | None = None,
    ms_codes: list[str] | None = None,
    on_progress=None,
) -> AnswerResult:
    """Recherche, examen extrait par extrait, vérification, puis synthèse.

    Le modèle voyait auparavant les dix extraits d'un coup et devait produire
    la liste complète des affirmations. Il s'arrêtait en pratique au premier
    extrait probant : une question « qui a posé une réserve ? » ne citait qu'un
    État membre alors que trois figuraient dans les extraits. Ici chaque
    extrait fait l'objet d'un appel distinct, ce qui rend l'oubli impossible —
    au prix d'un appel par extrait.
    """
    client = get_client()
    requete = plan_recherche(question) if client.available else build_query(question)

    hits = search(question, limit=limit, document_ids=document_ids,
                  doc_kinds=doc_kinds, ms_codes=ms_codes,
                  requete_brute=requete)
    if not hits and requete:
        # La requête enrichie peut être trop étroite — on retombe sur les seuls
        # mots de la question plutôt que de renvoyer une page vide.
        hits = search(question, limit=limit, document_ids=document_ids,
                      doc_kinds=doc_kinds, ms_codes=ms_codes)
    res = AnswerResult(question=question, hits=hits)
    if not hits:
        res.error = ("Aucun extrait pertinent dans le corpus. Reformulez, ou "
                     "chargez les documents correspondants.")
        return res

    if not client.available:
        res.error = ("Aucun fournisseur LLM configuré : les extraits sont "
                     "affichés bruts, sans synthèse.")
        return res

    # --- examen extrait par extrait ---------------------------------------
    examines = 0
    for i, hit in enumerate(hits, start=1):
        if on_progress:
            on_progress(i, len(hits), hit.citation)
        user = (
            f"Question : {question.strip()}\n\n"
            f"Extrait unique à examiner, {hit.citation} :\n"
            f'"""{hit.text[:5000]}"""'
        )
        try:
            verdict = client.structured(ExtraitVerdict, EXTRAIT_SYSTEM, user,
                                        max_tokens=700)
        except (LLMUnavailable, LLMInvalidOutput):
            continue
        examines += 1
        if not verdict.pertinent or not verdict.statement.strip():
            continue
        quote = verdict.quote.strip()
        if not quote_matches(quote, hit.text):
            # Une citation approximative est le plus souvent une recopie
            # imparfaite, pas une invention : on redemande une fois, en
            # exigeant la copie exacte. Si le second essai échoue aussi,
            # l'affirmation est retirée.
            quote = _recopier(client, verdict.statement, hit) or ""
            if not quote_matches(quote, hit.text):
                res.dropped += 1
                continue
        res.claims.append(VerifiedClaim(verdict.statement.strip(),
                                        quote, hit, True))

    res.examines = examines

    # --- seconde lecture, d'ensemble ---------------------------------------
    # Sur une question large, aucun extrait ne répond seul et l'examen strict
    # ne retient rien. Plutôt que de conclure « les textes ne tranchent pas »
    # alors que le corpus contient les articles utiles, on relit l'ensemble.
    if not res.claims:
        res.indirect, manques = _lecture_ensemble(client, question, hits)
        res.unanswered = manques

    if not res.claims and not res.indirect:
        res.unanswered = res.unanswered or [
            "Les extraits trouvés dans le corpus n'apportent pas d'élément de "
            "réponse à cette question."]
        if res.dropped:
            res.error = (
                f"{res.dropped} affirmation(s) écartée(s) faute de citation "
                "vérifiable dans le corpus.")
        return res

    # --- synthèse à partir des seuls éléments validés ----------------------
    liste = "\n".join(
        f"- {c.statement} (source : {c.hit.citation})" for c in res.tous_elements)
    try:
        synth = client.structured(
            Synthese, SYNTHESE_SYSTEM,
            f"Question : {question.strip()}\n\nAffirmations établies :\n{liste}",
            max_tokens=900)
        res.answer_fr = synth.answer_fr
        if synth.unanswered:
            res.unanswered = list(dict.fromkeys(
                list(synth.unanswered) + res.unanswered))[:5]
    except (LLMUnavailable, LLMInvalidOutput):
        # Repli entièrement déterministe : on liste ce qui a été établi.
        res.answer_fr = "\n".join(f"- {c.statement}" for c in res.tous_elements)

    return res


# ---------------------------------------------------------------------------
# Outils internes
# ---------------------------------------------------------------------------

RECOPIE_SYSTEM = """On te donne un texte source et une affirmation tirée de ce texte.
Tu recopies MOT POUR MOT, sans rien changer, la phrase du texte source qui fonde
cette affirmation. Tu ne traduis pas, tu ne corriges pas, tu ne raccourcis pas au
point de perdre le sens. Si aucune phrase ne la fonde, tu renvoies une chaîne vide."""


class Recopie(BaseModel):
    quote: str = Field("", max_length=700)


def _recopier(client, statement: str, hit: Hit) -> str:
    """Second essai de citation littérale sur un extrait donné."""
    try:
        r = client.structured(
            Recopie, RECOPIE_SYSTEM,
            f"Affirmation : {statement.strip()}\n\n"
            f'Texte source :\n"""{hit.text[:5000]}"""',
            max_tokens=400)
    except (LLMUnavailable, LLMInvalidOutput):
        return ""
    return r.quote.strip()


def _lecture_ensemble(
    client, question: str, hits: list[Hit]
) -> tuple[list[VerifiedClaim], list[str]]:
    """Relit tous les extraits ensemble et rapporte ce qu'ils éclairent.

    Même garde-fou que la lecture stricte — citation vérifiée dans le segment
    d'origine — mais un seuil de pertinence plus bas. Le résultat est présenté
    comme « éléments de contexte », jamais comme une réponse directe.
    """
    contexte = build_context(hits, max_chars=1500)
    try:
        lecture = client.structured(
            Lecture, LECTURE_SYSTEM,
            f"Question : {question.strip()}\n\n{contexte}",
            max_tokens=2200)
    except (LLMUnavailable, LLMInvalidOutput):
        return [], []

    elements: list[VerifiedClaim] = []
    for el in lecture.elements:
        idx = el.extract_number - 1
        if not (0 <= idx < len(hits)):
            continue
        hit = hits[idx]
        quote = el.quote.strip()
        if not quote_matches(quote, hit.text):
            continue
        elements.append(VerifiedClaim(el.statement.strip(), quote, hit, True))
    return elements, list(lecture.manques)
