"""Tests for SFX synthesis and word-level timing alignment."""
from __future__ import annotations

from pathlib import Path

from src.audio.sfx import ensure_sfx_library
from src.audio.timings import compute_word_timings, wav_duration


def test_sfx_library_synthesizes_valid_wavs(tmp_path: Path) -> None:
    lib = ensure_sfx_library(tmp_path)
    assert len(lib) >= 5
    for name, wav_path in lib.items():
        assert wav_path.exists(), name
        assert wav_duration(wav_path) > 0.05


def test_compute_word_timings_monotonic_and_exact_span() -> None:
    timings = compute_word_timings("Brewtan saves the day!", total_duration=2.4, offset=0.5)
    assert len(timings) == 4
    assert timings[0].start == 0.5
    assert abs(timings[-1].end - 2.9) < 0.02
    for a, b in zip(timings, timings[1:]):
        assert a.end <= b.start + 1e-6
