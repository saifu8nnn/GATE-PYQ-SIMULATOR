"""
image_cropper.py — Crop question regions from PDF pages and save as PNG.

Rules
-----
  * The image is the canonical question representation. Text is NOT used.
  * Each crop uses the exact PDF-coordinate boundaries found by question_detector.
    - start_y / end_y are already correct: they sit above the question heading
      and above the "Answer key" line respectively.
  * Multi-page questions are stitched vertically with Pillow.
  * The crop ALWAYS includes the complete question body including all options,
    mathematical notation, tables, diagrams, and code.
  * It is better to include slightly too much than to cut content.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from config import RENDER_SCALE, LEFT_PADDING, RIGHT_PADDING
from models import QuestionBoundary
from utils import get_logger, clamp, page_height, page_width

logger = get_logger()


# ── Pixmap → PIL conversion ────────────────────────────────────────────────────

def _pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    """Convert a fitz.Pixmap to a PIL Image (RGB, white background)."""
    mode = "RGBA" if pix.alpha else "RGB"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    return img


# ── Single-page crop ───────────────────────────────────────────────────────────

def _crop_page_region(
    page: fitz.Page,
    y_start: float,
    y_end: float,
    scale: float = RENDER_SCALE,
) -> Image.Image:
    """
    Render the horizontal strip [y_start, y_end] of `page` at `scale` DPI.

    Parameters
    ----------
    page    : Open fitz.Page
    y_start : Top of the region in PDF points
    y_end   : Bottom of the region in PDF points
    scale   : Render multiplier (2.5 → ~180 DPI)

    Returns
    -------
    PIL.Image (RGB)
    """
    pw = page_width(page)
    ph = page_height(page)

    # Clamp to page bounds
    y0 = clamp(y_start, 0.0, ph)
    y1 = clamp(y_end,   0.0, ph)

    # Guard against zero-height or inverted strips
    if y1 - y0 < 5:
        y1 = min(ph, y0 + 5)

    # Full page width with optional horizontal padding
    x0 = max(0.0,  -LEFT_PADDING)    # effectively 0 since LEFT_PADDING >= 0
    x1 = min(pw,    pw + RIGHT_PADDING)

    clip   = fitz.Rect(x0, y0, x1, y1)
    matrix = fitz.Matrix(scale, scale)
    pix    = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)

    return _pixmap_to_pil(pix)


# ── Vertical stitch ────────────────────────────────────────────────────────────

def _stitch_vertical(images: list[Image.Image]) -> Image.Image:
    """
    Concatenate a list of PIL Images vertically.
    All images are expanded to the maximum width, padded with white on the right.
    """
    if not images:
        raise ValueError("No images to stitch")
    if len(images) == 1:
        return images[0]

    max_w  = max(img.width for img in images)
    total_h = sum(img.height for img in images)

    canvas   = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y_offset = 0
    for img in images:
        canvas.paste(img, (0, y_offset))
        y_offset += img.height
    return canvas


# ── Main crop function ─────────────────────────────────────────────────────────

def crop_question(
    doc: fitz.Document,
    boundary: QuestionBoundary,
    output_path: Path,
    scale: float = RENDER_SCALE,
) -> Image.Image:
    """
    Crop a complete question (one or more pages) and save as a PNG.

    The boundary coordinates are used directly:
      - boundary.start_page / start_y: top of the question heading (minus padding)
      - boundary.end_page   / end_y  : just above the "Answer key" line

    Multi-page questions are rendered page-by-page and stitched vertically.

    Parameters
    ----------
    doc         : Open fitz.Document
    boundary    : QuestionBoundary from question_detector
    output_path : Destination PNG file path
    scale       : Render scale (default from config.py)

    Returns
    -------
    The final composed PIL Image (also written to output_path).
    """
    sp = boundary.start_page
    ep = boundary.end_page
    sy = boundary.start_y
    ey = boundary.end_y

    logger.debug(
        f"  Cropping: p{sp}:{sy:.1f} - p{ep}:{ey:.1f}"
    )

    strips: list[Image.Image] = []

    if sp == ep:
        # ── Single-page question ──────────────────────────────────────────────
        img = _crop_page_region(doc[sp], sy, ey, scale)
        strips.append(img)

    else:
        # ── Multi-page question ───────────────────────────────────────────────
        for page_idx in range(sp, ep + 1):
            page = doc[page_idx]
            ph   = page_height(page)

            if page_idx == sp:
                # First page: from start_y to the bottom of the page
                img = _crop_page_region(page, sy, ph, scale)
            elif page_idx == ep:
                # Last page: from the top of the page to end_y
                img = _crop_page_region(page, 0.0, ey, scale)
            else:
                # Middle pages: entire page
                img = _crop_page_region(page, 0.0, ph, scale)

            strips.append(img)
            logger.debug(
                f"    Page {page_idx}: rendered {img.width}x{img.height} px"
            )

    final = _stitch_vertical(strips)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(output_path), format="PNG", optimize=True)
    logger.info(
        f"  Saved: {output_path.name}  ({final.width}x{final.height} px)"
    )
    return final
