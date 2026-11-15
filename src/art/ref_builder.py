"""Character reference sheet builder (§7.7)."""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR, ROOT, load_all_characters, load_models, load_style_guide
from src.common.quota import QuotaTracker


def render_placeholder_ref_sheet(char: dict[str, Any], out_path: Path) -> Path:
    """Create a clean #F0F0F0 reference sheet with height ruler & palette swatches."""
    w, h = 1600, 900
    img = Image.new("RGB", (w, h), "#F0F0F0")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(ASSETS_DIR / "fonts" / "Esteban-Regular.ttf"), 24)
    except Exception:
        font = ImageFont.load_default()

    draw.text((40, 28), f"{char['name']} ({char['species']}) - bible v{char['bible_version']} | H={char['height_units']}x", fill="#1A1A1A", font=font)

    # Height ruler on left
    draw.line([(70, 120), (70, 820)], fill="#555555", width=3)
    for y in range(120, 821, 70):
        draw.line([(58, y), (82, y)], fill="#555555", width=2)

    pri = char["palette"]["primary"]
    sec = char["palette"]["secondary"]
    acc = char["palette"]["accent"]
    labels = ["Front", "3/4", "Side", "Back", "Happy", "Surprised", "Determined", "Laughing"]
    for idx, lbl in enumerate(labels):
        col, row = idx % 4, idx // 4
        cx = 260 + col * 340
        cy = 280 + row * 360
        draw.rounded_rectangle([cx - 120, cy - 120, cx + 120, cy + 120], radius=24, fill=pri, outline="#222222", width=4)
        draw.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=sec, outline=acc, width=6)
        draw.text((cx - 50, cy + 132), lbl, fill="#222222", font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def build_ref_sheet(slug: str, offline: bool = False, quota: QuotaTracker | None = None) -> Path:
    chars = load_all_characters()
    char = chars[slug]
    out_path = ROOT / char["reference_sheet"]
    if out_path.exists():
        return out_path
    from src.common.gemini import call_with_key_failover, has_gemini_keys

    if offline or not has_gemini_keys():
        return render_placeholder_ref_sheet(char, out_path)

    qt = quota or QuotaTracker()
    model = load_models().get("image_models", ["gemini-2.5-flash-image"])[0]
    prompt = (
        f"{load_style_guide()}\n\n"
        f"Character reference sheet on a plain #F0F0F0 background with a simple height ruler on the left: "
        f"4 full-body turnaround poses (front, 3/4, side, back) on top row and 4 close-up expressions "
        f"(happy, surprised, determined, laughing) on bottom row.\n"
        f"{char['visual_prompt']}\n"
        f"MUST HAVE: {'; '.join(char['anchors'])}\n"
        f"FORBIDDEN: {', '.join(char['forbidden'])}\n"
        f"NO text, NO labels."
    )
    if qt.can_spend("image", 1):
        try:
            from google.genai import types

            resp = call_with_key_failover(
                lambda client: client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
                )
            )
            qt.spend("image", 1)
            for cand in getattr(resp, "candidates", []) or []:
                for part in cand.content.parts:
                    if getattr(part, "inline_data", None) is not None:
                        img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        img.save(out_path)
                        return out_path
        except Exception:
            pass
    return render_placeholder_ref_sheet(char, out_path)
