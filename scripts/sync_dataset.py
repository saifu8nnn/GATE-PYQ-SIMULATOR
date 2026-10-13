"""
sync_dataset.py — Publish an approved question dataset into the offline frontend.

Reads a source questions JSON (pilot or full dataset), validates every record,
copies the referenced images into frontend/public/images/, and writes TWO
manifests into frontend/public/data/:

  questions.json  — display data ONLY (never contains correct_answer)
  answers.json    — grading data (id -> answer/status/marks), fetched by the
                    UI only at submission time so an active exam cannot leak
                    answers from the initial dataset load.

A manifest entry also records the local image URL ("/images/<id>.png") so the
UI never builds paths itself.

Exit codes: 0 = all records synced; 1 = one or more records skipped/failed.

Usage:
  python scripts/sync_dataset.py                       # pilot dataset (default)
  python scripts/sync_dataset.py --source output/data/questions.json
  python scripts/sync_dataset.py --allow-skips         # exit 0 even with skips
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FRONTEND_PUBLIC = PROJECT_ROOT / "frontend" / "public"
PUBLIC_IMAGES = FRONTEND_PUBLIC / "images"
PUBLIC_DATA = FRONTEND_PUBLIC / "data"

DEFAULT_SOURCE = PROJECT_ROOT / "output" / "validation_pilot" / "data" / "pilot_questions.json"

# Fields every display record must carry (frontend contract)
REQUIRED_FIELDS = [
    "id", "exam", "year", "subject", "question_type", "image",
]
VALID_ANSWER_STATUSES = {"verified", "needs_review", "not_available"}
VALID_QUESTION_TYPES = {
    "MCQ", "MSQ", "NAT", "DESCRIPTIVE", "FILL_IN_THE_BLANK",
    "MATCH_THE_FOLLOWING", "UNKNOWN", None,
}
# Image must resolve to frontend/public/images/<stem>.png
IMAGE_URL_PREFIX = "/images/"


def validate_record(rec: dict) -> list[str]:
    """Return a list of problems; empty list means the record is syncable."""
    problems: list[str] = []

    for f in REQUIRED_FIELDS:
        if rec.get(f) in (None, ""):
            # question_type may legitimately be None → surfaced as UNKNOWN later
            if f == "question_type":
                continue
            problems.append(f"missing required field: {f}")

    qid = rec.get("id")
    if qid and not all(c.isalnum() or c in "-._" for c in qid):
        problems.append(f"id contains unsafe characters: {qid!r}")

    status = rec.get("answer_status")
    if status not in VALID_ANSWER_STATUSES:
        problems.append(f"invalid answer_status: {status!r}")

    if rec.get("question_type") not in VALID_QUESTION_TYPES:
        problems.append(f"invalid question_type: {rec.get('question_type')!r}")

    # verified answers must carry a value + evidence
    if status == "verified":
        if rec.get("correct_answer") is None:
            problems.append("verified answer without value")
        if not rec.get("answer_evidence"):
            problems.append("verified answer without evidence")

    year = rec.get("year")
    if not isinstance(year, int) or not (1984 <= year <= 2030):
        problems.append(f"implausible year: {year!r}")

    # image filename must match the ID (path integrity)
    img = rec.get("image") or ""
    if img and Path(img).stem != qid:
        problems.append(f"image stem {Path(img).stem!r} != id {qid!r}")

    return problems


def build_display_record(rec: dict) -> dict:
    """Display-side manifest entry: metadata + local image URL, NO answers."""
    qtype = rec.get("question_type") or "UNKNOWN"
    return {
        "id": rec["id"],
        "exam": rec.get("exam"),
        "year": rec.get("year"),
        "set": rec.get("set"),
        "subject": rec.get("subject"),
        "topic": rec.get("topic"),
        "subtopic": rec.get("subtopic"),
        "questionNumber": rec.get("question_number"),
        "questionType": qtype,
        "marks": rec.get("marks"),
        "optionsPresent": bool(rec.get("options_present")),
        "optionLabels": rec.get("option_labels_detected") or [],
        "imageUrl": IMAGE_URL_PREFIX + Path(rec["image"]).name,
        "sourcePages": rec.get("source_pages") or [],
        "verified": bool(rec.get("verified", False)),
    }


def build_grading_record(rec: dict) -> Optional[dict]:
    """
    Grading-side entry. Only questions with a usable grading rule are included;
    the frontend treats absence as 'ungradable' (never 'incorrect').
    """
    status = rec.get("answer_status")
    qtype = rec.get("question_type") or "UNKNOWN"
    if status != "verified":
        return None
    return {
        "id": rec["id"],
        "questionType": qtype,
        "correctAnswer": rec.get("correct_answer"),
        "marks": rec.get("marks"),
        "answerStatus": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="questions JSON to sync (default: pilot dataset)")
    parser.add_argument("--allow-skips", action="store_true",
                        help="exit 0 even if some records were skipped")
    args = parser.parse_args()

    src: Path = args.source
    if not src.exists():
        print(f"[ERROR] Source dataset not found: {src}")
        return 1

    with open(src, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid JSON in {src}: {exc}")
            return 1

    if not isinstance(records, list):
        print(f"[ERROR] Expected a list of records in {src}")
        return 1

    print(f"Source:  {src}")
    print(f"Records: {len(records)}")

    PUBLIC_IMAGES.mkdir(parents=True, exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)

    display: list[dict] = []
    grading: list[dict] = []
    skipped: list[tuple[str, list[str]]] = []
    seen_ids: set[str] = set()
    images_copied = 0
    images_already = 0

    src_image_dir = src.resolve().parent.parent / "images"

    for rec in records:
        qid = rec.get("id", "<no-id>")

        if qid in seen_ids:
            skipped.append((qid, ["duplicate id"]))
            continue
        seen_ids.add(qid)

        problems = validate_record(rec)
        if problems:
            skipped.append((qid, problems))
            continue

        # ── image copy (from the dataset's own images/ dir) ──────────────────
        img_name = Path(rec["image"]).name
        src_img = src_image_dir / img_name
        dst_img = PUBLIC_IMAGES / img_name

        if not src_img.exists():
            skipped.append((qid, [f"source image missing: {src_img}"]))
            continue

        if dst_img.exists() and dst_img.stat().st_size == src_img.stat().st_size:
            images_already += 1
        else:
            shutil.copy2(src_img, dst_img)
            images_copied += 1

        display.append(build_display_record(rec))
        g = build_grading_record(rec)
        if g is not None:
            grading.append(g)

    # ── write manifests ──────────────────────────────────────────────────────
    manifest = {
        "dataset": {
            "name": "validation_pilot" if "pilot" in src.name else "full_dataset",
            "source": str(src.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "totalQuestions": len(display),
            "gradableQuestions": len(grading),
        },
        "questions": display,
    }

    with open(PUBLIC_DATA / "questions.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(PUBLIC_DATA / "answers.json", "w", encoding="utf-8") as f:
        json.dump({"answers": grading}, f, indent=2, ensure_ascii=False)

    # ── verify every manifest image path resolves ────────────────────────────
    broken = [d["id"] for d in display
              if not (FRONTEND_PUBLIC / d["imageUrl"].lstrip("/")).exists()]

    # ── report ───────────────────────────────────────────────────────────────
    print(f"\nSynced:    {len(display)} display records")
    print(f"Gradable:  {len(grading)} (verified answers)")
    print(f"Images:    {images_copied} copied, {images_already} already present")
    print(f"Broken image refs in manifest: {len(broken)}")
    if skipped:
        print(f"\nSKIPPED ({len(skipped)}):")
        for qid, problems in skipped:
            print(f"  - {qid}: {'; '.join(problems)}")
    if broken:
        print(f"BROKEN: {broken}")

    if broken or (skipped and not args.allow_skips):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
