"""v3.4 procedural CC0 Cartoon / Game-Show Funk BGM loop (numpy only, zero licence risk).
126 BPM syncopated slap-funk bassline with octave pops, staccato brass/clavinet chord stabs, playful cartoon marimba
melody hook, and crisp funk drum groove (kick, snappy snare + ghost notes, 16th hi-hats). Shifts into hype double-time
arrangement at `intense_from` (OVERTIME). Returns normalized mono float32 at SR."""
from __future__ import annotations

import numpy as np

from src.audio.sfx import SR, _env, _noise, _osc, smooth

# Funky Mixolydian / Dorian game-show progression in F: F7 -> Ab7 -> Bb7 -> C7 (semitones above C2/C3)
ROOTS = [5, 8, 10, 12]
CHORDS = [
    (5, 9, 12, 15),    # F7
    (8, 12, 15, 18),   # Ab7
    (10, 14, 17, 20),  # Bb7
    (12, 16, 19, 22),  # C7
]
C2 = 65.406


def _hz(semi: float, base: float = C2) -> float:
    return base * (2.0 ** (semi / 12.0))


def _slap_bass(buf: np.ndarray, start: float, dur: float, freq: float, pop_oct: bool = False, amp: float = 0.52) -> None:
    i0 = int(start * SR)
    n = int(dur * SR)
    if i0 >= buf.size or n <= 0:
        return
    n = min(n, buf.size - i0)
    t = np.arange(n, dtype=np.float32) / SR
    f = freq * (2.0 if pop_oct else 1.0)
    # Punchy FM/harmonic funk bass with bright initial pluck transient that mellows fast
    mod = np.sin(2.0 * np.pi * f * 2.0 * t) * np.exp(-t * (28.0 if pop_oct else 18.0)) * (2.2 if pop_oct else 1.4)
    sig = np.sin(2.0 * np.pi * f * t + mod).astype(np.float32)
    sub = np.sin(2.0 * np.pi * freq * t).astype(np.float32) * 0.55
    env = _env(n, a=0.002, r=max(0.04, dur * 0.72), curve=2.6)
    buf[i0:i0 + n] += (sig * 0.68 + sub * 0.42) * env * amp


def _brass_stab(buf: np.ndarray, start: float, dur: float, semis: tuple[int, ...], amp: float = 0.16) -> None:
    i0 = int(start * SR)
    n = int(dur * SR)
    if i0 >= buf.size or n <= 0:
        return
    n = min(n, buf.size - i0)
    t = np.arange(n, dtype=np.float32) / SR
    acc = np.zeros(n, dtype=np.float32)
    for s in semis:
        f = _hz(s + 12)
        # Slight pitch scoop into the chord stab for authentic cartoon game-show brass feel
        f_curve = f * (1.0 - 0.03 * np.exp(-t * 45.0))
        ph = 2.0 * np.pi * np.cumsum(f_curve) / SR
        acc += _osc(ph, "saw") * 0.6 + _osc(ph * 1.004, "pulse") * 0.4
    acc = smooth(acc, 4) * _env(n, a=0.004, r=max(0.04, dur * 0.75), curve=2.8) * (amp / len(semis))
    buf[i0:i0 + n] += acc


def _marimba(buf: np.ndarray, start: float, dur: float, semi: float, amp: float = 0.17) -> None:
    i0 = int(start * SR)
    n = int(dur * SR)
    if i0 >= buf.size or n <= 0:
        return
    n = min(n, buf.size - i0)
    t = np.arange(n, dtype=np.float32) / SR
    f = _hz(semi)
    # Woody cartoon marimba: fundamental + 4th harmonic overtone with fast decay
    sig = np.sin(2.0 * np.pi * f * t) + 0.35 * np.sin(2.0 * np.pi * f * 4.0 * t) * np.exp(-t * 36.0)
    env = _env(n, a=0.0015, r=max(0.035, dur * 0.62), curve=3.2)
    buf[i0:i0 + n] += sig.astype(np.float32) * env * amp


def _kick(buf: np.ndarray, start: float, amp: float = 0.78) -> None:
    i0 = int(start * SR)
    n = min(int(0.14 * SR), buf.size - i0)
    if n <= 0 or i0 < 0:
        return
    t = np.arange(n, dtype=np.float32) / SR
    f = 155.0 * (46.0 / 155.0) ** (t / 0.14)
    click = smooth(_noise(0.012), 3)
    sig = np.sin(2.0 * np.pi * np.cumsum(f) / SR).astype(np.float32) * _env(n, a=0.001, r=0.085, curve=2.8)
    buf[i0:i0 + n] += sig * amp
    cn = min(click.size, n)
    buf[i0:i0 + cn] += click[:cn] * 0.18 * amp


