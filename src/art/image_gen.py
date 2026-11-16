"""Offline deterministic 2x3 page renderer for CI/tests only (live mode uses src/panels/compose.py)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from src.common.config import load_all_characters


def render_offline_comic_page(script: dict[str, Any], out_path: Path) -> Path:
    """Render a deterministic 2x3 comic page with 24px white gutters for CI unit/smoke tests ONLY."""
    gutter = 24
    pw, ph = 900, 900
    w = gutter * 3 + pw * 2
    h = gutter * 4 + ph * 3
    img = Image.new("RGB", (w, h), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    chars = load_all_characters()

    bg_colors = ["#E3F2FD", "#FFF8E1", "#FCE4EC", "#E8F5E9", "#EDE7F6", "#FFF3E0"]
    for idx, panel in enumerate(script["panels"][:6]):
        row, col = idx // 2, idx % 2
        x0 = gutter + col * (pw + gutter)
        y0 = gutter + row * (ph + gutter)
        x1, y1 = x0 + pw, y0 + ph
        draw.rectangle([x0, y0, x1, y1], fill=bg_colors[idx % len(bg_colors)], outline="#222222", width=4)

        slugs = panel.get("characters", [])[:3]
        for ci, slug in enumerate(slugs):
            c = chars.get(slug)
            if not c:
                continue
            pri = c["palette"]["primary"]
            acc = c["palette"]["accent"]
            scale = min(1.8, max(0.35, float(c.get("height_units", 1.0))))
            rad = int(95 * scale)
            cx = x0 + 220 + ci * 240
            cy = y1 - 140 - rad
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=pri, outline="#111111", width=5)
            draw.ellipse([cx - rad // 2, cy - rad // 2, cx + rad // 2, cy + rad // 2], fill=acc)
            ew = max(8, rad // 6)
            draw.ellipse([cx - ew * 2, cy - ew, cx - ew // 2, cy + ew // 2], fill="#FFFFFF")
            draw.ellipse([cx + ew // 2, cy - ew, cx + ew * 2, cy + ew // 2], fill="#FFFFFF")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
