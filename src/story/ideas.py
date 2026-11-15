"""Story idea selection, all-ages sanitization, and holiday triggers."""
from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.common.config import ROOT, load_calendar

LEGACY_REWRITES: tuple[tuple[str, str], ...] = (
    (r"hidden sniper", "hidden confetti-camera drone"),
    (r"wants a sacrifice—of ketchup", "wants a giant splash of ketchup"),
    (r"chanting in Latin", "beeping in dramatic operatic robo-chords"),
    (r"headbutting climbers off cliffs", "bouncing climbers onto giant inflatable beanbags"),
    (r"blackmails social media users", "swaps everyone's profile pics with silly goat selfies"),
    (r"force-feeds pastries with microchip trackers", "hands out glittery rainbow donuts that make shoes squeak"),
    (r"mind-control ray", "disco-dance ray"),
    (r"hypnotizes?", "distracts with dazzling laser-light shows"),
    (r"short-term memory loss", "uncontrollable silly hiccups"),
    (r"explosive coloring books", "pop-up glitter coloring books"),
    (r"exploding snacks", "pop-fizzle confetti snacks"),
    (r"missile launcher", "confetti-stream launcher"),
    (r"flamethrower-wielding", "steam-puffing"),
)


def sanitize_legacy_idea(idea: str) -> str:
    out = idea
    for pat, repl in LEGACY_REWRITES:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def check_holiday_trigger(today: date | None = None) -> dict[str, Any] | None:
    d = today or date.today()
    cal = load_calendar().get("holidays", [])
    for h in cal:
        try:
            target = date(d.year, int(h["month"]), int(h["day"]))
        except ValueError:
            continue
        lead = int(h.get("lead_days", 4))
        if d <= target <= d + timedelta(days=lead):
            return h
    return None


def pick_unused_seed_idea(bible: dict[str, Any], rng: random.Random | None = None) -> str | None:
    rng = rng or random.Random()
    src = ROOT / "action_story.json"
    if not src.exists():
        return None
    raw = json.loads(src.read_text(encoding="utf-8"))
    used = set(bible.get("used_seed_ideas", []))
    avail = [item["story_idea"] for item in raw if item.get("story_idea") and item["story_idea"] not in used]
    if not avail:
        return None
    choice = rng.choice(avail)
    return sanitize_legacy_idea(choice)
