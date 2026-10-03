# Evaluation

What has been tested, what failed, and what is not measured yet.

This document exists because an instrument whose error modes are undocumented is
not an instrument. Everything below is either a check that runs automatically or
an observation made on a real document, with the date and the consequence.

---

## 1. What runs automatically

117 tests, on every commit. They protect the rules, not the interface.

| Suite | Tests | What it holds in place |
|---|---|---|
| `test_garde_fous.py` | 15 | The grounding guarantee. A verbatim quotation is accepted; a paraphrase is rejected; an invented quotation is rejected; a quotation shorter than the minimum length is rejected; a hallucinated assertion is removed from the answer rather than flagged. Also the silence rule: a deletion request is an opposition, a scrutiny reservation is an opposition, a drafting amendment is partial alignment. |
| `test_modificatif.py` | 32 | The amending-act reader: parsing of instructions, Latin ordinals, quote-depth tracking, reconstruction fidelity levels, cross-version instruction comparison, and one regression test per defect listed in §3. |
| `test_modules_v1.py` | 28 | Scoring, coalitions, Council arithmetic, reliability alerts. |
| `test_livrables.py` | 17 | Word note, Excel workbook, PNG figures — that they build, and that the colour palette is the same across all four outputs. |
| `test_reperes.py` | 15 | Version markers, reference frames, section ordering. |
| `test_base.py` | 6 | Persistence, index integrity, repair without data loss. |
| `test_ecran_omnibus.py` | 4 | The amending-act screen itself, rendered headless without a browser: counters, map, both exports, all three views. |

The last suite was added after a defect reached the user that unit tests could
not have caught — see §3.1.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

---

## 2. What has not been measured, and the script that would measure it

**Agreement with manual coding is not measured.** This is the most important gap
in this document.

The honest framing: the tool produces a position per member state per article;
the reference standard for that object is an analyst coding the same table by
hand. Until the two are compared on the same corpus, the classification accuracy
is unknown — the automated tests verify that the rules are applied as specified,
not that the specification produces correct answers.

`evaluation/compare_to_manual.py` implements the comparison. Given a hand-coded
matrix and the tool's output on the same consolidated comments table, it reports
overall agreement, agreement per class, Cohen's κ, and the confusion matrix, and
writes out the disagreeing cells for inspection. The study has not been run on a
public corpus because no hand-coded matrix over a public corpus exists; running
it requires a working-party table and the matrix an analyst built from it.

```bash
python evaluation/compare_to_manual.py --manual coded_by_hand.csv --doc-id <id>
```

What the result would need to say to be worth anything: the number of cells, the
κ, and above all the *shape* of the disagreements — whether the tool fails on
long contributions carrying several demands at once, on implicit oppositions, or
on scrutiny reservations. That analysis is the interesting output; the headline
percentage is not.

---

## 3. Defects found, and what each one changed

These are real failures observed on a real Commission proposal — the digital
omnibus, COM(2025) 837, which amends ten acts in 70 instructions. Each is listed
with its consequence, because the consequence is usually more informative than
the bug.

### 3.1 A silent truncation that looked like a result

The word-level before/after rendering stopped at 900 words. The first article of
the Data Act runs to several thousand, and the paragraphs the omnibus adds to it
come at the end. The rendering therefore displayed the whole article **with no
change marked at all**, on an article carrying six instructions.

This is the worst failure mode a tool of this kind can have: an empty result that
looks like a result. A reader concludes the article is untouched.

*Changed:* the amending-act view no longer caps the rendering; elsewhere the cap
rose to 4 000 words and **any truncation is now written on screen**. A "show only
changed passages" toggle elides long unchanged stretches, and the added/removed
word counts are displayed under every rendering, so that "nothing visible" and
"nothing changed" can be told apart. Four regression tests.

### 3.2 Deletions that were not carried into the text

*"Point (c) is deleted"*, *"paragraph 2 is deleted"* were parsed correctly but not
applied to the reconstructed article: the "after" text came out identical to the
"before", so nothing appeared struck through although the act deletes something.

