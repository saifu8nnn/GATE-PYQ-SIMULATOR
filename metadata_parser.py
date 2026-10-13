"""
metadata_parser.py — Extract structured metadata from a QuestionBoundary.

Answer key lookup strategy (in priority order)
-----------------------------------------------
1. Use the section_number captured by question_detector (e.g. "5.1.5") to
   look up the answer directly in the pre-built answer_key_table.
   This is the reliable path: section number -> answer-key page -> value.

2. As a fallback, try to parse an inline answer from boundary.answer_text
   (the text on the "Answer key☟" line itself, if present).
   This is rarely populated in this PDF format.

3. If neither yields a result, set answer_status = NOT_AVAILABLE.

Answer status semantics
-----------------------
- "verified"      : answer found in dedicated answer-key table via section number.
                    The association is positively confirmed.
- "needs_review"  : inline answer parsed but not confirmed via table;
                    OR no section_number / section number absent from the index
                    (an unresolved mapping — NOT a confirmed N/A).
- "not_available" : answer-key table was checked and the entry is explicitly
                    N/A in the source.
"""

from __future__ import annotations

import re
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from answer_key_reader import ParsedAnswer

import config as _config  # imported as module so defaults are always current

from config import (
    TYPE_MAP,
    DIFFICULTY_TOKENS,
    MARKS_TOKENS,
    SOURCE_PDF_NAME,
)
from models import Question, QuestionBoundary, AnswerStatus, QuestionType
from utils import get_logger, make_question_id

logger = get_logger()


# ── Tag-line parser ────────────────────────────────────────────────────────────

_TAG_YEAR_RE = re.compile(
    r"^gate(?:(?:cse|it)-(\d{4})|(\d{4}))\b",
    re.IGNORECASE,
)


def parse_tag_line(tag_line: Optional[str]) -> dict:
    result: dict = {
        "year":          None,
        "question_type": None,
        "marks":         None,
        "difficulty":    None,
    }
    if not tag_line:
        return result

    line = tag_line.strip().lower()
    year_m = _TAG_YEAR_RE.match(line)
    if year_m:
        year_str = year_m.group(1) or year_m.group(2)
        try:
            result["year"] = int(year_str)
        except (TypeError, ValueError):
            pass

    for token in re.split(r"[\s,]+", line):
        if token in MARKS_TOKENS:
            result["marks"] = MARKS_TOKENS[token]
        elif token in DIFFICULTY_TOKENS:
            result["difficulty"] = token
        elif token in TYPE_MAP:
            result["question_type"] = TYPE_MAP[token]

    return result


# ── Question number sanitizer ──────────────────────────────────────────────────

def _sanitize_question_number(raw: str) -> str:
    """Strip trailing stray punctuation; preserve mid-string dots and dashes."""
    return raw.strip().rstrip(".,;:!?")


# ── Answer resolution from key table ──────────────────────────────────────────

def _resolve_answer_from_table(
    section_number: Optional[str],
    answer_key_table: dict,
) -> tuple[Any, str, Optional[str], Optional[str]]:
    """
    Look up the answer from the pre-built answer_key_table.

    Returns (correct_answer, answer_status, answer_source, answer_evidence).
    """
    if not section_number:
        # Cannot attempt a mapping at all — unresolved, NOT a confirmed N/A.
        return None, AnswerStatus.NEEDS_REVIEW, None, (
            "no section_number captured for this question — answer mapping unresolved"
        )

    if not answer_key_table:
        return None, AnswerStatus.NEEDS_REVIEW, "answer_key_index", (
            f"{section_number} -> answer key table not loaded"
        )

    parsed = answer_key_table.get(section_number)
    if parsed is None:
        # Section number exists but the index has no entry — unresolved.
        return None, AnswerStatus.NEEDS_REVIEW, "answer_key_index", (
            f"{section_number} -> not present in answer key index"
        )

    evidence = f"{section_number} -> {parsed.raw!r} (p{parsed.source_page})"

    if parsed.answer_type == "NOT_AVAILABLE":
        return None, AnswerStatus.NOT_AVAILABLE, "answer_key_page", evidence

    if parsed.answer_type == "UNKNOWN":
        return None, AnswerStatus.NEEDS_REVIEW, "answer_key_page", evidence

    # Genuine answer found
    return parsed.value, AnswerStatus.VERIFIED, "answer_key_page", evidence


