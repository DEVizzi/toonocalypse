"""Tests for render QA (skipped cleanly if ffmpeg is unavailable, runs in CI)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src.render.qa import check_render_qa, frame_difference_score


def test_frame_difference_score(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(a)
    Image.new("RGB", (64, 64), (10, 20, 30)).save(b)
    assert frame_difference_score(a, b) == 0.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_check_render_qa_validates_vertical_mp4(tmp_path: Path) -> None:
    mp4 = tmp_path / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=2.0:r=30",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "2.0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    res = check_render_qa(mp4, is_vertical=True)
    assert res.passed, res.reasons
    assert res.width == 1080 and res.height == 1920
    assert res.has_audio
