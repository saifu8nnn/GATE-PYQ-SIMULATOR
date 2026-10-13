"""Shared fixtures: project root importability + synthetic PDF builders.

All extraction tests run against tiny synthetic PDFs generated with PyMuPDF —
hermetic and fast, no dependence on volume2.pdf (one optional integration
test rechecks the real answer-key page when the PDF is present).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None


requires_fitz = pytest.mark.skipif(fitz is None, reason="PyMuPDF not installed")


# ── Synthetic PDF builders ───────────────────────────────────────────────────

PAGE_W, PAGE_H = 612, 792  # letter size in points


def new_doc():
    return fitz.open()


def add_page(doc):
    return doc.new_page(width=PAGE_W, height=PAGE_H)


def bold(page, x, y, text, size=10.5):
    """Insert bold text (bold flag bit 16 matters for detectors)."""
    page.insert_text((x, y), text, fontname="hebo", fontsize=size)


def plain(page, x, y, text, size=10):
    page.insert_text((x, y), text, fontname="helv", fontsize=size)


def question_page(
    doc,
    *,
    section_num: str | None,
    topic: str,
    year: int,
    qnum: str,
    body_lines: list[str],
    tag_line: str | None = None,
    answer_line: str | None = None,
    option_lines: list[str] | None = None,
):
    """Build one page containing one complete question in the book's layout."""
    page = add_page(doc)
    y = 100.0
    if section_num:
        bold(page, 45, y, section_num)  # left-margin bold section number
    bold(page, 120, y, f"{topic}: GATE CSE {year} | Question: {qnum}")
    y += 24
    for line in body_lines:
        plain(page, 120, y, line)
        y += 16
    for opt in option_lines or []:
        plain(page, 120, y, opt)
        y += 16
    if tag_line:
        plain(page, 120, y + 6, tag_line)
        y += 20
    if answer_line:
        plain(page, 120, y + 6, answer_line)
    return page


def answer_key_page(doc, pairs: list[tuple[str, str]]):
    """Build a dedicated 'Answer Keys' page with section-number/value pairs."""
    page = add_page(doc)
    bold(page, 120, 80, "Answer Keys", size=12)
    y = 110.0
    for key, value in pairs:
        bold(page, 60, y, key)
        plain(page, 200, y, value)
        y += 20
    return page


# ── Convenience fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def make_doc():
    """Factory fixture: with make_doc() as doc: ... doc is a fresh fitz doc."""
    docs = []

    def _make():
        doc = new_doc()
        docs.append(doc)
        return doc

    yield _make
    for d in docs:
        d.close()


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def pilot_json_path() -> Path:
    return PROJECT_ROOT / "output" / "validation_pilot" / "data" / "pilot_questions.json"


@pytest.fixture(scope="session")
def volume2_path() -> Path:
    return PROJECT_ROOT / "volume2.pdf"