# ── Inline answer fallback ─────────────────────────────────────────────────────

_MCQ_INLINE_RE = re.compile(
    r"(?:answer\s*(?:key)?\s*[☟:→\-–]|ans\s*[:\-–])\s*([A-D])\b",
    re.IGNORECASE,
)
_NAT_INLINE_RE = re.compile(
    r"(?:answer\s*(?:key)?\s*[☟:→\-–]|ans\s*[:\-–])\s*([\-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _resolve_answer_inline(
    answer_text: Optional[str],
    question_type: Optional[str],
) -> tuple[Any, str, Optional[str], Optional[str]]:
    """Fallback: parse inline answer text from the Answer key line."""
    if not answer_text:
        return None, AnswerStatus.NOT_AVAILABLE, None, None

    text = answer_text.strip()

    # Bare single letter
    if re.match(r"^[A-D]$", text.upper()):
        return text.upper(), AnswerStatus.NEEDS_REVIEW, "inline", text

    m = _MCQ_INLINE_RE.search(text)
    if m:
        return m.group(1).upper(), AnswerStatus.NEEDS_REVIEW, "inline", text

    m2 = _NAT_INLINE_RE.search(text)
    if m2:
        val = m2.group(1)
        try:
            return (float(val) if "." in val else int(val)), AnswerStatus.NEEDS_REVIEW, "inline", text
        except ValueError:
            pass

    return None, AnswerStatus.NOT_AVAILABLE, None, None


# ── Type reconciliation with answer ───────────────────────────────────────────

def _reconcile_type_with_answer(
    question_type: Optional[str],
    parsed_answer_type: Optional[str],
    option_lines: list,
) -> Optional[str]:
    """
    Cross-check question_type against what the answer key says.
    Never overrides a tag-derived type. Only fills in None.
    """
    if question_type is not None:
        return question_type

    # Infer from answer type
    if parsed_answer_type == "MCQ":
        # Only accept if options were detected in the boundary
        if len(option_lines) >= 3:
            return QuestionType.MCQ
    elif parsed_answer_type == "MSQ":
        return QuestionType.MSQ
    elif parsed_answer_type == "NAT":
        return QuestionType.NAT
    elif parsed_answer_type in ("RANGE",):
        return QuestionType.NAT

    # Infer MCQ purely from detected options (no answer key needed)
    if all(opt in option_lines for opt in ["A", "B", "C", "D"]):
        return QuestionType.MCQ
    if len(option_lines) >= 3:
        return QuestionType.MCQ

    return None


# ── Main parser ────────────────────────────────────────────────────────────────

