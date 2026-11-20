"""M5 procedural chiptune music bed (numpy only, zero licence risk — README decision). Upbeat 150 bpm I-V-vi-IV loop
in C major: triangle bass, 25% pulse arpeggio lead, noise/sine drum kit. `intense_from` switches to the OVERTIME
arrangement (16th hats, octave-up lead, double kicks). Returns mono float32 at SR."""
from __future__ import annotations

import numpy as np

from src.audio.sfx import SR, _env, _noise, _osc, smooth

PROG = [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)]       # C, G, Am, F (semitones above C)
ROOTS = [0, 7, 9, 5]
C3 = 130.81


def _hz(semi: float, base: float = C3) -> float:
    return base * 2 ** (semi / 12)


def _note(buf: np.ndarray, start: float, dur: float, freq: float, kind: str, amp: float, rel: float = 0.6) -> None:
    i0 = int(start * SR)
    n = int(dur * SR)
    if i0 >= buf.size or n <= 0:
        return
    n = min(n, buf.size - i0)
    t = np.arange(n, dtype=np.float32) / SR
    x = _osc(2 * np.pi * freq * t, kind) * _env(n, a=0.003, r=dur * rel, curve=2.2) * amp
    buf[i0:i0 + n] += x


def _kick(buf, start, amp=0.9):
    i0 = int(start * SR)
    n = min(int(0.16 * SR), buf.size - i0)
    if n <= 0:
        return
    t = np.arange(n, dtype=np.float32) / SR
    f = 150 * (45 / 150) ** (t / 0.16)
    buf[i0:i0 + n] += np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32) * _env(n, r=0.09) * amp


def _snare(buf, start, amp=0.5):
    i0 = int(start * SR)
    n = min(int(0.14 * SR), buf.size - i0)
    if n <= 0:
        return
    buf[i0:i0 + n] += smooth(_noise(0.14)[:n], 2) * _env(n, r=0.05) * amp


def _hat(buf, start, amp=0.18):
    i0 = int(start * SR)
    n = min(int(0.04 * SR), buf.size - i0)
    if n <= 0:
        return
    x = _noise(0.04)[:n]
    buf[i0:i0 + n] += (x - smooth(x, 4)) * _env(n, r=0.015) * amp


def chiptune(duration: float, bpm: float = 150.0, intense_from: float = 1e9, seed: int = 0) -> np.ndarray:
    buf = np.zeros(int(duration * SR) + SR, np.float32)
    beat = 60.0 / bpm
    bar = beat * 4
    s16 = beat / 4
    rng = np.random.default_rng(seed)
    patterns = [[0, 1, 2, 1, 0, 2, 1, 2], [0, 2, 1, 2, 3, 2, 1, 0], [2, 1, 0, 1, 2, 3, 2, 1]]
    nbars = int(duration / bar) + 2
    for b in range(nbars):
        t0 = b * bar
        if t0 > duration:
            break
        chord = PROG[b % 4]
        root = ROOTS[b % 4]
        hot = t0 >= intense_from
        # bass: driving eighths (root / octave)
        for k in range(8):
            semi = root - 12 + (12 if k % 4 == 2 else 0)
            _note(buf, t0 + k * beat / 2, beat / 2 * 0.9, _hz(semi), "tri", 0.42 if not hot else 0.5, rel=0.7)
        # lead arpeggio: 16ths over chord tones, pattern changes every 2 bars
        pat = patterns[(b // 2 + int(rng.integers(0, 2))) % len(patterns)]
        octave = 24 if not hot else 36
        steps = 16
        for k in range(steps):
            if not hot and k % 2 == 1 and b % 2 == 0:
                continue                                        # breathing room in the calm section
            idx = pat[k % len(pat)]
            semi = chord[idx % 3] + (12 if idx == 3 else 0) + octave
            _note(buf, t0 + k * s16, s16 * 0.85, _hz(semi), "pulse", 0.13 if not hot else 0.12, rel=0.5)
        # drums
        for k in range(4):
            bt = t0 + k * beat
            if k in (0, 2):
                _kick(buf, bt)
            if hot and k in (1, 3):
                _kick(buf, bt + beat / 2, 0.6)
            if k in (1, 3):
                _snare(buf, bt)
            for h in range(4 if hot else 2):
                _hat(buf, bt + h * (beat / (4 if hot else 2)), 0.16 if h % 2 == 0 else 0.1)
    out = buf[: int(duration * SR)]
    fade = min(out.size, int(0.25 * SR))
    out[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    m = float(np.max(np.abs(out))) or 1.0
    return (out / m * 0.9).astype(np.float32)