def _snare(buf: np.ndarray, start: float, amp: float = 0.44) -> None:
    i0 = int(start * SR)
    n = min(int(0.12 * SR), buf.size - i0)
    if n <= 0 or i0 < 0:
        return
    t = np.arange(n, dtype=np.float32) / SR
    body = np.sin(2.0 * np.pi * 195.0 * t).astype(np.float32) * np.exp(-t * 32.0) * 0.45
    snap = smooth(_noise(0.12)[:n], 2) * _env(n, a=0.001, r=0.048, curve=3.0)
    buf[i0:i0 + n] += (body + snap) * amp


def _hat(buf: np.ndarray, start: float, open_hat: bool = False, amp: float = 0.14) -> None:
    dur = 0.085 if open_hat else 0.032
    i0 = int(start * SR)
    n = min(int(dur * SR), buf.size - i0)
    if n <= 0 or i0 < 0:
        return
    x = _noise(dur)[:n]
    hp = x - smooth(x, 4)
    buf[i0:i0 + n] += hp * _env(n, a=0.001, r=dur * 0.65, curve=2.6) * amp


def funk_bgm(duration: float, bpm: float = 126.0, intense_from: float = 1e9, seed: int = 0) -> np.ndarray:
    buf = np.zeros(int(duration * SR) + SR, np.float32)
    beat = 60.0 / bpm
    s16 = beat / 4.0
    bar = beat * 4.0
    rng = np.random.default_rng(seed)

    # 16-step syncopated funk bass groove: (step, length_16ths, semi_offset, octave_pop)
    bass_groove = [
        (0, 2, 0, False),
        (2, 1, 0, True),
        (3, 1, 10, False),
        (6, 2, 7, False),
        (8, 2, 0, False),
        (11, 1, 12, True),
        (12, 2, 10, False),
        (14, 2, 7, False),
    ]
    melodies = [
        [(0, 0), (3, 4), (6, 7), (8, 10), (10, 7), (12, 4), (14, 7)],
        [(0, 7), (2, 10), (4, 12), (7, 10), (10, 7), (12, 4), (15, 0)],
        [(1, 4), (3, 7), (6, 12), (8, 10), (11, 7), (13, 4), (14, 2)],
    ]

    nbars = int(duration / bar) + 2
    for b in range(nbars):
        t0 = b * bar
        if t0 > duration:
            break
        root = ROOTS[b % 4]
        chord = CHORDS[b % 4]
        hot = t0 >= intense_from
        swing = 0.012 * beat

        # 1. Syncopated slap-funk bassline
        for st, ln, off, pop in bass_groove:
            ts = t0 + st * s16 + (swing if st % 2 == 1 else 0.0)
            _slap_bass(buf, ts, ln * s16 * 0.88, _hz(root + off), pop_oct=pop or (hot and st % 4 == 2),
                       amp=0.46 if not hot else 0.54)

        # 2. Off-beat game-show brass/clavinet chord stabs (steps 2, 6, 11, 14)
        for st, ln in ((2, 1.4), (6, 1.8), (11, 1.4), (14, 1.6)):
            ts = t0 + st * s16 + (swing if st % 2 == 1 else 0.0)
            _brass_stab(buf, ts, ln * s16, chord, amp=0.18 if not hot else 0.23)

        # 3. Playful cartoon marimba melody hook
        mel = melodies[(b + int(rng.integers(0, 2))) % len(melodies)]
        oct_shift = 24 if not hot else 36
        for st, deg in mel:
            ts = t0 + st * s16 + (swing if st % 2 == 1 else 0.0)
            _marimba(buf, ts, s16 * 1.6, root + deg + oct_shift, amp=0.15 if not hot else 0.18)

        # 4. Crisp funk drum kit (syncopated kick, backbeat + ghost snares, 16th hats)
        for st in (0, 3, 8, 10) if not hot else (0, 3, 6, 8, 10, 14):
            _kick(buf, t0 + st * s16 + (swing if st % 2 == 1 else 0.0), amp=0.76 if st in (0, 8) else 0.56)
        for st in (4, 12):
            _snare(buf, t0 + st * s16, amp=0.46)
        for st in (7, 9, 15):
            _snare(buf, t0 + st * s16 + swing, amp=0.16)   #funk ghost notes
        for st in range(16):
            if not hot and st % 2 == 1 and st not in (3, 7, 11, 15):
                continue
            ts = t0 + st * s16 + (swing if st % 2 == 1 else 0.0)
            _hat(buf, ts, open_hat=(st in (6, 14)), amp=0.14 if st % 2 == 0 else 0.09)

    out = buf[: int(duration * SR)]
    fade = min(out.size, int(0.18 * SR))
    if fade > 1:
        out[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    m = float(np.max(np.abs(out))) or 1.0
    return (out / m * 0.90).astype(np.float32)


# Backwards-compatible alias
chiptune = funk_bgm
