"""2x3 comic page image generation with fallback models and offline dry-run renderer."""
from __future__ import annotations

import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from src.art.prompt_builder import build_page_prompt
from src.common.config import load_all_characters, load_models
from src.common.quota import QuotaTracker


def render_offline_comic_page(script: dict[str, Any], out_path: Path) -> Path:
    """Render a deterministic 2x3 comic page with 24px white gutters for dry-run & CI tests."""
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
            # Expressive eyes
            ew = max(8, rad // 6)
            draw.ellipse([cx - ew * 2, cy - ew, cx - ew // 2, cy + ew // 2], fill="#FFFFFF")
            draw.ellipse([cx + ew // 2, cy - ew, cx + ew * 2, cy + ew // 2], fill="#FFFFFF")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def generate_comic_page(
    script: dict[str, Any],
    out_path: Path,
    offline: bool = False,
    quota: QuotaTracker | None = None,
) -> Path:
    """Generate a 2x3 comic page using Gemini image models with fallback, or offline renderer."""
    if out_path.exists():
        return out_path
    if offline or not os.environ.get("GOOGLE_API_KEY"):
        return render_offline_comic_page(script, out_path)

    qt = quota or QuotaTracker()
    models_cfg = load_models()
    image_models = models_cfg.get("image_models", ["gemini-2.5-flash-image"])
    delay = float(models_cfg.get("quota", {}).get("min_delay_between_images_sec", 5))
    prompt, ref_paths = build_page_prompt(script)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    contents: list[Any] = [prompt]
    for rp in ref_paths[:4]:
        contents.append(Image.open(rp))

    last_err: Exception | None = None
    for model_name in image_models:
        if not qt.can_spend("image", 1):
            break
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            )
            qt.spend("image", 1)
            for cand in getattr(resp, "candidates", []) or []:
                for part in cand.content.parts:
                    if getattr(part, "inline_data", None) is not None:
                        img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        img.save(out_path)
                        time.sleep(delay)
                        return out_path
        except Exception as exc:
            last_err = exc
            time.sleep(delay)

    if last_err:
        raise RuntimeError(f"All image models failed: {last_err}") from last_err
    return render_offline_comic_page(script, out_path)
