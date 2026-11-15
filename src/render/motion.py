"""Fast ffmpeg motion-comic filtergraph builders (zoom, pan, impact shake)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def render_panel_clip(
    image_path: Path,
    out_mp4: Path,
    duration: float,
    width: int,
    height: int,
    camera: str = "zoom_in",
    impact: bool = False,
    fps: int = 30,
) -> Path:
    """Render one animated panel clip using fast ffmpeg zoompan + optional impact shake."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for rendering")

    frames = max(15, int(round(duration * fps)))
    if camera == "zoom_out":
        z_expr = f"max(1.0,1.12-0.12*on/{frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_right":
        z_expr = "1.10"
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_left":
        z_expr = "1.10"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "static_loop":
        z_expr = "1.0"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:  # zoom_in
        z_expr = f"min(1.12,1.0+0.12*on/{frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    shake = f",crop=iw-16:ih-16:8+8*sin(n*1.9)*lt(n\\,6):8+8*cos(n*2.3)*lt(n\\,6),scale={width}:{height}" if impact else ""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={fps}"
        f"{shake},setsar=1"
    )
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y",
            "-loop", "1", "-i", str(image_path),
            "-vf", vf,
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(fps),
            str(out_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_mp4
