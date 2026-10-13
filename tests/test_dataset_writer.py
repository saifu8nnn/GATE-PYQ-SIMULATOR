"""Tests for safe incremental dataset writing (known risk B / D4)."""

from __future__ import annotations

import json

from dataset_writer import build_taxonomy, merge_records, write_all
from models import Question


def make_q(qid="gate-cse-1999-q1.25", version=2, year=1999, subject="Databases",
           topic="B Tree", qnum="1.25", answer="B"):
    return Question(
        id=qid, exam="GATE CSE", year=year, set=None,
        subject=subject, topic=topic, subtopic=None,
        question_number=qnum, question_number_raw=qnum, section_number="5.1.5",
        question_type="MCQ", marks=None, difficulty=None,
        options_present=True, option_labels_detected=["A", "B", "C", "D"],
        correct_answer=answer, answer_status="verified",
        answer_source="answer_key_page", answer_evidence="5.1.5 -> 'B' (p338)",
        image=f"images/{qid}.png", source_pdf="volume2.pdf", source_pages=[260],
        verified=False, notes=None, extraction_version=version,
    )


def test_new_ids_are_appended():
    merged, stats = merge_records([], [make_q(), make_q("gate-cse-2000-q1.22")], 2)
    assert stats["added"] == 2
    assert len(merged) == 2


def test_same_version_is_idempotent():
    existing = [make_q().to_dict()]
    merged, stats = merge_records(existing, [make_q()], 2)
    assert stats["unchanged"] == 1
    assert stats["updated"] == 0


def test_version_bump_updates_in_place():
    existing = [make_q(version=1).to_dict()]
    merged, stats = merge_records(existing, [make_q(version=2)], 2)
    assert stats["updated"] == 1
    assert merged[0]["extraction_version"] == 2


def test_existing_unrelated_records_are_never_lost():
    other = make_q(qid="gate-cse-2002-q17", year=2002, qnum="17").to_dict()
    existing = [other]
    merged, stats = merge_records(existing, [make_q()], 2)
    assert stats["added"] == 1
    ids = {r["id"] for r in merged}
    assert ids == {"gate-cse-2002-q17", "gate-cse-1999-q1.25"}


def test_identity_conflict_is_reported_and_kept():
    # Same ID but a different year → conflicting record, first one kept.
    existing = [make_q(year=1999).to_dict()]
    merged, stats = merge_records(existing, [make_q(year=2001)], 2)
    assert stats["conflicts"] == 1
    assert merged[0]["year"] == 1999  # existing record preserved
    assert stats["conflict_messages"] and "year" in stats["conflict_messages"][0]


def test_id_collision_from_different_raw_numbers_is_surfaced():
    # Normalization can, in principle, map two distinct source numbers onto one
    # ID (e.g. "1,viii" vs "1-viii"). The merge layer must report this as a
    # conflict instead of silently dropping one question.
    a = make_q(qid="gate-cse-1992-q1-viii", qnum="1-viii")
    b = make_q(qid="gate-cse-1992-q1-viii", qnum="1,viii")
    merged, stats = merge_records([a.to_dict()], [b], 2)
    assert stats["conflicts"] == 1
    assert "question_number" in stats["conflict_messages"][0]
    assert merged[0]["question_number"] == "1-viii"  # first record kept


def test_write_all_keeps_json_csv_taxonomy_consistent(tmp_path):
    json_path = tmp_path / "questions.json"
    csv_path = tmp_path / "questions.csv"
    tax_path = tmp_path / "taxonomy.json"

    qs = [
        make_q(),
        make_q(qid="gate-cse-1994-q14a", year=1994, qnum="14a", answer=None),
    ]
    # first batch
    write_all(qs, json_path, csv_path, tax_path, current_version=1)
    # second batch updates one record via version bump and adds a new one
    updated = make_q(version=2)
    write_all([updated, make_q(qid="gate-cse-2001-q22", year=2001, qnum="22")],
              json_path, csv_path, tax_path, current_version=2)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    ids = {r["id"] for r in data}
    assert ids == {"gate-cse-1999-q1.25", "gate-cse-1994-q14a", "gate-cse-2001-q22"}
    # updated record has the new version
    by_id = {r["id"]: r for r in data}
    assert by_id["gate-cse-1999-q1.25"]["extraction_version"] == 2

    # CSV carries the same IDs
    csv_ids = set()
    with open(csv_path, encoding="utf-8") as f:
        header = f.readline()
        assert "id" in header
        for line in f:
            csv_ids.add(line.split(",")[0])
    assert csv_ids == ids

    # taxonomy only contains actual subjects/topics from records
    tax = json.loads(tax_path.read_text(encoding="utf-8"))
    assert set(tax.keys()) == {"Databases"}
    assert "B Tree" in tax["Databases"]


def test_taxonomy_never_invents_topics():
    tax = build_taxonomy([make_q(topic=None)])
    assert tax == {"Databases": {}}
