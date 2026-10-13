"""
pilot_extractor.py — Cross-section validation pilot for the GATE PYQ pipeline.

Extracts 8 questions from each of 10 sections in volume2.pdf (80 questions total).
Section 5 (Databases) already has 10 questions — those are loaded from the
existing output/data/questions.json and included in the pilot dataset.

Outputs:
  output/validation_pilot/data/pilot_questions.json
  output/validation_pilot/data/pilot_questions.csv
  output/validation_pilot/images/<id>.png  (one per question)

Usage:
  $env:PYTHONUTF8=1; python pilot_extractor.py
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import traceback
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

# ── Project root on sys.path ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Import pipeline modules (do NOT modify config.py) ─────────────────────────
from config import PDF_PATH, SOURCE_PDF_NAME, RENDER_SCALE, EXTRACTION_VERSION
from pdf_locator import (
    find_section_start,
    find_section_end,
    _find_section_heading_on_page,
    _get_bold_large_lines,
)


def _derive_subject(doc: fitz.Document, start_page: int, fallback: str) -> str:
    """
    Read the subject name from the actual bold section heading on the located
    start page (e.g. "Databases (268)" → "Databases"). Never invents a name:
    if no heading matches, the caller-provided fallback is used.
    """
    import re as _re
    for line in _get_bold_large_lines(doc[start_page]):
        text = line["text"].strip()
        if _re.match(rf"^{_re.escape(fallback)}\b", text, _re.IGNORECASE):
            # Strip a trailing question-count like " (268)"
            return _re.sub(r"\s*\(\d+\)\s*$", "", text).strip() or fallback
    return fallback
from question_detector import detect_question_boundaries
from metadata_parser import build_question
from image_cropper import crop_question
from answer_key_reader import load_answer_key_table
from models import Question
from utils import get_logger, ensure_dirs, open_pdf

logger = get_logger()

# ── Pilot output directories ───────────────────────────────────────────────────
PILOT_DIR        = PROJECT_ROOT / "output" / "validation_pilot"
PILOT_DATA_DIR   = PILOT_DIR / "data"
PILOT_IMAGE_DIR  = PILOT_DIR / "images"
PILOT_REPORT_DIR = PILOT_DIR / "reports"

PILOT_JSON_PATH  = PILOT_DATA_DIR / "pilot_questions.json"
PILOT_CSV_PATH   = PILOT_DATA_DIR / "pilot_questions.csv"

# ── Existing baseline (Databases, already extracted) ──────────────────────────
EXISTING_JSON    = PROJECT_ROOT / "output" / "data" / "questions.json"
EXISTING_IMG_DIR = PROJECT_ROOT / "output" / "images"

# CSV column order — same as dataset_writer.py
CSV_COLUMNS = [
    "id", "exam", "year", "set", "subject", "topic", "subtopic",
    "question_number", "question_number_raw", "section_number",
    "question_type", "marks", "difficulty",
    "options_present", "option_labels_detected",
    "correct_answer", "answer_status", "answer_source", "answer_evidence",
    "image", "source_pdf", "source_pages",
    "verified", "notes",
]

# ── Section list (derived from sample_plan.json) ───────────────────────────────
# Each tuple: (section_number, section_name, start_page_0based, end_page_0based)
# Databases (section 5) is skipped for extraction — handled via existing data.
SECTIONS_TO_EXTRACT = [
    (1,  "Algorithms",                    6,   87),
    (2,  "CO and Architecture",           88,  147),
    (3,  "Compiler Design",               148, 209),
    (4,  "Computer Networks",             210, 258),
    # 5 = Databases → skipped, use existing
    (6,  "Digital Logic",                 340, 410),
    (7,  "Operating System",              411, 498),
    (8,  "Programming and DS: DS",        499, 552),
    (9,  "Programming: Programming in C", 553, 594),
    (10, "Theory of Computation",         595, 662),
]

MAX_QUESTIONS_PER_SECTION = 8


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_existing_databases_questions() -> list[dict]:
    """Load the 10 Databases B Tree questions from the main pipeline output."""
    if not EXISTING_JSON.exists():
        logger.warning(f"Existing questions.json not found at {EXISTING_JSON}")
        return []
    with open(EXISTING_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Loaded {len(data)} existing Databases questions from {EXISTING_JSON}")
    return data


def copy_existing_images(questions_dicts: list[dict]) -> None:
    """
    Copy images for existing Databases questions into the pilot images folder.
    Skips silently if source image is missing.
    """
    copied = 0
    for q in questions_dicts:
        img_name = Path(q.get("image", "")).name
        if not img_name:
            continue
        src = EXISTING_IMG_DIR / img_name
        dst = PILOT_IMAGE_DIR / img_name
        if dst.exists():
            continue
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1
        else:
            logger.warning(f"  Source image missing: {src}")
    logger.info(f"Copied {copied} existing Databases images to pilot images dir.")


def patch_image_paths(questions_dicts: list[dict]) -> list[dict]:
    """
    Rewrite 'image' paths to use the pilot images/ prefix
    (they already say 'images/<name>.png', which is correct relative to pilot dir).
    """
    patched = []
    for q in questions_dicts:
        d = dict(q)
        # Already relative: "images/gate-cse-1989-q12a.png" — keep as-is
        patched.append(d)
    return patched


def write_pilot_json(all_questions_dicts: list[dict]) -> None:
    PILOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PILOT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_questions_dicts, f, indent=2, ensure_ascii=False)
    logger.info(f"pilot_questions.json written: {len(all_questions_dicts)} questions")


def write_pilot_csv(all_questions_dicts: list[dict]) -> None:
    PILOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PILOT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for q in all_questions_dicts:
            row = dict(q)
            if isinstance(row.get("source_pages"), list):
                row["source_pages"] = ",".join(str(p) for p in row["source_pages"])
            if isinstance(row.get("correct_answer"), list):
                row["correct_answer"] = ",".join(str(x) for x in row["correct_answer"])
            if isinstance(row.get("option_labels_detected"), list):
                row["option_labels_detected"] = ",".join(row["option_labels_detected"])
            writer.writerow(row)
    logger.info(f"pilot_questions.csv written: {len(all_questions_dicts)} rows")


# ── Per-section extractor ──────────────────────────────────────────────────────

def extract_section(
    doc: fitz.Document,
    section_num: int,
    section_name: str,
    known_start: int,
    known_end: int,
    answer_key_table: dict,
) -> tuple[list[dict], str]:
    """
    Extract up to MAX_QUESTIONS_PER_SECTION questions from one section.

    Returns (list_of_question_dicts, status_message).
    The known_start / known_end from sample_plan are used as HINTS:
    we first try find_section_start(); if it fails or returns a page outside
    [known_start-2 .. known_start+10], we fall back to known_start directly.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Section {section_num}: {section_name!r}  (hint pages {known_start}-{known_end})")
    logger.info(f"{'='*60}")

    # ── Step 1: locate section start ──────────────────────────────────────────
    # The PDF is the source of truth: find_section_start verifies an actual
    # bold heading for `section_name` in the document. Plan hints are only a
    # fallback, and a hinted page must ALSO contain the heading — otherwise
    # we search for the heading rather than trusting a page number.
    located_start: Optional[int] = None
    try:
        located_start = find_section_start(doc, section_name)
        logger.info(f"  Section start located at p{located_start} (PDF heading found)")
    except RuntimeError as exc:
        logger.warning(f"  find_section_start failed: {exc}")
        # Verify the hint page actually contains the section heading
        if _find_section_heading_on_page(doc[known_start], section_name):
            logger.warning(f"  Hint page {known_start} verified to contain the heading; using it.")
            located_start = known_start
        else:
            # Scan near the hint for the real heading
            found: Optional[int] = None
            for cand in range(max(0, known_start - 15), min(len(doc), known_start + 16)):
                if _find_section_heading_on_page(doc[cand], section_name):
                    found = cand
                    break
            if found is not None:
                logger.warning(f"  Heading found near hint at p{found}; using it.")
                located_start = found
            else:
                msg = f"Section heading {section_name!r} not found near hint p{known_start}"
                logger.error(f"  {msg}")
                return [], f"FAILED ({msg})"

    # ── Step 2: locate section end ────────────────────────────────────────────
    located_end: Optional[int] = None
    try:
        located_end = find_section_end(doc, located_start)
        if located_end is not None:
            # Cap to known_end from plan (adds safety)
            if located_end > known_end + 5:
                logger.warning(
                    f"  find_section_end returned p{located_end}, "
                    f"capping to plan hint p{known_end}"
                )
                located_end = known_end
            else:
                logger.info(f"  Section end located at p{located_end} (plan hint: p{known_end})")
        else:
            logger.warning(f"  find_section_end returned None; using plan hint p{known_end}")
            located_end = known_end
    except Exception as exc:
        logger.warning(f"  find_section_end error: {exc}; using plan hint p{known_end}")
        located_end = known_end

    # ── Step 3: detect question boundaries ────────────────────────────────────
    try:
        boundaries = detect_question_boundaries(
            doc,
            section_start_page=located_start,
            section_end_page=located_end,
            max_questions=MAX_QUESTIONS_PER_SECTION,
        )
    except Exception as exc:
        msg = f"detect_question_boundaries failed: {exc}"
        logger.error(f"  {msg}")
        logger.debug(traceback.format_exc())
        return [], f"FAILED ({msg})"

    if not boundaries:
        msg = "No question boundaries detected"
        logger.warning(f"  {msg}")
        return [], f"FAILED ({msg})"

    # Subject comes from the actual heading on the located page (PDF truth)
    subject = _derive_subject(doc, located_start, section_name)
    if subject != section_name:
        logger.info(f"  Subject from PDF heading: {subject!r} (plan said {section_name!r})")

    logger.info(f"  Detected {len(boundaries)} question boundaries")

    # ── Step 4: build questions + crop images ─────────────────────────────────
    extracted: list[dict] = []
    errors: list[str] = []

    for i, boundary in enumerate(boundaries, 1):
        label = f"[{section_num}.{i}/{len(boundaries)}]"
        logger.info(f"  {label} {boundary.heading_text[:70]}")

        # Build metadata — subject is the section actually located in the PDF
        try:
            question = build_question(boundary, answer_key_table, subject=subject)
        except Exception as exc:
            msg = f"build_question failed: {exc}"
            logger.error(f"    {msg}")
            logger.debug(traceback.format_exc())
            errors.append(msg)
            continue

        # Crop image
        img_path = PILOT_IMAGE_DIR / Path(question.image).name
        try:
            crop_question(doc, boundary, img_path)
        except Exception as exc:
            msg = f"[{question.id}] crop_question failed: {exc}"
            logger.error(f"    {msg}")
            logger.debug(traceback.format_exc())
            errors.append(msg)
            question.notes = f"Crop error: {exc}"

        extracted.append(question.to_dict())
        logger.info(
            f"    ✓ {question.id}  type={question.question_type or '?'}  "
            f"ans={question.correct_answer!r}  status={question.answer_status}"
        )

    n = len(extracted)
    n_err = len(errors)
    status = f"OK ({n} extracted"
    if n_err:
        status += f", {n_err} errors"
    status += ")"
    return extracted, status


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Ensure output directories exist ───────────────────────────────────────
    ensure_dirs(PILOT_DIR, PILOT_DATA_DIR, PILOT_IMAGE_DIR, PILOT_REPORT_DIR)

    # ── Load existing Databases questions ─────────────────────────────────────
    databases_questions = load_existing_databases_questions()
    databases_questions = patch_image_paths(databases_questions)
    copy_existing_images(databases_questions)

    # ── Open PDF ──────────────────────────────────────────────────────────────
    if not PDF_PATH.exists():
        logger.error(f"PDF not found: {PDF_PATH}")
        sys.exit(1)
    doc = open_pdf(PDF_PATH)

    # ── Load answer key table ONCE + duplicate/conflict audit ───────────────
    logger.info("Loading answer key table from full PDF (this may take a moment)...")
    ak_audit: dict = {}
    answer_key_table = load_answer_key_table(doc, audit=ak_audit)
    logger.info(f"Answer key table: {len(answer_key_table)} entries")
    logger.info(
        f"Answer key audit: {len(ak_audit.get('duplicates', []))} duplicates, "
        f"{len(ak_audit.get('conflicts', []))} conflicts"
    )
    # Persist audit evidence for validate_pilot.py
    import json as _json
    AK_AUDIT_JSON = PILOT_DATA_DIR / "answer_key_index_audit.json"
    PILOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(AK_AUDIT_JSON, "w", encoding="utf-8") as f:
        _json.dump({
            "entries": len(answer_key_table),
            "duplicates": [list(x) for x in ak_audit.get("duplicates", [])],
            "conflicts": [list(x) for x in ak_audit.get("conflicts", [])],
        }, f, indent=2, ensure_ascii=False)

    # ── Extract each section ──────────────────────────────────────────────────
    all_new_questions: list[dict] = []
    section_results: dict[str, dict] = {}

    for (sec_num, sec_name, start_p, end_p) in SECTIONS_TO_EXTRACT:
        extracted, status = extract_section(
            doc=doc,
            section_num=sec_num,
            section_name=sec_name,
            known_start=start_p,
            known_end=end_p,
            answer_key_table=answer_key_table,
        )
        all_new_questions.extend(extracted)
        section_results[sec_name] = {
            "section_number": sec_num,
            "extracted": len(extracted),
            "status": status,
        }

    doc.close()

    # ── Merge: Databases (existing) + new sections ────────────────────────────
    # De-duplicate by ID
    seen_ids: set[str] = set()
    all_questions: list[dict] = []

    # Add Databases baseline first
    for q in databases_questions:
        qid = q.get("id", "")
        if qid not in seen_ids:
            seen_ids.add(qid)
            all_questions.append(q)

    # Add new sections
    for q in all_new_questions:
        qid = q.get("id", "")
        if qid not in seen_ids:
            seen_ids.add(qid)
            all_questions.append(q)
        else:
            logger.debug(f"  Dedup: skipping duplicate ID {qid}")

    # ── Write outputs ──────────────────────────────────────────────────────────
    write_pilot_json(all_questions)
    write_pilot_csv(all_questions)

    # ── Print summary ──────────────────────────────────────────────────────────
    WIDE = "=" * 65
    print(f"\n{WIDE}")
    print("PILOT EXTRACTION SUMMARY")
    print(WIDE)
    print(f"{'Section':<35} {'#':>5}  Status")
    print("-" * 65)

    # Databases (existing)
    print(f"{'5. Databases (existing baseline)':<35} {len(databases_questions):>5}  OK (pre-extracted)")

    total_new = 0
    failed_sections = []
    for sec_name, result in section_results.items():
        n = result["extracted"]
        total_new += n
        status = result["status"]
        num = result["section_number"]
        label = f"{num}. {sec_name}"
        print(f"{label:<35} {n:>5}  {status}")
        if "FAILED" in status:
            failed_sections.append(sec_name)

    print("-" * 65)
    total = len(databases_questions) + total_new
    print(f"{'TOTAL':<35} {total:>5}")
    print(f"\nNew questions extracted (9 sections):  {total_new}")
    print(f"Existing Databases questions:          {len(databases_questions)}")
    print(f"Grand total in pilot dataset:          {total}")
    print(f"\nOutput files:")
    print(f"  JSON:   {PILOT_JSON_PATH}")
    print(f"  CSV:    {PILOT_CSV_PATH}")
    print(f"  Images: {PILOT_IMAGE_DIR}  ({len(list(PILOT_IMAGE_DIR.glob('*.png')))} PNG files)")

    if failed_sections:
        print(f"\nFAILED SECTIONS ({len(failed_sections)}):")
        for s in failed_sections:
            print(f"  ✗ {s}  — {section_results[s]['status']}")
    else:
        print("\nAll sections extracted successfully.")

    print(WIDE + "\n")

    # ── Type breakdown ─────────────────────────────────────────────────────────
    type_counts: dict[str, int] = {}
    answer_status_counts: dict[str, int] = {}
    for q in all_questions:
        qt = q.get("question_type") or "unknown"
        type_counts[qt] = type_counts.get(qt, 0) + 1
        qs = q.get("answer_status", "unknown")
        answer_status_counts[qs] = answer_status_counts.get(qs, 0) + 1

    print("Question type breakdown:")
    for qt, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {qt:<25} {cnt:>4}")

    print("\nAnswer status breakdown:")
    for qs, cnt in sorted(answer_status_counts.items(), key=lambda x: -x[1]):
        print(f"  {qs:<25} {cnt:>4}")

    print()

    # Exit with error code if any sections failed
    if failed_sections:
        sys.exit(1)


if __name__ == "__main__":
    main()
