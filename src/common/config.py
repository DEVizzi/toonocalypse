"""Configuration and character-bible loaders."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
CHAR_DIR = ROOT / "characters"
ASSETS_DIR = ROOT / "assets"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_settings() -> dict[str, Any]:
    return load_yaml("settings.yaml")


def load_models() -> dict[str, Any]:
    return load_yaml("models.yaml")


def load_playbook() -> dict[str, Any]:
    return load_yaml("playbook.yaml")


def load_calendar() -> dict[str, Any]:
    return load_yaml("calendar.yaml")


def load_style_guide() -> str:
    return (CONFIG_DIR / "style_guide.md").read_text(encoding="utf-8").strip()


def load_heroes() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((CHAR_DIR / "heroes").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d["slug"]] = d
    return out


def load_villains() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((CHAR_DIR / "villains").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d["slug"]] = d
    return out


def load_all_characters() -> dict[str, dict[str, Any]]:
    chars = load_heroes()
    chars.update(load_villains())
    return chars


def display_name(slug: str, settings: dict[str, Any] | None = None) -> str:
    cfg = settings or load_settings()
    overrides = cfg.get("display_names") or {}
    if slug in overrides:
        return str(overrides[slug])
    chars = load_all_characters()
    return str(chars[slug]["name"]) if slug in chars else slug
