# Architecture

What each file does, and why it exists. Written for someone who has to take this
over, audit it, or host it. It does not replace the code: every module carries an
explanation of its own choices at the top, and that is where the detail is.

---

## The separation that organises everything

```
app.py, accueil.py   Streamlit entry point, navigation, sidebar
pages/               one file per screen — no calculation, only display
core/                all logic — no module here imports Streamlit
data/                corpus, SQLite database, exports — never committed
assets/              logo and variants
examples/            synthetic corpus generator
evaluation/          agreement study against a hand-coded matrix
tests/               117 automated tests
docs/                this documentation; docs/fr/ holds the original French set
```

**No module in `core/` imports Streamlit.** That is what makes every calculation
testable without an interface, and what would allow the same logic to be served
some other way without rewriting any of it. It is also what makes the test suite
meaningful: the tests exercise the rules, not the widgets.

The pipeline, end to end:

```
PDF / DOCX
   ↓ ingest.py            read, detect type, segment
   ↓ wk_parser.py         (comments table) one contribution per member state
   ↓ store.py             SQLite + FTS5 full-text index
   ↓ scoring.py           classify each contribution
   ↓ coalition.py         who agrees with whom, Council arithmetic
   ↓ report.py / excel.py Word note, workbook, figures
```

---

## `core/` — infrastructure

| File | What it does |
|---|---|
| `config.py` | All configuration, driven by `REGWATCH_*` and `ALBERT_*` environment variables. Holds the version string shown on screen, the demonstration lock on the API key, and `chemin_affiche()`, which never displays an absolute path — the tool runs on machines whose directory layouts differ, and an absolute path leaks the session name of whoever prepared the copy. |
| `store.py` | Persistence: documents, segments, contributions, analyses, reference positions, audit log. Schema migrations (`PRAGMA user_version`), hot backup and restore, index integrity check and repair. The only module that writes to disk. |
| `llm.py` | The model client, under constraint. Imposes an output schema, retries, and converts every network failure into a typed error the screens know how to display. Three providers: a state-operated endpoint (default), any OpenAI-compatible endpoint, and an offline mode that calls nothing. |
| `schemas.py` | The output contracts imposed on the model, in Pydantic. A model answering outside the schema is rejected, not patched up. |
| `palette.py` | The two colour conventions — accessible (blue/red, legible with colour vision deficiency) and the directorate's own red/amber/green — in one place, so that screen, PNG, Word and Excel cannot disagree. |
| `duree.py` | Estimating and displaying the duration of a long operation. Analysing 700 contributions takes half an hour; saying so before starting is a feature. |

## `core/` — reading documents

| File | What it does |
|---|---|
| `ingest.py` | Universal ingestion. Reads PDF or DOCX, detects document type, segments into explanatory memorandum, recitals, articles and annexes, and subdivides long articles. Handles **amending acts** separately, segmenting them instruction by instruction rather than article by article. Strips the running footer of Union documents, which text extraction otherwise glues to the end of sentences. |
| `wk_parser.py` | Reads consolidated comments tables: one row per contribution, with the member state, the article targeted, and the distinction between a general comment and a drafting proposal. |
| `nonpaper.py` | Extracts positions from free-form documents — non-papers, white papers, meeting reports. Infers the author, and extracts a position only where there is one: a passage of courtesy or procedure yields none. |
| `eurlex.py` | Retrieves public texts from EUR-Lex **as HTML, not PDF**: the Official Journal PDF is a two-column layout whose extraction introduces discrepancies that would later be counted as amendments. Also holds the catalogue mapping CELEX identifiers to the names practitioners use. |
| `labels.py` | Readable labels. `Article 24 (2/12)` refers to nothing in the official text; this module replaces it with the first provision the fragment actually contains. |
| `titres.py` | Groups articles by title of the regulation, from headings read in the text or from bounds set by hand. |

## `core/` — analysis

| File | What it does |
|---|---|
| `retrieval.py` | SQLite **FTS5** full-text index, standalone table, BM25 ranking. Serves search and the selection of passages submitted to the model. |
| `qa.py` | Sourced answering: each assertion carries a quotation, and the quotation is verified verbatim against the source. Unverified assertions are removed, and their number reported. |
| `scoring.py` | The core of the mapping. Classifies each contribution — aligned, partially aligned, divergent — against a reference frame. Applies the **silence rule**: on an article the delegation did not amend, the reference is maintenance of the text as it stands. One model call per contribution, never a batch. |
| `coalition.py` | Pairwise agreement, bloc detection, and Council arithmetic: qualified majority (15 of 27 and 65 % of population), blocking minority (at least 4 states and more than 35 %). |
| `ponderation.py` | Weighting of a criterion written in plain language by the analyst, to re-rank member states by what matters in the file at hand. |
| `diff.py` | Comparison of two versions of the same text: article matching, similarity, and qualification of a difference's significance. Matching and measurement are deterministic; only the qualification calls a model. |
| `modificatif.py` | **The amending-act reader.** Parses modification instructions, groups them by target act then target article, reconstructs each article before and after when the consolidated text is loaded, produces the cross-cutting synthesis of the act, and compares two versions of the same omnibus instruction by instruction. Entirely deterministic apart from the significance rating. The largest module in the package, and the most heavily commented. |
| `amendements.py` | "Were our amendments taken up?" — tracking a list of amendments in a destination text, with a verdict per amendment and an explicit refusal to conclude where the evidence is missing. |
| `fiabilite.py` | What, in a displayed result, needs the analyst's eye: contributions classified without a model, quotations not found, articles documented by too few states, scrutiny reservations. These alerts live in a dedicated panel and **never enter a deliverable** — a note to management does not carry the tool's doubts; the analyst does. |
| `aide.py` | The application's knowledge base: thirty hand-written cards, each in two registers — the explanation, and the implementation detail (formulas, thresholds, libraries). The in-app assistant answers from these cards and nothing else. It knows neither European law nor the loaded documents, and says so. |

