"""The ONLY way prompts are built (§7.2).

Order: [character blocks, left-to-right] → [action, ≤25 words, no appearance words] → [location block]
→ [composition note] → [STYLE_PHRASE, verbatim, always last].
"""
from __future__ import annotations

import re
from typing import Any

from src.art.blocks import checked
from src.common.config import phrases

MAX_ACTION_WORDS = 25
# Appearance belongs to the frozen character block, never to the per-panel action.
APPEARANCE_WORDS = {"hair", "haired", "hairstyle", "eyes", "eyed", "skin", "wearing", "wears", "dressed", "outfit",
                    "clothes", "shirt", "kurta", "jacket", "scarf", "dress", "cloak", "tunic", "beard", "moustache",
                    "mustache", "tattoo", "freckles", "bald", "ponytail", "braid", "topknot"}


def lint_action(action: str) -> list[str]:
    errs = []
    words = re.findall(r"[a-z]+", action.lower())
    if len(words) > MAX_ACTION_WORDS:
        errs.append(f"action has {len(words)} words (max {MAX_ACTION_WORDS})")
    bad = sorted(set(words) & APPEARANCE_WORDS)
    if bad:
        errs.append(f"action contains appearance words {bad}")
    return errs


def composition_note(chars: list[dict[str, str]]) -> str:
    parts = ["empty sky in upper quarter"]
    for c in chars:
        facing = "facing right" if c["side"] == "left" else "facing left" if c["side"] == "right" else "facing the viewer"
        parts.append(f"{c['name']} on the {c['side']} {facing}")
    return ", ".join(parts)


def build(panel: dict[str, Any], frozen: dict[str, dict]) -> str:
    """panel: {characters: [{name, side}], action, location}. frozen: blocks.freeze() output."""
    errs = lint_action(panel["action"])
    if errs:
        raise ValueError(f"panel {panel.get('id')}: {'; '.join(errs)}")
    order = {"left": 0, "center": 1, "right": 2}
    chars = sorted(panel.get("characters", []), key=lambda c: order.get(c["side"], 1))
    if len(chars) > 2:
        raise ValueError(f"panel {panel.get('id')}: max 2 characters")
    pieces = [checked(frozen["characters"][c["name"]]) for c in chars]
    pieces += [panel["action"].strip().rstrip("."), checked(frozen["locations"][panel["location"]])]
    if chars:
        pieces.append(composition_note(chars))
    else:
        pieces.append("empty sky in upper quarter, no people")
    pieces.append(phrases()["STYLE_PHRASE"])
    return ", ".join(pieces)


def portrait_prompt(name: str, frozen: dict[str, dict]) -> str:
    # Deviation from the spec text: "character reference sheet" makes models draw multi-view turnarounds,
    # which breaks the one-figure QA; a single full-body front view is used instead (README: decisions).
    return ", ".join([checked(frozen["characters"][name]),
                      "single character portrait, full body front view, neutral pose, plain light grey background",
                      phrases()["STYLE_PHRASE"]])
