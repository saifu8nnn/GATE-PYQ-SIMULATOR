"""
answer_key_reader.py — Parse the dedicated Answer Keys section in volume2.pdf.

PDF structure (confirmed by inspection)
----------------------------------------
Near the end of each subject section there is a dedicated multi-column
Answer Keys table.  Its layout on the page is:

    Answer Keys          <- bold header line
    5.1.1                <- section number (bold)
    N/A                  <- answer value (plain)
    5.1.2
    N/A
    5.1.5
    B
    5.1.7
    B
    ...

The section numbers follow the pattern  <section>.<subsection>.<question-index>
e.g. 5.1.5  (section 5 = Databases, subsection 1 = B Tree, question 5).

Answer formats observed:
    Single option     : "A" "B" "C" "D"
    Multiple options  : "A;B;C"  "A;C;D"   (MSQ)
    Numeric           : "42"  "3.14"  "52"
    Range             : "50 : 52"  "7.07:7.09"  "819 : 820 ; 205 : 205"
    True/False        : "True"  "False"
    Not available     : "N/A"
    Unknown/special   : "X"     (treat as needs_review)

This module:
1. Scans the ENTIRE PDF for "Answer Keys" header pages.
2. Parses each key-value pair into a dict {section_number -> ParsedAnswer}.
3. Returns the complete lookup table.

A ParsedAnswer carries:
    raw          : str   — verbatim text from the PDF
    value        : Any   — normalised Python value
    answer_type  : str   — "MCQ" | "MSQ" | "NAT" | "RANGE" | "BOOL" |
                           "NOT_AVAILABLE" | "UNKNOWN"
    source_page  : int   — 0-based PDF page index where the entry was found
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import fitz  # PyMuPDF

from utils import get_logger

logger = get_logger()

# ── Regex helpers ──────────────────────────────────────────────────────────────

_SECTION_NUM_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Single A-D letter (MCQ), optionally followed by a period / trailing text
_MCQ_RE = re.compile(r"^([A-D])$", re.IGNORECASE)

# Leading option letter with trailing punctuation or explanatory text,
# e.g. "A."  "A)"  "A. TCP, but not UDP"  "A.  only"
_MCQ_LEADING_RE = re.compile(r"^([A-D])\s*[.)]\s*\S*")

# Multiple letters separated by semicolons (MSQ)
_MSQ_RE = re.compile(r"^[A-D](?:;[A-D])+$", re.IGNORECASE)

# Pure integer or decimal
_NAT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

# Range: "50 : 52"  "7.07:7.09"  — may contain spaces around colon
_RANGE_RE = re.compile(
    r"^[+-]?\d+(?:\.\d+)?\s*:\s*[+-]?\d+(?:\.\d+)?$"
)

# Complex multi-range: "819 : 820 ; 205 : 205"
_MULTI_RANGE_RE = re.compile(
    r"^[+-]?\d+(?:\.\d+)?\s*:\s*[+-]?\d+(?:\.\d+)?(?:\s*;\s*[+-]?\d+(?:\.\d+)?\s*:\s*[+-]?\d+(?:\.\d+)?)+$"
)

_TRUE_FALSE_RE = re.compile(r"^(true|false)$", re.IGNORECASE)
_NA_RE = re.compile(r"^N/A$", re.IGNORECASE)
_UNKNOWN_RE = re.compile(r"^X$", re.IGNORECASE)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedAnswer:
    raw: str                        # verbatim text from PDF
    value: Any                      # normalised value
    answer_type: str                # see module docstring
    source_page: int                # 0-based PDF page index

    def is_available(self) -> bool:
        return self.answer_type not in ("NOT_AVAILABLE", "UNKNOWN")


# ── Answer value parser ────────────────────────────────────────────────────────

def _parse_answer_value(raw: str, page_idx: int) -> ParsedAnswer:
    """
    Classify and normalise a raw answer string.
    Never raises — falls back to UNKNOWN.

    Normalisations are conservative: trailing punctuation on a bare option
    letter ("A.") and an option letter followed by descriptive text
    ("A. TCP, but not UDP") normalise to the option label while preserving the
    verbatim text in `raw`. Anything genuinely ambiguous (truncated ranges
    like "17 :", unknown sentinels "X", malformed "Q-Q") stays UNKNOWN so it
    is surfaced as needs_review instead of being presented as a real answer.
    """
    s = raw.strip()

    if _NA_RE.match(s):
        return ParsedAnswer(raw=s, value=None, answer_type="NOT_AVAILABLE", source_page=page_idx)

    if _UNKNOWN_RE.match(s):
        return ParsedAnswer(raw=s, value=None, answer_type="UNKNOWN", source_page=page_idx)

    if _TRUE_FALSE_RE.match(s):
        val = s.lower() == "true"
        return ParsedAnswer(raw=s, value=val, answer_type="BOOL", source_page=page_idx)

    if _MCQ_RE.match(s):
        return ParsedAnswer(raw=s, value=s.upper(), answer_type="MCQ", source_page=page_idx)

    if _MSQ_RE.match(s):
        opts = sorted(o.strip().upper() for o in s.split(";"))
        return ParsedAnswer(raw=s, value=opts, answer_type="MSQ", source_page=page_idx)

    if _MULTI_RANGE_RE.match(s):
        return ParsedAnswer(raw=s, value=s, answer_type="RANGE", source_page=page_idx)

    if _RANGE_RE.match(s):
        parts = [p.strip() for p in s.split(":")]
        try:
            lo = float(parts[0]) if "." in parts[0] else int(parts[0])
            hi = float(parts[1]) if "." in parts[1] else int(parts[1])
            return ParsedAnswer(raw=s, value=[lo, hi], answer_type="RANGE", source_page=page_idx)
        except (ValueError, IndexError):
            pass

    if _NAT_RE.match(s):
        try:
            val = float(s) if "." in s else int(s)
            return ParsedAnswer(raw=s, value=val, answer_type="NAT", source_page=page_idx)
        except ValueError:
            pass

    # Option letter with trailing junk or explanatory text → MCQ label.
    # Only the bare label becomes the value; raw keeps the full text.
    m_letter = _MCQ_LEADING_RE.match(s)
    if m_letter:
        letter = m_letter.group(1).upper()
        return ParsedAnswer(raw=s, value=letter, answer_type="MCQ", source_page=page_idx)

    # Fallback: store raw string but mark as UNKNOWN for manual review
    logger.warning(f"  Answer key: unrecognised format {s!r} on page {page_idx}")
    return ParsedAnswer(raw=s, value=s, answer_type="UNKNOWN", source_page=page_idx)


# ── Page-level parser ──────────────────────────────────────────────────────────

def _is_answer_key_page(page: fitz.Page) -> bool:
    """
    Return True if this page contains the 'Answer Keys' section header.
    The header is bold and appears as a standalone line.
    """
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            bold = any(s.get("flags", 0) & 16 for s in spans)
            if bold and re.match(r"^answer\s*keys?$", text, re.IGNORECASE):
                return True
    return False


def _looks_like_heading(text: str) -> bool:
    """
    True if a candidate 'answer value' is actually a question heading that
    leaked into the value column (e.g. "Transaction and Concurrency: GATE IT
    2008 | Question: 63"). Pairing such a text as an answer would corrupt the
    key/value alignment for that page.
    """
    if len(text) > 60:
        return True
    if "| Question" in text or "Question:" in text:
        return True
    if re.search(r":\s*GATE\s+(?:CSE|IT)\b", text, re.IGNORECASE):
        return True
    if re.match(r"^gate(?:(?:cse|it)-\d{4}|\d{4})\b", text, re.IGNORECASE):
        return True
    return False


def _parse_answer_key_page(
    page: fitz.Page,
    page_idx: int,
    table: dict[str, ParsedAnswer],
    audit: Optional[dict] = None,
) -> int:
    """
    Parse all section_number / answer pairs on this page into `table`.
    Returns the count of entries added.

    If `audit` is provided it is populated with duplicate/conflict evidence:
        audit["duplicates"] : list of (key, page, first_raw, second_raw)
        audit["conflicts"]  : subset where the two raw values disagree
    """
    # Extract all non-empty text lines in reading order (top-to-bottom)
    lines: list[str] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(
                s.get("text", "") for s in line.get("spans", [])
            ).strip()
            if text:
                lines.append(text)

    # The table is laid out as alternating pairs: key / value / key / value ...
    # But on multi-column pages the order from get_text may interleave columns.
    # Strategy: collect all section-number tokens and their following values.
    # We walk the list and whenever we see a section_number, the NEXT token
    # that is not itself a section number is the answer.
    added = 0
    i = 0
    while i < len(lines):
        token = lines[i].strip()
        if _SECTION_NUM_RE.match(token):
            # Look ahead for the answer value
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if not candidate:
                    j += 1
                    continue
                if _SECTION_NUM_RE.match(candidate):
                    # Next key without a value — skip, handle at j
                    break
                if _looks_like_heading(candidate):
                    # NOT an answer value — record the key as UNKNOWN so the
                    # record surfaces as needs_review instead of silently
                    # pairing it with unrelated text.
                    if token not in table:
                        table[token] = ParsedAnswer(
                            raw=candidate, value=None,
                            answer_type="UNKNOWN", source_page=page_idx,
                        )
                        logger.warning(
                            f"  AK: {token} paired with heading-like text on "
                            f"p{page_idx} — marked UNKNOWN"
                        )
                    break
                # This is the answer
                if token not in table:
                    parsed = _parse_answer_value(candidate, page_idx)
                    table[token] = parsed
                    added += 1
                    logger.debug(f"  AK: {token} -> {parsed.raw!r} ({parsed.answer_type})")
                else:
                    # Duplicate key — keep first, record evidence for audit
                    first = table[token]
                    if audit is not None:
                        entry = (token, page_idx, first.raw, candidate)
                        audit.setdefault("duplicates", []).append(entry)
                        if first.raw.strip().upper() != candidate.strip().upper():
                            audit.setdefault("conflicts", []).append(entry)
                        logger.warning(
                            f"  AK duplicate key {token}: "
                            f"{first.raw!r} (p{first.source_page}) vs "
                            f"{candidate!r} (p{page_idx})"
                        )
                i = j  # advance past the value
                break
            else:
                # No value found before end of page
                pass
        i += 1

    return added


# ── Main public function ───────────────────────────────────────────────────────

def load_answer_key_table(
    doc: fitz.Document,
    audit: Optional[dict] = None,
) -> dict[str, ParsedAnswer]:
    """
    Scan the entire PDF and build a complete answer-key lookup table.

    Parameters
    ----------
    doc   : open PDF
    audit : optional dict; on return it contains
            "duplicates" — every (key, page, first_raw, second_raw) seen twice
            "conflicts"  — the subset where the two values disagree
            so callers can measure index integrity instead of trusting a
            table that already silently dropped duplicates.

    Returns
    -------
    dict mapping section_number (str, e.g. "5.1.5") -> ParsedAnswer
    """
    table: dict[str, ParsedAnswer] = {}
    pages_found: list[int] = []
    if audit is not None:
        audit.setdefault("duplicates", [])
        audit.setdefault("conflicts", [])

    for page_idx, page in enumerate(doc):
        if _is_answer_key_page(page):
            pages_found.append(page_idx)
            count = _parse_answer_key_page(page, page_idx, table, audit=audit)
            logger.debug(f"  Answer-key page {page_idx}: {count} entries parsed")

    # Also scan pages immediately after each found page (table may span pages)
    extra_pages = set()
    for p in pages_found:
        for ep in range(p + 1, min(p + 5, len(doc))):
            if ep not in pages_found:
                extra_pages.add(ep)

    for page_idx in sorted(extra_pages):
        page = doc[page_idx]
        count = _parse_answer_key_page(page, page_idx, table, audit=audit)
        if count > 0:
            logger.debug(f"  Answer-key continuation page {page_idx}: {count} entries")

    logger.info(
        f"Answer key table loaded: {len(table)} entries "
        f"from {len(pages_found)} header page(s): {pages_found}"
    )
    return table
