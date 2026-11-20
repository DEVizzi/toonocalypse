"""M5 procedural cartoon SFX (numpy only, zero samples, zero licences). Every function returns a mono float32 array
at SR in [-1, 1]. Kept short and punchy for Shorts: bonks, boings, slide-whistle falls, splats, zaps, airhorn, risers,
dings, gate clank + referee whistle, crowd oohs/cheers, betrayal sting, tape-rewind, winner fanfare."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

SR = 44100
_RNG = np.random.default_rng(1234)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur), dtype=np.float32) / SR


def _env(n: int, a: float = 0.005, r: float = 0.08, curve: float = 4.0) -> np.ndarray:
    """Fast attack, exponential decay envelope."""
    t = np.arange(n, dtype=np.float32) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    dec = np.exp(-curve * np.maximum(0, t - a) / max(r, 1e-3))
    return (att * dec).astype(np.float32)


def _sweep(f0: float, f1: float, dur: float, kind: str = "sine", expo: bool = True) -> np.ndarray:
    t = _t(dur)
    k = t / max(dur, 1e-4)
    f = f0 * (f1 / f0) ** k if expo else f0 + (f1 - f0) * k
    ph = 2 * np.pi * np.cumsum(f) / SR
    return _osc(ph, kind)


def _osc(ph: np.ndarray, kind: str) -> np.ndarray:
    if kind == "square":
        return np.sign(np.sin(ph)).astype(np.float32) * 0.7
    if kind == "pulse":
        return np.where((ph / (2 * np.pi)) % 1.0 < 0.25, 0.7, -0.7).astype(np.float32)
    if kind == "saw":
        return (2 * ((ph / (2 * np.pi)) % 1.0) - 1).astype(np.float32) * 0.6
    if kind == "tri":
        return (2 * np.abs(2 * ((ph / (2 * np.pi)) % 1.0) - 1) - 1).astype(np.float32)
    return np.sin(ph).astype(np.float32)


def _tone(freq: float, dur: float, kind: str = "sine") -> np.ndarray:
    return _osc(2 * np.pi * freq * _t(dur), kind)


def _noise(dur: float) -> np.ndarray:
    return _RNG.uniform(-1, 1, int(SR * dur)).astype(np.float32)


def smooth(x: np.ndarray, k: int) -> np.ndarray:
    """Cheap low-pass (moving average of k samples)."""
    if k <= 1:
        return x
    return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same").astype(np.float32)


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    return (x * (peak / m)).astype(np.float32) if m > 1e-6 else x


def _mix(*parts: np.ndarray) -> np.ndarray:
    n = max(p.size for p in parts)
    out = np.zeros(n, np.float32)
    for p in parts:
        out[: p.size] += p
    return out


# ------------------------------------------------------------------------------------------------ the bank
@lru_cache(maxsize=64)
def bonk(pitch: float = 1.0) -> np.ndarray:
    body = _sweep(460 * pitch, 120 * pitch, 0.16) * _env(int(SR * 0.16), r=0.07)
    click = smooth(_noise(0.02), 3) * _env(int(SR * 0.02), r=0.008) * 0.6
    return _norm(_mix(body, click))


@lru_cache(maxsize=8)
def thud() -> np.ndarray:
    body = _sweep(110, 42, 0.22) * _env(int(SR * 0.22), r=0.1)
    rumble = smooth(_noise(0.18), 40) * _env(int(SR * 0.18), r=0.06) * 3.0
    return _norm(_mix(body, rumble), 0.85)


@lru_cache(maxsize=8)
def boing() -> np.ndarray:
    t = _t(0.42)
    f = (220 * (480 / 220) ** (t / 0.42)) * (1 + 0.18 * np.sin(2 * np.pi * 16 * t) * np.exp(-t * 3))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    return _norm(x * _env(t.size, a=0.004, r=0.3, curve=3.0))


@lru_cache(maxsize=8)
def fall_whistle(dur: float = 0.65) -> np.ndarray:
    """Classic cartoon slide-whistle drop."""
    t = _t(dur)
    f = 1500 * (280 / 1500) ** (t / dur) * (1 + 0.02 * np.sin(2 * np.pi * 7 * t))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    env = np.clip(t / 0.03, 0, 1) * np.clip((dur - t) / 0.08, 0, 1)
    return _norm(x * env * 0.8, 0.7)


@lru_cache(maxsize=8)
def splat() -> np.ndarray:
    n = smooth(_noise(0.3), 12) * _env(int(SR * 0.3), a=0.002, r=0.12) * 2.5
    low = _sweep(160, 50, 0.2) * _env(int(SR * 0.2), r=0.09)
    return _norm(_mix(n, low))


@lru_cache(maxsize=8)
def zap() -> np.ndarray:
    x = _sweep(1400, 180, 0.22, "square") * _env(int(SR * 0.22), r=0.12)
    crushed = np.round(x * 6) / 6
    return _norm(crushed.astype(np.float32), 0.6)


@lru_cache(maxsize=8)
def pop() -> np.ndarray:
    return _norm(_sweep(700, 1700, 0.06) * _env(int(SR * 0.06), r=0.03), 0.55)


@lru_cache(maxsize=4)
def airhorn() -> np.ndarray:
    t = _t(0.8)
    vib = 1 + 0.006 * np.sin(2 * np.pi * 6 * t)
    x = sum(_osc(2 * np.pi * np.cumsum(f * vib) / SR, "saw") for f in (311.1, 370.0, 466.2))
    env = np.clip(t / 0.02, 0, 1) * np.clip((0.8 - t) / 0.1, 0, 1)
    return _norm(smooth(x * env, 3), 0.8)


@lru_cache(maxsize=4)
def riser() -> np.ndarray:
    t = _t(0.9)
    sw = _sweep(180, 1400, 0.9) * (t / 0.9) * 0.6
    air = smooth(_noise(0.9), 6) * (t / 0.9) ** 2 * 0.5
    return _norm(_mix(sw, air), 0.7)


@lru_cache(maxsize=4)
def ding() -> np.ndarray:
    x = _tone(1318.5, 0.7) + 0.5 * _tone(2637, 0.7) + 0.25 * _tone(3955.5, 0.7)
    return _norm(x * _env(x.size, a=0.002, r=0.35, curve=3.0), 0.6)


@lru_cache(maxsize=4)
def gate_clank() -> np.ndarray:
    metal = sum(_tone(f, 0.45) * a for f, a in ((523, 1.0), (1187, 0.7), (1693, 0.5), (2460, 0.35)))
    metal = metal * _env(metal.size, a=0.001, r=0.18)
    click = _noise(0.015) * 0.8
    t = _t(0.5)
    whistle = np.sin(2 * np.pi * np.cumsum(2650 + 120 * np.sign(np.sin(2 * np.pi * 28 * t))) / SR).astype(np.float32)
    whistle = whistle * np.clip(t / 0.02, 0, 1) * np.clip((0.5 - t) / 0.05, 0, 1) * 0.5
    out = _mix(metal, click)
    lead = np.zeros(int(SR * 0.12), np.float32)
    return _norm(_mix(out, np.concatenate([lead, whistle])), 0.85)


@lru_cache(maxsize=4)
def crowd_ooh() -> np.ndarray:
    t = _t(1.1)
    voices = sum(np.sin(2 * np.pi * np.cumsum(f * (1 - 0.12 * t / 1.1) * (1 + 0.01 * np.sin(2 * np.pi * (5 + i) * t))) / SR)
                 for i, f in enumerate((260, 330, 395, 520)))
    breath = smooth(_noise(1.1), 25) * 2.0
    env = np.sin(np.pi * np.clip(t / 1.1, 0, 1)) ** 1.5
    return _norm(((voices * 0.25 + breath) * env).astype(np.float32), 0.6)


@lru_cache(maxsize=4)
def cheer() -> np.ndarray:
    t = _t(2.2)
    crowd = smooth(_noise(2.2), 9) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 3.3 * t)))
    env = np.clip(t / 0.15, 0, 1) * np.clip((2.2 - t) / 0.6, 0, 1)
    whistles = np.zeros_like(t)
    for st in (0.3, 0.9, 1.4):
        m = (t > st) & (t < st + 0.35)
        whistles[m] += np.sin(2 * np.pi * (2400 + 300 * np.sin(2 * np.pi * 9 * (t[m] - st))) * t[m]) * 0.25
    return _norm(((crowd * 1.4 + whistles) * env).astype(np.float32), 0.7)


@lru_cache(maxsize=4)
def betrayal_sting() -> np.ndarray:
    """Dun-dun-DUNNN minor stab."""
    parts = []
    for root, dur in ((146.8, 0.16), (138.6, 0.16), (110.0, 0.7)):
        ch = sum(_tone(root * m, dur, "saw") for m in (1.0, 1.189, 1.498))
        parts.append(smooth(ch * _env(ch.size, a=0.004, r=dur * 0.7, curve=2.5), 4))
        parts.append(np.zeros(int(SR * 0.03), np.float32))
    return _norm(np.concatenate(parts), 0.75)


@lru_cache(maxsize=4)
def rewind() -> np.ndarray:
    t = _t(0.45)
    chirp = np.sin(2 * np.pi * np.cumsum(600 + 2400 * (t / 0.45) ** 2 + 300 * np.sin(2 * np.pi * 40 * t)) / SR)
    return _norm((chirp * np.clip((0.45 - t) / 0.08, 0, 1) * 0.6).astype(np.float32), 0.5)


@lru_cache(maxsize=4)
def fire_crackle() -> np.ndarray:
    n = _noise(0.45)
    pops = (np.abs(_RNG.standard_normal(n.size)) > 2.6).astype(np.float32)
    x = smooth(n, 30) * 2.0 + pops * _noise(0.45) * 0.8
    return _norm(x * _env(n.size, a=0.01, r=0.3, curve=3.0), 0.6)


@lru_cache(maxsize=4)
def fanfare() -> np.ndarray:
    notes = [(523.3, 0.12), (659.3, 0.12), (784.0, 0.12), (1046.5, 0.5)]
    parts = []
    for f, d in notes:
        x = _tone(f, d, "pulse") + 0.5 * _tone(f / 2, d, "tri")
        parts.append(x * _env(x.size, a=0.004, r=d * 0.9, curve=2.0))
    chord = sum(_tone(f, 0.9, "pulse") for f in (523.3, 659.3, 784.0)) * 0.5
    parts.append(chord * _env(chord.size, a=0.01, r=0.7, curve=2.0))
    return _norm(np.concatenate(parts), 0.8)


# ------------------------------------------------------------------------------------------------ v4.3 accents
@lru_cache(maxsize=4)
def record_scratch() -> np.ndarray:
    """Quick vinyl record-scratch (sudden reversal punchline): noisy wobbling band-pass chirp back & forth."""
    t = _t(0.30)
    wob = np.sin(2 * np.pi * (3.2 * t + 9.0 * t * t))
    f = 900 + 1500 * wob
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    grit = smooth(_noise(0.30), 4) * (0.55 + 0.45 * np.abs(wob)).astype(np.float32)
    env = np.clip(t / 0.01, 0, 1) * np.clip((0.30 - t) / 0.05, 0, 1)
    return _norm(((tone * 0.55 + grit * 0.8) * env).astype(np.float32), 0.6)


@lru_cache(maxsize=4)
def sad_slide_whistle() -> np.ndarray:
    """Tiny sad descending slide-whistle (dummy/self-KO punchline)."""
    t = _t(0.55)
    f = 880 * (330 / 880) ** (t / 0.55) * (1 + 0.035 * np.sin(2 * np.pi * 6.5 * t))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    env = np.clip(t / 0.02, 0, 1) * np.clip((0.55 - t) / 0.12, 0, 1)
    return _norm((x * env * 0.8).astype(np.float32), 0.5)


@lru_cache(maxsize=4)
def comic_bonk() -> np.ndarray:
    """Crisp hollow wood-block cartoon bonk (betrayal punchline)."""
    body = _sweep(980, 520, 0.09, "tri") * _env(int(SR * 0.09), r=0.035)
    knock = _sweep(1900, 1300, 0.03) * _env(int(SR * 0.03), r=0.01) * 0.5
    return _norm(_mix(body, knock), 0.7)


@lru_cache(maxsize=4)
def glitch_zip() -> np.ndarray:
    """Short electronic 'bzzt-zip' for Glitch's lag-blink: bit-crushed buzz then a rising zip."""
    buzz_t = _t(0.07)
    buzz = np.sign(np.sin(2 * np.pi * 140 * buzz_t)) * 0.6 + smooth(_noise(0.07), 2) * 0.4
    buzz = np.round(buzz * 4) / 4 * _env(buzz_t.size, a=0.002, r=0.06, curve=2.0)
    zip_ = _sweep(500, 3800, 0.08, "square") * _env(int(SR * 0.08), a=0.002, r=0.07, curve=2.5)
    return _norm(np.concatenate([buzz.astype(np.float32), np.round(zip_ * 5) / 5]).astype(np.float32), 0.55)


@lru_cache(maxsize=2)
def grand_fanfare() -> np.ndarray:
    """Louder, longer Grand Final championship fanfare (brass triad climb + held major chord + timpani)."""
    notes = [(392.0, 0.14), (523.3, 0.14), (659.3, 0.14), (784.0, 0.22), (659.3, 0.12), (1046.5, 0.7)]
    parts = []
    for f, d in notes:
        x = _tone(f, d, "saw") + 0.6 * _tone(f / 2, d, "pulse") + 0.3 * _tone(f * 2, d, "tri")
        parts.append(x * _env(x.size, a=0.006, r=d * 0.95, curve=1.6))
    chord = sum(_tone(f, 1.4, "saw") for f in (523.3, 659.3, 784.0, 1046.5)) * 0.4
    parts.append(chord * _env(chord.size, a=0.02, r=1.2, curve=1.8))
    out = np.concatenate(parts)
    for k in range(3):                                  # timpani rolls under the climb
        tp = _sweep(98, 60, 0.25) * _env(int(SR * 0.25), r=0.12)
        s = int(SR * 0.14 * k * 2)
        out[s:s + tp.size] += tp[: max(0, min(tp.size, out.size - s))] * 0.9
    return _norm(out.astype(np.float32), 0.9)

