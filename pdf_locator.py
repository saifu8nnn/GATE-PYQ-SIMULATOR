"""
pdf_locator.py — Find the Databases section start page in volume2.pdf.

Strategy
--------
The book is structured as numbered top-level sections.  Each section starts with
a two-part heading that occupies the same y-band on the page:

    Left column  : section number only, e.g. "5"   (size ~10.5, bold)
    Right column : section title,       e.g. "Databases (268)"  (size ~10.5, bold)

The Table of Contents (pages 1-5, 0-based) also contains the word "Databases" but
the entries there are small (size ~9.8) and appear inside long multi-column rows.

Algorithm
---------
1. Skip every page that looks like a TOC page (many purely-numeric lines at the
   same y-coordinate → it's a multi-column answer-key / TOC page).
2. On each remaining page, collect all BOLD lines whose font size is > 10 pt.
3. Look for a pair of bold lines on the same y-band where:
     - one line is *just* the section number (e.g. "5")
     - the other line starts with the section title (e.g. "Databases")
   These always co-occur on the same ~2-pt y-band.
4. Return the page index of the first such match.

Fallbacks
---------
If the strict heuristic finds nothing, relax progressively until a match is found.
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF

from utils import get_logger, iter_text_lines

logger = get_logger()

# ── Constants ──────────────────────────────────────────────────────────────────

# Minimum font size that a section-level heading can have
_HEADING_FONT_SIZE = 10.0

# How many leading pages to treat as front-matter (cover + TOC)
# The Databases section cannot appear this early.
_FRONT_MATTER_PAGES = 6

# Regex: a standalone section number like "5" or "12"
_SECTION_NUM_RE = re.compile(r"^\d{1,2}$")

# Y-coordinate tolerance (points) for two spans to be on the "same line"
_Y_TOLERANCE = 4.0


# ── TOC / answer-key page detector ────────────────────────────────────────────

def _is_toc_or_answer_key_page(page: fitz.Page) -> bool:
    """
    Return True if this page looks like a Table of Contents or answer-key page.

    Heuristic: if a large fraction of non-empty lines consist purely of digits
    (or short answer tokens like "A", "B", "C/D", numbers) arranged in many
    columns, it is a reference/TOC page and not a question page.
    """
    page_dict = page.get_text("dict")
    all_lines: list[str] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if text:
                all_lines.append(text)

    if len(all_lines) < 5:
        return False

    # Count lines that are pure numbers or very short answer tokens
    numeric_or_answer = sum(
        1 for l in all_lines
        if re.match(r"^[\d\.\:\;\s\-]+$", l) or re.match(r"^[A-D]$", l)
    )
    ratio = numeric_or_answer / len(all_lines)
    return ratio > 0.55


# ── Span-level line collector (returns rich info) ──────────────────────────────

def _get_bold_large_lines(page: fitz.Page) -> list[dict]:
    """
    Return every line on the page that is bold AND large (> _HEADING_FONT_SIZE).
    Each entry: {text, y0, y1, x0, x1, size}
    """
    results: list[dict] = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            sizes = [s.get("size", 0) for s in spans]
            flags = [s.get("flags", 0) for s in spans]
            max_size = max(sizes) if sizes else 0
            is_bold = any(f & 16 for f in flags)  # flag bit 4 = bold

            if is_bold and max_size >= _HEADING_FONT_SIZE:
                bbox = line.get("bbox", (0, 0, 0, 0))
                results.append({
                    "text":  text,
                    "y0":    bbox[1],
                    "y1":    bbox[3],
                    "x0":    bbox[0],
                    "x1":    bbox[2],
                    "size":  max_size,
                })
    return results


# ── Section heading detector ───────────────────────────────────────────────────

def _find_section_heading_on_page(
    page: fitz.Page,
    section_name: str,
) -> bool:
    """
    Return True if this page contains the top-level section heading for
    `section_name`.

    The heading consists of two bold/large lines at roughly the same y-position:
      - A standalone digit string (the section number)
      - A string that starts with `section_name`
    """
    bold_lines = _get_bold_large_lines(page)
    if not bold_lines:
        return False

    # Group by y-band
    name_lower = section_name.lower()
    for line in bold_lines:
        stripped = line["text"].strip()
        # Does this line start with the section title?
        if not stripped.lower().startswith(name_lower):
            continue
        # Find a companion line within Y_TOLERANCE that is a section number
        for other in bold_lines:
            if other is line:
                continue
            if abs(other["y0"] - line["y0"]) <= _Y_TOLERANCE:
                if _SECTION_NUM_RE.match(other["text"].strip()):
                    logger.debug(
                        f"  Heading pair found: [{other['text'].strip()}] + "
                        f"[{stripped[:60]}] at y={line['y0']:.1f}"
                    )
                    return True
    return False


# ── Main locator ───────────────────────────────────────────────────────────────

def find_section_start(doc: fitz.Document, section_name: str = "Databases") -> int:
    """
    Locate the page index (0-based) where the `section_name` section begins.

    Raises RuntimeError if the section cannot be found.
    """
    logger.info(f"Searching for section heading: '{section_name}'")

    # ── Pass 1: strict heuristic (bold+large paired heading) ─────────────────
    for page_idx in range(_FRONT_MATTER_PAGES, len(doc)):
        page = doc[page_idx]

        if _is_toc_or_answer_key_page(page):
            logger.debug(f"  p{page_idx}: skipping (TOC/answer-key page)")
            continue

        if _find_section_heading_on_page(page, section_name):
            logger.info(
                f"  Section '{section_name}' found on page {page_idx} "
                f"(1-based: {page_idx + 1}) via bold-heading heuristic"
            )
            return page_idx

    # ── Pass 2: relax — any bold line that starts with section_name ───────────
    logger.warning(
        "Strict heading heuristic found nothing. Relaxing to bold-line scan."
    )
    for page_idx in range(_FRONT_MATTER_PAGES, len(doc)):
        page = doc[page_idx]
        if _is_toc_or_answer_key_page(page):
            continue
        for line in _get_bold_large_lines(page):
            if line["text"].strip().lower().startswith(section_name.lower()):
                logger.warning(
                    f"  Relaxed match on page {page_idx}: '{line['text'].strip()[:60]}'"
                )
                return page_idx

    # ── Pass 3: raw text search, skip TOC ────────────────────────────────────
    logger.warning("Bold-line scan also failed. Falling back to raw text search.")
    for page_idx in range(_FRONT_MATTER_PAGES, len(doc)):
        page = doc[page_idx]
        if _is_toc_or_answer_key_page(page):
            continue
        text = page.get_text("text")
        for line in text.split("\n"):
            stripped = line.strip()
            if re.match(
                rf"^{re.escape(section_name)}\s*(\(\d+\))?$",
                stripped,
                re.IGNORECASE,
            ):
                logger.warning(f"  Raw-text match on page {page_idx}: '{stripped}'")
                return page_idx

    raise RuntimeError(
        f"Could not locate the '{section_name}' section in volume2.pdf.\n"
        "Please check that the PDF is the correct GATE Overflow Volume 2."
    )


# ── Section-end locator ────────────────────────────────────────────────────────

def find_section_end(doc: fitz.Document, start_page: int) -> Optional[int]:
    """
    Find the first page after `start_page` that contains a *different*
    top-level section heading (i.e. a bold/large section number paired with
    a title that does NOT start with the current section name).

    Returns the page index or None (meaning: use end of PDF).
    """
    # The section number on the start page
    start_page_obj = doc[start_page]
    bold_lines = _get_bold_large_lines(start_page_obj)
    current_section_num: Optional[str] = None
    for line in bold_lines:
        if _SECTION_NUM_RE.match(line["text"].strip()):
            current_section_num = line["text"].strip()
            break

    if current_section_num is None:
        logger.warning("Could not determine current section number; section end may be imprecise.")

    for page_idx in range(start_page + 1, len(doc)):
        page = doc[page_idx]

        if _is_toc_or_answer_key_page(page):
            continue

        bold = _get_bold_large_lines(page)
        if not bold:
            continue

        # Look for a standalone section number that differs from current_section_num
        nums_on_page = [
            l for l in bold
            if _SECTION_NUM_RE.match(l["text"].strip())
        ]
        for num_line in nums_on_page:
            num = num_line["text"].strip()
            if current_section_num and num == current_section_num:
                continue  # same section sub-numbering

            # Is there a companion heading line at the same y?
            for other in bold:
                if other is num_line:
                    continue
                if abs(other["y0"] - num_line["y0"]) <= _Y_TOLERANCE:
                    heading = other["text"].strip()
                    if len(heading) > 3 and not heading[0].isdigit():
                        logger.debug(
                            f"  Next section '{heading[:50]}' found on page {page_idx}"
                        )
                        return page_idx

    return None
