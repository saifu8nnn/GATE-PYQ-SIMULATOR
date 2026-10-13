"""
dataset_writer.py — Write questions.json, questions.csv, and taxonomy.json.

Rules
-----
  * Loads existing data before writing to support resumability.
  * Never duplicates a record with the same ID.
  * Writes only relative paths in the JSON/CSV (not absolute paths).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from config import DATA_DIR, IMAGE_DIR
from models import Question
from utils import get_logger, ensure_dirs

logger = get_logger()

# CSV column order
CSV_COLUMNS = [
    "id", "exam", "year", "set", "subject", "topic", "subtopic",
    "question_number", "question_number_raw", "section_number",
    "question_type", "marks", "difficulty",
    "options_present", "option_labels_detected",
    "correct_answer", "answer_status", "answer_source", "answer_evidence",
    "image", "source_pdf", "source_pages",
    "verified", "notes", "extraction_version",
]

# Fields that identify WHICH question a record describes. If two records share
# an ID but disagree on these, they are conflicting records, not an update.
_IDENTITY_FIELDS = ("year", "set", "section_number", "question_number")


# ── questions.json ─────────────────────────────────────────────────────────────

def load_existing_questions(json_path: Path) -> list[dict]:
    """Load the existing questions.json if it exists, else return empty list."""
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                logger.warning(f"  Corrupt JSON detected at {json_path}. Starting fresh.")
    return []


def existing_ids(json_path: Path) -> set[str]:
    """Return the set of question IDs already in questions.json."""
    records = load_existing_questions(json_path)
    return {r["id"] for r in records if "id" in r}


def merge_records(
    existing: list[dict],
    incoming: list[Question],
    current_version: Optional[int] = None,
) -> tuple[list[dict], dict]:
    """
    Merge incoming Question objects into existing raw dict records.

    Merge rules (deterministic):
      * New ID                       → append.
      * Same ID, same extraction_version → keep the existing record
        (idempotent rerun; nothing is lost, nothing changes).
      * Same ID, different extraction_version AND compatible identity fields
        → intentional UPDATE: replace the record in place (this is how a
        cropper/detector fix regenerates stale records).
      * Same ID, same version but conflicting identity fields, or a version
        change that also contradicts the identity fields
        → CONFLICT: the existing record is kept and the conflict is reported.

    Returns (merged_records, stats) where stats has counts:
      added, updated, unchanged, conflicts (with a list of conflict messages).
    """
    stats: dict = {
        "added": 0, "updated": 0, "unchanged": 0,
        "conflicts": 0, "conflict_messages": [],
    }
    by_id: dict[str, int] = {r["id"]: i for i, r in enumerate(existing) if "id" in r}

    for q in incoming:
        rec = q.to_dict()
        qid = rec["id"]
        if qid not in by_id:
            existing.append(rec)
            by_id[qid] = len(existing) - 1
            stats["added"] += 1
            continue

        idx = by_id[qid]
        old = existing[idx]

        # Identity must agree — a same-ID record describing a different
        # question is a conflict, never an update.
        mismatches = [
            f"{f}: {old.get(f)!r} != {rec.get(f)!r}"
            for f in _IDENTITY_FIELDS
            if old.get(f) != rec.get(f)
        ]
        if mismatches:
            stats["conflicts"] += 1
            stats["conflict_messages"].append(
                f"{qid}: conflicting record kept ({'; '.join(mismatches)})"
            )
            continue

        old_ver = old.get("extraction_version")
        new_ver = rec.get("extraction_version")
        if old_ver == new_ver or (current_version is not None and old_ver == current_version):
            stats["unchanged"] += 1
            continue

        # Different version + compatible identity → intentional update.
        existing[idx] = rec
        stats["updated"] += 1

    return existing, stats


def write_questions_json(
    questions: list[Question],
    json_path: Path,
    current_version: Optional[int] = None,
) -> dict:
    """
    Merge new questions into questions.json per merge_records() rules.
    Never loses unrelated existing records; returns merge stats.
    """
    existing = load_existing_questions(json_path)
    existing, stats = merge_records(existing, questions, current_version)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    logger.info(
        f"  questions.json — {len(existing)} total "
        f"({stats['added']} added, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['conflicts']} conflicts)"
    )
    for msg in stats["conflict_messages"]:
        logger.warning(f"  CONFLICT: {msg}")
    return stats


# ── questions.csv ──────────────────────────────────────────────────────────────

def write_questions_csv(questions: list[Question], csv_path: Path) -> None:
    """
    Write all questions to questions.csv.
    Rebuilds the entire CSV from the provided list (not incremental).
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for q in questions:
            row = q.to_dict()
            # Flatten list fields for CSV
            if isinstance(row.get("source_pages"), list):
                row["source_pages"] = ",".join(str(p) for p in row["source_pages"])
            if isinstance(row.get("correct_answer"), list):
                row["correct_answer"] = ",".join(str(x) for x in row["correct_answer"])
            writer.writerow(row)
    logger.info(f"  questions.csv — {len(questions)} rows")


