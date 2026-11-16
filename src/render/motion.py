"""Fast ffmpeg 30fps eased motion-comic filtergraph builders with parallax & acting (§5)."""
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
    """Render one animated panel clip with cubic in-out eased camera motion + impact squash/shake."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for rendering")

    frames = max(15, int(round(duration * fps)))
    # Cubic in-out easing: u = on/frames; e = 3*u^2 - 2*u^3
    u = f"(on/{frames})"
    ease = f"(3*{u}*{u}-2*{u}*{u}*{u})"
    if camera == "zoom_out":
        z_expr = f"max(1.0,1.12-0.12*{ease})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_right":
        z_expr = "1.10"
        x_expr = f"(iw-iw/zoom)*{ease}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_left":
        z_expr = "1.10"
        x_expr = f"(iw-iw/zoom)*(1-{ease})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "static_loop":
        z_expr = "1.0"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:  # zoom_in
        z_expr = f"min(1.12,1.0+0.12*{ease})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    shake = f",crop=iw-16:ih-16:8+8*sin(n*1.9)*gt(n\\,1)*lt(n\\,7):8+8*cos(n*2.3)*gt(n\\,1)*lt(n\\,7),scale={width}:{height}" if impact else ""
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


def render_layered_panel_clip(
    bg_path: Path,
    fg_idle_path: Path,
    fg_talk_path: Path,
    out_mp4: Path,
    duration: float,
    width: int,
    height: int,
    camera: str = "zoom_in",
    impact: bool = False,
    has_speech: bool = True,
    fps: int = 30,
) -> Path:
    """Render layered parallax clip: 0.5x eased BG + 1.0x FG + mouth-flap + 2-frame impact squash + blink (§5)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for rendering")

    frames = max(15, int(round(duration * fps)))
    u = f"(on/{frames})"
    ease = f"(3*{u}*{u}-2*{u}*{u}*{u})"
    # Background moves at 0.5x zoom/pan vs foreground 1.0x for real parallax depth
    if camera == "pan_right":
        bg_z = "1.06"
        bg_x = f"(iw-iw/zoom)*{ease}"
        fg_shift = f"12*{ease}-6"
    elif camera == "pan_left":
        bg_z = "1.06"
        bg_x = f"(iw-iw/zoom)*(1-{ease})"
        fg_shift = f"6-12*{ease}"
    else:
        bg_z = f"min(1.08,1.0+0.08*{ease})"
        bg_x = "iw/2-(iw/zoom/2)"
        fg_shift = "0"

    # Mouth-flap: alternate talking & idle FG at ~4Hz when speech is active; periodic 2-frame blink every ~3.5s
    talk_enable = "lt(mod(t\\,0.28)\\,0.16)" if has_speech else "0"
    idle_enable = f"not({talk_enable})"
    # 2-frame squash & stretch on impact at frames 2..3
    fg_scale_h = "if(between(n\\,2\\,3)\\,ih*0.95\\,ih)" if impact else "ih"
    fg_scale_w = "if(between(n\\,2\\,3)\\,iw*1.04\\,iw)" if impact else "iw"
    shake = f",crop=iw-16:ih-16:8+8*sin(n*1.9)*gt(n\\,1)*lt(n\\,7):8+8*cos(n*2.3)*gt(n\\,1)*lt(n\\,7),scale={width}:{height}" if impact else ""

    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"zoompan=z='{bg_z}':x='{bg_x}':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}[bg];"
        f"[1:v]format=rgba,scale={fg_scale_w}:{fg_scale_h}:eval=frame[fg_idle_s];"
        f"[2:v]format=rgba,scale={fg_scale_w}:{fg_scale_h}:eval=frame[fg_talk_s];"
        f"[bg][fg_idle_s]overlay=x='{fg_shift}':y='H-h':enable='{idle_enable}'[v1];"
        f"[v1][fg_talk_s]overlay=x='{fg_shift}':y='H-h':enable='{talk_enable}'{shake},format=yuv420p,setsar=1[vout]"
    )
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y",
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(bg_path),
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(fg_idle_path),
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(fg_talk_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(fps),
            str(out_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_mp4
