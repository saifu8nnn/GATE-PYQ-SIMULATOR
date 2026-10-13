"""
utils.py — Shared helper functions for the GATE PYQ extraction pipeline.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import fitz  # PyMuPDF


# ── Logging setup ─────────────────────────────────────────────────────────────

def get_logger(name: str = "gate_pyq") -> logging.Logger:
    """Return a consistently-configured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "[%(levelname)s] %(asctime)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


logger = get_logger()


# ── File / directory helpers ──────────────────────────────────────────────────

def ensure_dirs(*dirs: Path) -> None:
    """Create directories if they do not exist."""
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def verify_pdf(pdf_path: Path) -> None:
    """Raise FileNotFoundError if the PDF is missing."""
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}\n"
            f"Please place volume2.pdf in: {pdf_path.parent}"
        )
    logger.info(f"PDF found: {pdf_path}")


# ── PDF helpers ───────────────────────────────────────────────────────────────

def open_pdf(pdf_path: Path) -> fitz.Document:
    doc = fitz.open(str(pdf_path))
    logger.info(f"Opened PDF — pages: {len(doc)}")
    return doc


def get_page_text(page: fitz.Page) -> str:
    """
    Extract plain text from a page.
    Used ONLY for locating questions and parsing metadata —
    never as the displayed question content.
    """
    return page.get_text("text")


def get_page_dict(page: fitz.Page) -> dict:
    """
    Extract text as a structured dict with coordinates.
    Used to locate the y-positions of headings and boundaries.
    """
    return page.get_text("dict")


# ── Coordinate helpers ────────────────────────────────────────────────────────

def page_height(page: fitz.Page) -> float:
    return page.rect.height


def page_width(page: fitz.Page) -> float:
    return page.rect.width


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Text block helpers ────────────────────────────────────────────────────────

def iter_text_lines(page: fitz.Page):
    """
    Yield (line_text, y0, y1, x0, x1) for every line on the page.
    Iterates through blocks → lines in the 'dict' representation.
    """
    page_dict = get_page_dict(page)
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:      # type 0 = text block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            bbox = line.get("bbox", (0, 0, 0, 0))
            x0, y0, x1, y1 = bbox
            yield text, y0, y1, x0, x1


# ── ID generation ─────────────────────────────────────────────────────────────

def make_question_id(
    year: int,
    question_number: str,
    set_tag: Optional[str] = None,
) -> str:
    """
    Deterministically generate a permanent question ID.

    The question_number is sanitized for use in an ID/filename:
      - Lowercased, whitespace stripped
      - Trailing punctuation (commas, dots, semicolons) removed
      - Remaining characters outside [a-z0-9.-] replaced by '-'
        (e.g. "," in "01,viii" → "-"; meaningful parts are kept,
        never dropped: "1.25", "14a", "2-ii", "37,isro-dec2017-55")
      - The original unsanitized value is preserved in
        Question.question_number_raw

    Determinism: the same inputs always yield the same ID.
    If nothing usable remains, a stable sha1-based suffix is used so that
    distinct raw numbers cannot collapse into one ID.

    Examples:
        gate-cse-2024-s1-q24
        gate-cse-1994-q14a
        gate-cse-1989-q12a
        gate-cse-1994-q1.19     (trailing comma stripped: "1.19," → "1.19")
        gate-cse-1992-q01-viii  ("01,viii" → "01-viii")
    """
    import hashlib

    base = f"gate-cse-{year}"
    if set_tag:
        # Normalise "Set 1" → "s1", "Set 2" → "s2" etc.
        set_num = "".join(filter(str.isdigit, set_tag))
        base += f"-s{set_num}"

    raw = question_number.strip()
    # Normalise question number for the ID
    q_num = raw.lower().replace(" ", "")
    # Strip any trailing punctuation that can't be part of a valid ID/filename
    q_num = q_num.rstrip(".,;:!?")
    # Replace any other ID-unsafe characters (e.g. commas) with '-'
    q_num = re.sub(r"[^a-z0-9.\-]+", "-", q_num)
    q_num = re.sub(r"-+", "-", q_num).strip("-.")

    if not q_num:
        # Fall back to a stable hash of the raw value — deterministic and
        # collision-free for distinct raws.
        q_num = "n" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]

    base += f"-q{q_num}"
    return base


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pixel helpers ─────────────────────────────────────────────────────────────

def is_mostly_white(img, threshold: float = 0.98) -> bool:
    """
    Return True if more than `threshold` fraction of pixels are near-white.
    Used to flag suspiciously blank crops.

    img: PIL.Image
    """
    from PIL import ImageStat
    if img.mode != "RGB":
        img = img.convert("RGB")
    stat = ImageStat.Stat(img)
    # Mean brightness per channel; 255 = pure white
    means = stat.mean
    brightness = sum(means) / (3 * 255)
    return brightness > threshold
