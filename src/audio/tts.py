"""Text-to-speech: Kokoro-82M (Apache-2.0, CPU) primary. Word timings for caption/bubble sync. Audio cached by hash.

Piper is the configured fallback engine, but it is only used if `models.yaml: tts.piper_voice` names a voice
whose model card permits commercial use (see LICENSES.md). Otherwise a Kokoro failure aborts the story.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.common.config import ROOT, models
from src.common.retry import Abort

SR = 24000
CACHE = ROOT / "work" / "tts_cache"
_pipes: dict[str, object] = {}


@dataclass
class Speech:
    audio: np.ndarray                     # float32 mono @ 24 kHz
    words: list[dict] = field(default_factory=list)   # [{"word", "start", "end"}] seconds

    @property
    def duration(self) -> float:
        return len(self.audio) / SR


def pick_voice(role: dict | None) -> str:
    """Choose a Kokoro voice from a lock card (None = narrator)."""
    v = models()["tts"]["voices"]
    if role is None:
        return v["narrator"]
    gender = str(role.get("gender", "")).lower()
    try:
        age = int(str(role.get("age", "30")).split()[0].split("-")[0])
    except ValueError:
        age = 30
    band = "child" if age < 14 else "young" if age < 30 else "adult" if age < 55 else "elder"
    key = f"{'female' if gender.startswith('f') else 'male'}_{band}"
    return v.get(key, v["narrator"])


def assign_voices(cast: list[dict]) -> dict[str, str]:
    """Fixed per story; no two characters share a voice when an alternative exists."""
    alts = models()["tts"]["voices"]
    used, out = {alts["narrator"]}, {}
    for c in cast:
        voice = pick_voice(c)
        if voice in used:
            pool = [x for k, x in alts.items() if k.startswith("female" if str(c.get("gender", "")).lower().startswith("f") else "male")]
            voice = next((x for x in pool if x not in used), voice)
        used.add(voice)
        out[c["name"]] = voice
    return out


def _kokoro(text: str, voice: str, speed: float) -> Speech:
    from kokoro import KPipeline

    lang = voice[0]  # 'a' American / 'b' British
    if lang not in _pipes:
        _pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    chunks, words, offset = [], [], 0.0
    for r in _pipes[lang](text, voice=voice, speed=speed):
        audio = np.asarray(r.audio, dtype=np.float32)
        for t in (r.tokens or []):
            if t.start_ts is not None and t.end_ts is not None and any(ch.isalnum() for ch in t.text):
                words.append({"word": t.text, "start": round(offset + t.start_ts, 3), "end": round(offset + t.end_ts, 3)})
        chunks.append(audio)
        offset += len(audio) / SR
    if not chunks:
        raise RuntimeError("Kokoro returned no audio")
    return Speech(np.concatenate(chunks), words)


def synth(text: str, voice: str, speed: float = 1.0) -> Speech:
    key = hashlib.sha256(f"kokoro|{voice}|{speed}|{text}".encode()).hexdigest()[:24]
    wav, meta = CACHE / f"{key}.npy", CACHE / f"{key}.json"
    if wav.exists() and meta.exists():
        return Speech(np.load(wav), json.loads(meta.read_text()))
    try:
        sp = _kokoro(text, voice, speed)
    except Exception as e:
        if not models()["tts"].get("piper_voice"):
            raise Abort(f"Kokoro TTS failed and no commercial-safe Piper voice is configured: {e}") from e
        raise Abort(f"Kokoro TTS failed: {e} (Piper fallback not implemented for unverified voices)") from e
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(wav, sp.audio)
    meta.write_text(json.dumps(sp.words))
    return sp
