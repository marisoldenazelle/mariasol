# Method

What this tool measures, how, and why each choice was made rather than the
obvious alternative. It is written for someone deciding whether to trust a
number the interface displays.

---

## 1. The problem

A European regulation under negotiation in the Council generates a particular
document: the *consolidated comments table*. Delegations submit written comments
and drafting suggestions, the presidency compiles them article by article, and
the result circulates as a working document of several hundred pages — one row
per delegation per article, in prose, in English, with no structure a machine can
read directly.

An analyst reading that document is trying to answer four questions:

1. Who shares our position on this article, and who does not?
2. Which blocs are forming, including blocs that do not include us?
3. Does the group we are assembling reach a qualified majority, or does the group
   against us reach a blocking minority?
4. What exactly changed between this compromise text and the previous one?

Today each of these is answered by hand, in a spreadsheet, over several days. The
answer is obsolete when the next compromise circulates. That is the gap this
tool addresses.

Quantitative research on Council decision-making faces the same bottleneck from
the other direction: the established datasets build member state positions
through expert interviews and manual coding, which is accurate, slow and
retrospective. The data this tool produces — a position per state, per article,
with the passage it rests on — is the same kind of object, derived from primary
documents, during the negotiation rather than after it.

---

## 2. The unit of analysis

Everything is organised around the **(article, member state)** pair.

Documents are segmented at import into sections: explanatory memorandum,
recitals, articles, annexes. Long articles are subdivided, then re-joined before
comparison — a subdivided article compared fragment by fragment produces the
worst possible output, an article merely lengthened between two versions
appearing as "deleted plus two additions".

Each contribution carries the section it targets, the delegation that wrote it,
and whether it is a general comment or a drafting proposal. That distinction
matters: a drafting proposal is a position with a text attached, a comment is a
position without one.

---

## 3. Classification, and the reference frame problem

Each contribution is classified as **aligned**, **partially aligned** or
**divergent**. The question is: aligned with *what*?

Two reference frames are offered, and they answer different questions.

**Against the national position.** "Who is with us." This is the frame for
building a coalition.

**Against the initial text.** "Who wants to change it" — ourselves included. This
is the frame for reading pressure on the text, independently of our own view.

On an article the delegation did not amend, the two coincide, and this is where
a domain rule had to be made explicit and implemented:

> **Not amending counts as acceptance.** On an article where the delegation
> tabled neither an amendment nor a comment, the reference is maintenance of the
> initial text as it stands. A state demanding its deletion or rewriting diverges
> from that reference; a state accepting it aligns.

This is a tacit convention of negotiation practice. Leaving it implicit would
have meant treating two thirds of the articles of a typical file as having no
reference at all, and therefore no classification. Stating it, implementing it,
and labelling every cell derived from it as "silence rule" on screen makes it
contestable — which is the only form in which a tacit rule belongs in an
instrument.

A classification is never final. The analyst can overrule the reference position
for an article, which reclassifies every contribution on it.

### One model call per contribution

Never a batch. A model given fifteen contributions at once answers on the first
and forgets the rest; the failure is silent and looks like a result. One call per
contribution makes that failure mode impossible, at the cost of time — roughly
three seconds per contribution, stated on screen before the run starts, with
partial results persisted as they arrive so an interruption loses nothing.

### The offline path

Without a model, a lexical classifier recognises the standard formulas of working
party comments — *we do not support*, *should be deleted*, *scrutiny
reservation*. It misses an opposition expressed without a marker, and every cell
it produces is labelled as heuristically derived. It exists so that the tool is
usable where no model is available, and so that this repository can be run by
anyone.

---

## 4. The grounding guarantee

This is the central claim, and the one worth attacking first.

Every assertion a model produces must carry a quotation from the source. The
program then searches for that quotation *verbatim* in the document — normalising
whitespace and apostrophes, requiring a minimum length so that a four-word
fragment cannot match by accident. If the quotation is not found, the assertion
is **removed**. It is not shown with a warning; it is not shown.

Two consequences, both deliberate:

