"""M5/v3.4 TTS: MC Tuno's energetic broadcaster voice via edge-tts (`en-US-BrianMultilingualNeural` with
`en-US-DavisNeural` fallback, rate=+20%, pitch=+4Hz). Strips leading and trailing silence (< -40 dB) and shifts
WordBoundary timestamps so zero dead-air gaps occur."""
from __future__ import annotations

import asyncio
import shutil
import subprocess

import numpy as np

from src.audio.sfx import SR
from src.config import settings

SILENCE_DB = -40.0
SILENCE_LIN = float(10 ** (SILENCE_DB / 20.0))   # 0.01 (-40 dB)


async def _stream(text: str, voice: str, rate: str, pitch: str) -> tuple[bytes, list[tuple[float, float, str]]]:
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:                                   # edge-tts < 7 has no boundary arg (WordBoundary by default)
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    words: list[tuple[float, float, str]] = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            t0 = chunk["offset"] / 1e7
            words.append((t0, t0 + chunk["duration"] / 1e7, chunk.get("text", "")))
    return bytes(audio), words


def _decode(mp3: bytes) -> np.ndarray | None:
    if not mp3 or not shutil.which("ffmpeg"):
        return None
    p = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"],
        input=mp3, capture_output=True, check=False,
    )
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def trim_silence_40db(pcm: np.ndarray, words: list[tuple[float, float, str]]) -> tuple[np.ndarray, list[tuple[float, float, str]]]:
    """Strips leading & trailing silence below -40 dB relative to peak (zero dead-air padding) and shifts WordBoundaries."""
    if pcm.size == 0:
        return pcm, words
    peak = float(np.max(np.abs(pcm)))
    if peak < 1e-4:
        return pcm, words
    win = max(1, int(0.005 * SR))
    rms_env = np.sqrt(np.convolve(pcm * pcm, np.ones(win, dtype=np.float32) / win, mode="same"))
    thr = max(1e-4, peak * SILENCE_LIN)
    idx = np.where(rms_env >= thr)[0]
    if not idx.size:
        return pcm, words
    lead = max(0, int(idx[0]) - int(0.004 * SR))
    tail = min(pcm.size, int(idx[-1]) + int(0.008 * SR))
    out = pcm[lead:tail].copy()
    fade = min(out.size // 4, int(0.004 * SR))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    shift = lead / SR
    dur = out.size / SR
    shifted = []
    for w0, w1, w in words:
        nw0 = max(0.0, min(dur, w0 - shift))
        nw1 = max(nw0 + 0.02, min(dur, w1 - shift))
        shifted.append((nw0, nw1, w))
    return out, shifted


PROSODY: dict[str, tuple[str, str]] = {
    "normal": ("+16%", "+2Hz"),     # INTRO / FILLER / generic reactions
    "hype": ("+26%", "+9Hz"),       # KO / BETRAYAL / MULTI-KO / CLIMAX / WINNER / GRAND FINAL (v4.3: more contrast)
    "deadpan": ("+12%", "-3Hz"),    # SELF_KO / DUMMY_ROAST / IRONIC FAIL (v4.3: calmer, cheekier)
}
BOOTH_MIC_AF = "highpass=f=120,equalizer=f=2800:width_type=o:width=1.5:g=3.5,acompressor=threshold=-16dB:ratio=4:attack=5:release=60"
_CACHE: dict[tuple[str, str], tuple[np.ndarray, list[tuple[float, float, str]]] | None] = {}
LAST_VOICE: dict[str, str] = {"voice": ""}


def synthesize(text: str, style: str = "normal") -> tuple[np.ndarray, list[tuple[float, float, str]]] | None:
    """Native-pitch edge-tts synthesis with per-beat prosody (never resampled). Results cached per (text, style)."""
    ck = (text, style)
    if ck in _CACHE:
        return _CACHE[ck]
    a = settings()["audio"]
    voices = [a["voice"]]
    fb = a.get("voice_fallback")
    if fb and fb not in voices:
        voices.append(fb)
    rate, pitch = PROSODY.get(style, PROSODY["normal"])
    mp3 = b""
    words: list[tuple[float, float, str]] = []
    for v in voices:
        try:
            mp3, words = asyncio.run(_stream(text, v, rate, pitch))
            if mp3:
                LAST_VOICE["voice"] = v
                break
        except Exception:
            continue
    pcm = _decode(mp3)
    if pcm is None or pcm.size < int(SR * 0.12):
        _CACHE[ck] = None
        return None
    res = trim_silence_40db(pcm, words)
    _CACHE[ck] = res
    return res


def booth_mic_eq(voice: np.ndarray) -> np.ndarray:
    """Runs the isolated narration stem through a crisp headset-mic chain (highpass + 2.8 kHz presence + compressor).
    Falls back to the dry stem if ffmpeg is unavailable. Length is preserved exactly."""
    if voice.size == 0 or not shutil.which("ffmpeg"):
        return voice
    pcm16 = (np.clip(voice, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    p = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-i", "pipe:0",
         "-af", BOOTH_MIC_AF, "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"],
        input=pcm16, capture_output=True, check=False,
    )
    if p.returncode != 0 or not p.stdout:
        return voice
    out = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if out.size < voice.size:
        out = np.concatenate([out, np.zeros(voice.size - out.size, np.float32)])
    return out[: voice.size]


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return shutil.which("ffmpeg") is not None
