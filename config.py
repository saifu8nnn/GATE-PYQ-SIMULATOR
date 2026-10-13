"""
config.py — Central configuration for the GATE PYQ extraction pipeline.
All paths, constants, and tunable parameters live here.
"""

from pathlib import Path

# ── Directories ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
PDF_PATH   = BASE_DIR / "volume2.pdf"

OUTPUT_DIR = BASE_DIR / "output"
IMAGE_DIR  = OUTPUT_DIR / "images"
DATA_DIR   = OUTPUT_DIR / "data"
REPORT_DIR = OUTPUT_DIR / "reports"

# ── Extraction scope ──────────────────────────────────────────────────────────
SECTION_NAME   = "Databases"
SOURCE_PDF_NAME = "volume2.pdf"
MAX_QUESTIONS  = 10                # Phase 1: first 10 only

# ── Extraction version ────────────────────────────────────────────────────────
# Bump this whenever croppers/detectors change in a way that requires images or
# records to be regenerated. Records carrying a different version are treated as
# intentional updates (re-cropped + rewritten) instead of being skipped, so an
# old, defective image can never silently survive a pipeline fix.
EXTRACTION_VERSION = 2

# ── Rendering ─────────────────────────────────────────────────────────────────
RENDER_SCALE = 2.5                 # 2.5× gives ~180 DPI from a 72-DPI PDF

# ── Crop padding (PDF points, before scaling) ─────────────────────────────────
TOP_PADDING    = 20
BOTTOM_PADDING = 20
LEFT_PADDING   = 15
RIGHT_PADDING  = 15

# ── Section search fallbacks (tried in order) ─────────────────────────────────
SECTION_SEARCH_TERMS = [
    "Databases (268)",
    "5. Databases",
    "Databases",
]

# ── Regex for question headings ───────────────────────────────────────────────
# Matches:  "B Tree: GATE CSE 2024 Set 2 | Question: 14a"
# Also:     "Indexing: GATE CSE 1994 | Question: 12a"
import re  # noqa: E402  (import here so the constant is near its definition)

QUESTION_HEADING_RE = re.compile(
    r"""
    ^
    (?P<topic>.+?)          # topic, e.g. "B Tree" or "Indexing"
    :\s*
    GATE\s*(?:CSE|IT)       # exam type
    \s+
    (?P<year>19\d{2}|20\d{2})           # year
    (?:                     # optional Set
        \s*Set\s*(?P<set>\d+)
    )?
    \s*\|\s*Question\s*:\s*
    (?P<question_number>[\w.,\-]+)      # e.g. 14a, 2-ii, 1.16, 02,xiv
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# ── Tag-line regex ────────────────────────────────────────────────────────────
# Matches both:
#   Modern: "gatecse-2020 numerical-answers databases b-tree indexing 2-marks"
#           "gateit-2001 databases ..."
#   Old:    "gate1989  databases  b-tree  descriptive"
#           "gate1994  databases  b-tree  normal  descriptive"
TAG_LINE_RE = re.compile(
    r"^gate(?:(?:cse|it)-\d{4}|\d{4})\b",
    re.IGNORECASE | re.MULTILINE,
)

# ── Type normalisation map ────────────────────────────────────────────────────
TYPE_MAP = {
    "numerical-answers": "NAT",
    "numerical-answer":  "NAT",
    "multiple-selects":  "MSQ",
    "multiple-select":   "MSQ",
    "descriptive":       "DESCRIPTIVE",
    "fill-in-the-blanks": "FILL_IN_THE_BLANK",
    "fill-in-the-blank":  "FILL_IN_THE_BLANK",
    "match-the-following": "MATCH_THE_FOLLOWING",
    "match-the-following-type": "MATCH_THE_FOLLOWING",
}

# ── Known difficulty tokens ───────────────────────────────────────────────────
DIFFICULTY_TOKENS = {"easy", "normal", "difficult", "hard"}

# ── Known marks tokens ───────────────────────────────────────────────────────
MARKS_TOKENS = {"1-mark": 1, "2-marks": 2, "1mark": 1, "2marks": 2}

# ── Answer-key boundary markers ──────────────────────────────────────────────
ANSWER_KEY_RE = re.compile(
    r"^answer\s*key\b|^answer\s*:\s*|^\s*ans\s*[:\.]",
    re.IGNORECASE | re.MULTILINE,
)

# ── Image validation thresholds ──────────────────────────────────────────────
MIN_IMAGE_WIDTH      = 500    # pixels
MIN_IMAGE_HEIGHT     = 100    # pixels
BLANK_PIXEL_THRESHOLD = 0.98  # >98% white → suspicious
