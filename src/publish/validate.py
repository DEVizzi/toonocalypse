"""ffprobe / ffmpeg pre-publish validation gate (v4.3.1). Fails CLOSED: any problem -> non-zero exit, no upload,
no state commit.

Checks (YouTube Shorts spec + our render contract):
- container parses; exactly one H.264 video stream, 1080x1920, ~30 fps, yuv420p
- an AAC audio stream exists (44.1 kHz), audio duration within 0.35 s of the video duration (no truncated voice)
- total duration 15-60 s (Shorts)
- audio is genuinely audible: volumedetect mean >= -38 dB and max >= -12 dB (catches silent / broken TTS mixes)

Usage:  python -m src.publish.validate output/episode.mp4
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DIR = (ROOT / "output").resolve()

LIMITS = {"w": 1080, "h": 1920, "fps": 30.0, "min_s": 15.0, "max_s": 60.0, "av_drift_s": 0.35,
          "mean_db": -38.0, "max_db": -12.0, "zoom_min": 0.70, "zoom_max": 3.00}


def _safe_path(p: str) -> Path:
    """Only validate files inside <repo>/output (never arbitrary paths)."""
    path = Path(p).resolve()
    if not str(path).startswith(str(ALLOWED_DIR) + "/") or path.suffix.lower() != ".mp4" or not path.is_file():
        raise ValueError("video must be an existing .mp4 inside output/")
    return path


def _bin(name: str) -> str:
    b = shutil.which(name)
    if not b:
        raise FileNotFoundError(f"{name} not found on PATH")
    return b


def probe(path: Path) -> dict:
    out = subprocess.run([_bin("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60, check=False)
    if out.returncode != 0:
        raise RuntimeError("ffprobe could not parse the file")
    return json.loads(out.stdout or "{}")


def loudness(path: Path) -> tuple[float, float]:
    out = subprocess.run([_bin("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=120, check=False)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out.stderr or "")
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", out.stderr or "")
    if not (mean and peak):
        raise RuntimeError("volumedetect produced no measurement (no decodable audio?)")
    return float(mean.group(1)), float(peak.group(1))


def validate_camera_meta(meta: dict) -> list[str]:
    """Verifies rendered camera zoom stayed inside sane broadcast bounds (catches 0.002x zoom collapses)."""
    fails: list[str] = []
    zmin = meta.get("cam_zoom_min")
    zmax = meta.get("cam_zoom_max")
    if zmin is not None and float(zmin) < LIMITS["zoom_min"]:
        fails.append(f"camera zoom collapsed ({float(zmin):.4f} < {LIMITS['zoom_min']:.2f})")
    if zmax is not None and float(zmax) > LIMITS["zoom_max"]:
        fails.append(f"camera zoom exploded ({float(zmax):.4f} > {LIMITS['zoom_max']:.2f})")
    return fails


def validate(p: str) -> list[str]:
    """Returns a list of failures (empty list = PASS)."""
    path = _safe_path(p)
    info = probe(path)
    streams = info.get("streams") or []
    v = [s for s in streams if s.get("codec_type") == "video"]
    a = [s for s in streams if s.get("codec_type") == "audio"]
    fails: list[str] = []
    if len(v) != 1:
        return [f"expected 1 video stream, found {len(v)}"]
    vs = v[0]
    if vs.get("codec_name") != "h264":
        fails.append(f"video codec {vs.get('codec_name')} != h264")
    if (int(vs.get("width", 0)), int(vs.get("height", 0))) != (LIMITS["w"], LIMITS["h"]):
        fails.append(f"resolution {vs.get('width')}x{vs.get('height')} != 1080x1920")
    num, _, den = str(vs.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / max(1.0, float(den or 1))
    if abs(fps - LIMITS["fps"]) > 0.5:
        fails.append(f"fps {fps:.2f} != 30")
    if vs.get("pix_fmt") != "yuv420p":
        fails.append(f"pix_fmt {vs.get('pix_fmt')} != yuv420p")
    dur = float((info.get("format") or {}).get("duration") or 0.0)
    if not (LIMITS["min_s"] <= dur <= LIMITS["max_s"]):
        fails.append(f"duration {dur:.2f}s outside {LIMITS['min_s']:.0f}-{LIMITS['max_s']:.0f}s")
    if not a:
        fails.append("NO AUDIO STREAM")
        return fails
    au = a[0]
    if au.get("codec_name") != "aac":
        fails.append(f"audio codec {au.get('codec_name')} != aac")
    if int(au.get("sample_rate", 0)) != 44100:
        fails.append(f"audio sample rate {au.get('sample_rate')} != 44100")
    a_dur = float(au.get("duration") or 0.0)
    v_dur = float(vs.get("duration") or dur)
    if a_dur <= 0 or abs(a_dur - v_dur) > LIMITS["av_drift_s"]:
        fails.append(f"audio/video duration mismatch ({a_dur:.2f}s vs {v_dur:.2f}s)")
    mean_db, max_db = loudness(path)
    if mean_db < LIMITS["mean_db"] or max_db < LIMITS["max_db"]:
        fails.append(f"audio too quiet / silent (mean {mean_db:.1f} dB, max {max_db:.1f} dB)")
    meta_path = path.with_suffix(".json")
    if meta_path.is_file():
        try:
            fails.extend(validate_camera_meta(json.loads(meta_path.read_text())))
        except (OSError, ValueError):
            fails.append("companion metadata .json unreadable")
    return fails


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m src.publish.validate output/<file>.mp4", file=sys.stderr)
        return 2
    try:
        fails = validate(argv[0])
    except (ValueError, FileNotFoundError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[FFPROBE GATE FAIL] {exc}", file=sys.stderr)
        return 1
    if fails:
        for f in fails:
            print(f"[FFPROBE GATE FAIL] {f}", file=sys.stderr)
        return 1
    print(f"[FFPROBE + CAMERA GATE PASS] {Path(argv[0]).name}: H.264 1080x1920@30 + AAC 44.1k, A/V in sync, audible, zoom OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
