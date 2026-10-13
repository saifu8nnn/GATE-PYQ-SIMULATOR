"""Tests for validation rules (known risk C / D5, D9)."""

from __future__ import annotations

import pytest

from conftest import requires_fitz

from models import Question
from validator import validate_questions


def make_q(**over):
    defaults = dict(
        id="gate-cse-1999-q1.25", exam="GATE CSE", year=1999, set=None,
        subject="Databases", topic="B Tree", subtopic=None,
        question_number="1.25", question_number_raw="1.25",
        section_number="5.1.5", question_type="MCQ", marks=None, difficulty=None,
        options_present=True, option_labels_detected=["A", "B", "C", "D"],
        correct_answer="B", answer_status="verified",
        answer_source="answer_key_page", answer_evidence="5.1.5 -> 'B' (p338)",
        image="images/gate-cse-1999-q1.25.png", source_pdf="volume2.pdf",
        source_pages=[260], verified=False, notes=None, extraction_version=2,
    )
    defaults.update(over)
    return Question(**defaults)


def _mk_images(tmp_path, questions):
    from PIL import Image
    img_dir = tmp_path / "images"
    img_dir.mkdir(exist_ok=True)
    for q in questions:
        Image.new("RGB", (1000, 400), (250, 250, 252)).save(img_dir / f"{q.id}.png")
    return img_dir


def test_valid_question_passes(tmp_path):
    q = make_q()
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert report.passed(), report.summary()


def test_mcq_without_detected_options_is_critical(tmp_path):
    q = make_q(question_type="MCQ", options_present=False, option_labels_detected=None)
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert not report.passed()
    assert any("missing detected options" in e for e in report.errors)


def test_verified_requires_value_and_evidence(tmp_path):
    q = make_q(correct_answer=None)
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert any("verified but no answer value" in e for e in report.errors)

    q2 = make_q(id="gate-cse-2000-q1.22", answer_evidence=None)
    report2 = validate_questions([q2], _mk_images(tmp_path, [q, q2]))
    assert any("no answer evidence" in e for e in report2.errors)


def test_not_available_requires_explicit_na_evidence(tmp_path):
    q = make_q(correct_answer=None, answer_status="not_available",
               answer_evidence="some parser failure")
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert any("without explicit" in e for e in report.errors)

    q_ok = make_q(correct_answer=None, answer_status="not_available",
                  answer_evidence="5.1.2 -> 'N/A' (p338)")
    report_ok = validate_questions([q_ok], _mk_images(tmp_path, [q_ok]))
    assert report_ok.passed(), report_ok.summary()


def test_needs_review_is_not_an_error(tmp_path):
    # D9: UNKNOWN answer-key entries map to needs_review — a valid state.
    q = make_q(correct_answer=None, answer_status="needs_review",
               answer_evidence="5.17.28 -> heading text, UNKNOWN")
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert report.passed(), report.summary()


def test_duplicate_ids_are_errors(tmp_path):
    q1 = make_q()
    q2 = make_q(year=2001)  # same id, different identity
    report = validate_questions([q1, q2], _mk_images(tmp_path, [q1]))
    assert any("Duplicate IDs" in e for e in report.errors)


def test_missing_image_is_error_with_id(tmp_path):
    q = make_q()
    empty = tmp_path / "noimages"
    empty.mkdir()
    report = validate_questions([q], empty)
    assert report.images_missing == 1
    assert any(q.id in e and "Image missing" in e for e in report.errors)


def test_image_filename_must_match_id(tmp_path):
    q = make_q(image="images/some-other-name.png")
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert any("does not match ID" in e for e in report.errors)


def test_implausible_year_is_error(tmp_path):
    q = make_q(year=1789)
    report = validate_questions([q], _mk_images(tmp_path, [q]))
    assert any("Implausible year" in e for e in report.errors)


def test_no_record_cap_by_default(tmp_path):
    # D5: the old MAX_QUESTIONS cap made large pilots unvalidatable.
    qs = [
        make_q(id=f"gate-cse-1999-q{i}", question_number=str(i),
               section_number=f"5.1.{i}")
        for i in range(1, 26)
    ]
    report = validate_questions(qs, _mk_images(tmp_path, qs))
    assert report.total_questions == 25
