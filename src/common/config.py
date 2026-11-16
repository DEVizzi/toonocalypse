"""Load YAML config and the style guide. All tunables come from config/."""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
ASSETS_DIR = ROOT / "assets"


@functools.lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}


def settings() -> dict[str, Any]:
    return load_yaml("settings.yaml")


def models() -> dict[str, Any]:
    return load_yaml("models.yaml")


def categories() -> dict[str, Any]:
    return load_yaml("categories.yaml")


@functools.lru_cache(maxsize=None)
def style_guide() -> dict[str, str]:
    """Return {'positive': ..., 'negative': ...} parsed from config/style_guide.md."""
    text = (CONFIG_DIR / "style_guide.md").read_text(encoding="utf-8")
    sections = dict(re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M))
    return {
        "positive": sections.get("Positive style", "").strip(),
        "negative": sections.get("Negative prompt", "").strip(),
    }
