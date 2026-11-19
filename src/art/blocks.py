"""Character and location blocks (§5.2, §5.3): built by code in a fixed order, frozen per story, hash-checked."""
from __future__ import annotations

import hashlib
from typing import Any

CHARACTER_FIELDS = ["name", "age", "gender", "build", "face_shape", "hair", "eye_colour", "skin_tone", "outfit",
                    "accessory"]
MAX_LOCATION_WORDS = 35


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def character_block(card: dict[str, Any]) -> str:
    """'<Name>, a <age> year old <gender>, <build>, <face shape>, <hair> hair, <eyes> eyes, <skin> skin,
    wearing <outfit>, <accessory>' — the name is always the first words."""
    missing = [f for f in CHARACTER_FIELDS if not str(card.get(f, "")).strip()]
    if missing:
        raise ValueError(f"lock card {card.get('name', '?')} missing {missing}")
    c = {k: " ".join(str(card[k]).split()) for k in CHARACTER_FIELDS}
    hair = c["hair"] if "hair" in c["hair"].lower() or "bald" in c["hair"].lower() else f"{c['hair']} hair"
    return (f"{c['name']}, a {c['age']} year old {c['gender']}, {c['build']}, {c['face_shape']}, {hair}, "
            f"{c['eye_colour']} eyes, {c['skin_tone']} skin, wearing {c['outfit']}, {c['accessory']}")


def location_block(card: dict[str, Any]) -> str:
    text = " ".join(str(card["description"]).split())
    if len(text.split()) > MAX_LOCATION_WORDS:
        raise ValueError(f"location {card.get('id')} block exceeds {MAX_LOCATION_WORDS} words")
    return text


def freeze(cast: list[dict], locations: list[dict]) -> dict[str, dict[str, str]]:
    """Build every block once and record its sha256 (stored in the story bible)."""
    chars = {c["name"]: character_block(c) for c in cast}
    locs = {loc["id"]: location_block(loc) for loc in locations}
    return {"characters": {n: {"block": b, "sha256": sha(b)} for n, b in chars.items()},
            "locations": {i: {"block": b, "sha256": sha(b)} for i, b in locs.items()}}


def checked(frozen: dict[str, str]) -> str:
    """Return the block only if it still matches its recorded hash."""
    if sha(frozen["block"]) != frozen["sha256"]:
        raise ValueError("block hash mismatch: a frozen block was modified")
    return frozen["block"]
