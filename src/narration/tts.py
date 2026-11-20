"""M5 TTS: MC Tuno's voice via edge-tts (free Microsoft Edge neural voices, no API key). Returns PCM + per-word
timings (WordBoundary) for karaoke captions and lip-sync. Decoding uses ffmpeg (already required for rendering).
If edge-tts or the network is unavailable, returns None and the episode ships with SFX + music only."""
from __future__ import annotations

import asyncio
import shutil
import subprocess

import numpy as np

from src.audio.sfx import SR
from src.config import settings


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
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                       input=mp3, capture_output=True, check=False)
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def synthesize(text: str) -> tuple[np.ndarray, list[tuple[float, float, str]]] | None:
    a = settings()["audio"]
    try:
        mp3, words = asyncio.run(_stream(text, a["voice"], a["voice_rate"], a["voice_pitch"]))
    except Exception:
        return None
    pcm = _decode(mp3)
    if pcm is None or pcm.size < SR * 0.2:
        return None
    # trim leading/trailing silence (keeps placement tight) and shift word timings accordingly
    thr = 0.02
    idx = np.where(np.abs(pcm) > thr)[0]
    if idx.size:
        lead = max(0, int(idx[0]) - int(0.02 * SR))
        tail = min(pcm.size, int(idx[-1]) + int(0.08 * SR))
        pcm = pcm[lead:tail]
        shift = lead / SR
        words = [(max(0.0, w0 - shift), max(0.0, w1 - shift), w) for w0, w1, w in words]
    return pcm, words


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return shutil.which("ffmpeg") is not None
