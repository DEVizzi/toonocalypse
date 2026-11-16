"""Daily layered panel compositor from reusable Art Library (§3.3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from src.common.config import ROOT, load_all_characters


def _scale_factor(char_data: dict[str, Any]) -> float:
    """Map character bible height_units to normalized frame height fraction."""
    hu = float(char_data.get("height_units", 1.0))
    return max(0.30, min(0.76, 0.36 * hu + 0.16))


def _paste_with_contact_shadow(canvas: Image.Image, sprite: Image.Image, x: int, y: int) -> None:
    """Draw a soft elliptical contact shadow under the sprite, then alpha-composite sprite."""
    sw, sh = sprite.size
    shadow = Image.new("RGBA", (sw, max(24, sh // 10)), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.ellipse([int(sw * 0.18), 4, int(sw * 0.82), shadow.height - 4], fill=(15, 18, 28, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    canvas.alpha_composite(shadow, (x, y + sh - shadow.height // 2 - 4))
    canvas.alpha_composite(sprite, (x, y))


def _apply_lighting_match(fg: Image.Image, bg: Image.Image) -> Image.Image:
    """Subtly match foreground brightness/warmth to the background scene."""
    bg_small = bg.convert("RGB").resize((16, 16))
    pixels = list(bg_small.getdata())
    avg_luma = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / (len(pixels) * 255.0)
    factor = max(0.86, min(1.12, 0.85 + 0.30 * avg_luma))
    rgb = fg.convert("RGB")
    alpha = fg.split()[3]
    adjusted = ImageEnhance.Brightness(rgb).enhance(factor).convert("RGBA")
    adjusted.putalpha(alpha)
    return adjusted


def compose_panel_layers(
    panel: dict[str, Any],
    library_index: dict[str, Any],
    out_dir: Path,
    size: tuple[int, int] = (1080, 1920),
    aspect_key: str = "9x16",
    pose_override: dict[str, str] | None = None,
) -> dict[str, Path]:
    """Compose background + scale-accurate character layers + shadows + lighting into separate & composite PNGs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = int(panel.get("panel_id", 1))
    chars_bible = load_all_characters()
    bgs_map = library_index.get("backgrounds", {})
    chars_map = library_index.get("characters", {})

    bg_slug = str(panel.get("background", ""))
    bg_info = bgs_map.get(bg_slug) or next(iter(bgs_map.values()), {})
    bg_rel = bg_info.get(aspect_key) or bg_info.get("9x16") or bg_info.get("16x9")
    if not bg_rel or not (ROOT / bg_rel).exists():
        raise FileNotFoundError(f"Missing library background '{bg_slug}' ({bg_rel})")

    bg_img = ImageOps.fit(Image.open(ROOT / bg_rel).convert("RGBA"), size, method=Image.Resampling.LANCZOS)
    bg_path = out_dir / f"panel_{pid}_bg.png"
    bg_img.convert("RGB").save(bg_path)

    fg_canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    slugs = list(panel.get("characters", []))[:3]
    poses_dict = dict(panel.get("poses") or {})
    if pose_override:
        poses_dict.update(pose_override)

    w, h = size
    count = max(1, len(slugs))
    for idx, slug in enumerate(slugs):
        char_poses = chars_map.get(slug, {})
        pose_name = poses_dict.get(slug, "idle")
        pose_entry = char_poses.get(pose_name) or char_poses.get("idle")
        if not pose_entry or not (ROOT / pose_entry["path"]).exists():
            raise FileNotFoundError(f"Missing library sprite for '{slug}' pose '{pose_name}'")

        sprite = Image.open(ROOT / pose_entry["path"]).convert("RGBA")
        cdata = chars_bible.get(slug, {"height_units": 1.0})
        target_h = int(h * _scale_factor(cdata))
        target_w = max(64, int(sprite.width * (target_h / max(1, sprite.height))))
        max_w = int(w * (0.72 if count == 1 else (0.44 if count == 2 else 0.31)))
        if target_w > max_w:
            target_h = max(64, int(target_h * (max_w / target_w)))
            target_w = max_w
        sprite = sprite.resize((target_w, target_h), Image.Resampling.LANCZOS)
        sprite = _apply_lighting_match(sprite, bg_img)

        cx = int(w * (idx + 1) / (count + 1))
        x = max(20, min(w - target_w - 20, cx - target_w // 2))
        y = int(h * 0.84) - target_h
        _paste_with_contact_shadow(fg_canvas, sprite, x, max(24, y))

    fg_path = out_dir / f"panel_{pid}_fg.png"
    fg_canvas.save(fg_path)

    comp = bg_img.copy()
    comp.alpha_composite(fg_canvas)
    comp_path = out_dir / f"panel_{pid}_comp.png"
    comp.convert("RGB").save(comp_path)
    return {"bg": bg_path, "fg": fg_path, "composite": comp_path}


def compose_comic_page(
    script: dict[str, Any],
    library_index: dict[str, Any],
    work_dir: Path,
    out_page_path: Path,
) -> tuple[Path, list[dict[str, Path]]]:
    """Compose all 6 panels from library assets and assemble a 2x3 page with 24px white gutters."""
    gutter = 24
    pw, ph = 900, 900
    w = gutter * 3 + pw * 2
    h = gutter * 4 + ph * 3
    page = Image.new("RGB", (w, h), "#FFFFFF")
    draw = ImageDraw.Draw(page)

    panel_layers: list[dict[str, Path]] = []
    layers_dir = work_dir / "composed_layers"
    for idx, panel in enumerate(script["panels"][:6]):
        v_layers = compose_panel_layers(panel, library_index, layers_dir / "v", size=(1080, 1920), aspect_key="9x16")
        w_layers = compose_panel_layers(panel, library_index, layers_dir / "w", size=(1920, 1080), aspect_key="16x9")
        p_layers = compose_panel_layers(panel, library_index, layers_dir / "page", size=(pw, ph), aspect_key="16x9")
        talk_layers = compose_panel_layers(
            panel,
            library_index,
            layers_dir / "talk",
            size=(1080, 1920),
            aspect_key="9x16",
            pose_override={s: "talking" for s in panel.get("characters", [])},
        )
        idle_layers = compose_panel_layers(
            panel,
            library_index,
            layers_dir / "idle",
            size=(1080, 1920),
            aspect_key="9x16",
            pose_override={s: "idle" for s in panel.get("characters", [])},
        )
        panel_layers.append({
            "v_bg": v_layers["bg"],
            "v_fg": v_layers["fg"],
            "v_talk_fg": talk_layers["fg"],
            "v_idle_fg": idle_layers["fg"],
            "v_comp": v_layers["composite"],
            "w_bg": w_layers["bg"],
            "w_fg": w_layers["fg"],
            "w_comp": w_layers["composite"],
        })

        row, col = idx // 2, idx % 2
        x0 = gutter + col * (pw + gutter)
        y0 = gutter + row * (ph + gutter)
        thumb = Image.open(p_layers["composite"]).convert("RGB")
        page.paste(thumb, (x0, y0))
        draw.rectangle([x0, y0, x0 + pw - 1, y0 + ph - 1], outline="#222222", width=3)

    out_page_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(out_page_path)
    return out_page_path, panel_layers
