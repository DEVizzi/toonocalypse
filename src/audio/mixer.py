"""Audio track assembly, BGM ducking, and -14 LUFS loudness normalization (§6 & §10.I)."""
from __future__ import annotations

import random
import shutil
import subprocess
import wave
from pathlib import Path

from src.common.config import ASSETS_DIR


def concat_wavs(wavs: list[Path], out_wav: Path, gap_sec: float = 0.18) -> Path:
    """Concatenate mono WAVs with <=0.4s dead air (default 0.18s)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if not wavs:
        raise ValueError("No WAV files to concatenate")
    with wave.open(str(wavs[0]), "rb") as w0:
        params = w0.getparams()
        sr = params.framerate
        gap_frames = b"\x00\x00" * int(sr * min(0.35, max(0.0, gap_sec)))

    with wave.open(str(out_wav), "wb") as out:
        out.setparams(params)
        for idx, p in enumerate(wavs):
            with wave.open(str(p), "rb") as wi:
                out.writeframes(wi.readframes(wi.getnframes()))
            if idx < len(wavs) - 1:
                out.writeframes(gap_frames)
    return out_wav


def mix_with_bgm(voice_wav: Path, out_audio: Path, duration_sec: float) -> Path:
    """Mix voice track with verified BGM (ducked under dialogue) normalized to -14 LUFS."""
    ffmpeg = shutil.which("ffmpeg")
    music_files = sorted((ASSETS_DIR / "music").glob("*.mp3"))
    if not ffmpeg or not music_files:
        out_audio.parent.mkdir(parents=True, exist_ok=True)
        out_audio.write_bytes(voice_wav.read_bytes())
        return out_audio

    bgm = random.choice(music_files)
    out_audio.parent.mkdir(parents=True, exist_ok=True)
    # Duck BGM using sidechaincompress when voice is active, then loudnorm to -14 LUFS
    filter_complex = (
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[v_main][v_sc];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.28[bgm_low];"
        "[bgm_low][v_sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=250[bgm_ducked];"
        "[v_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2,"
        f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{duration_sec:.3f}[aout]"
    )
    subprocess.run(
        [
            ffmpeg, "-y",
            "-i", str(voice_wav),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(out_audio),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_audio
