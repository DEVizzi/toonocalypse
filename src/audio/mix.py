"""Audio: music bed per mood (licensed track from assets/music/<mood>/ if present, else an in-repo synthesized
CC0 pad), synthesized CC0 SFX, ducking under voices, and two-pass loudness normalization to -14 LUFS."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from src.common.config import ASSETS_DIR, settings

SR = 48000
CHORDS = {  # semitone offsets from A2 (110 Hz); 4 chords x 4 s loops
    "epic": [[0, 3, 7, 12], [8, 12, 15, 20], [3, 7, 10, 15], [10, 14, 17, 22]],
    "mystery": [[0, 3, 6, 10], [1, 4, 8, 13], [0, 3, 7, 11], [-2, 2, 5, 8]],
    "emotional": [[3, 7, 10, 15], [10, 14, 17, 22], [0, 3, 7, 12], [8, 12, 15, 20]],
    "tech": [[0, 7, 12, 15], [5, 12, 17, 20], [3, 10, 15, 19], [7, 14, 19, 22]],
}


def _hz(semi: float) -> float:
    return 110.0 * 2 ** (semi / 12)


def synth_bed(mood: str, seconds: float) -> np.ndarray:
    """Soft evolving pad (+ arpeggio for tech, + low pulse for epic). Original, dedicated to CC0."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    chords = CHORDS.get(mood, CHORDS["emotional"])
    seg = 4.0
    for k in range(int(np.ceil(seconds / seg))):
        a, b = int(k * seg * SR), min(n, int((k + 1) * seg * SR) + SR)
        if a >= n:
            break
        tt = t[a:b] - k * seg
        env = np.minimum(1, tt / 1.2) * np.minimum(1, np.maximum(0, (seg + 1 - tt)) / 1.2)
        for semi in chords[k % len(chords)]:
            f = _hz(semi)
            out[a:b] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2.003 * f * tt)) * 0.08
        if mood == "tech":
            arp = chords[k % len(chords)]
            step = (tt * 4).astype(int) % len(arp)
            freq = np.array([_hz(arp[i] + 12) for i in step])
            pluck = np.exp(-((tt * 4) % 1) * 6)
            out[a:b] += np.sin(2 * np.pi * freq * tt) * pluck * 0.05
        if mood == "epic":
            out[a:b] += np.sin(2 * np.pi * _hz(chords[k % len(chords)][0] - 12) * tt) * np.exp(-((tt * 1) % 1) * 4) * 0.12
    # cheap stereo-less "room": two delays
    for d, g in ((0.11, 0.35), (0.23, 0.2)):
        i = int(d * SR)
        out[i:] += out[:-i] * g
    return out / max(1e-6, np.abs(out).max()) * 0.5


def load_track(mood: str, seconds: float) -> np.ndarray | None:
    folder = ASSETS_DIR / "music" / mood
    files = sorted(folder.glob("*.mp3")) + sorted(folder.glob("*.wav")) if folder.exists() else []
    if not files:
        return None
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(files[0]), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    reps = int(np.ceil(seconds * SR / max(1, len(a))))
    return np.tile(a, reps)[: int(seconds * SR)]


def sfx(kind: str) -> np.ndarray:
    rng = np.random.default_rng(7)
    if kind == "impact":
        t = np.arange(int(0.6 * SR)) / SR
        return (np.sin(2 * np.pi * 55 * t) * np.exp(-t * 7) + rng.normal(0, 0.4, t.size) * np.exp(-t * 25)).astype(np.float32) * 0.7
    if kind == "whoosh":
        t = np.arange(int(0.45 * SR)) / SR
        noise = rng.normal(0, 1, t.size)
        sm = np.convolve(noise, np.ones(40) / 40, mode="same")
        return (sm * np.sin(np.pi * t / t[-1]) * 1.6).astype(np.float32) * 0.5
    t = np.arange(int(1.2 * SR)) / SR  # chime
    return (sum(np.sin(2 * np.pi * f * t) for f in (880, 1318.5, 1760)) * np.exp(-t * 3) / 3).astype(np.float32) * 0.4


def mix(speech: np.ndarray, mood: str, duration: float, sfx_events: list[tuple[float, str]]) -> np.ndarray:
    n = int(duration * SR)
    speech = np.pad(speech, (0, max(0, n - len(speech))))[:n]
    bed = load_track(mood, duration)
    bed = synth_bed(mood, duration) if bed is None else bed
    bed = np.pad(bed, (0, max(0, n - len(bed))))[:n]
    # ducking: music 0.30 normally, 0.09 under speech, smoothed over ~120 ms
    env = np.abs(speech) > 0.01
    win = int(0.12 * SR)
    env = np.convolve(env.astype(np.float32), np.ones(win) / win, mode="same") > 0.02
    gain = np.where(env, 0.09, 0.30).astype(np.float32)
    gain = np.convolve(gain, np.ones(win) / win, mode="same")
    out = speech + bed * gain
    for t, kind in sfx_events:
        s = sfx(kind)
        i = int(t * SR)
        out[i:i + len(s)] += s[: max(0, n - i)]
    fade = int(0.3 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def write_wav(path: Path, audio: np.ndarray) -> Path:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def loudnorm(src: Path, dst: Path) -> Path:
    target = settings()["video"]["loudness_lufs"]
    f1 = f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json"
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", f1, "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(res.stderr[res.stderr.rindex("{"): res.stderr.rindex("}") + 1])
    f2 = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f2, "-ar", str(SR), str(dst)], check=True)
    return dst
