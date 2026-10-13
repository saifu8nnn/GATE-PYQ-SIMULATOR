"""
question_detector.py — Detect question boundaries within the Databases section.

Each question in the PDF has the structure:

    <section-number>          e.g. "5.1.5"   (bold, left margin, same y as heading)
    <Topic>: GATE CSE <Year> [Set <N>] | Question: <number>   (bold heading)
    ... question content (text, images, options) ...
    <tag-line>   e.g. "gatecse-2020 databases b-tree 2-marks"
    Answer key☟

The bold section number (5.x.y) appears at the SAME y-coordinate as the
heading, but in the left-margin column (x ≈ 42-75).

This module captures:
- The section number (e.g. "5.1.5") for answer-key lookup.
- The option lines (A./B./C./D.) for MCQ type inference.
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF

from config import (
    QUESTION_HEADING_RE,
    TOP_PADDING,
    BOTTOM_PADDING,
)
from models import QuestionBoundary
from utils import get_logger, page_height

logger = get_logger()

# ── Patterns ───────────────────────────────────────────────────────────────────

_ANSWER_KEY_RE = re.compile(
    r"^answer\s*(?:key)?\s*[☟:→\-–]?",
    re.IGNORECASE,
)

_ANSWER_VALUE_RE = re.compile(
    r"^answer\s*(?:key)?\s*[☟:→\-–]?\s*(.+)$",
    re.IGNORECASE,
)

_TAG_LINE_RE = re.compile(
    r"^gate(?:(?:cse|it)-\d{4}|\d{4})\b",
    re.IGNORECASE,
)

_OPTION_LINE_RE = re.compile(r"^[A-D]\.\s", re.IGNORECASE)

# Section number: digits.digits.digits  e.g. "5.1.5"
_SECTION_NUM_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Y-tolerance: section number and heading appear on the same horizontal band
_Y_TOLERANCE = 6.0


# ── Rich line iterator ─────────────────────────────────────────────────────────

def _iter_lines_rich(page: fitz.Page):
    """
    Yield (text, y0, y1, x0, x1, is_bold) for every non-empty line.
    """
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            bbox = line.get("bbox", (0, 0, 0, 0))
            bold = any(s.get("flags", 0) & 16 for s in spans)
            if text.strip():
                yield text, bbox[1], bbox[3], bbox[0], bbox[2], bold


# ── Main detector ──────────────────────────────────────────────────────────────

def detect_question_boundaries(
    doc: fitz.Document,
    section_start_page: int,
    section_end_page: Optional[int],
    max_questions: int,
) -> list[QuestionBoundary]:
    """
    Scan pages and return at most max_questions QuestionBoundary objects.

    For each question heading found, also look for a bold section-number token
    (matching \\d+\\.\\d+\\.\\d+) at the same y-band — this is the key for
    the answer-key lookup table.
    """
    end_page = section_end_page if section_end_page is not None else len(doc) - 1
    logger.info(
        f"Detecting question boundaries: pages {section_start_page}-{end_page}"
    )

    boundaries: list[QuestionBoundary] = []
    current: Optional[QuestionBoundary] = None

    def close_current(end_p: int, end_y: float, answer: Optional[str] = None) -> None:
        nonlocal current
        if current is None:
            return
        ph = page_height(doc[end_p])
        current.end_page = end_p
        current.end_y = max(0.0, min(end_y, ph))
        if answer and current.answer_text is None:
            current.answer_text = answer
        boundaries.append(current)
        logger.debug(
            f"  Closed: p{current.start_page}:{current.start_y:.1f}"
            f" - p{current.end_page}:{current.end_y:.1f}"
            f"  sec={current.section_number!r}"
            f"  opts={current.option_lines}"
            f"  '{current.heading_text[:50]}'"
        )
        current = None

    for page_idx in range(section_start_page, end_page + 1):
        page = doc[page_idx]
        ph = page_height(page)

        # ── Collect all rich lines for this page ──────────────────────────────
        page_lines = list(_iter_lines_rich(page))

        # ── Build a y-band -> section_number lookup (bold, left-margin) ───────
        # Section numbers are bold and their x0 is small (left margin, < 100pt)
        section_nums_by_y: list[tuple[float, str]] = []
        for text, y0, y1, x0, x1, bold in page_lines:
            stripped = text.strip()
            if bold and x0 < 100 and _SECTION_NUM_RE.match(stripped):
                section_nums_by_y.append((y0, stripped))

        for text, y0, y1, x0, x1, bold in page_lines:
            stripped = text.strip()
            if not stripped:
                continue

            # ── New question heading? ─────────────────────────────────────────
            heading_match = QUESTION_HEADING_RE.match(stripped)
            if heading_match:
                close_current(page_idx, y0 - BOTTOM_PADDING)
                if len(boundaries) >= max_questions:
                    logger.info(f"Reached {max_questions} boundaries — stopping.")
                    return boundaries

                # Find section number at same y-band
                sec_num: Optional[str] = None
                for sy, sn in section_nums_by_y:
                    if abs(sy - y0) <= _Y_TOLERANCE:
                        sec_num = sn
                        break

                current = QuestionBoundary(
                    heading_text=stripped,
                    start_page=page_idx,
                    start_y=max(0.0, y0 - TOP_PADDING),
                    end_page=page_idx,
                    end_y=ph,
                    tag_line=None,
                    answer_text=None,
                    heading_match=heading_match,
                    option_lines=[],
                    section_number=sec_num,
                )
                logger.debug(
                    f"  Opened: p{page_idx}:{y0:.1f}  sec={sec_num!r}"
                    f"  '{stripped[:60]}'"
                )
                continue

            if current is None:
                continue

            # ── Tag line? ─────────────────────────────────────────────────────
            if _TAG_LINE_RE.match(stripped):
                if current.tag_line is None:
                    current.tag_line = stripped
                continue

            # ── Answer key? ───────────────────────────────────────────────────
            if _ANSWER_KEY_RE.match(stripped):
                val_match = _ANSWER_VALUE_RE.match(stripped)
                answer_text: Optional[str] = None
                if val_match:
                    candidate = val_match.group(1).strip()
                    if candidate and candidate not in ("☟", "→", "-", "–"):
                        answer_text = candidate
                close_current(page_idx, y0 - BOTTOM_PADDING, answer=answer_text)
                if len(boundaries) >= max_questions:
                    logger.info(f"Reached {max_questions} boundaries — stopping.")
                    return boundaries
                continue

            # ── Option line? ──────────────────────────────────────────────────
            if _OPTION_LINE_RE.match(stripped):
                letter = stripped[0].upper()
                if letter not in current.option_lines:
                    current.option_lines.append(letter)

        # End of page: update tentative end
        if current is not None and current.end_page <= page_idx:
            current.end_page = page_idx
            current.end_y = ph

    # Close any still-open boundary
    if current is not None:
        close_current(current.end_page, page_height(doc[current.end_page]))

    logger.info(f"Total boundaries detected: {len(boundaries)}")
    return boundaries[:max_questions]


# ── Debug helper ───────────────────────────────────────────────────────────────

def print_boundaries(boundaries: list[QuestionBoundary]) -> None:
    print("\n" + "=" * 60)
    print("DETECTED QUESTION BOUNDARIES")
    print("=" * 60)
    for i, b in enumerate(boundaries, 1):
        m = b.heading_match
        if m:
            info = (
                f"  topic={m.group('topic')!r:24s}  "
                f"year={m.group('year')}  "
                f"q={m.group('question_number')}"
            )
        else:
            info = f"  heading={b.heading_text[:60]!r}"
        print(
            f"[{i:02d}] p{b.start_page}:{b.start_y:6.1f} -> "
            f"p{b.end_page}:{b.end_y:6.1f}  sec={b.section_number!r}"
        )
        print(info)
        if b.tag_line:
            print(f"       tag: {b.tag_line}")
        if b.answer_text:
            print(f"       ans: {b.answer_text[:60]}")
        if b.option_lines:
            print(f"       options: {b.option_lines}")
        print()
