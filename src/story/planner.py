"""Multi-part arc planner, casting rotation, and cliffhanger scheduler (§4 & §7.10 & §10.B)."""
from __future__ import annotations

import random
from typing import Any

from src.common.config import load_heroes, load_playbook, load_villains

CLIFFHANGER_TYPES = [
    "reveal_twist",
    "ticking_clock",
    "open_question",
    "mild_cartoon_peril",
    "emotional_turn",
    "freeze_frame",
]

FAVOURED_PAIRINGS = [
    ("master-bamboo", "dr-pancake"),
    ("dr-slickscale", "mango-mike"),
    ("blazetail", "neon-noodle"),
    ("brewtan-the-yeti", "detective-bubbles"),
    ("codecorn", "lla-m4"),
    ("captain-thorn", "snuggle-doom"),
]

SETTINGS_POOL = [
    "Brewtan's Cozy Cocoa Café",
    "Downtown Clocktower Plaza",
    "Neon Arcade & Bowling Alley",
    "Sunny Boardwalk Juice Stand",
    "City Science Museum",
    "Rooftop Community Garden",
    "Grand Central Bakery",
    "Harbor Lighthouse Pier",
]


def choose_format(
    bible: dict[str, Any],
    holiday: dict[str, Any] | None = None,
    forced_format: str | None = None,
    rng: random.Random | None = None,
) -> tuple[str, int]:
    """Choose story format & locked part count respecting rhythm rules."""
    rng = rng or random.Random()
    if forced_format:
        counts = {"One-Shot": 1, "Mini-Arc": 3, "Arc": rng.choice([4, 5]), "Epic": rng.choice([6, 7])}
        return forced_format, counts[forced_format]
    if holiday:
        return "One-Shot", 1

    past = bible.get("past_stories", [])
    last_fmt = past[-1]["format"] if past else None
    recent_formats = [s.get("format") for s in past[-2:]]
    epics_last_30 = sum(1 for s in past[-10:] if s.get("format") == "Epic")

    # Place 1-2 One-Shots between multi-part arcs
    if last_fmt in ("Mini-Arc", "Arc", "Epic"):
        return "One-Shot", 1

    weights = dict(load_playbook().get("format_weights", {"One-Shot": 0.30, "Mini-Arc": 0.35, "Arc": 0.25, "Epic": 0.10}))
    if last_fmt == "Epic" or "Epic" in recent_formats or epics_last_30 >= 1:
        weights["Epic"] = 0.0

    choices = list(weights.keys())
    probs = [max(0.0, float(weights[k])) for k in choices]
    if sum(probs) <= 0:
        fmt = "One-Shot"
    else:
        fmt = rng.choices(choices, weights=probs, k=1)[0]

    part_map = {"One-Shot": 1, "Mini-Arc": 3, "Arc": rng.choice([4, 5]), "Epic": rng.choice([6, 7])}
    return fmt, part_map[fmt]


def select_cast(
    bible: dict[str, Any],
    fmt: str,
    forced_heroes: list[str] | None = None,
    forced_villain: str | None = None,
    rng: random.Random | None = None,
) -> tuple[list[str], str]:
    """Select 1 lead + supporting heroes + 1 villain, respecting §7.10 rotation."""
    rng = rng or random.Random()
    heroes = load_heroes()
    villains = load_villains()
    all_hero_slugs = list(heroes.keys())

    if forced_heroes:
        cast_heroes = forced_heroes[:3]
    else:
        last_lead = bible.get("last_lead_hero")
        appearances = bible.get("hero_appearances", {})
        eligible_leads = [s for s in all_hero_slugs if s != last_lead]
        eligible_leads.sort(key=lambda s: (int(appearances.get(s, 0)), rng.random()))
        lead = eligible_leads[0]

        if fmt == "One-Shot":
            partner = next((b if a == lead else a for a, b in FAVOURED_PAIRINGS if lead in (a, b)), None)
            cast_heroes = [lead] + ([partner] if partner and rng.random() < 0.7 else [])
        else:
            others = [s for s in all_hero_slugs if s != lead]
            others.sort(key=lambda s: (int(appearances.get(s, 0)), rng.random()))
            cast_heroes = [lead] + others[:2]

    villain = forced_villain or rng.choice(list(villains.keys()))
    return cast_heroes, villain


def rotate_cliffhangers(part_count: int, rng: random.Random | None = None) -> list[str | None]:
    """Return cliffhanger type per part; never the same type twice in a row; final part is None."""
    rng = rng or random.Random()
    if part_count <= 1:
        return [None]
    out: list[str | None] = []
    prev: str | None = None
    for _ in range(part_count - 1):
        opts = [c for c in CLIFFHANGER_TYPES if c != prev]
        pick = rng.choice(opts)
        out.append(pick)
        prev = pick
    out.append(None)
    return out


def pick_setting(bible: dict[str, Any], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    recent = set(bible.get("used_settings", [])[-3:])
    avail = [s for s in SETTINGS_POOL if s not in recent] or SETTINGS_POOL
    return rng.choice(avail)
