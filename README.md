# GATE CSE PYQ — Offline Extraction & Practice Platform

Extracts GATE CSE previous-year questions from the GATE Overflow PDF books into
canonical question images + structured metadata, and serves them through a
fully offline, GATE-style practice application.

**No internet is needed at runtime.** No external AI service, image URL, CDN,
hosted database or analytics ever touches the app. All question content is
local PNG images extracted from the source PDFs.

```
PDF → section detection → question boundaries → metadata → image crop
    → answer-key association → validation → dataset → sync → offline frontend
```

## Repository layout

```
volume2.pdf                  source book (place here; not committed)
config.py                    all pipeline configuration (incl. EXTRACTION_VERSION)
models.py                    Question / QuestionBoundary dataclasses
pdf_locator.py               finds subject section headings in the PDF
question_detector.py         question boundary detection (headings, options, tags)
metadata_parser.py           metadata + answer-key lookup; ID generation
image_cropper.py             boundary-based cropping, multi-page stitching
answer_key_reader.py         parses the dedicated "Answer Keys" pages (audited)
dataset_writer.py            safe incremental JSON/CSV/taxonomy writer (merge rules)
validator.py                 image + metadata + answer-status validation
utils.py                     helpers, deterministic question-ID generation
extractor.py                 main pipeline (single section, resumable)
pilot_extractor.py           cross-section validation pilot (10 subjects)
validate_pilot.py            pilot audit, contact sheets, validation report
scripts/sync_dataset.py      publishes an approved dataset into the frontend
tests/                       pytest suite (hermetic synthetic-PDF fixtures)
frontend/                    React + Vite + TypeScript offline app
DATASET_CONTRACT.md          the data interface between pipeline and UI
PROJECT_PROGRESS.md          stage log, defects, decisions, current state
output/
  data/                      main dataset (questions.json/csv, taxonomy.json)
  images/                    main dataset images
  reports/                   contact sheets, review_summary.csv
  validation_pilot/          isolated pilot: images/, data/, reports/
```

## 1. Environment setup

- Python 3.12+ with `pip install -r requirements.txt` (PyMuPDF, Pillow, pytest)
- Node 18+ for the frontend (`npm install` inside `frontend/`)
- Place `volume2.pdf` in the project root.

## 2. Extraction pipeline

```bash
# Baseline section extraction (resumable; re-runs skip up-to-date records)
python extractor.py

# Cross-section validation pilot (10 subjects, 82 questions, isolated output)
PYTHONUTF8=1 python pilot_extractor.py

# Pilot validation: audit CSV, contact sheets, JSON + Markdown report
PYTHONUTF8=1 python validate_pilot.py
```

Key safety properties:

- **Subjects come from the located PDF section heading**, never from config.
- **`EXTRACTION_VERSION`** (config.py): bump it to force regeneration of stale
  images/records; version mismatches are re-cropped, never silently reused.
- **IDs are deterministic** (`gate-cse-1999-q1.25`); internal punctuation is
  normalized (`01,viii` → `q01-viii`), trailing punctuation stripped, and the
  raw number is preserved in `question_number_raw`.
- **Merging is safe**: appending a batch preserves unrelated records; same-ID
  records with conflicting identity fields are reported, never silently merged.
- **Answer statuses are strict**: `verified` (answer-key table + evidence),
  `needs_review` (unresolved mapping — never presented as an answer),
  `not_available` (explicit source `N/A` only; a parser failure can never
  produce this state).

## 3. Validation gate (before trusting any dataset)

`validate_pilot.py` exits non-zero on hard errors and writes
`output/validation_pilot/reports/validation_report.{json,md}` covering:
image existence/dimensions, MCQ option preservation, metadata completeness,
answer-key cross-checks, JSON↔CSV consistency, index-integrity audit
(duplicate/conflicting answer-key entries are listed in
`data/answer_key_index_audit.json`).

Current status (see PROJECT_PROGRESS.md for numbers): all six acceptance
criteria pass on the 82-question pilot; the two short-height images were
source-verified as genuinely short questions.

**Contact sheets are for human review.** Automated checks cannot prove that a
crop is visually complete — review
`output/validation_pilot/reports/contact_sheet_*.png` against the PDF before
promoting a dataset.

## 4. Publishing a dataset to the frontend

```bash
python scripts/sync_dataset.py                                # pilot (default)
python scripts/sync_dataset.py --source output/data/questions.json
```

The script validates every record, copies images into `frontend/public/images/`,
and writes two manifests into `frontend/public/data/`:

- `questions.json` — display data only (**no answers**)
- `answers.json` — grading data, fetched by the UI **only at submission time**

It verifies every manifest image path and exits non-zero if any record was
skipped (override with `--allow-skips`).

## 5. Running the offline frontend

```bash
cd frontend
npm install          # first time only
python ../scripts/sync_dataset.py   # put a dataset in place first
npm run dev          # development server (http://localhost:5173)
# — or —
npm run build        # production build into frontend/dist (fully offline)
npm run preview      # serve the built app locally
```

The built `frontend/dist` + `frontend/public` work from any static file
server with zero network access. The dashboard shows which dataset is loaded
(the pilot subset is labelled as such — it is NOT the full book collection).

Practice modes: topic-wise, subtopic-wise (when the metadata provides
subtopics), subject-wise, year-wise (single year or range), and mixed — all
over the same normalized dataset API. The exam UI provides a GATE-style
palette (five states, shape+text distinctions), deadline-based timer with
auto-submit, Save & Next / Mark for Review & Next / Clear Response, bookmarks,
results with honest ungradable handling, and per-question review. Progress and
bookmarks persist in `localStorage` and survive dataset updates (stable IDs).

## 6. Testing

```bash
python -m pytest tests -q          # 74 extraction tests (synthetic PDFs + real anchors)
cd frontend && npm test            # 53 frontend tests (vitest + testing-library)
```

The extraction tests are hermetic (tiny generated PDFs); three integration
anchors additionally recheck the real answer-key mappings in `volume2.pdf`
(skipped automatically when the PDF is absent).

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Dataset failed to load` in the UI | Run `python scripts/sync_dataset.py`; the error panel lists the exact validation problems |
| Missing question image in the UI | The error state shows the question ID; re-run the sync script to restore `frontend/public/images/` |
| `NameError`/import errors in pipeline | `pip install -r requirements.txt`; run from the project root |
| Old images survive a cropper fix | Bump `EXTRACTION_VERSION` in config.py and re-run the extractor — stale records are re-cropped automatically |
| `validate_pilot.py` exit code 1 | Read `validation_report.md`; hard errors must be fixed or the records excluded before publishing |
| Answers visible in browser devtools | Expected: client-side keys cannot be secret. The UI never renders them before submission; do not publish `answers.json` on a shared host |

## 8. Known limitations

- The shipped dataset is the **82-question validation pilot**, not the full
  book; full extraction is gated on human review of contact sheets.
- 75 conflicting duplicate answer-key index entries and 27 malformed entries
  exist index-wide (documented in `answer_key_index_audit.json`); any record
  whose section number is affected must be manually checked before its answer
  is marked `verified`.
- Descriptive / fill-in-the-blank / match-the-following questions are never
  auto-graded; NAT answers use exact numeric comparison (no invented tolerance);
  MSQ uses exact set match (no partial credit without source rules).
- Detailed solutions are not present in the source books and are never
  fabricated by the app.
