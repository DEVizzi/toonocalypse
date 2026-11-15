"""Character-voiced TTS synthesis (Piper primary, espeak fallback, WAV tone dry-run)."""
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from src.common.config import ROOT, load_all_characters, load_models, load_playbook


def _write_fallback_speech_wav(text: str, out_path: Path, length_scale: float = 1.0) -> Path:
    """Deterministic speech-paced WAV for offline tests when Piper/espeak are absent."""
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


def synthesize_line(
    text: str,
    voice_cfg: dict[str, Any],
    out_wav: Path,
    is_narrator: bool = False,
    models_dir: Path | None = None,
) -> Path:
    if out_wav.exists():
        return out_wav
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    length_scale = float(voice_cfg.get("length_scale", 1.0))
    if is_narrator:
        mult = float(load_playbook().get("narration", {}).get("narration_length_scale_multiplier", 0.92))
        length_scale *= mult

    pitch = float(voice_cfg.get("pitch_semitones", 0))
    fx = str(voice_cfg.get("fx", "none"))
    raw_wav = out_wav.with_suffix(".raw.wav")

    piper_bin = shutil.which("piper")
    model_name = voice_cfg.get("model", "en_US-lessac-medium")
    model_file = (models_dir or (ROOT / ".cache" / "piper")) / f"{model_name}.onnx"

    synthesized = False
    if piper_bin and model_file.exists():
        cmd = [
            piper_bin,
            "--model",
            str(model_file),
            "--output_file",
            str(raw_wav),
            "--length_scale",
            f"{length_scale:.2f}",
        ]
        if voice_cfg.get("speaker_id") is not None:
            cmd.extend(["--speaker", str(voice_cfg["speaker_id"])])
        try:
            subprocess.run(cmd, input=text, text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            synthesized = True
        except Exception:
            synthesized = False

    if not synthesized:
        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak_bin:
            try:
                subprocess.run([espeak_bin, "-w", str(raw_wav), text], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                synthesized = True
            except Exception:
                synthesized = False

    if not synthesized:
        _write_fallback_speech_wav(text, raw_wav, length_scale=length_scale)

    _apply_voice_fx(raw_wav, out_wav, pitch, fx)
    if raw_wav.exists() and raw_wav != out_wav:
        raw_wav.unlink()
    return out_wav


def generate_voice_samples(out_dir: Path | None = None) -> list[Path]:
    """Generate characters/voices/<slug>.wav for every hero and villain."""
    chars = load_all_characters()
    target_dir = out_dir or (ROOT / "characters" / "voices")
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for slug, char in sorted(chars.items()):
        p = target_dir / f"{slug}.wav"
        if not p.exists():
            line = f"{char['name']} reporting in! {char['catchphrase']}"
            synthesize_line(line, char["voice"], p)
        outputs.append(p)
    return outputs
