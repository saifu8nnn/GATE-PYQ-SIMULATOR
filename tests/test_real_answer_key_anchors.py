"""Integration anchors against the real volume2.pdf (skipped when absent).

Rechecks the two documented regression mappings on the Databases answer-key
page ONLY (0-based page 337 = PDF page 338) — no full-PDF scan, so this stays
fast (~1s).
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from answer_key_reader import _parse_answer_key_page  # noqa: E402


DA_KEY_PAGE_0BASED = 337


@pytest.fixture(scope="module")
def databases_key_table(volume2_path):
    if not volume2_path.exists():
        pytest.skip("volume2.pdf not present")
    doc = fitz.open(str(volume2_path))
    try:
        # The Databases answer-key block starts at the header page (0-based
        # 337 = PDF page 338) and may span the following pages — scan the
        # block, not a single hard-coded page (page numbers are not universal
        # constants; the mapping evidence is what we assert).
        table: dict = {}
        for page_idx in range(337, 342):
            _parse_answer_key_page(doc[page_idx], page_idx, table)
        return table
    finally:
        doc.close()


def test_anchor_1999_q1_25_is_b(databases_key_table):
    pa = databases_key_table.get("5.1.5")
    assert pa is not None, "section 5.1.5 missing from the Databases answer-key page"
    assert pa.value == "B"
    assert pa.answer_type == "MCQ"


def test_anchor_2000_q1_22_is_b(databases_key_table):
    pa = databases_key_table.get("5.1.7")
    assert pa is not None, "section 5.1.7 missing from the Databases answer-key page"
    assert pa.value == "B"
    assert pa.answer_type == "MCQ"


def test_page_contains_na_entries_too(databases_key_table):
    na = [k for k, v in databases_key_table.items() if v.answer_type == "NOT_AVAILABLE"]
    assert len(na) >= 3, "expected several explicit N/A entries on the key page"
