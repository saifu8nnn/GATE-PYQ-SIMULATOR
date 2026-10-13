"""
extractor.py — Main orchestrator for the GATE PYQ Phase 1 extraction pipeline.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

from config import (
    PDF_PATH, OUTPUT_DIR, IMAGE_DIR, DATA_DIR, REPORT_DIR,
    SECTION_NAME, MAX_QUESTIONS, SOURCE_PDF_NAME, EXTRACTION_VERSION,
)
from models import Question, AnswerStatus
from pdf_locator import find_section_start, find_section_end
from question_detector import detect_question_boundaries, print_boundaries
from metadata_parser import build_question
from image_cropper import crop_question
from answer_key_reader import load_answer_key_table
from dataset_writer import write_all, existing_ids, load_existing_questions
from validator import validate_questions
from utils import get_logger, ensure_dirs, verify_pdf, open_pdf, utc_now_iso

logger = get_logger()

JSON_PATH       = DATA_DIR   / "questions.json"
CSV_PATH        = DATA_DIR   / "questions.csv"
TAXONOMY_PATH   = DATA_DIR   / "taxonomy.json"
REPORT_PATH     = REPORT_DIR / "processing_report.json"
REVIEW_CSV_PATH = REPORT_DIR / "review_summary.csv"

QUESTIONS_PER_SHEET = 4


# ── Contact sheet ──────────────────────────────────────────────────────────────

def build_contact_sheets(questions: list[Question], image_dir: Path) -> list[Path]:
    THUMB_H_MAX = 600
    SHEET_W     = 1100
    LABEL_H     = 32
    PADDING     = 14
    BG_COLOR    = (245, 245, 245)
    LABEL_BG    = (40, 55, 90)
    LABEL_FG    = (255, 255, 255)
    BORDER      = (180, 185, 205)
    TITLE_H     = 50

    if not questions:
        return []

    try:
        font_title = ImageFont.truetype("arial.ttf", 18)
        font_label = ImageFont.truetype("arial.ttf", 13)
    except (IOError, OSError):
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()

    saved: list[Path] = []
    groups = [questions[i:i+QUESTIONS_PER_SHEET] for i in range(0, len(questions), QUESTIONS_PER_SHEET)]

    for sheet_idx, group in enumerate(groups, 1):
        sheet_path = REPORT_DIR / f"contact_sheet_{sheet_idx}.png"
        thumbs: list[Image.Image] = []
        for q in group:
            img_path = image_dir / Path(q.image).name
            if img_path.exists():
                try:
                    img = Image.open(img_path).convert("RGB")
                    avail_w = SHEET_W - 2 * PADDING
                    scale = min(avail_w / img.width, THUMB_H_MAX / img.height, 1.0)
                    thumb = img.resize((int(img.width*scale), int(img.height*scale)), Image.LANCZOS)
                except Exception as exc:
                    thumb = Image.new("RGB", (SHEET_W-2*PADDING, 80), (255,200,200))
                    ImageDraw.Draw(thumb).text((8,8), f"Error: {exc}", fill=(180,0,0))
            else:
                thumb = Image.new("RGB", (SHEET_W-2*PADDING, 80), (255,230,180))
                ImageDraw.Draw(thumb).text((8,8), "IMAGE MISSING", fill=(180,80,0))
            thumbs.append(thumb)

        total_h = TITLE_H + PADDING + sum(LABEL_H + t.height + PADDING for t in thumbs)
        sheet = Image.new("RGB", (SHEET_W, total_h), BG_COLOR)
        draw  = ImageDraw.Draw(sheet)

        total_sheets = len(groups)
        q_start = (sheet_idx-1)*QUESTIONS_PER_SHEET+1
        q_end   = min(sheet_idx*QUESTIONS_PER_SHEET, len(questions))
        title = f"GATE PYQ — {SECTION_NAME} — Sheet {sheet_idx}/{total_sheets} (Q{q_start}-Q{q_end} of {len(questions)})"
        draw.text((PADDING, 14), title, fill=(30,30,60), font=font_title)

        y_cursor = TITLE_H + PADDING
        for i, (q, thumb) in enumerate(zip(group, thumbs)):
            global_idx = (sheet_idx-1)*QUESTIONS_PER_SHEET + i + 1
            lx0, ly0 = PADDING, y_cursor
            lx1, ly1 = SHEET_W-PADDING, y_cursor+LABEL_H
            draw.rectangle((lx0, ly0, lx1, ly1), fill=LABEL_BG)
            ans_display = str(q.correct_answer) if q.correct_answer is not None else "?"
            label = (
                f"Q{global_idx}. {q.id}  |  sec={q.section_number or '?'}  "
                f"type={q.question_type or '?'}  ans={ans_display}  status={q.answer_status}"
            )
            draw.text((lx0+8, ly0+8), label, fill=LABEL_FG, font=font_label)
            y_cursor += LABEL_H
            tx = PADDING + (SHEET_W - 2*PADDING - thumb.width)//2
            draw.rectangle((PADDING, y_cursor, SHEET_W-PADDING, y_cursor+thumb.height), fill=(255,255,255))
            sheet.paste(thumb, (tx, y_cursor))
            draw.rectangle((PADDING, ly0, SHEET_W-PADDING, y_cursor+thumb.height), outline=BORDER, width=1)
            y_cursor += thumb.height + PADDING

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        sheet.save(str(sheet_path), format="PNG", optimize=True)
        logger.info(f"Contact sheet saved: {sheet_path}")
        saved.append(sheet_path)
    return saved


# ── Review summary ─────────────────────────────────────────────────────────────

def write_review_summary(questions, image_dir, val_warnings, val_errors):
    import re as _re
    REVIEW_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    warn_map: dict[str, list[str]] = {}
    for msg in val_warnings + val_errors:
        m = _re.match(r"^\[([^\]]+)\]", msg)
        if m:
            warn_map.setdefault(m.group(1), []).append(msg)

    with open(REVIEW_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "year", "topic", "section_number", "question_number",
            "question_number_raw", "question_type", "marks",
            "options_present", "option_labels_detected",
            "correct_answer", "answer_status", "answer_source", "answer_evidence",
            "source_pages", "img_width", "img_height", "warnings"
        ])
        writer.writeheader()
        for q in questions:
            img_path = image_dir / Path(q.image).name
            w, h = 0, 0
            if img_path.exists():
                try:
                    im = Image.open(img_path)
                    w, h = im.size
                except Exception:
                    pass
            ans = q.correct_answer
            if isinstance(ans, list):
                ans = ";".join(str(x) for x in ans)
            writer.writerow({
                "id":                    q.id,
                "year":                  q.year,
                "topic":                 q.topic,
                "section_number":        q.section_number,
                "question_number":       q.question_number,
                "question_number_raw":   getattr(q, "question_number_raw", None),
                "question_type":         q.question_type,
                "marks":                 q.marks,
                "options_present":       q.options_present,
                "option_labels_detected": ";".join(q.option_labels_detected) if q.option_labels_detected else None,
                "correct_answer":        ans,
                "answer_status":         q.answer_status,
                "answer_source":         q.answer_source,
                "answer_evidence":       q.answer_evidence,
                "source_pages":          ",".join(str(p) for p in q.source_pages),
                "img_width":             w,
                "img_height":            h,
                "warnings":              " | ".join(warn_map.get(q.id, [])),
            })
    logger.info(f"Review summary saved: {REVIEW_CSV_PATH}")


# ── Answer stats helper ────────────────────────────────────────────────────────

def _answer_stats(questions: list[Question]) -> dict:
    verified     = [q for q in questions if q.answer_status == AnswerStatus.VERIFIED]
    needs_review = [q for q in questions if q.answer_status == AnswerStatus.NEEDS_REVIEW]
    not_avail    = [q for q in questions if q.answer_status == AnswerStatus.NOT_AVAILABLE]
    descriptive  = [q for q in questions if q.question_type == "DESCRIPTIVE"]
    mcq_msq      = [q for q in questions if q.question_type in ("MCQ", "MSQ")]
    nat          = [q for q in questions if q.question_type == "NAT"]
    unknown_type = [q for q in questions if q.question_type is None]
    return {
        "answers_verified":     len(verified),
        "answers_needs_review": len(needs_review),
        "answers_not_available": len(not_avail),
        "type_descriptive":     len(descriptive),
        "type_mcq_msq":         len(mcq_msq),
        "type_nat":             len(nat),
        "type_unknown":         len(unknown_type),
        "verified_ids":         [q.id for q in verified],
        "needs_review_ids":     [q.id for q in needs_review],
    }


# ── Console report ─────────────────────────────────────────────────────────────

def print_extraction_report(questions, report, contact_paths):
    WIDE = "=" * 58
    print(f"\n{WIDE}")
    print("GATE PYQ EXTRACTION REPORT")
    print(WIDE)
    print(f"Source:               {report['source_pdf']}")
    print(f"Section:              {report['section']}")
    print(f"Requested:            {report['requested_questions']}")
    print(f"Found:                {report['questions_found']}")
    print(f"Cropped:              {report['images_created']}")
    print(f"Processed:            {report['questions_processed']}")

    ans = report.get("answer_stats", {})
    print(f"\nAnswer stats:")
    print(f"  Verified answers:      {ans.get('answers_verified', 0)}")
    print(f"  Needs review:          {ans.get('answers_needs_review', 0)}")
    print(f"  Not available (N/A):   {ans.get('answers_not_available', 0)}")
    print(f"  Type MCQ/MSQ:          {ans.get('type_mcq_msq', 0)}")
    print(f"  Type NAT:              {ans.get('type_nat', 0)}")
    print(f"  Type DESCRIPTIVE:      {ans.get('type_descriptive', 0)}")
    print(f"  Type unknown:          {ans.get('type_unknown', 0)}")

    if report.get("errors"):
        print(f"\nERRORS ({len(report['errors'])}):")
        for e in report["errors"]:
            print(f"  x {e}")

    if report.get("warnings"):
        print(f"\nWARNINGS ({len(report['warnings'])}):")
        for w in report["warnings"]:
            print(f"  ! {w}")

    print(f"\n{WIDE}")
    print("QUESTIONS")
    print(WIDE)
    for i, q in enumerate(questions, 1):
        img_ok = "OK" if (IMAGE_DIR / Path(q.image).name).exists() else "MISSING"
        ans_v  = str(q.correct_answer) if q.correct_answer is not None else "null"
        print(f"\n{i:2d}. {q.id}")
        print(f"    sec={q.section_number}  type={q.question_type or '?'}  marks={q.marks}")
        print(f"    answer={ans_v}  status={q.answer_status}  src={q.answer_source}")
        print(f"    evidence: {q.answer_evidence}")
        print(f"    opts={q.option_labels_detected}  pages={q.source_pages}  img={img_ok}")

    print(f"\n{WIDE}")
    for p in contact_paths:
        print(f"Contact sheet:  {p}")
    print(f"Review summary: {REVIEW_CSV_PATH}")
    print(f"questions.json: {JSON_PATH}")
    print(f"questions.csv:  {CSV_PATH}")
    print(WIDE + "\n")


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run() -> None:
    started_at = utc_now_iso()
    ensure_dirs(OUTPUT_DIR, IMAGE_DIR, DATA_DIR, REPORT_DIR)

    verify_pdf(PDF_PATH)
    doc = open_pdf(PDF_PATH)

    # Load answer key table ONCE from the full PDF
    logger.info("Loading answer key table...")
    answer_key_table = load_answer_key_table(doc)

    # Locate Databases section
    section_start = find_section_start(doc, SECTION_NAME)
    section_end   = find_section_end(doc, section_start)
    logger.info(f"Databases section: page {section_start} -> {section_end or 'end'}")

    # Detect boundaries
    boundaries = detect_question_boundaries(doc, section_start, section_end, MAX_QUESTIONS)
    print_boundaries(boundaries)
    questions_found = len(boundaries)

    # Existing records: used to decide update-vs-skip AND to detect staleness.
    # A record produced by an older EXTRACTION_VERSION (or one whose image is
    # missing) is fully reprocessed — its image is re-cropped, never reused.
    existing_records = {r["id"]: r for r in load_existing_questions(JSON_PATH)
                        if "id" in r}
    logger.info(f"Already recorded: {len(existing_records)} question(s)")

    processed_questions: list[Question] = []
    errors: list[str]   = []
    warnings: list[str] = []
    images_created = 0

    for i, boundary in enumerate(boundaries, 1):
        logger.info(f"[{i}/{questions_found}] Processing: {boundary.heading_text[:70]}")

        try:
            # Pass answer_key_table + subject (the located section) into build_question
            question = build_question(boundary, answer_key_table, subject=SECTION_NAME)
        except Exception as exc:
            msg = f"Metadata parse failed for boundary {i}: {exc}"
            logger.error(msg)
            errors.append(msg)
            continue

        image_path = IMAGE_DIR / Path(question.image).name
        old = existing_records.get(question.id)
        stale = (
            old is None
            or old.get("extraction_version") != EXTRACTION_VERSION
            or not image_path.exists()
        )

        if not stale:
            logger.info(f"  Skipping crop (up-to-date): {question.id}")
            processed_questions.append(question)
            continue

        if old is not None:
            logger.info(
                f"  Regenerating (v{old.get('extraction_version')} "
                f"→ v{EXTRACTION_VERSION}): {question.id}"
            )

        try:
            crop_question(doc, boundary, image_path)
            images_created += 1
        except Exception as exc:
            msg = f"[{question.id}] Image crop failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            question.notes = f"Crop error: {exc}"
            warnings.append(msg)

        processed_questions.append(question)

    doc.close()

    if processed_questions:
        write_all(processed_questions, JSON_PATH, CSV_PATH, TAXONOMY_PATH,
                  current_version=EXTRACTION_VERSION)
    else:
        logger.warning("No questions processed.")

    val_report = validate_questions(processed_questions, IMAGE_DIR)
    errors.extend(val_report.errors)
    warnings.extend(val_report.warnings)

    contact_paths = build_contact_sheets(processed_questions, IMAGE_DIR)
    write_review_summary(processed_questions, IMAGE_DIR, val_report.warnings, val_report.errors)

    completed_at = utc_now_iso()
    ans_stats = _answer_stats(processed_questions)
    processing_report = {
        "source_pdf":            SOURCE_PDF_NAME,
        "section":               SECTION_NAME,
        "requested_questions":   MAX_QUESTIONS,
        "questions_found":       questions_found,
        "questions_processed":   len(processed_questions),
        "images_created":        images_created,
        "answer_stats":          ans_stats,
        "errors":                errors,
        "warnings":              warnings,
        "started_at":            started_at,
        "completed_at":          completed_at,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(processing_report, f, indent=2, ensure_ascii=False)
    logger.info(f"Processing report saved: {REPORT_PATH}")

    print_extraction_report(processed_questions, processing_report, contact_paths)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    run()
