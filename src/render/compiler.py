"""Long-form 16:9 compilation builder using fast ffmpeg stream copy (§4 & §6)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR, load_settings


def _make_card_clip(image_path: Path, out_mp4: Path, duration: float = 3.5) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y",
            "-loop", "1", "-i", str(image_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", f"{duration:.2f}",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest",
            str(out_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_mp4


def compile_wide_film(title: str, wide_clips: list[Path], out_mp4: Path, work_dir: Path) -> Path:
    """Join title card + wide clips + finalLike.jpg end card with ffmpeg -c copy."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    if not wide_clips:
        raise ValueError("No wide clips provided for compilation")

    work_dir.mkdir(parents=True, exist_ok=True)
    series_name = load_settings().get("series_name", "Toonocalypse")

    # Title card
    title_img = work_dir / "title_card.png"
    img = Image.new("RGB", (1920, 1080), "#12172B")
    draw = ImageDraw.Draw(img)
    try:
        f_big = ImageFont.truetype(str(ASSETS_DIR / "fonts" / "PlayfairDisplay-Regular.ttf"), 84)
        f_sub = ImageFont.truetype(str(ASSETS_DIR / "fonts" / "Esteban-Regular.ttf"), 42)
    except Exception:
        f_big = ImageFont.load_default()
        f_sub = ImageFont.load_default()
    draw.text((140, 380), series_name.upper(), fill="#FFE033", font=f_sub)
    draw.text((140, 460), title[:48], fill="#FFFFFF", font=f_big)
    img.save(title_img)

    title_mp4 = _make_card_clip(title_img, work_dir / "title_card.mp4", duration=3.0)
    end_img = ASSETS_DIR / "outro" / "finalLike.jpg"
    clips = [title_mp4] + wide_clips
    if end_img.exists():
        clips.append(_make_card_clip(end_img, work_dir / "end_card.mp4", duration=4.0))

    concat_txt = work_dir / "compile_list.txt"
    concat_txt.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", "-movflags", "+faststart", str(out_mp4)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_mp4
