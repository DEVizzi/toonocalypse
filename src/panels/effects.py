"""Code-drawn comic SFX text and speed lines for impact panels (§6 & §10.D)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR


def add_impact_effects(img: Image.Image, sfx_text: str = "POW!") -> Image.Image:
    out = img.copy().convert("RGBA")
    w, h = out.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Radial comic speed lines around the border
    cx, cy = w // 2, h // 2
    r_inner = min(w, h) * 0.36
    r_outer = max(w, h) * 0.72
    for deg in range(0, 360, 12):
        rad = math.radians(deg)
        x0 = cx + int(r_inner * math.cos(rad))
        y0 = cy + int(r_inner * math.sin(rad))
        x1 = cx + int(r_outer * math.cos(rad))
        y1 = cy + int(r_outer * math.sin(rad))
        draw.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 110), width=3)

    if sfx_text:
        font_path = ASSETS_DIR / "fonts" / "PlayfairDisplay-Regular.ttf"
        fsize = max(44, w // 12)
        try:
            font = ImageFont.truetype(str(font_path), fsize)
        except Exception:
            font = ImageFont.load_default()
        tx, ty = int(w * 0.60), int(h * 0.14)
        # Bold outline + bright yellow comic fill
        for dx, dy in ((-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)):
            draw.text((tx + dx, ty + dy), sfx_text, font=font, fill=(20, 20, 20, 255))
        draw.text((tx, ty), sfx_text, font=font, fill=(255, 224, 40, 255))

    return Image.alpha_composite(out, overlay).convert("RGB")
