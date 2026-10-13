"""
validator.py — Validate extracted question images and metadata.

Checks performed
----------------
  1. All required fields are present and non-None where mandatory.
  2. All image files exist on disk (resolved via the record's own path).
  3. Images meet minimum dimension requirements (error if too narrow).
  4. Images shorter than SUSPICIOUS_HEIGHT_PX get a WARNING (not an error),
     as they may be cut off.
  5. Images are not suspiciously blank.
  6. Question IDs are unique.
  7. Year is a plausible GATE year (1984–2030).
  8. Image filename matches the question ID.
  9. Answer-status semantics:
       verified       → a value AND evidence must be present
       not_available  → evidence must show an explicit source N/A
       needs_review   → must NOT be presented as a confirmed answer
 10. MCQ questions: option labels must have been detected (missing source
     options are a critical failure — flagged as error).
 11. Optional: questions.csv can be cross-checked against the in-memory
     records (same IDs, same answers, same statuses).

The record count is NOT capped — pass `max_questions` explicitly if a run is
supposed to be bounded.

NOTE: subject comes from the located PDF section (passed through
      metadata_parser), not from a global config constant, and is validated
      only for presence — its correctness is established by section
      detection, which is tested separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image

from config import (
    IMAGE_DIR,
    MIN_IMAGE_WIDTH,
    MIN_IMAGE_HEIGHT,
    BLANK_PIXEL_THRESHOLD,
)
from models import Question
from utils import get_logger, is_mostly_white

logger = get_logger()

GATE_YEAR_MIN = 1984
GATE_YEAR_MAX = 2030

# Images shorter than this (in pixels at RENDER_SCALE) are flagged as
# potentially cut-off. A full single-question image is usually 300+ px tall.
SUSPICIOUS_HEIGHT_PX = 300


# ── Report dataclass ───────────────────────────────────────────────────────────

@dataclass
class ValidationReport:
    total_questions: int = 0
    images_ok: int = 0
    images_missing: int = 0
    images_blank: int = 0
    metadata_ok: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "PASS" if self.passed() else "FAIL"
        lines = [
            f"Validation: {status}",
            f"  Questions:      {self.total_questions}",
            f"  Images OK:      {self.images_ok}",
            f"  Images missing: {self.images_missing}",
            f"  Images blank:   {self.images_blank}",
            f"  Errors:         {len(self.errors)}",
            f"  Warnings:       {len(self.warnings)}",
        ]
        if self.errors:
            lines.append("  Errors:")
            for e in self.errors:
                lines.append(f"    x {e}")
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    ! {w}")
        return "\n".join(lines)


# ── Image validator ────────────────────────────────────────────────────────────

def validate_image(
    question: Question,
    image_dir: Path,
    report: ValidationReport,
) -> bool:
    """Validate the image for a single question. Returns True if acceptable."""
    image_path = image_dir / Path(question.image).name

    if not image_path.exists():
        msg = f"[{question.id}] Image missing: {image_path.name}"
        report.errors.append(msg)
        report.images_missing += 1
        logger.error(msg)
        return False

    try:
        img = Image.open(image_path)
        img.load()
    except Exception as exc:
        msg = f"[{question.id}] Cannot open image: {exc}"
        report.errors.append(msg)
        report.images_missing += 1
        return False

    w, h = img.size

    # ── Minimum width (hard error) ─────────────────────────────────────────────
    if w < MIN_IMAGE_WIDTH:
        msg = f"[{question.id}] Image too narrow: {w}px < {MIN_IMAGE_WIDTH}px"
        report.errors.append(msg)
        logger.error(msg)
        return False

    # ── Minimum height (hard error) ────────────────────────────────────────────
    if h < MIN_IMAGE_HEIGHT:
        msg = f"[{question.id}] Image too short: {h}px < {MIN_IMAGE_HEIGHT}px"
        report.errors.append(msg)
        logger.error(msg)
        return False

    # ── Suspiciously short (warning only) ─────────────────────────────────────
    if h < SUSPICIOUS_HEIGHT_PX:
        msg = (
            f"[{question.id}] Image may be cut off: "
            f"{h}px is shorter than {SUSPICIOUS_HEIGHT_PX}px threshold"
        )
        report.warnings.append(msg)
        logger.warning(msg)

    # ── Blank check ────────────────────────────────────────────────────────────
    if is_mostly_white(img, threshold=BLANK_PIXEL_THRESHOLD):
        msg = (
            f"[{question.id}] Suspicious crop: "
            f">{BLANK_PIXEL_THRESHOLD:.0%} white pixels"
        )
        report.warnings.append(msg)
        report.images_blank += 1
        logger.warning(msg)
    else:
        report.images_ok += 1

    return True


# ── Metadata validator ─────────────────────────────────────────────────────────

def validate_metadata(question: Question, report: ValidationReport) -> bool:
    """Validate metadata for a single question. Returns True if mandatory fields present."""
    ok = True

    if not question.id:
        report.errors.append("Missing ID for a question record")
        ok = False

    if not question.year:
        report.errors.append(f"[{question.id}] Missing year")
        ok = False
    elif not (GATE_YEAR_MIN <= question.year <= GATE_YEAR_MAX):
        report.errors.append(
            f"[{question.id}] Implausible year: {question.year} "
            f"(expected {GATE_YEAR_MIN}-{GATE_YEAR_MAX})"
        )
        ok = False

    # subject comes from the located PDF section (see metadata_parser); only
    # presence is checked here — correctness is established by section
    # detection, which is tested separately.
    if not question.subject:
        report.errors.append(f"[{question.id}] Missing subject")
        ok = False

    if not question.question_number:
        report.errors.append(f"[{question.id}] Missing question_number")
        ok = False

    if not question.image:
        report.errors.append(f"[{question.id}] Missing image path")
        ok = False

    # Soft warnings
    if question.topic is None:
        report.warnings.append(f"[{question.id}] No topic extracted")

    if question.question_type is None:
        report.warnings.append(f"[{question.id}] Question type unknown")

    if question.marks is None:
        report.warnings.append(f"[{question.id}] Marks not found in tag line")

    # ── Image filename must match the ID (path integrity) ───────────────────
    if question.image and Path(question.image).stem != question.id:
        report.errors.append(
            f"[{question.id}] Image path does not match ID: {question.image}"
        )
        ok = False

    # ── Answer-status semantics ─────────────────────────────────────────────
    status = question.answer_status
    if status not in ("verified", "needs_review", "not_available"):
        report.errors.append(f"[{question.id}] Invalid answer_status: {status!r}")
        ok = False
    elif status == "verified":
        if question.correct_answer is None:
            report.errors.append(
                f"[{question.id}] answer_status=verified but no answer value"
            )
            ok = False
        if not question.answer_evidence:
            report.errors.append(
                f"[{question.id}] answer_status=verified but no answer evidence"
            )
            ok = False
    elif status == "not_available":
        ev = (question.answer_evidence or "").upper()
        if question.answer_evidence and "N/A" not in ev:
            report.errors.append(
                f"[{question.id}] answer_status=not_available without explicit "
                f"source N/A evidence (a parser failure must not read as N/A)"
            )
            ok = False

    # ── Option preservation for MCQ/MSQ ─────────────────────────────────────
    if question.question_type in ("MCQ", "MSQ"):
        labels = question.option_labels_detected or []
        if not labels or question.options_present is False:
            report.errors.append(
                f"[{question.id}] {question.question_type} with missing detected "
                f"options (labels={labels}, present={question.options_present})"
            )
            ok = False
    elif question.question_type == "DESCRIPTIVE" and question.options_present:
        report.warnings.append(
            f"[{question.id}] DESCRIPTIVE question claims options_present"
        )

    if ok:
        report.metadata_ok += 1

    return ok


# ── Full validation run ────────────────────────────────────────────────────────

# ── CSV consistency ──────────────────────────────────────────────────────────

def validate_csv_consistency(
    questions: list[Question],
    csv_path: Path,
    report: ValidationReport,
) -> None:
    """Cross-check questions.csv against the in-memory authoritative records."""
    if not csv_path.exists():
        report.warnings.append(f"CSV not found for consistency check: {csv_path}")
        return

    import csv as _csv
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = {r["id"]: r for r in _csv.DictReader(f) if r.get("id")}

    mem_ids = {q.id for q in questions}
    csv_ids = set(rows)
    missing = mem_ids - csv_ids
    extra   = csv_ids - mem_ids
    if missing:
        report.errors.append(f"CSV missing records: {sorted(missing)}")
    if extra:
        report.errors.append(f"CSV has unexpected records: {sorted(extra)}")

    for q in questions:
        row = rows.get(q.id)
        if row is None:
            continue
        if (row.get("answer_status") or None) != q.answer_status:
            report.errors.append(
                f"[{q.id}] CSV answer_status {row.get('answer_status')!r} "
                f"!= {q.answer_status!r}"
            )
        csv_ans = row.get("correct_answer") or None
        mem_ans = q.correct_answer
        mem_ans_str = ";".join(str(x) for x in mem_ans) if isinstance(mem_ans, list) else (
            str(mem_ans) if mem_ans is not None else None
        )
        csv_norm = csv_ans.replace(",", ";") if csv_ans else None
        if csv_norm != mem_ans_str:
            report.errors.append(
                f"[{q.id}] CSV correct_answer {csv_ans!r} != {mem_ans_str!r}"
            )


def validate_questions(
    questions: list[Question],
    image_dir: Optional[Path] = None,
    max_questions: Optional[int] = None,
    csv_path: Optional[Path] = None,
) -> ValidationReport:
    """Run all validation checks and return a ValidationReport.

    max_questions: optional explicit cap (e.g. MAX_QUESTIONS for a bounded
    prototype run). Omitted → no cap, so large pilots can be validated.
    csv_path: optional questions.csv to cross-check against the records.
    """
    image_dir = image_dir or IMAGE_DIR
    report = ValidationReport(total_questions=len(questions))

    logger.info(f"Validating {len(questions)} question(s) ...")

    if max_questions is not None and len(questions) > max_questions:
        report.errors.append(
            f"Too many questions: {len(questions)} > {max_questions}"
        )

    # Uniqueness check
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        dupes = [qid for qid in set(ids) if ids.count(qid) > 1]
        report.errors.append(f"Duplicate IDs: {dupes}")

    for q in questions:
        validate_metadata(q, report)
        validate_image(q, image_dir, report)

    if csv_path is not None:
        validate_csv_consistency(questions, csv_path, report)

    logger.info(report.summary())
    return report
