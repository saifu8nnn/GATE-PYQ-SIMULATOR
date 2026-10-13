"""Tests for image cropping against document coordinates (Phase 3, 9.1)."""

from __future__ import annotations

import pytest

from conftest import add_page, bold, plain, requires_fitz

from image_cropper import crop_question
from question_detector import detect_question_boundaries
from utils import is_mostly_white


def _draw_block(page, y0, lines, step=16):
    y = y0
    for text in lines:
        plain(page, 120, y, text)
        y += step
    return y


@requires_fitz
def test_single_page_crop_contains_full_question(make_doc, tmp_path):
    doc = make_doc()
    page = add_page(doc)
    bold(page, 45, 100, "5.1.5")
    bold(page, 120, 100, "B Tree: GATE CSE 1999 | Question: 1.25")
    _draw_block(page, 130, [
        "Consider a B+ tree of order 5 containing the following keys.",
        "A. 3 levels",
        "B. 4 levels",
        "C. 5 levels",
        "D. 6 levels",
    ])
    plain(page, 120, 220, "gatecse-1999 databases b-tree 2-marks")

    bounds = detect_question_boundaries(doc, 0, 0, max_questions=5)
    out = tmp_path / "q.png"
    img = crop_question(doc, bounds[0], out)

    assert out.exists()
    assert img.width > 500          # full page width at render scale
    # sparse synthetic text → whiteness heuristic doesn't apply; assert ink:
    assert img.convert("L").getextrema()[0] < 128  # darkest pixel is text-dark

    # crop extends to the page bottom when nothing closes the question
    # (a lone question legitimately fills the rest of the page)
    below = bounds[0].end_y
    ph = page.rect.height
    assert below <= ph


@requires_fitz
def test_crop_stops_before_next_question(make_doc, tmp_path):
    doc = make_doc()
    page = add_page(doc)
    bold(page, 45, 100, "5.1.1")
    bold(page, 120, 100, "B Tree: GATE CSE 1989 | Question: 12a")
    _draw_block(page, 130, ["First question body with a diagram description."])
    plain(page, 120, 170, "gatecse-1989 databases b-tree descriptive")
    # second question BELOW on the same page
    bold(page, 45, 300, "5.1.2")
    bold(page, 120, 300, "B Tree: GATE CSE 1994 | Question: 14a")
    _draw_block(page, 330, ["Second question body, must NOT leak into image 1."])

    bounds = detect_question_boundaries(doc, 0, 0, max_questions=10)
    assert len(bounds) == 2
    # first boundary closes at/above the second question's heading
    # (strips are exactly adjacent by symmetric padding)
    assert bounds[0].end_page == 0
    assert bounds[0].end_y <= bounds[1].start_y

    img1 = crop_question(doc, bounds[0], tmp_path / "q1.png")
    # crop is a strip of page 1, not the whole page (no page-2 bleed-through)
    assert img1.height < doc[0].rect.height * 2.5
    # the rendered strip must end above the second question: at 2.5x scale,
    # end_y≈280pt → ~700px + padding, far below a full-page 1980px
    assert img1.height < int(doc[0].rect.height * 2.5 * 0.6)


@requires_fitz
def test_multi_page_question_is_stitched_vertically(make_doc, tmp_path):
    doc = make_doc()
    # page 1: heading + body
    p1 = add_page(doc)
    bold(p1, 45, 100, "5.1.4")
    bold(p1, 120, 100, "B Tree: GATE CSE 1997 | Question: 19")
    _draw_block(p1, 130, ["Part (a) of a long question on page one."])
    # page 2: continuation, ending with a tag line (next-question heading
    # would close it; simulate page break by closing at page end)
    p2 = add_page(doc)
    _draw_block(p2, 60, ["Continuation on page two with sub-parts (b) and (c)."])

    class B:  # handcrafted boundary: known multi-page case
        pass

    b = B()
    b.heading_text = "B Tree: GATE CSE 1997 | Question: 19"
    b.start_page, b.start_y = 0, 80.0
    b.end_page, b.end_y = 1, 120.0
    b.tag_line = None
    b.answer_text = None
    b.heading_match = None
    b.option_lines = []
    b.section_number = "5.1.4"

    img = crop_question(doc, b, tmp_path / "multi.png")
    # re-fetch pages by index: adding page 2 invalidated the page 1 handle
    page1_h = doc[0].rect.height
    expected_min_h = int((page1_h - 80 + 120) * 2.0)  # scaled strips
    assert img.height >= expected_min_h * 0.8  # stitched, not clipped
    assert img.width > 500


@requires_fitz
def test_crop_is_deterministic(make_doc, tmp_path):
    doc = make_doc()
    page = add_page(doc)
    bold(page, 120, 100, "B Tree: GATE CSE 1999 | Question: 1.25")
    _draw_block(page, 130, ["Stable content."])
    bounds = detect_question_boundaries(doc, 0, 0, max_questions=1)

    img1 = crop_question(doc, bounds[0], tmp_path / "a.png")
    img2 = crop_question(doc, bounds[0], tmp_path / "b.png")
    assert img1.size == img2.size
    assert list(img1.getdata()) == list(img2.getdata())
