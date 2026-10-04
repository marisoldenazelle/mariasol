# mariasol

**A tool for European legislative negotiation. It reads the documents a Council
working party actually circulates and maps where the twenty-seven member states
stand on a draft regulation, article by article.**

[![tests](https://github.com/marisoldenazelle/mariasol/actions/workflows/ci.yml/badge.svg)](https://github.com/marisoldenazelle/mariasol/actions/workflows/ci.yml)
[![licence](https://img.shields.io/badge/licence-MIT-black)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-black)](requirements.txt)

In the Council of the European Union, a Commission proposal is negotiated
article by article in a working party of national delegations. Delegations send
written comments; the presidency's secretariat merges them into one document — a
consolidated comments table, circulated under a WK number — where each row is one
delegation's remark on one provision. A file of ordinary size produces several
hundred remarks, and five or six successive versions of them over a year.

Reading that table is the analytical core of the job. Who is with us, who is
against us, on which articles, and does the opposition weigh enough to block? It
is done by hand, by one analyst, in a spreadsheet, over several days per version.
By the time the map is finished the presidency has circulated a new compromise
text and the map is out of date.

mariasol builds that map from the primary documents, and makes every cell of it
contestable on the evidence. It was written inside a French ministry directorate
for its own negotiators, under constraints that are the interesting part of the
problem: the documents may not leave controlled infrastructure, the arithmetic
must be reproducible by hand, and nothing a language model asserts may stand
without a quotation that a program — not the model — has found in the source.

<sub>The interface is in French throughout: it was built for French civil
servants. Every screenshot below runs on the synthetic corpus shipped with this
repository — a fictional regulation, a fictional omnibus and 237 fictional
contributions from the 27 member states.</sub>

---

## The documents, and what reading them means

Everything the tool does follows from the shape of the material, so it is worth
being concrete about the material.

**The consolidated comments table.** A multi-page PDF table. The first column
carries the Commission's text with the article headings; the last column carries
the delegations' contributions, each introduced by a two-line country marker
(`FR` then `(Comments):` or `(Drafting suggestions):`). Later in a negotiation
the same document grows a third column for the presidency's compromise text,
which sits *between* the two. The parser therefore reads the first and last
columns and never the middle one — a three-column table parsed naively drops
every contribution, which is the kind of defect that is invisible until someone
counts. Extraction is pure pdfplumber and regular expressions, with no model
involved: structure must be reproducible and auditable before anything is
interpreted.

**Everything else.** A negotiation is not only its WK tables. The tool ingests
PDF and DOCX, detects what it is looking at, and segments accordingly:
Commission proposals, presidency compromise texts, Official Journal texts fetched
from EUR-Lex, internal working documents, and free-form material — non-papers,
white papers, meeting reports — from which positions are extracted with the
author inferred and nothing invented where a passage is mere courtesy or
procedure. Positions drawn from a non-paper enter the same matrix as positions
drawn from a WK table, so a delegation that has not written in the table but has
circulated a paper is not silently absent from the map.

**Amending acts are a different object.** An omnibus does not rewrite a
regulation; it states what to change in it: *"in Article 5 of Regulation (EU)
2023/2854, paragraph 2 is replaced by the following"*. Its own Article 1
corresponds to nothing in the text being amended, so comparing two documents
article by article produces nonsense. The tool parses the instructions instead,
groups them by target act and target article, reconstructs each article before
and after when the consolidated text is loaded, and compares two versions of the
same omnibus instruction by instruction.

**The silence rule.** On an article the French delegation did not amend, the
reference position is maintenance of the text as it stands. Not amending is a
position — it is agreement — and treating it as absence of data is the single
most consequential modelling choice in the tool. It is stated on screen wherever
it applies.

---

## What it produces

### Coalitions, and how they form

Pairwise agreement is computed between every pair of member states from their
article-level positions. A graph is built on those agreements, an edge drawn
above a threshold the analyst moves, and connected blocs are read off it with
their population weight. The threshold is a control, not a hyperparameter: moving
it is how you see which alliances are solid and which are artefacts of one
article.

![Bloc detection on the agreement graph at a 0.90 threshold: five blocs, each
with its member-state count and share of EU population](docs/img/coalitions.png)

Blocs are reported with their population share because in the Council that is
what decides anything. The eight states in grey agree with no one above the
threshold — which is itself a finding, and the sort of thing a spreadsheet does
not tell you.

### Contentious articles, and consensual ones

Each article is placed by the mean position of the member states who expressed
one and by the dispersion of those positions. The two axes separate two
situations a single ranking confuses: an article everyone dislikes in the same
way, and an article on which the room is split. The first is a lost cause or a
trade; the second is where a negotiation is actually conducted.

![Articles plotted by mean position and dispersion, with the ranked table
beneath](docs/img/contentious.png)

Low and to the left: broad, homogeneous opposition. High on the vertical axis:
the member states divide, and those are the articles worth spending capital on.
The table beneath ranks every article with the number of member states analysed
and the number of outright oppositions, so a point based on nine contributions is
not read like a point based on twenty-three.

### The tracking table

The same object the analyst keeps by hand: one row per article, the French
reference position in the first column, one column per member state, coloured by
compatibility with that reference.

![The tracking table: one row per article, one column per member state, each cell
carrying the summary of the contribution and the page it came from](docs/img/tracking.png)

Each cell carries the summary of the contribution and, in brackets, the provision
cited or the page it was found on. Where a state spoke more than twice on an
article the cell says how many remarks remain and they are all in the detail tab
and in the exported workbook. The colour follows the least favourable position
expressed, never an average. This is exactly the "Détail par article" sheet of
the exported Excel file, on screen and before exporting it.

### The alignment matrix

The same data as a heat map, with a choice of reference frame that changes what
the question means.

![The alignment matrix: 12 articles by the 26 other member states, read against
the French reference position](docs/img/positions.png)

*Against the national position* answers "who is with us". *Against the initial
text* answers "who wants to change this, ourselves included" — a different and
sometimes more useful map, because it shows the pressure on the text rather than
the pressure on us. On an article the delegation did not amend the two coincide,
by the silence rule. An empty cell means no contribution, and is not agreement.

### Council arithmetic

A group of member states, composed by hand or pre-filled from any article's
positions, and what that group would give if it voted: qualified majority
(55 % of member states — 15 of 27 — representing 65 % of the population) and
blocking minority (at least 4 states representing more than 35 %).

![Council arithmetic pre-filled from Article 11: qualified majority not reached,
opposition insufficient to block, and the pivot states whose accession would
change that](docs/img/arithmetic.png)

This is counterfactual arithmetic, not prediction. Written positions in a working
party are not votes and a working party does not vote; the tool says so on the
screen that performs the calculation. What it is for is the question a negotiator
actually asks — *is this enough, and if not, who is missing* — and the pivot
table answers the second half: which states, by population weight, would turn an
insufficient opposition into a blocking minority. Population figures live in a
versioned CSV and are meant to be replaced by those of the Council's rules of
procedure in force.

### Amending acts

Where an omnibus strikes: one row per amended act, one cell per affected article,
the exponent giving the number of instructions bearing on it.

![The amending-act map: three amended acts, nine affected articles, twelve
instructions, with the operation counts beneath](docs/img/overview.png)

The map is deterministic — it follows the operations written in the act, which
can be read without help. Only the rating of a change's significance calls a
model. Beneath it, what the act does by operation and what each amended text
takes, then every instruction with its page and its quoted new text, then a Word
synthesis note and an Excel workbook.

### And also

| | |
|---|---|
| **Sourced search** | A question in French, an answer in which every assertion cites a passage located verbatim in the corpus. |
| **Amendment tracking** | "Were our amendments taken up?" — a verdict per amendment in a destination text, with an explicit refusal to conclude where the evidence is missing. |
| **Weighting** | A criterion written in plain language by the analyst, used to re-rank member states by what matters in the file at hand. |
| **Deliverables** | Word note and Excel workbook, both editable, in the format the directorate already uses. Not screenshots — real tables, and charts bound to cells. |

More on each, and on why each is built the way it is, in
**[docs/METHOD.md](docs/METHOD.md)**.

---

## Three design commitments

These are the point of the project. Everything else follows from them.

### Computation is deterministic; the model only qualifies

Alignment matrices, pairwise agreement rates, coalition detection,
qualified-majority arithmetic, version diffs, amending-act parsing — all of it is
arithmetic and pattern analysis, reproducible by hand on any single case. The
language model never computes and never decides. It is asked one question only:
*given this passage and this reference position, what kind of divergence is
this?* An analyst who disagrees with an answer can open the contribution, read
the quotation the model relied on, and overrule it; overruling the French
reference position reclassifies the whole article.

This matters beyond engineering taste. A negotiator who cannot reconstruct why a
state appears in the "opposed" column will not use the number, and should not.

### Grounding is extractive, and enforced by the program

Every claim the model produces carries a quotation. The program then searches for
that quotation *verbatim* in the source document. Claims whose quotation cannot
be found are **discarded, not flagged** — the analyst never sees them.

The trade-off is explicit and instrumented: this buys precision with recall, and
the number of discarded claims is displayed on screen next to every answer. A
high count is not a bug report, it is a signal that the model is extrapolating on
that question. Nothing here makes hallucination impossible; what it does is make
unsupported assertions non-viable, and make the cost of that choice visible.

### Retrieval is lexical by necessity, not by default

The index is SQLite FTS5 with BM25 ranking — sparse retrieval, no embeddings.
That is a governance decision wearing technical clothes. Building a vector index
means sending an entire corpus of restricted negotiation documents to an
embedding endpoint, once. For documents circulated under distribution
restrictions, that single operation is the whole question.

Inference runs against a state-operated model endpoint hosted under national
security qualification, or against any OpenAI-compatible endpoint, or not at
all: in offline mode, import, indexing, full-text search, version comparison,
amending-act parsing and every coalition calculation remain fully functional. The
sovereignty constraint determined the architecture, rather than being bolted onto
it afterwards.

---

## Run it

No credentials, no restricted document, no network:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python examples/make_demo_corpus.py      # a fictional regulation, omnibus and comments table
streamlit run app.py
```

The development requirements are included because the demo corpus writer needs
them; `requirements.txt` alone is enough to run the application on real
documents.

The demo corpus is entirely synthetic — no real text, no real delegation, no real
position — but it is parsed by exactly the same code path as a real Commission
proposal, including the drafting conventions the amending-act reader targets. It
generates 237 contributions from the 27 member states across 12 articles, with
three camps built in so that blocs and contentious articles are there to be
found. Position classification runs in its offline lexical mode, so every
screenshot above reproduces without a model.

To use a model, copy `.env.example` to `.env` and set a key. See
[docs/fr/DEMARRAGE.md](docs/fr/DEMARRAGE.md) for the step-by-step install guide
(French).

---

## What it does not do

It does not state the law. It does not predict an outcome: written positions in a
working party are not votes, and Council arithmetic says what a distribution
*would* give if it transposed into a vote, which never happens as such.

It does not replace reading the documents — it says where to read, and quotes
what it relies on. A classification is meant to be contested: the contribution,
the retained quotation and the full text are two clicks away.

And the qualification of a change's significance is model-produced, therefore
contestable on the evidence. On one real amending act the model classified 30 of
36 articles as "major", which is a ranking that ranks nothing; the screen now
says so itself when that proportion exceeds 60 %. That episode, and the others,
are in **[docs/EVALUATION.md](docs/EVALUATION.md)**.

---

## Repository

```
app.py, accueil.py     entry point and navigation
core/                  all logic — no Streamlit import anywhere in this package
pages/                 one file per screen
examples/              synthetic corpus generator
evaluation/            agreement study against a hand-coded matrix
tests/                 117 tests
docs/                  method, evaluation, architecture
docs/fr/               original French documentation, including the delivered PDF dossier
CHANGELOG.md           development log (French) — every fix, and the reasoning behind it
```

The `core/` ↔ `pages/` separation is strict and deliberate: no module in `core/`
imports Streamlit. That is what makes every calculation testable without an
interface, and what would allow the same logic to be served some other way
without rewriting any of it.

**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** goes file by file.

---

## Provenance and status

Built in 2026 within the *Direction générale des entreprises* (French Ministry
for the Economy), for the directorate's own negotiators, and delivered with a
deployment dossier — the nine PDF guides in
[`docs/fr/pdf/`](docs/fr/pdf) are the documents actually handed over.

This repository contains the code and its documentation. It contains no Council
document, no internal data and no API key. The interface language is French
throughout, because that is who it was written for.

Licensed under the MIT Licence — see [LICENSE](LICENSE).
