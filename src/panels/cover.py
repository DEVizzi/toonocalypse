"""Episode cover / thumbnail frame builder (§6.3 & §10.H)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR


def build_cover_image(
    hook_panel_path: Path,
    out_path: Path,
    hook_words: str,
    part_num: int,
    part_count: int,
    size: tuple[int, int] = (1080, 1920),
) -> Path:
    """Create a cover frame from the hook panel + <=3-word punch + Pt X/N badge."""
    panel = Image.open(hook_panel_path).convert("RGB")
    tw, th = size
    # Center-crop panel to target aspect
    target_ratio = tw / th
    pw, ph = panel.size
    if pw / ph > target_ratio:
        new_w = int(ph * target_ratio)
        left = (pw - new_w) // 2
        panel = panel.crop((left, 0, left + new_w, ph))
    else:
        new_h = int(pw / target_ratio)
        top = (ph - new_h) // 2
        panel = panel.crop((0, top, pw, top + new_h))
    cover = panel.resize(size, Image.LANCZOS)

    draw = ImageDraw.Draw(cover)
    font_path = ASSETS_DIR / "fonts" / "PlayfairDisplay-Regular.ttf"
    try:
        big_font = ImageFont.truetype(str(font_path), 88)
        badge_font = ImageFont.truetype(str(font_path), 52)
    except Exception:
        big_font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    words = " ".join(hook_words.split()[:3]).upper()
    tx = int(tw * 0.08)
    ty = int(th * 0.14)
    for dx, dy in ((-4, -4), (4, -4), (-4, 4), (4, 4)):
        draw.text((tx + dx, ty + dy), words, font=big_font, fill="#111111")
    draw.text((tx, ty), words, font=big_font, fill="#FFE033")

    if part_count > 1:
        badge = f"Pt {part_num}/{part_count}"
        bx0, by0 = int(tw * 0.08), int(th * 0.07)
        bx1, by1 = bx0 + 250, by0 + 78
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=18, fill="#D32F2F", outline="#FFFFFF", width=4)
        draw.text((bx0 + 24, by0 + 10), badge, font=badge_font, fill="#FFFFFF")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cover.save(out_path, quality=95)
    return out_path
