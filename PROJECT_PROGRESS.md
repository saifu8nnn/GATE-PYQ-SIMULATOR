# PROJECT_PROGRESS — GATE CSE PYQ Extraction + Offline Exam Platform

Last updated: 2026-10-13 (Stages A–F complete: pipeline fixed+validated, dataset
contract, offline frontend built and tested, docs written)

---

## 1. Architecture map (as-is, confirmed by reading the code)

```
volume2.pdf (663 pages, GATE Overflow Vol. 2)
    │
    ├─ answer_key_reader.load_answer_key_table(doc)
    │      scans whole PDF for bold "Answer Keys" headers + 4 following pages
    │      → { "5.1.5": ParsedAnswer(raw, value, answer_type, source_page) }
    │      → 2,483 entries; pages ~85..660; Databases key page = 0-based 337 (1-based 338)
    │
    ├─ pdf_locator.find_section_start(doc, name)  → 0-based page of section heading
    │      find_section_end(doc, start)           → page of next different section heading
    │
    ├─ question_detector.detect_question_boundaries(doc, start, end, max)
    │      heading regex  "<Topic>: GATE CSE <Year> [Set N] | Question: <num>"
    │      left-margin bold section number (5.x.y) at same y-band → boundary.section_number
    │      tag-line ("gatecse-2020 ... 2-marks") → type/marks/difficulty
    │      closes boundary at next heading OR at "Answer key" line
    │      → QuestionBoundary list
    │
    ├─ metadata_parser.build_question(boundary, answer_key_table) → Question dataclass
    │      answer lookup: section_number → table → (value, verified|needs_review|not_available)
    │      inline answer fallback; ID via utils.make_question_id
    │
    ├─ image_cropper.crop_question(doc, boundary, path) → PNG (full-width strip,
    │      multi-page questions stitched vertically, RENDER_SCALE=2.5)
    │
    ├─ dataset_writer.write_all → output/data/{questions.json, questions.csv, taxonomy.json}
    ├─ validator.validate_questions → existence/dimension/blank/dup/year checks
    └─ extractor.run() → contact sheets + review_summary.csv + processing_report.json

Pilot (isolated, does not touch output/data):
    pilot_extractor.py → output/validation_pilot/{images,data}/   (8 q × 9 sections + 10 baseline)
    validate_pilot.py  → output/validation_pilot/{data,reports}/  audit CSV, contact sheets, report
```

Data schema: `models.Question` — identity (id, exam, year, set), taxonomy (subject, topic,
subtopic), question identity (question_number, question_number_raw, section_number,
question_type, marks, difficulty), options (options_present, option_labels_detected),
answer (correct_answer, answer_status ∈ {verified, needs_review, not_available},
answer_source, answer_evidence), image (relative path), provenance (source_pdf,
source_pages), quality (verified=false manual flag, notes).

## 2. Current outputs (measured, not assumed)

| Artifact | State (as of Stages A–F complete) |
|---|---|
| output/data/questions.json | 10 B-Tree Databases regression questions (1989–2002), extraction_version=2, images regenerated |
| output/validation_pilot/data/pilot_questions.json | 82 questions across 10 subjects, all v2, images present (82/82) |
| answer key index | 2,483 entries: 1700 MCQ, 314 N/A, 269 NAT, 98 MSQ, 41 RANGE, 40 UNKNOWN, 21 BOOL; audit: 75 conflicting dup keys, 27 malformed |
| validation_report.json | 0 hard errors; 56 verified answer matches, 25 confirmed N/A, 0 mismatches, 1 needs_review |
| tests | 74 pytest (tests/) + 53 vitest (frontend/) — all passing |
| frontend | React+Vite+TS offline app in frontend/; build + preview verified |
| README / requirements | present |
| git repo | not initialised (not requested) |

## 3. Confirmed defects (with evidence)

- **D1 (critical) — pipeline is currently broken.** `metadata_parser.py:285` references bare
  `SECTION_NAME` which is *not imported* (module only does `import config as _config`).
  Reproduced: `parse_metadata(...)` → `NameError: name 'SECTION_NAME' is not defined`.
  File mtime (21:01) is *after* the pilot run (20:45), so a later edit introduced this.
  Any rerun of `extractor.py` or `pilot_extractor.py` fails at `build_question`.