*Changed:* points and paragraphs are now located and removed — on condition that
their marker is **unique within the article**, otherwise the instruction is left
aside rather than applied at a guess. Each instruction is now marked on screen as
carried or not carried into the rendering.

### 3.3 An inserted article attributed to an existing one

*"The following Article 18a is inserted"* was attributed to Article 18. The
numeral capture group absorbed the space that followed it, so the Latin ordinal
no longer found the whitespace it required.

The consequence is not cosmetic: an instruction *creating* an article was
reported as *modifying* a different, existing one.

*Found while building the synthetic fixture shipped in `examples/` — which is an
argument for shipping one.* Regression test covering `18 bis` and
`32 novovicies`.

### 3.4 An article losing one point reported as deleted

Article 64 of the GDPR, from which the omnibus removes a single point, was
labelled "Deleted". The article survives, and the screen said otherwise.

*Changed:* deletion is now recorded only where the instruction targets the whole
article.

### 3.5 Reference contributions counted as unanalysed

The reliability panel reported "70 contributions not analysed out of 725" on a
complete run. The 70 were the national delegation's own contributions, which
*are* the reference frame and are therefore never classified. The most alarming
figure on the screen was describing normal operation.

*Changed:* they leave the denominator, and the launch panel now shows the
arithmetic — 725 in the document, −70 reference, − already analysed = the number
to process.

### 3.6 A running footer entering the instruction text

The footer of a COM document (`FR FR` and the page number) was glued by text
extraction to the last sentence of each page — often an instruction. The screen
read *"in paragraph 2, the following points are added: FR FR 23"*.

*Changed:* the footer is stripped at read time, for every module at once.

---

## 4. Known limitations of the significance rating

The model is asked to rate each amendment as *major*, *minor* or *drafting*. Two
measured problems, neither fully solved.

**The rating does not discriminate.** On the digital omnibus, 30 of 36
characterised articles came back "major". A ranking that keeps five articles out
of six ranks nothing. The instruction was tightened — the amendment must
*create, remove or displace* an obligation, a right, a threshold, a competence or
a deadline, and the model must be able to name what changes for whom — which
brought the proportion to 20 of 30. Still 67 %. Two readings remain open: the act
genuinely is heavy throughout, or the model over-rates. **This is unresolved.**

The interface does not pretend otherwise: above 60 % of characterised articles
rated major, a warning says the rating is no longer discriminating and points the
reader back to the verbatim instructions.

**A numeric direction error.** On Article 33 of the GDPR, where the notification
deadline moves from 72 to 96 hours, the model summarised it as *"reduces the
notification deadline from 72 to 96 hours"*. The deadline is lengthened. The
instruction now requires the before and after values to be stated and the
direction checked, but this correction has not been evaluated at scale.

Both are arguments for the same thing: the verbatim instruction, with its page
number, is what is authoritative. The summary is an aid to triage, and the
interface says so.

---

## 5. Reliability signals in the interface

Distinct from testing: a set of checks runs on every result and surfaces what
needs the analyst's eye — contributions classified without a model, citations not
found, articles documented by fewer than three member states, state pairs sharing
too few articles for an agreement rate to mean anything, scrutiny reservations
recorded.

These alerts live in a dedicated panel and **never enter a deliverable**. A note
to management does not carry the tool's doubts; the analyst does.

---

## 6. Deployment acceptance

A ten-step acceptance protocol was run before handover
([docs/fr/TEST.md](fr/TEST.md), French). Steps 1 to 9 passed as specified on the
digital omnibus: 10 amended acts and 70 instructions read, the GDPR notification
deadline correctly shown moving from 72 to 96 hours with strikethrough,
Article 88 correctly shown as inserted, Article 64 correctly shown as modified
rather than deleted, and the amendment-tracking screen correctly refusing an
amending act as a target text rather than returning false verdicts.

The defects in §3 are the ones that protocol, and the review of its output,
surfaced.
