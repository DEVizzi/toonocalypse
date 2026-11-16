"""Character-voiced TTS synthesis: Gemini TTS primary, Piper fallback, line hash cache (§4)."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from src.common.config import ROOT, load_all_characters, load_models, load_playbook
from src.common.gemini import classify_gemini_error, get_client, has_gemini_key
from src.common.quota import QuotaTracker

GEMINI_VOICES = ("Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr", "Leda", "Orus")
TTS_CACHE_DIR = ROOT / "assets" / "tts_cache"


def _write_fallback_speech_wav(text: str, out_path: Path, length_scale: float = 1.0) -> Path:
    """Deterministic speech-paced WAV ONLY for offline unit/smoke tests (never in live mode)."""
    sr = 22050
    words = max(1, len(text.split()))
    dur = max(0.8, min(6.0, words * 0.34 * length_scale))
    n = int(sr * dur)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        buf = bytearray()
        for i in range(n):
            t = i / sr
            env = 0.25 * (0.5 + 0.5 * math.sin(2 * math.pi * 3.5 * t))
            val = int(max(-1.0, min(1.0, env * math.sin(2 * math.pi * 220.0 * t))) * 32767)
            buf.extend(struct.pack("<h", val))
        wf.writeframes(bytes(buf))
    return out_path


def _apply_voice_fx(raw_wav: Path, out_wav: Path, pitch_semitones: float, fx: str) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or (pitch_semitones == 0 and fx == "none"):
        if raw_wav != out_wav:
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            out_wav.write_bytes(raw_wav.read_bytes())
        return out_wav

    filters: list[str] = []
    if pitch_semitones != 0:
        factor = 2.0 ** (pitch_semitones / 12.0)
        filters.append(f"asetrate=22050*{factor:.4f},aresample=22050,atempo={1.0/factor:.4f}")
    if fx == "light_robot":
        filters.append("aecho=0.8:0.88:12:0.35")

    cmd = [ffmpeg, "-y", "-i", str(raw_wav)]
    if filters:
        cmd.extend(["-af", ",".join(filters)])
    cmd.append(str(out_wav))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_wav


def _gemini_voice_for(voice_cfg: dict[str, Any], is_narrator: bool) -> str:
    if is_narrator:
        return str(voice_cfg.get("gemini_voice") or "Charon")
    if voice_cfg.get("gemini_voice"):
        return str(voice_cfg["gemini_voice"])
    key = json.dumps(voice_cfg, sort_keys=True)
    idx = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(GEMINI_VOICES)
    return GEMINI_VOICES[idx]


def _synthesize_gemini_tts(text: str, voice_name: str, out_wav: Path, quota: QuotaTracker | None = None) -> Path:
    from google.genai import types

    qt = quota or QuotaTracker()
    if not has_gemini_key() or not qt.can_spend("tts", 1):
        raise RuntimeError("Gemini TTS unavailable or quota exhausted")

    cli = get_client()
    models = load_models().get("tts", {}).get("gemini_tts_models", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
    last_exc: Exception | None = None
    for model in models:
        try:
            resp = cli.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                        )
                    ),
                ),
            )
            for cand in getattr(resp, "candidates", []) or []:
                for part in cand.content.parts:
                    inline = getattr(part, "inline_data", None)
                    if inline is not None and inline.data:
                        out_wav.parent.mkdir(parents=True, exist_ok=True)
                        # Gemini TTS returns 24kHz 16-bit mono PCM (or WAV)
                        data = inline.data
                        if data[:4] == b"RIFF":
                            out_wav.write_bytes(data)
                        else:
                            with wave.open(str(out_wav), "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(data)
                        qt.spend("tts", 1)
                        return out_wav
        except Exception as exc:
            last_exc = exc
            if classify_gemini_error(exc) == "not_found":
                continue
    raise RuntimeError(f"Gemini TTS failed: {last_exc}")


def _synthesize_piper(text: str, voice_cfg: dict[str, Any], out_wav: Path) -> Path:
    piper = shutil.which("piper")
    model = str(voice_cfg.get("model") or "en_US-lessac-medium")
    model_path = ROOT / "assets" / "voices" / f"{model}.onnx"
    if not piper or not model_path.exists():
        raise RuntimeError(f"Piper binary or voice model missing ({model_path})")

    raw_wav = out_wav.with_suffix(".raw.wav")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        piper,
        "--model", str(model_path),
        "--output_file", str(raw_wav),
        "--length_scale", str(voice_cfg.get("length_scale", 1.0)),
    ]
    if "speaker_id" in voice_cfg:
        cmd.extend(["--speaker", str(voice_cfg["speaker_id"])])
    subprocess.run(cmd, input=text, text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _apply_voice_fx(raw_wav, out_wav, float(voice_cfg.get("pitch_semitones", 0)), str(voice_cfg.get("fx", "none")))
    if raw_wav.exists():
        raw_wav.unlink()
    return out_wav


def tts_reachable() -> tuple[bool, str]:
    """Preflight check (§6.1): verify Gemini key or Piper voice model is available."""
    if has_gemini_key():
        return True, "gemini-tts-ready"
    piper = shutil.which("piper")
    models_dir = ROOT / "assets" / "voices"
    if piper and models_dir.exists() and any(models_dir.glob("*.onnx")):
        return True, "piper-ready"
    return False, "Neither GOOGLE_API_KEY (Gemini TTS) nor Piper voice models are available"


def synthesize_line(
    text: str,
    voice_cfg: dict[str, Any],
    out_path: Path,
    is_narrator: bool = False,
    offline: bool = False,
    quota: QuotaTracker | None = None,
) -> Path:
    """Synthesize dialogue/narration with Gemini TTS primary, Piper fallback, and line-hash cache."""
    if offline:
        return _write_fallback_speech_wav(text, out_path, float(voice_cfg.get("length_scale", 1.0)))

    g_voice = _gemini_voice_for(voice_cfg, is_narrator=is_narrator)
    cache_key = hashlib.sha256(
        f"{text}|{g_voice}|{json.dumps(voice_cfg, sort_keys=True)}".encode("utf-8")
    ).hexdigest()[:24]
    cached = TTS_CACHE_DIR / f"{cache_key}.wav"
    if cached.exists() and cached.stat().st_size > 1000:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(cached.read_bytes())
        return out_path

    # Primary: Gemini TTS
    try:
        _synthesize_gemini_tts(text, g_voice, out_path, quota=quota)
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(out_path.read_bytes())
        return out_path
    except Exception as gemini_exc:
        print(f"[tts] Gemini TTS failed ({gemini_exc}); trying Piper fallback...")

    # Fallback: Piper
    try:
        _synthesize_piper(text, voice_cfg, out_path)
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(out_path.read_bytes())
        return out_path
    except Exception as piper_exc:
        raise RuntimeError(f"TTS aborted: Gemini TTS and Piper both failed ({piper_exc})") from piper_exc


def generate_voice_samples(out_dir: Path | None = None) -> list[Path]:
    """Generate short preview WAVs for all bible characters."""
    dest = out_dir or (ROOT / "assets" / "voice_samples")
    dest.mkdir(parents=True, exist_ok=True)
    chars = load_all_characters()
    out: list[Path] = []
    for slug, c in sorted(chars.items()):
        p = dest / f"{slug}.wav"
        synthesize_line(c["catchphrase"], c["voice"], p, offline=not has_gemini_key())
        out.append(p)
    return out