**Precision is bought with recall.** A true assertion whose quotation the model
paraphrased instead of copying is destroyed along with the false ones. The number
of discarded assertions is displayed next to every answer, which turns the
trade-off into a readable signal rather than a hidden loss: a high count means
the model is extrapolating on that question, and the question should be
reformulated or the corpus checked.

**It is a program-level guarantee, not a prompt-level one.** The verification is
ordinary string search in `core/qa.py`, tested automatically on every version.
Nothing depends on the model complying with an instruction.

What this does *not* claim: that hallucination is impossible. A model can produce
a wrong statement supported by a real quotation taken out of context. The
guarantee is narrower and checkable — no assertion survives without a locatable
textual basis — and it is the strongest claim the architecture actually supports.

---

## 5. Coalition arithmetic

Entirely deterministic, and this is where the tool is a measuring instrument
rather than an assistant.

**Pairwise agreement** between two states is computed over the articles both have
expressed a position on. Cells where a state has said nothing are never filled
with zero: silence is not agreement, and the distinction between "opposed" and
"absent" is preserved throughout. A pair sharing fewer than three articles is
flagged — two coincidences are enough to display 100 %.

**Blocs** are detected on the agreement graph above a threshold the analyst sets,
rather than by an opaque community-detection optimum. Finer partitions were
possible; a bloc nobody can justify is not usable in a briefing.

**Council arithmetic.** Qualified majority requires 15 of 27 states representing
at least 65 % of the Union population; a blocking minority requires at least 4
states representing more than 35 %. Population figures serve this calculation and
nothing else.

The caveat is stated wherever the number appears: written positions in a working
party are not votes. The arithmetic says what a given distribution *would* give
if it transposed into a vote, which never happens as such. The figures are for
prioritising whom to approach, not for announcing an outcome.

---

## 6. Amending acts

An omnibus does not rewrite the regulation it amends. It states what to change in
it:

> *In Article 5 of Regulation (EU) 2023/2854, paragraph 2 is replaced by the
> following: «…»*

Its own Article 1 corresponds to nothing in the target regulation. Comparing the
two article by article — which is what a generic version-comparison tool does —
pairs Article 1 of one with Article 1 of the other and produces an output that
looks like a comparison and is not one. This was the single largest correctness
failure the project had, and the module exists to fix it.

The reader is entirely deterministic — regular expressions and segmentation, no
model. It targets the drafting conventions of Union legislation, stable for
decades: the enacting-terms marker, the per-target article heading, the chapeau
*"is amended as follows"*, numbered instructions and lettered sub-instructions,
quoted new text in guillemets, Latin ordinals up to *novovicies*. Numbered items
are read *outside quotation marks only*, by tracking quote depth, because quoted
new text contains numbered paragraphs that look exactly like instructions.

### Reconstruction, and its three declared fidelity levels

When the consolidated target text is loaded, each affected article is rebuilt
before and after, and the result is labelled:

- **exact** — every instruction was applied;
- **partial** — some were;
- **not applied** — none were, and the text shown is the one before.

An instruction targeting a clause or a phrase inside an article — *"the words
'within a reasonable period' are deleted"* — is **not applied**, because locating
it mechanically risks contresens. Each instruction is marked on screen as
*carried into the text below* or *not carried into the text below*. A
reconstruction presented as the law in force while being approximate would be
worse than no reconstruction at all.

### Comparing two versions of the same omnibus

A presidency compromise on an omnibus resembles the Commission proposal with
passages changed, and does not say which. Comparing the two texts word by word
would drown the reader — the first article of an omnibus runs to thirty thousand
characters. The comparison is therefore made **instruction by instruction**,
grouped by target article, because the negotiation question is not "what moved in
the text" but "on which articles of the Data Act did the presidency change what
the Commission proposed".

---

## 7. What is explicitly not claimed

- **Legal correctness of a classification.** The model qualifies a convergence;
  it does not state the law.
- **Exhaustiveness of extraction.** Segmenting a badly structured PDF can lose
  contributions. Counts are displayed at import for exactly this reason.
- **Significance ratings as a ranking.** See
  [EVALUATION.md](EVALUATION.md) — on one real act the model rated 30 of 36
  articles "major", and a ranking that keeps everything ranks nothing.
- **Any predictive validity.** None is measured, and none is claimed.