def parse_metadata(
    boundary: QuestionBoundary,
    answer_key_table: Optional[dict] = None,
    subject: Optional[str] = None,
) -> dict:
    """
    Combine all sources into a complete metadata dict.

    Parameters
    ----------
    boundary         : QuestionBoundary from question_detector
    answer_key_table : Optional pre-built {section_number -> ParsedAnswer} dict
    subject          : Subject determined from the PDF section actually being
                       processed (NOT from a global config value). If None,
                       falls back to config.SECTION_NAME for backwards
                       compatibility with old callers.
    """
    m = boundary.heading_match
    if m is None:
        raise ValueError(
            f"QuestionBoundary has no heading_match: {boundary.heading_text!r}"
        )

    # ── From heading ──────────────────────────────────────────────────────────
    topic         = m.group("topic").strip().title() if m.group("topic") else None
    year_str      = m.group("year")
    set_raw       = m.group("set")
    q_num_raw     = m.group("question_number").strip()
    q_num_clean   = _sanitize_question_number(q_num_raw)

    try:
        year = int(year_str)
    except (TypeError, ValueError):
        year = None

    set_tag = f"Set {set_raw}" if set_raw else None

    # ── From tag line ─────────────────────────────────────────────────────────
    tag_data = parse_tag_line(boundary.tag_line)
    if year is None:
        year = tag_data["year"]
    if year is None:
        logger.warning(f"  Could not determine year: {boundary.heading_text!r}")

    question_type = tag_data["question_type"]
    marks         = tag_data["marks"]
    difficulty    = tag_data["difficulty"]

    # ── Options metadata ──────────────────────────────────────────────────────
    opts = boundary.option_lines
    options_present        = len(opts) > 0 if opts else None
    option_labels_detected = sorted(opts) if opts else None

    # ── Answer lookup (table first, inline fallback) ──────────────────────────
    correct_answer, answer_status, answer_source, answer_evidence = \
        _resolve_answer_from_table(boundary.section_number, answer_key_table or {})

    if correct_answer is None and answer_status == AnswerStatus.NEEDS_REVIEW:
        # Mapping is unresolved — try inline "Answer key" line as a fallback.
        # Inline results are always needs_review (never auto-verified), and an
        # explicit source N/A (not_available) is never overridden here.
        inline_answer, inline_status, inline_source, inline_evidence = \
            _resolve_answer_inline(boundary.answer_text, question_type)
        if inline_answer is not None:
            correct_answer, answer_status = inline_answer, inline_status
            answer_source, answer_evidence = inline_source, inline_evidence

    # ── Get answer_type for type reconciliation ───────────────────────────────
    parsed_answer_type = None
    if answer_key_table and boundary.section_number:
        pa = answer_key_table.get(boundary.section_number)
        if pa:
            parsed_answer_type = pa.answer_type

    # ── Reconcile question_type ───────────────────────────────────────────────
    question_type = _reconcile_type_with_answer(
        question_type, parsed_answer_type, opts
    )

    # ── ID ────────────────────────────────────────────────────────────────────
    question_id    = make_question_id(year=year or 0, question_number=q_num_clean, set_tag=set_tag)
    image_path_rel = f"images/{question_id}.png"

    # ── Source pages ──────────────────────────────────────────────────────────
    if boundary.start_page == boundary.end_page:
        source_pages = [boundary.start_page]
    else:
        source_pages = list(range(boundary.start_page, boundary.end_page + 1))

    if subject is None:
        subject = getattr(_config, "SECTION_NAME", "UNKNOWN")

    return {
        "id":                    question_id,
        "exam":                  "GATE CSE",
        "year":                  year,
        "set":                   set_tag,
        "subject":               subject,
        "topic":                 topic,
        "subtopic":              None,
        "question_number":       q_num_clean,
        "question_number_raw":   q_num_raw,
        "section_number":        boundary.section_number,
        "question_type":         question_type,
        "marks":                 marks,
        "difficulty":            difficulty,
        "options_present":       options_present,
        "option_labels_detected": option_labels_detected,
        "correct_answer":        correct_answer,
        "answer_status":         answer_status,
        "answer_source":         answer_source,
        "answer_evidence":       answer_evidence,
        "image":                 image_path_rel,
        "source_pdf":            SOURCE_PDF_NAME,
        "source_pages":          source_pages,
        "verified":              False,
        "notes":                 None,
        "extraction_version":    getattr(_config, "EXTRACTION_VERSION", None),
    }


def build_question(
    boundary: QuestionBoundary,
    answer_key_table: Optional[dict] = None,
    subject: Optional[str] = None,
) -> Question:
    """Build a Question dataclass from a QuestionBoundary.

    `subject` must be the name of the PDF section the boundary was detected in.
    """
    meta = parse_metadata(boundary, answer_key_table, subject=subject)
    return Question(**meta)
