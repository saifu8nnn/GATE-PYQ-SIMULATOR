"""Tests for question heading parsing and boundary detection (Phase 2, 9.1)."""

from __future__ import annotations

import pytest

from conftest import answer_key_page, bold, plain, question_page, requires_fitz

from config import QUESTION_HEADING_RE
from question_detector import detect_question_boundaries


# ── Heading regex: historical numbering formats must all parse ───────────────

@pytest.mark.parametrize(
    "heading,year,qnum",
    [
        ("B Tree: GATE CSE 1999 | Question: 1.25", "1999", "1.25"),
        ("Indexing: GATE CSE 1994 | Question: 12a", "1994", "12a"),
        ("B Tree: GATE CSE 1994 | Question: 14b", "1994", "14b"),
        ("Normalization: GATE CSE 1990 | Question: 2-iv", "1990", "2-iv"),
        ("SQL: GATE CSE 1992 | Question: 01,viii", "1992", "01,viii"),
        ("Assembler: GATE CSE 1992 | Question: 03,ii", "1992", "03,ii"),
        ("Relational Algebra: GATE CSE 1998 | Question: 1.33", "1998", "1.33"),
        ("Syntax Analysis: GATE CSE 2014 Set 2 | Question: 21", "2014", "21"),
        ("Joins: GATE IT 2005 | Question: 82a", "2005", "82a"),
    ],
)
def test_heading_regex_parses_historical_formats(heading, year, qnum):
    m = QUESTION_HEADING_RE.match(heading)
    assert m is not None, f"failed to parse heading: {heading!r}"
    assert m.group("year") == year
    assert m.group("question_number") == qnum


def test_heading_regex_extracts_set_number():
    m = QUESTION_HEADING_RE.match("B Tree: GATE CSE 2015 Set 2 | Question: 6")
    assert m is not None
    assert m.group("set") == "2"


def test_heading_regex_ignores_ordinary_text():
    assert QUESTION_HEADING_RE.match("The purpose of instruction location counter") is None
    assert QUESTION_HEADING_RE.match("Answer key") is None


# ── Boundary detection on synthetic pages ────────────────────────────────────

@requires_fitz
def test_detects_question_with_section_number_and_options(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num="5.1.5",
        topic="B Tree",
        year=1999,
        qnum="1.25",
        body_lines=["Consider a B+ tree of order 5."],
        option_lines=["A. 3", "B. 4", "C. 5", "D. 6"],
        tag_line="gatecse-1999 databases b-tree 2-marks",
    )
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=10)
    assert len(bounds) == 1
    b = bounds[0]
    assert b.section_number == "5.1.5"
    assert b.option_lines == ["A", "B", "C", "D"]
    assert b.tag_line is not None and "2-marks" in b.tag_line
    assert b.heading_match.group("question_number") == "1.25"


@requires_fitz
def test_question_ends_at_answer_key_line(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num="5.1.1",
        topic="B Tree",
        year=1989,
        qnum="12a",
        body_lines=["Draw a B+ tree."],
        answer_line="Answer key",
    )
    # another question AFTER the answer line must not be swallowed
    question_page(
        doc,
        section_num="5.1.2",
        topic="B Tree",
        year=1994,
        qnum="14a",
        body_lines=["Insert keys into the tree."],
    )
    bounds = detect_question_boundaries(doc, 0, 1, max_questions=10)
    assert len(bounds) == 2
    # the answer line CLOSED q1 on page 0 — it must not swallow the rest of
    # the document until the next heading
    assert bounds[0].end_page == 0
    assert bounds[0].end_y < doc[0].rect.height
    # q2 begins on page 1 and keeps its own boundary
    assert bounds[1].start_page == 1
    assert bounds[1].heading_match.group("question_number") == "14a"


@requires_fitz
def test_multi_page_question_boundary(make_doc):
    doc = make_doc()
    q1 = question_page(
        doc,
        section_num="5.1.4",
        topic="B Tree",
        year=1997,
        qnum="19",
        body_lines=["Part one of the question on page 1."],
    )
    q2 = question_page(
        doc,
        section_num=None,
        topic="B Tree",
        year=1997,
        qnum="19",
        body_lines=["Continuation text on page 2."],
    )
    # remove the duplicated heading on page 2 so it reads as continuation:
    # simpler: detect with only one heading by covering page 2's heading text
    # — instead detect across both pages; the second heading closes the first.
    bounds = detect_question_boundaries(doc, 0, 1, max_questions=10)
    assert len(bounds) == 2
    assert bounds[0].start_page == 0
    assert bounds[0].end_page == 1  # closed by the next heading on page 2
    assert q1 is not None and q2 is not None


@requires_fitz
def test_max_questions_cap_respected(make_doc):
    doc = make_doc()
    for i in range(5):
        question_page(
            doc,
            section_num=f"1.1.{i + 1}",
            topic="Algorithms",
            year=2000,
            qnum=str(i + 1),
            body_lines=[f"Question body {i + 1}"],
        )
    bounds = detect_question_boundaries(doc, 0, 4, max_questions=3)
    assert len(bounds) == 3


@requires_fitz
def test_missing_section_number_is_none_not_guessed(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num=None,
        topic="SQL",
        year=1998,
        qnum="7-a",
        body_lines=["No left-margin number here."],
    )
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=5)
    assert len(bounds) == 1
    assert bounds[0].section_number is None