- **D2 (critical) — subject misclassification (Phase 2.1 violation).** All 82 pilot records
  have `subject = "Databases"` although they were extracted from 10 different sections
  (verified: `subject_coverage = {'Databases': 82}`). Cause: subject comes from
  `config.SECTION_NAME`, not from the PDF section actually located. The pilot's
  monkey-patch of `config.SECTION_NAME` cannot work when the name was bound at import.

- **D3 — stale-image reuse (known risk A).** `extractor.py` skips `crop_question()` when
  `question.id in done_ids` but still appends the record → a cropper fix never
  regenerates old images; no extraction version exists.

- **D4 — dataset never updates (known risk B, inverse).** `write_questions_json` refuses
  to overwrite any existing ID ("intentional update" impossible); `write_all` merges the
  same way. Safe against loss, but metadata/answer fixes silently drop, and JSON/CSV can
  diverge (CSV rebuilt from merge, JSON from skip-list).
  Duplicate-ID *conflicts* are not detected — first write wins silently.

- **D5 — validation is shallow (known risk C).** `validator.py` checks existence, min
  dimensions, blankness, duplicate IDs, year range, and *caps at MAX_QUESTIONS=10*
  (so it cannot validate the 82-question pilot at all). It does NOT verify option
  preservation, answer-key association, JSON↔CSV consistency, taxonomy consistency,
  or image-path correctness (it resolves images by filename only).

- **D6 — IDs/filenames polluted by internal punctuation.** e.g.
  `gate-cse-1992-q01,viii`, `gate-cse-2009-q37,isro-dec2017-55` contain commas.
  Trailing punctuation is stripped (`1.22,` → `1.22`) but internal separators are not
  normalized. Regeneration must stay deterministic and distinct IDs must not collide.

- **D7 — answer-key audit cannot see duplicates.** `load_answer_key_table` dedups with
  first-wins (`if token not in table`), so the audit built *from that table* always
  reports 0 duplicates/0 conflicts — the measurement is structurally incapable of
  failing. Reader must record dropped duplicates for audit.

- **D8 — 40 malformed answer-key entries.** Observed raw values: `A.` (trailing period,
  should parse as MCQ A), `17 :` / `80000 :` (truncated ranges), `A. TCP, but not UDP`
  (label + text), `X` (needs_review sentinel), `Q-Q` (2 occurrences, genuinely unknown),
  and one pairing bug: `5.17.28 → "Transaction and Concurrency: GATE IT 2008 | Question: 63"`
  (a *heading* was consumed as the answer value → key/value pairing misalignment on that page).
  The single validation ERROR (`gate-cse-1992-q03,ii`: AK='Q-Q' vs JSON=None) is a mix of
  a genuinely ambiguous key and validator semantics (UNKNOWN should expect needs_review,
  not equality).

- **D9 — validator semantics for UNKNOWN AK entries** (follows from D8): expects
  `value == correct_answer` even when `answer_type == "UNKNOWN"`, producing a false error.

- **D10 — hardcoded section page ranges** in `pilot_extractor.SECTIONS_TO_EXTRACT`
  (plan hints, sample_plan.json not present in workspace). Used as fallback when
  `find_section_start` misses; acceptable for the pilot only if the located heading text
  is verified against the section name — currently the *name* passed in is trusted, and
  page hints are not derived from the PDF. Must not become the general locator.

- **D11 — no tests, no frontend, no README, no requirements file, no git repo.**

## 4. Known-good facts (regression anchors)

- Answer key pages exist; Databases key page = PDF page 338 (1-based).
- Mappings: `5.1.5 → B` (gate-cse-1999-q1.25), `5.1.7 → B` (gate-cse-2000-q1.22) —
  reconfirmed present in current pilot JSON with evidence `(p338)`.
- 10 B-Tree regression questions exist with images: 1989-Q12a, 1994-Q14a, 1994-Q14b,
  1997-Q19 (multi-page 259–260), 1999-Q1.25, 1999-Q21, 2000-Q1.22, 2000-Q21
  (multi-page 260–261), 2001-Q22, 2002-Q17 (multi-page 261–262).
- 12 multi-page questions detected across the pilot; all images exist.
- Environment: Python 3.12.7, PyMuPDF 1.24.11, Pillow 10.4.0, pytest 9.1.1,
  Node 24.17.0, npm 11.13.0 (registry reachable). Windows, bash shell.

## 5. Plan (stages B–F)

