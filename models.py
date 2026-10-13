"""
models.py — Data model for a single GATE PYQ question record.

Rules:
  * The 'image' field is the canonical question representation.
  * Text fields are metadata/location only.
  * Never set verified=True automatically.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import json


@dataclass
class Question:
    # ── Identity ──────────────────────────────────────────────────────────────
    id: str                         # e.g. "gate-cse-1994-q14a"
    exam: str                       # "GATE CSE"
    year: int                       # 1994
    set: Optional[str]              # "Set 1" | null

    # ── Taxonomy ──────────────────────────────────────────────────────────────
    subject: str                    # "Databases"
    topic: Optional[str]            # "B Tree"
    subtopic: Optional[str]         # nested topic if available

    # ── Question identity ─────────────────────────────────────────────────────
    question_number: str            # sanitized: "14a", "2-ii", "1.25"
    question_number_raw: Optional[str]  # original from PDF: "1.22,"
    section_number: Optional[str]   # PDF section index, e.g. "5.1.5"
    question_type: Optional[str]    # "MCQ"|"MSQ"|"NAT"|"DESCRIPTIVE"|None
    marks: Optional[int]            # 1 | 2 | null
    difficulty: Optional[str]       # "easy"|"normal"|"difficult"|null

    # ── Options ───────────────────────────────────────────────────────────────
    options_present: Optional[bool]         # True if A/B/C/D visible in source
    option_labels_detected: Optional[list]  # e.g. ["A","B","C","D"]

    # ── Answer ────────────────────────────────────────────────────────────────
    correct_answer: Any             # "C" | ["A","C"] | 42 | [50,52] | null
    answer_status: str              # "verified"|"needs_review"|"not_available"
    answer_source: Optional[str]    # "answer_key_page"|"inline"|null
    answer_evidence: Optional[str]  # raw text from source, e.g. "5.1.5 -> B"

    # ── Image (canonical) ─────────────────────────────────────────────────────
    image: str                      # relative path "images/gate-cse-1994-q14a.png"

    # ── Source provenance ─────────────────────────────────────────────────────
    source_pdf: str                 # "volume2.pdf"
    source_pages: list              # [124] or [124, 125]

    # ── Quality flags ─────────────────────────────────────────────────────────
    verified: bool = False          # Always starts False; set manually after review
    notes: Optional[str] = None     # Free-text reviewer comments
    extraction_version: Optional[int] = None  # Pipeline version that produced this record

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ── Boundary record (internal use, not persisted) ─────────────────────────────

@dataclass
class QuestionBoundary:
    """
    Raw boundary information found during PDF scanning.
    Used internally: question_detector -> image_cropper -> metadata_parser.
    """
    heading_text: str
    start_page: int
    start_y: float
    end_page: int
    end_y: float
    tag_line: Optional[str]
    answer_text: Optional[str]
    heading_match: Any = None
    option_lines: list = field(default_factory=list)
    section_number: Optional[str] = None   # e.g. "5.1.5" from left-margin bold


# ── Answer status constants ────────────────────────────────────────────────────

class AnswerStatus:
    VERIFIED      = "verified"
    NOT_AVAILABLE = "not_available"
    NEEDS_REVIEW  = "needs_review"


# ── Question type constants ────────────────────────────────────────────────────

class QuestionType:
    MCQ                 = "MCQ"
    MSQ                 = "MSQ"
    NAT                 = "NAT"
    DESCRIPTIVE         = "DESCRIPTIVE"
    FILL_IN_THE_BLANK   = "FILL_IN_THE_BLANK"
    MATCH_THE_FOLLOWING = "MATCH_THE_FOLLOWING"
    UNKNOWN             = "UNKNOWN"
