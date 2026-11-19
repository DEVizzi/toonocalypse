"""Config loading. Everything tunable lives in config/; code never hardcodes model names or phrases."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


@lru_cache(maxsize=None)
def _yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8")) or {}


def settings() -> dict:
    return _yaml("settings.yaml")


def models() -> dict:
    return _yaml("models.yaml")


@lru_cache(maxsize=None)
def phrases() -> dict[str, str]:
    """STYLE_PHRASE and NEGATIVE_PHRASE, read verbatim from config/style_guide.md."""
    text = (CONFIG / "style_guide.md").read_text(encoding="utf-8")
    out = {}
    for key in ("STYLE_PHRASE", "NEGATIVE_PHRASE"):
        m = re.search(rf"^## {key}\s*\n(.+?)\s*$", text, re.M)
        if not m:
            raise ValueError(f"{key} missing from config/style_guide.md")
        out[key] = m.group(1).strip()
    return out
