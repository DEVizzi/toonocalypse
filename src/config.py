"""Config access. TIMELINE and LAYOUT are the single source of truth for timing and safe zones (§4, §8)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
ASSETS = ROOT / "assets"


@lru_cache(maxsize=None)
def load(name: str = "settings.yaml") -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}


def settings() -> dict[str, Any]:
    return load("settings.yaml")


@dataclass(frozen=True)
class Timeline:
    cold_open_s: float
    flash_forward_s: float
    flash_forward_chance: float
    gameplay_target_min_s: float
    gameplay_target_max_s: float
    forced_resolution_s: float
    hard_stop_s: float
    escalation: tuple[tuple[float, float, str], ...]
    replay_s: float
    replay_speed: float
    replay_source_s: float
    replay_zoom: float
    winner_card_s: float
    loop_tail_s: float
    two_stage_chance: float
    two_stage_qualifier_s: float
    two_stage_survivors: int
    two_stage_sting_s: float
    two_stage_final_s: float

    def speed_at(self, gameplay_t: float) -> float:
        mult = 1.0
        for start, m, _ in self.escalation:
            if gameplay_t >= start:
                mult = m
        return mult

    def tail_s(self) -> float:
        return self.replay_s + self.winner_card_s + self.loop_tail_s


def _timeline() -> Timeline:
    t = dict(settings()["timeline"])
    t["escalation"] = tuple((float(a), float(b), str(c)) for a, b, c in t["escalation"])
    return Timeline(**t)


TIMELINE = _timeline()
LAYOUT: dict[str, Any] = settings()["layout"]
VIDEO: dict[str, Any] = settings()["video"]
W, H, FPS = VIDEO["width"], VIDEO["height"], VIDEO["fps"]


def font_path(name: str) -> str:
    return str(ASSETS / "fonts" / name)
