"""Tests for answer-key value parsing and page auditing (Phase 4, 9.1)."""

from __future__ import annotations

import pytest

from conftest import add_page, answer_key_page, bold, plain, requires_fitz

from answer_key_reader import (
    _parse_answer_value,
    _parse_answer_key_page,
    load_answer_key_table,
)


# ── Value classification ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected_type,expected_value",
    [
        ("A", "MCQ", "A"),
        ("d", "MCQ", "D"),
        ("A.", "MCQ", "A"),                          # D8: trailing period
        ("A. TCP, but not UDP", "MCQ", "A"),        # D8: label + explanation
        ("A) only", "MCQ", "A"),
        ("A;C;D", "MSQ", ["A", "C", "D"]),
        ("42", "NAT", 42),
        ("-3.5", "NAT", -3.5),
        ("50 : 52", "RANGE", [50, 52]),
        ("True", "BOOL", True),
        ("False", "BOOL", False),
        ("N/A", "NOT_AVAILABLE", None),
        ("n/a", "NOT_AVAILABLE", None),
        ("X", "UNKNOWN", None),                      # needs_review sentinel
        ("17 :", "UNKNOWN", "17 :"),                 # truncated range stays UNKNOWN
        ("Q-Q", "UNKNOWN", "Q-Q"),                   # genuinely ambiguous
    ],
)
def test_parse_answer_value(raw, expected_type, expected_value):
    pa = _parse_answer_value(raw, page_idx=0)
    assert pa.answer_type == expected_type
    assert pa.value == expected_value
    assert pa.raw == raw  # verbatim evidence preserved


def test_parse_never_raises_on_garbage():
    pa = _parse_answer_value("%%%", 0)
    assert pa.answer_type == "UNKNOWN"


# ── Page-level parsing + duplicate audit (D7) ────────────────────────────────

@requires_fitz
def test_page_pairs_keys_with_values(make_doc):
    doc = make_doc()
    answer_key_page(doc, [("5.1.5", "B"), ("5.1.6", "N/A"), ("5.1.7", "B")])
    table: dict = {}
    added = _parse_answer_key_page(doc[0], 0, table)
    assert added == 3
    assert table["5.1.5"].value == "B"
    assert table["5.1.6"].answer_type == "NOT_AVAILABLE"
    assert table["5.1.7"].value == "B"


@requires_fitz
def test_duplicate_keys_are_recorded_for_audit(make_doc):
    doc = make_doc()
    answer_key_page(doc, [("5.1.5", "B")])
    answer_key_page(doc, [("5.1.5", "C")])  # same key, conflicting value
    table: dict = {}
    audit: dict = {"duplicates": [], "conflicts": []}
    table = load_answer_key_table(doc, audit=audit)

    assert len(audit["duplicates"]) == 1
    assert len(audit["conflicts"]) == 1
    key, page, first_raw, second_raw = audit["conflicts"][0]
    assert key == "5.1.5"
    assert (first_raw, second_raw) == ("B", "C")
    # first-wins keeps the header-page value
    assert table["5.1.5"].value == "B"


@requires_fitz
def test_heading_text_is_never_paired_as_answer(make_doc):
    doc = make_doc()
    page = add_page(doc)
    bold(page, 120, 80, "Answer Keys", size=12)
    bold(page, 60, 110, "5.17.28")
    # a question heading leaked into the value column (D8 pairing bug case)
    plain(page, 200, 110, "Transaction and Concurrency: GATE IT 2008 | Question: 63")
    table: dict = {}
    _parse_answer_key_page(page, 0, table)
    assert "5.17.28" in table
    assert table["5.17.28"].answer_type == "UNKNOWN"  # surfaced, never verified