## `core/` — output

| File | What it does |
|---|---|
| `viz.py` | Interactive figures (Plotly): alignment matrix, ally ranking, contentious-article scatter, bloc graph, qualified-majority gauge. |
| `report.py` | Deliverables outside the screen: PNG figures (matplotlib rather than Plotly's image export, which requires a Chrome binary absent from an administration workstation), the mapping Word note, the company guidance sheet, and the amending-act synthesis note. Every table is a real Word table, editable, never a screenshot. |
| `excel.py` | The workbook, with charts bound to cells rather than pasted as images. Reproduces the exact hues of the active palette, so it can sit beside the hand-kept spreadsheet without the eye having to relearn the code. |
| `ui.py` | Shared interface elements: module header, "how this works" panel, reliability panel, coloured tracking table, and the map of an amending act. The only place in the application where display is hand-written in HTML, and the reason is given on site. |

---

## `pages/` — the screens

Each file is one screen. None contains a calculation: they call `core/`, display,
and return.

| Screen | What you do there |
|---|---|
| `0_Mode_d_emploi.py` | How to use the tool, plus an assistant answering from `aide.py`. |
| `1_Bibliotheque.py` | Load documents, fetch public texts from EUR-Lex, correct a type or a version marker. One unreadable file no longer fails the whole batch. |
| `2_Recherche.py` | A question, an answer whose every assertion cites a verbatim passage. Two modes: sourced answer, or raw extracts with no model call. |
| `3_Positions_Etats_membres.py` | The alignment matrix, the coloured tracking table, allies, contentious articles, contribution-level detail, non-paper input, Word and Excel exports. |
| `4_Coalitions.py` | Whom to approach, which blocs form without us, the pairwise detail, and Council arithmetic. |
| `5_Comparaison_de_versions.py` | A text through its versions, major changes ranked, word-level detail — and the **amending-act** tab, in three views. |
| `6_Suivi_des_amendements.py` | What became of our amendments. Refuses an amending act as a destination text rather than returning false verdicts. |
| `7_Regimes_d_acces.py` | A company situation described by a form, and what the loaded texts say about it, provision by provision. |
| `8_Administration.py` | Key and model, reference data, database state and repair, backup and restore, audit log. |

---

## Dependencies, and why each one

| Library | Role | Why it rather than another |
|---|---|---|
| `streamlit` | Interface | A web application with no server to administer and no JavaScript to maintain. |
| `pandas` | Tables | The exchange format between every module. |
| `pdfplumber` | PDF reading | Preserves line structure, which article segmentation needs. |
| `python-docx` | Word | Produces an **editable** document, on the machine, offline. |
| `openpyxl` | Excel | Writes charts bound to cells, not images. |
| `matplotlib` | PNG figures | Writes the file directly, without a browser. |
| `plotly` | On-screen figures | Interactive, and selectable, so a click on a chart navigates to an article. |
| `networkx` | Graphs | Bloc detection. |
| `pydantic` | Contracts | Imposes a verified output format on the model. |
| `openai` | HTTP client | The state-operated endpoint follows the same convention; no specific code is needed. |
| `sqlite3` | Database | Standard library. One file, no server. |

All are widely distributed free libraries, installable from an internal mirror.
No dependency on any online service other than the model endpoint.

---

## Things to know before touching it

**Never put `data/` in a synchronised folder.** Synchronising a SQLite file
while it is being written corrupts it. This is the only known way to lose data
with this tool.

**The environment variables are named `REGWATCH_*`.** The application's name
changed; the variables and the folder name did not, so that an existing
installation keeps working without anyone editing a configuration file.

**Demonstration mode locks the API key in `config.py`, not in the interface.** A
forgotten screen must not allow a key to be saved that would become active for
every user of a shared instance.

**A change in `core/` has to pass the tests.** `pytest -q`. The most important of
them is the grounding guard: it is the tool's principal promise.
