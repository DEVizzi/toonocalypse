"""Tests for character bible schema, species authority, safety, and color separation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.common.config import ROOT, load_all_characters, load_heroes, load_villains


def test_bible_validator_script_passes() -> None:
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_bible.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_hero_and_villain_counts() -> None:
    heroes = load_heroes()
    villains = load_villains()
    assert len(heroes) == 26
    assert len(villains) >= 6
    assert len(load_all_characters()) == len(heroes) + len(villains)
