"""Tests for 2x3 panel gutter detection, slicing, speech bubbles, and covers."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from src.panels.bubbles import draw_speech_bubble
from src.panels.cover import build_cover_image
from src.panels.slicer import detect_gutters, slice_page


def _make_synthetic_page(path: Path) -> None:
    img = Image.new("RGB", (1024, 1536), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    col_w, row_h, gap = 470, 470, 28
    for r in range(3):
        for c in range(2):
            x0 = 28 + c * (col_w + gap)
            y0 = 32 + r * (row_h + gap)
            draw.rectangle([x0, y0, x0 + col_w, y0 + row_h], fill=(80 + r * 40, 120 + c * 40, 200))
    img.save(path)


def test_slice_page_extracts_six_panels(tmp_path: Path) -> None:
    page = tmp_path / "page.png"
    _make_synthetic_page(page)
    boxes = detect_gutters(Image.open(page))
    assert len(boxes) == 6
    panels = slice_page(page, tmp_path / "panels")
    assert len(panels) == 6
    assert all(p.exists() for p in panels)


def test_speech_bubble_and_cover(tmp_path: Path) -> None:
    base = Image.new("RGB", (720, 720), (100, 140, 200))
    bubbled = draw_speech_bubble(base, "Brewtan", "Hold my cocoa!", position="top")
    assert bubbled.size == (720, 720)
    panel_path = tmp_path / "p0.png"
    bubbled.save(panel_path)
    cover = build_cover_image(panel_path, tmp_path / "cover.jpg", "WHO STOLE IT?", 1, 3)
    assert cover.exists()
    assert Image.open(cover).size == (1080, 1920)
