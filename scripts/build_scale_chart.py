#!/usr/bin/env python3
"""Render characters/scale_chart.png from the frozen character bible."""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
HEROES_DIR = ROOT / "characters" / "heroes"
VILLAINS_DIR = ROOT / "characters" / "villains"
OUT_PATH = ROOT / "characters" / "scale_chart.png"
FONT_PATH = ROOT / "assets" / "fonts" / "Esteban-Regular.ttf"


def build_scale_chart() -> Path:
    chars = []
    for d in (HEROES_DIR, VILLAINS_DIR):
        for p in sorted(d.glob("*.json")):
            chars.append(json.loads(p.read_text(encoding="utf-8")))
    chars.sort(key=lambda c: (float(c["height_units"]), c["name"]))

    w, h = 2400, 720
    margin_x, baseline_y = 70, 600
    max_h = max(float(c["height_units"]) for c in chars)
    px_per_unit = 440.0 / max_h

    img = Image.new("RGB", (w, h), "#F7F7F7")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype(str(FONT_PATH), 28)
        font_lbl = ImageFont.truetype(str(FONT_PATH), 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_lbl = ImageFont.load_default()

    draw.text((margin_x, 22), "Toonocalypse Character Scale Chart (1.0 = Percival)", fill="#1A1A1A", font=font_title)

    # Ruler gridlines
    for unit in (0.5, 1.0, 1.5, 2.0, 2.5):
        y = int(baseline_y - unit * px_per_unit)
        draw.line([(margin_x, y), (w - margin_x, y)], fill="#DCDCDC", width=1)
        draw.text((16, y - 8), f"{unit:.1f}x", fill="#666666", font=font_lbl)

    draw.line([(margin_x, baseline_y), (w - margin_x, baseline_y)], fill="#333333", width=3)

    step = (w - 2 * margin_x) / len(chars)
    for idx, c in enumerate(chars):
        cx = int(margin_x + (idx + 0.5) * step)
        bar_h = max(14, int(float(c["height_units"]) * px_per_unit))
        bar_w = max(18, int(step * 0.58))
        x0, y0 = cx - bar_w // 2, baseline_y - bar_h
        x1, y1 = cx + bar_w // 2, baseline_y
        pri = c["palette"]["primary"]
        acc = c["palette"]["accent"]
        draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=pri, outline="#222222", width=2)
        draw.rectangle([x0 + 3, y0 + 3, x1 - 3, y0 + 9], fill=acc)
        short = c["name"].split()[0][:9]
        draw.text((x0, baseline_y + 8 + (idx % 2) * 18), f"{short} ({c['height_units']})", fill="#222222", font=font_lbl)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    out = build_scale_chart()
    print(f"Wrote {out}")