- **Stage B — extraction fixes:** explicit `subject=` parameter through
  `build_question` (kill D1/D2); ID normalization for internal punctuation (D6);
  `EXTRACTION_VERSION` in config + version stamp on records + update-on-version-change
  merge rules in `dataset_writer` (D3/D4); answer-key reader records duplicates and
  fixes pairing/normalization (D7/D8); validator upgraded: remove MAX_QUESTIONS cap,
  add option/answer-key/CSV-consistency checks, UNKNOWN semantics (D5/D9);
  pilot uses located section names (D10). Then regenerate pilot + validation report.
- **Stage C — validation pilot:** rerun pilot_extractor + validate_pilot with fixes;
  verify subjects across 10 sections, regression cases, B-tree answers; report numbers.
- **Stage D — dataset contract:** documented schema + `scripts/sync_dataset.py`
  (validate → copy images → build manifest without leaking answers → verify paths).
- **Stage E — frontend:** React + Vite + TypeScript, offline, localStorage progress,
  dashboard, 4 practice modes, exam UI (palette/timer/nav), grading, results, bookmarks.
- **Stage F — tests + docs:** pytest suite for extraction modules; vitest for grading/
  navigation/persistence; README with offline startup; this file updated per stage.

## 6. Stage log

| Stage | Status | Notes |
|---|---|---|
| A — audit & baseline | DONE | This file created; no code changes yet; pytest installed |
| B — extraction fixes | DONE | All module fixes applied + verified by re-run (see below) |
| C — validation pilot | DONE | Pilot regenerated; ALL acceptance criteria PASS |
| D — dataset contract | DONE | DATASET_CONTRACT.md + scripts/sync_dataset.py; split manifests verified |
| E — frontend | DONE | React+Vite+TS offline app; build + preview verified serving all assets |
| F — tests & docs | DONE | 74 pytest + 53 vitest tests pass; README, requirements.txt |

### Test commands run so far
- `python -m pytest --version` → pytest 9.1.1 (freshly installed; no tests exist yet)
- Manual probes: `parse_metadata` NameError reproduced; pilot JSON/report inspected;
  AK audit CSV inspected; all 82 pilot images verified present.
- Stage B verification: import check of all 13 modules → OK; `parse_metadata`
  signature carries `subject=`; `python extractor.py` → exit 0, baseline 10 records
  re-written as extraction_version=2 with regenerated images, 5.1.5→B and 5.1.7→B
  reconfirmed.
- Stage C: `python pilot_extractor.py` → 82/82 questions, 10 subjects
  (Databases 10 + 9×8), all v2, 0 comma IDs, 0 duplicate IDs, 82/82 images.
  `python validate_pilot.py` → exit 0, ALL 6 acceptance criteria PASS:
  82≥80 extracted; 0 images missing; metadata 100%; answer resolution 100%
  (56 verified + 25 confirmed N/A, 0 mismatches); 0 duplicate pilot index keys;
  0 hard errors.
- Visual/source spot-check of the 2 short images:
  `gate-cse-1994-q14b` (145px) = complete one-line complexity question;
  `gate-cse-1992-q01-viii` (139px) = complete one-line fill-in-the-blank.
  Both crops end exactly at the next question's tag line → no clipping.

### Defect disposition (Stage B/C outcomes)
- D1, D2 FIXED & verified (subject param; 10 distinct subjects in regenerated pilot)
- D3 FIXED & verified (EXTRACTION_VERSION=2; baseline v1→v2 records re-cropped)
- D4 FIXED (merge_records: added/updated/unchanged/conflict stats; JSON+CSV+taxonomy
  generated from one merged record set)
- D5, D9 FIXED (validator: no cap, MCQ option-preservation errors, answer-status
  semantics incl. UNKNOWN→needs_review, CSV cross-check)
- D6 FIXED (IDs normalized: `gate-cse-1992-q01-viii` etc.; 0 comma IDs remain)
- D7 FIXED (reader records duplicates via audit dict; see disposition of D8)
- D8 FIXED for parsing ("A."→MCQ, "A. text"→MCQ label, heading-pairing detected);
  index-level audit now measurable: 2,483 entries, 75 duplicate keys with
  conflicting values, 27 malformed (UNKNOWN) entries. All 75 conflicts are
  continuation-page pairing artifacts; first-wins keeps the authoritative
  header-page value; evidence persisted in
  output/validation_pilot/data/answer_key_index_audit.json.
