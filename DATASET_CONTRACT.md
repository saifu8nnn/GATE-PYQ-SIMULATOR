# Dataset Contract — GATE CSE PYQ

This is the interface between the extraction pipeline and the offline frontend.
The UI depends **only** on the artifacts described here — never on extraction
scripts or raw PDF layout. `scripts/sync_dataset.py` produces these artifacts
from any approved dataset (pilot or full).

## 1. Source records (`output/.../questions.json`)

Authoritative per-question record, produced by `models.Question`:

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Stable deterministic ID, e.g. `gate-cse-1999-q1.25`. Safe for filenames. Regenerating the same question yields the same ID. |
| `exam` | str | `"GATE CSE"` |
| `year` | int | 1984–2030 |
| `set` | str\|null | `"Set 2"` when the source heading names a set |
| `subject` | str | From the actual PDF section heading (e.g. `"Databases"`) |
| `topic` | str\|null | Heading topic, e.g. `"B Tree"` |
| `subtopic` | str\|null | Reserved; null unless source supports it |
| `question_number` | str | Sanitized original number (`"1.25"`, `"14a"`, `"2-ii"`) |
| `question_number_raw` | str\|null | Verbatim number incl. punctuation (`"1.22,"`) |
| `section_number` | str\|null | Answer-key index key, e.g. `"5.1.5"` |
| `question_type` | str\|null | `MCQ`/`MSQ`/`NAT`/`DESCRIPTIVE`/`FILL_IN_THE_BLANK`/`MATCH_THE_FOLLOWING`; null when unknown |
| `marks` | int\|null | From tag line only; never guessed |
| `difficulty` | str\|null | From tag line only |
| `options_present` | bool\|null | True if A./B./C./D. lines detected in source |
| `option_labels_detected` | list\|null | e.g. `["A","B","C","D"]` — the labels the UI offers as responses |
| `correct_answer` | any\|null | `"B"` / `["A","C"]` / `42` / `[50,52]` / null |
| `answer_status` | str | `verified` \| `needs_review` \| `not_available` |
| `answer_source` | str\|null | `"answer_key_page"` \| `"inline"` \| null |
| `answer_evidence` | str\|null | e.g. `"5.1.5 -> 'B' (p338)"` |
| `image` | str | Relative path `"images/<id>.png"` — the canonical question content |
| `source_pdf` | str | `"volume2.pdf"` |
| `source_pages` | list[int] | 0-based PDF pages the crop covers |
| `verified` | bool | Manual review flag; always starts false |
| `notes` | str\|null | Reviewer comments |
| `extraction_version` | int\|null | Pipeline version; a version bump forces regeneration |

### Status semantics (strict)

- `verified` — the answer came from the PDF's dedicated answer-key table via
  the question's `section_number`, and always carries `correct_answer` +
  `answer_evidence`. Never set automatically for inline/ambiguous sources.
- `needs_review` — a mapping could not be established confidently (missing
  section number, unparseable key, inline-only answer). **Not** a confirmed N/A.
- `not_available` — the source answer key explicitly says `N/A` for this
  question; evidence contains the N/A. A parser failure is never recorded here.

## 2. Frontend manifests (produced by `scripts/sync_dataset.py`)

```
frontend/public/
├── data/
│   ├── questions.json   ← display manifest (NO answers inside)
│   └── answers.json     ← grading manifest (loaded only at submission)
└── images/
    └── <id>.png         ← one canonical image per question
```

### `questions.json` (display)

```json
{
  "dataset": { "name": "validation_pilot", "source": "...", "totalQuestions": 82,
               "gradableQuestions": 56 },
  "questions": [ {
      "id": "gate-cse-1999-q1.25",
      "exam": "GATE CSE", "year": 1999, "set": null,
      "subject": "Databases", "topic": "B Tree", "subtopic": null,
      "questionNumber": "1.25",
      "questionType": "MCQ",
      "marks": null,
      "optionsPresent": true,
      "optionLabels": ["A","B","C","D"],
      "imageUrl": "/images/gate-cse-1999-q1.25.png",
      "sourcePages": [260],
      "verified": false
  } ]
}
```

Rules:
- Never contains `correct_answer` / `answer_status` / `answer_evidence`.
- `questionType` is never null in the manifest (`"UNKNOWN"` when unknown).
- `imageUrl` always resolves inside `frontend/public/`; the sync script
  verifies every reference before writing.

### `answers.json` (grading)

```json
{ "answers": [ { "id": "gate-cse-1999-q1.25", "questionType": "MCQ",
                 "correctAnswer": "B", "marks": null,
                 "answerStatus": "verified" } ] }
```

- Contains **only** questions with `answer_status == verified`.
- Absence of an entry means *ungradable* — the UI must never interpret a
  missing entry as "incorrect".

## 3. Frontend grading contract

| Type | Response | Grading |
|---|---|---|
| MCQ | one label from `optionLabels` | exact label match |
| MSQ | set of labels | exact set match (no partial credit without source rules) |
| NAT | numeric/text input | exact match against stored value (no invented tolerance) |
| DESCRIPTIVE / FILL_IN_THE_BLANK / MATCH_THE_FOLLOWING | free text | never auto-graded; attempt recorded for self-review |
| UNKNOWN | none | grading disabled, reason shown |
| any, missing grading entry | — | reported as **ungradable**, not incorrect |

Marks are used only when stored; no negative-marking or partial-credit rules
are ever invented.

## 4. Safe updates

Question data is separate from user progress (localStorage, keyed by question
`id`). Syncing a new dataset never touches saved attempts; IDs are stable so
old attempts stay attached. Attempts referencing IDs absent from the loaded
dataset are ignored without crashing and can be pruned from Settings.
