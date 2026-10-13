"""Tests for ID generation, tag-line parsing and metadata building (Phase 2/4)."""

from __future__ import annotations

import pytest

from conftest import question_page, requires_fitz

from utils import make_question_id
from metadata_parser import parse_metadata, parse_tag_line, _sanitize_question_number
from question_detector import detect_question_boundaries
from models import AnswerStatus


# ── Deterministic IDs ────────────────────────────────────────────────────────

def test_ids_are_deterministic():
    a = make_question_id(1999, "1.25")
    b = make_question_id(1999, "1.25")
    assert a == b == "gate-cse-1999-q1.25"


def test_id_normalizes_internal_punctuation_but_keeps_meaning():
    # D6 regression: commas must not pollute IDs; parts must survive.
    assert make_question_id(1992, "01,viii") == "gate-cse-1992-q01-viii"
    assert make_question_id(1992, "03,ii") == "gate-cse-1992-q03-ii"
    assert make_question_id(2009, "37,isro-dec2017-55") == "gate-cse-2009-q37-isro-dec2017-55"


def test_id_strips_trailing_punctuation_only():
    assert make_question_id(2000, "1.22,") == "gate-cse-2000-q1.22"
    # internal dots/dashes preserved (meaningful parts)
    assert make_question_id(1990, "2-iv") == "gate-cse-1990-q2-iv"
    assert make_question_id(1994, "14a") == "gate-cse-1994-q14a"


def test_distinct_raw_numbers_never_collide():
    ids = [make_question_id(1992, raw) for raw in ["1,viii", "1,vii", "1", "1viii"]]
    assert len(set(ids)) == len(ids)


def test_set_tag_is_included_in_id():
    assert make_question_id(2014, "21", "Set 2") == "gate-cse-2014-s2-q21"


def test_unusable_number_gets_stable_hash_suffix():
    a = make_question_id(2000, "!!!")
    b = make_question_id(2000, "!!!")
    assert a == b
    assert a.startswith("gate-cse-2000-qn")


# ── Sanitizer ────────────────────────────────────────────────────────────────

def test_sanitize_keeps_original_semantics():
    assert _sanitize_question_number("1.22,") == "1.22"
    assert _sanitize_question_number(" 14a ") == "14a"
    assert _sanitize_question_number("01,viii") == "01,viii"  # raw preserved


# ── Tag-line parsing ─────────────────────────────────────────────────────────

def test_tag_line_modern_format():
    d = parse_tag_line("gatecse-2020 numerical-answers databases b-tree indexing 2-marks")
    assert d["year"] == 2020
    assert d["question_type"] == "NAT"
    assert d["marks"] == 2


def test_tag_line_old_format():
    d = parse_tag_line("gate1994  databases  b-tree  normal  descriptive")
    assert d["year"] == 1994
    assert d["question_type"] == "DESCRIPTIVE"
    assert d["difficulty"] == "normal"


def test_tag_line_absent_is_safe():
    d = parse_tag_line(None)
    assert d == {"year": None, "question_type": None, "marks": None, "difficulty": None}


# ── Metadata: subject comes from the caller, never from config ──────────────

@requires_fitz
def test_parse_metadata_uses_passed_subject(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num="3.1.1",
        topic="Assembler",
        year=1992,
        qnum="01,viii",
        body_lines=["The purpose of instruction location counter is ____"],
    )
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=5)
    meta = parse_metadata(bounds[0], {}, subject="Compiler Design")
    assert meta["subject"] == "Compiler Design"
    assert meta["id"] == "gate-cse-1992-q01-viii"
    assert meta["question_number_raw"] == "01,viii"
    assert meta["extraction_version"] is not None


@requires_fitz
def test_unresolved_answer_is_needs_review_not_na(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num=None,  # no answer-key mapping possible
        topic="SQL",
        year=1998,
        qnum="7-a",
        body_lines=["Some question"],
    )
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=5)
    meta = parse_metadata(bounds[0], {}, subject="Databases")
    # No section number must NEVER read as a confirmed N/A (Phase 4.3).
    assert meta["answer_status"] == AnswerStatus.NEEDS_REVIEW
    assert meta["correct_answer"] is None


@requires_fitz
def test_section_number_maps_to_answer_table(make_doc):
    doc = make_doc()
    question_page(
        doc,
        section_num="5.1.5",
        topic="B Tree",
        year=1999,
        qnum="1.25",
        body_lines=["MCQ about B+ trees"],
        option_lines=["A. 3", "B. 4", "C. 5", "D. 6"],
    )
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=5)

    class FakePA:
        raw = "B"
        value = "B"
        answer_type = "MCQ"
        source_page = 337

    meta = parse_metadata(bounds[0], {"5.1.5": FakePA()}, subject="Databases")
    assert meta["correct_answer"] == "B"
    assert meta["answer_status"] == AnswerStatus.VERIFIED
    assert "5.1.5" in meta["answer_evidence"]