- D10 MITIGATED for pilot (hint pages verified to contain the located heading;
  subject derived from the actual PDF heading, not the plan name)
- D11 RESOLVED (tests: 74 pytest + 53 vitest; README.md; requirements.txt;
  frontend/ built and verified; git repo not initialised — was not requested)

### Stage D outcomes
- `DATASET_CONTRACT.md` documents the source schema, the two frontend
  manifests, grading rules and safe-update rules.
- `scripts/sync_dataset.py` validated + synced the pilot: 82 display records,
  56 gradable, 82 images copied, 0 broken refs, exit 0. Verified: the display
  manifest contains ZERO answer fields (grep: 0 occurrences) while answers.json
  carries 56 grading entries. Answers are fetched only at submission time.

### Stage E outcomes (frontend)
- React 18 + Vite 5 + TypeScript (strict), zero runtime dependencies beyond
  React; no router lib, no remote fonts/assets. `base: "./"` → dist works
  from any static server offline.
- Structure: services/ (dataset, grading, storage), hooks/ (useSession state
  machine, useTimer deadline-based), components/ (QuestionImage with zoom +
  missing-image diagnostics, ResponseArea MCQ/MSQ/NAT/text/unknown, Palette
  with 5 states as shape+text, Filters from real metadata), pages/ (Dashboard,
  Setup, Exam, Results).
- Behaviours: 4+1 practice modes; palette states per spec; Save & Next /
  Mark for Review & Next (response retained) / Clear Response (targeted);
  untimed/timed sessions with drift-free deadline timer, 5-min/1-min warnings,
  auto-submit; submit confirmation with counts; results with correct /
  incorrect / ungradable / unanswered as SEPARATE buckets (unanswered is never
  scored incorrect); marks shown only when all graded items carry marks;
  bookmarks + session history + active-session resume in localStorage; reset
  is explicit + confirmed and keeps bookmarks; stale attempts prunable.
- **Bug found & fixed during testing**: useTimer originally re-ran its tick
  effect on every render (unstable onExpire dep + new state object) → infinite
  render loop that crashed the test worker. Fixed with callback ref + state
  bail-out (hooks/useTimer.ts).
- Verification: `npm run build` clean; 53/53 vitest tests pass (incl. full
  exam-flow integration tests through the real component tree with mocked
  local manifests); `vite preview` served index/data/answers/image all 200;
  bundle contains no runtime external URLs (only React's error-decoder text).

### Stage F outcomes (tests + docs)
- `python -m pytest tests -q` → **74 passed** (~5s): heading formats
  (12/12a/14b/2-iv/01,viii/1.33/Set N), boundary detection (section numbers,
  answer-line closing, multi-page, max cap), ID determinism + normalization,
  collision surfacing via merge conflicts, tag parsing, subject param, answer
  value classification (incl. D8 cases), duplicate/conflict audit,
  heading-pairing protection, merge rules (add/update/unchanged/conflict,
  no-loss), JSON↔CSV↔taxonomy consistency, crop completeness/stitch/
  determinism, validator semantics (options, statuses, no cap, images), plus
  3 real-PDF integration anchors (5.1.5→B, 5.1.7→B on the Databases key page;
  skipped automatically when volume2.pdf is absent).
- `npm test` (vitest) → **53 passed**: grading exactness (no invented NAT
  tolerance, exact MSQ sets, ungradable ≠ incorrect), persistence, dataset
  validation, session state machine, timer, and App-level integration tests
  (load, filters, full exam flow, results honesty, image error state,
  bookmark persistence across reload).
- README.md: setup, pipeline usage, validation gate, sync, offline frontend
  startup, troubleshooting table, honest limitations. requirements.txt pins
  PyMuPDF 1.24.11 / Pillow 10.4.0 / pytest 9.1.1.

### Residual limitations (documented, not blockers)
- 75 conflicting AK duplicate keys + 27 malformed entries exist index-wide
  (outside the pilot's questions); any full extraction touching those section
  numbers must consult answer_key_index_audit.json before marking `verified`.
- 1 pilot question (gate-cse-1992-q03-ii) is `needs_review` — its AK entry is
  genuinely ambiguous ("Q-Q") and is correctly NOT auto-resolved.
- Pilot images occasionally over-include a sliver of the preceding question's
  "Answer key" line or section number (cosmetic; never content loss).
