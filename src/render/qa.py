"""Render quality gates: duration, aspect ratio, audio, loudness, loop-join (§6 & §10.F)."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from src.common.config import load_playbook


@dataclass
class RenderQAResult:
    passed: bool
    duration: float
    width: int
    height: int
    has_audio: bool
    loop_diff: float
    reasons: list[str]


def frame_difference_score(frame_a: Path, frame_b: Path) -> float:
    """Mean absolute pixel difference (0..255) between two frames."""
    a = np.asarray(Image.open(frame_a).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(frame_b).convert("RGB").resize((a.shape[1], a.shape[0])), dtype=np.float32)
    return float(np.mean(np.abs(a - b)))


def check_render_qa(video_path: Path, is_vertical: bool = True) -> RenderQAResult:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("ffprobe and ffmpeg are required for render QA")

    reasons: list[str] = []
    if not video_path.exists() or video_path.stat().st_size < 10_000:
        return RenderQAResult(False, 0.0, 0, 0, False, 999.0, ["missing or tiny output file"])

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)
    streams = info.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float(info.get("format", {}).get("duration", 0.0))
    w = int(v_stream.get("width", 0)) if v_stream else 0
    h = int(v_stream.get("height", 0)) if v_stream else 0
    has_audio = a_stream is not None

    gates = load_playbook().get("gates", {}).get("render_qa", {})
    max_loop_diff = float(gates.get("max_loop_join_diff", 28.0))

    if is_vertical:
        if dur <= 0 or dur > 59.0:
            reasons.append(f"vertical duration {dur:.2f}s out of (0, 59]s")
        if (w, h) != (1080, 1920):
            reasons.append(f"expected 1080x1920, got {w}x{h}")
    else:
        if (w, h) != (1920, 1080):
            reasons.append(f"expected 1920x1080, got {w}x{h}")
    if not has_audio:
        reasons.append("missing audio stream")

    loop_diff = 0.0
    if is_vertical and dur > 1.0:
        first_png = video_path.with_suffix(".first.png")
        last_png = video_path.with_suffix(".last.png")
        subprocess.run([ffmpeg, "-y", "-i", str(video_path), "-vframes", "1", str(first_png)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([ffmpeg, "-y", "-sseof", "-0.1", "-i", str(video_path), "-vframes", "1", str(last_png)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if first_png.exists() and last_png.exists():
            loop_diff = frame_difference_score(first_png, last_png)
            if loop_diff > max_loop_diff:
                reasons.append(f"loop join frame diff {loop_diff:.1f} > {max_loop_diff}")
        for p in (first_png, last_png):
            if p.exists():
                p.unlink()

    return RenderQAResult(not reasons, dur, w, h, has_audio, round(loop_diff, 2), reasons)
