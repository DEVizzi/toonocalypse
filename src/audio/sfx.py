"""Procedural CC0 1.0 sound-effect synthesizer (stdlib wave + math)."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from src.common.config import ASSETS_DIR

SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: list[float]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            frames.extend(struct.pack("<h", int(clamped * 32767)))
        wf.writeframes(bytes(frames))
    return path


def _synth_sweep(dur: float, f0: float, f1: float, amp: float = 0.6) -> list[float]:
    n = int(SAMPLE_RATE * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f0 + (f1 - f0) * t
        env = math.sin(math.pi * t)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        out.append(amp * env * math.sin(phase))
    return out


def ensure_sfx_library(sfx_dir: Path | None = None) -> dict[str, Path]:
    d = sfx_dir or (ASSETS_DIR / "sfx")
    specs = {
        "pop": _synth_sweep(0.12, 320, 780, 0.7),
        "whoosh": _synth_sweep(0.28, 600, 140, 0.45),
        "boing": _synth_sweep(0.35, 180, 520, 0.65),
        "splat": _synth_sweep(0.22, 260, 95, 0.7),
        "zap": _synth_sweep(0.18, 920, 240, 0.6),
        "ding": _synth_sweep(0.40, 880, 880, 0.55),
        "end_chime": _synth_sweep(0.45, 523.25, 783.99, 0.5),
    }
    paths: dict[str, Path] = {}
    for name, samples in specs.items():
        p = d / f"{name}.wav"
        if not p.exists():
            _write_wav(p, samples)
        paths[name] = p
    return paths