# ── taxonomy.json ──────────────────────────────────────────────────────────────

def build_taxonomy(questions: list[Question]) -> dict:
    """
    Build a taxonomy dict from the questions list.
    Only includes topics actually encountered — never invented.

    Structure:
        {
          "Databases": {
            "B Tree": [],
            "Indexing": []
          }
        }
    """
    taxonomy: dict = {}
    for q in questions:
        subject = q.subject
        topic   = q.topic

        if subject not in taxonomy:
            taxonomy[subject] = {}

        if topic and topic not in taxonomy[subject]:
            taxonomy[subject][topic] = []

    return taxonomy


def write_taxonomy(questions: list[Question], taxonomy_path: Path) -> None:
    taxonomy = build_taxonomy(questions)
    taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
    with open(taxonomy_path, "w", encoding="utf-8") as f:
        json.dump(taxonomy, f, indent=2, ensure_ascii=False)
    logger.info(f"  taxonomy.json — {sum(len(v) for v in taxonomy.values())} topics")


# ── All-in-one writer ──────────────────────────────────────────────────────────

def write_all(
    questions: list[Question],
    json_path: Optional[Path] = None,
    csv_path: Optional[Path]  = None,
    taxonomy_path: Optional[Path] = None,
    current_version: Optional[int] = None,
) -> dict:
    """Write JSON, CSV, and taxonomy in one call.

    All three outputs are generated from the SAME authoritative merged record
    set, so JSON/CSV/taxonomy can never diverge.
    Returns the merge stats from write_questions_json().
    """
    ensure_dirs(DATA_DIR)

    json_path     = json_path     or DATA_DIR / "questions.json"
    csv_path      = csv_path      or DATA_DIR / "questions.csv"
    taxonomy_path = taxonomy_path or DATA_DIR / "taxonomy.json"

    # Merge new into existing (single source of truth)
    all_questions_dicts = load_existing_questions(json_path)
    all_questions_dicts, stats = merge_records(
        all_questions_dicts, questions, current_version
    )

    # Persist JSON first (re-uses the already-merged list — no double merge)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_questions_dicts, f, indent=2, ensure_ascii=False)
    logger.info(
        f"  questions.json — {len(all_questions_dicts)} total "
        f"({stats['added']} added, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['conflicts']} conflicts)"
    )
    for msg in stats["conflict_messages"]:
        logger.warning(f"  CONFLICT: {msg}")

    # Re-hydrate for CSV/taxonomy from the merged set
    merged_questions = []
    for d in all_questions_dicts:
        try:
            merged_questions.append(Question(**d))
        except TypeError:
            logger.warning(f"  Could not reconstruct Question from dict: {d.get('id')}")

    write_questions_csv(merged_questions, csv_path)
    write_taxonomy(merged_questions, taxonomy_path)
    return stats
