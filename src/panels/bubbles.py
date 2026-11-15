"""Code-drawn comic speech bubbles and narration boxes (§5 & §10.E)."""
from __future__ import annotations

from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("PlayfairDisplay-Regular.ttf", "Esteban-Regular.ttf"):
        p = ASSETS_DIR / "fonts" / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_speech_bubble(
    img: Image.Image,
    speaker_name: str,
    text: str,
    position: str = "top",
) -> Image.Image:
    """Draw a crisp white comic speech bubble with speaker tag inside safe margins."""
    out = img.copy().convert("RGBA")
    w, h = out.size
    draw = ImageDraw.Draw(out)

    font_size = max(24, w // 28)
    font = _load_font(font_size)
    tag_font = _load_font(max(18, font_size - 6))

    wrapped = wrap(text.strip(), width=26)[:3]
    line_h = font_size + 6
    box_w = min(int(w * 0.78), max(280, int(max((draw.textlength(ln, font=font) for ln in wrapped), default=200) + 48)))
    box_h = len(wrapped) * line_h + 44

    x0 = (w - box_w) // 2
    y0 = int(h * 0.08) if position == "top" else int(h * 0.62)
    x1, y1 = x0 + box_w, y0 + box_h

    # Tail pointer
    tail_x = x0 + box_w // 3
    tail_y = y1 + 26 if position == "top" else y0 - 26
    draw.polygon([(tail_x - 14, y1 - 2), (tail_x + 14, y1 - 2), (tail_x - 4, tail_y)], fill=(255, 255, 255, 245), outline=(20, 20, 20, 255))

    draw.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=(255, 255, 255, 245), outline=(20, 20, 20, 255), width=4)
    draw.text((x0 + 18, y0 + 8), speaker_name.upper(), fill=(200, 30, 50, 255), font=tag_font)

    ty = y0 + 32
    for ln in wrapped:
        draw.text((x0 + 20, ty), ln, fill=(18, 18, 18, 255), font=font)
        ty += line_h
    return out.convert("RGB")
