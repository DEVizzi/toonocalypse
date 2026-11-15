#!/usr/bin/env python3
"""Validate the Toonocalypse character bible (heroes, villains, ΔE, species, safety).

Exits 0 on pass, 1 on any violation. Run in CI and after any bible edit.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HEROES_SRC = ROOT / "heroes.json"
HEROES_DIR = ROOT / "characters" / "heroes"
VILLAINS_DIR = ROOT / "characters" / "villains"

REQUIRED_FIELDS = {
    "slug",
    "name",
    "bible_version",
    "role",
    "species",
    "pronouns",
    "age_group",
    "size_class",
    "height_units",
    "palette",
    "silhouette",
    "visual_prompt",
    "anchors",
    "forbidden",
    "outfit",
    "prop",
    "personality",
    "speech_style",
    "catchphrase",
    "quirks",
    "voice",
    "theme_motif",
    "relationships",
    "reference_sheet",
}

FORBIDDEN_STUDIOS = ("pixar", "dreamworks", "ghibli", "disney", "nickelodeon", "illumination")
VILLAIN_CHROME = "#C0C4C8"
VILLAIN_GLOWS = {"#B2FF00", "#FFB000", "#9D00FF"}

BANNED_QUIRK_WORDS = (
    "addicted",
    "motor oil",
    "sniper",
    "sacrifice",
    "blackmail",
    "hypnoti",
    "mind-control",
    "mind control",
    "force-feed",
    "headbutting climbers off cliffs",
)


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_str}")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def ciede2000(hex1: str, hex2: str) -> float:
    """Compute CIEDE2000 ΔE between two hex colors."""
    L1, a1, b1 = rgb_to_lab(hex_to_rgb(hex1))
    L2, a2, b2 = rgb_to_lab(hex_to_rgb(hex2))

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_bar = (C1 + C2) / 2.0
    G = 0.5 * (1 - math.sqrt((C_bar**7) / (C_bar**7 + 25**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    def hp(ap: float, b: float) -> float:
        if ap == 0 and b == 0:
            return 0.0
        ang = math.degrees(math.atan2(b, ap))
        return ang + 360.0 if ang < 0 else ang

    h1p = hp(a1p, b1)
    h2p = hp(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    L_bar_p = (L1 + L2) / 2.0
    C_bar_p = (C1p + C2p) / 2.0
    if C1p * C2p == 0:
        h_bar_p = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar_p = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        h_bar_p = (h1p + h2p + 360) / 2.0
    else:
        h_bar_p = (h1p + h2p - 360) / 2.0

    T = (
        1
        - 0.17 * math.cos(math.radians(h_bar_p - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar_p))
        + 0.32 * math.cos(math.radians(3 * h_bar_p + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar_p - 63))
    )
    d_theta = 30 * math.exp(-(((h_bar_p - 275) / 25) ** 2))
    R_C = 2 * math.sqrt((C_bar_p**7) / (C_bar_p**7 + 25**7))
    S_L = 1 + (0.015 * ((L_bar_p - 50) ** 2)) / math.sqrt(20 + ((L_bar_p - 50) ** 2))
    S_C = 1 + 0.045 * C_bar_p
    S_H = 1 + 0.015 * C_bar_p * T
    R_T = -math.sin(math.radians(2 * d_theta)) * R_C

    return math.sqrt(
        (dLp / S_L) ** 2
        + (dCp / S_C) ** 2
        + (dHp / S_H) ** 2
        + R_T * (dCp / S_C) * (dHp / S_H)
    )


def load_chars(directory: Path) -> list[dict[str, Any]]:
    chars = []
    for p in sorted(directory.glob("*.json")):
        chars.append(json.loads(p.read_text(encoding="utf-8")))
    return chars


def validate_bible() -> list[str]:
    errors: list[str] = []
    if not HEROES_SRC.exists():
        return [f"Missing authoritative source: {HEROES_SRC}"]

    auth_heroes = json.loads(HEROES_SRC.read_text(encoding="utf-8"))
    auth_by_name = {h["name"]: h for h in auth_heroes}

    heroes = load_chars(HEROES_DIR)
    villains = load_chars(VILLAINS_DIR)

    if len(heroes) != len(auth_heroes):
        errors.append(f"Expected {len(auth_heroes)} hero files in {HEROES_DIR}, found {len(heroes)}")
    if len(villains) < 6:
        errors.append(f"Expected at least 6 seed villain files in {VILLAINS_DIR}, found {len(villains)}")

    all_chars = heroes + villains
    all_slugs = {c.get("slug") for c in all_chars}

    # Schema & content checks
    for c in all_chars:
        slug = c.get("slug", "<unknown>")
        missing = REQUIRED_FIELDS - set(c.keys())
        if missing:
            errors.append(f"[{slug}] Missing required fields: {sorted(missing)}")
        if len(str(c.get("visual_prompt", ""))) > 350:
            errors.append(f"[{slug}] visual_prompt exceeds 350 chars ({len(c['visual_prompt'])})")
        anchors = c.get("anchors", [])
        if not (3 <= len(anchors) <= 5):
            errors.append(f"[{slug}] anchors must have 3-5 items, got {len(anchors)}")
        if not c.get("forbidden"):
            errors.append(f"[{slug}] forbidden list must be non-empty")
        if "hair_fur" in c:
            errors.append(f"[{slug}] hair_fur must be normalized out")
        blob = json.dumps(c).lower()
        for studio in FORBIDDEN_STUDIOS:
            if studio in blob:
                errors.append(f"[{slug}] contains forbidden studio/brand name: {studio}")
        safe_blob = json.dumps({k: v for k, v in c.items() if k != "forbidden"}).lower()
        for bad_w in BANNED_QUIRK_WORDS:
            if bad_w in safe_blob:
                errors.append(f"[{slug}] contains non-all-ages quirk/wording: {bad_w}")
        for rel_slug in (c.get("relationships") or {}):
            if rel_slug not in all_slugs:
                errors.append(f"[{slug}] relationship references unknown slug: {rel_slug}")

    # Authoritative name & species check against heroes.json
    hero_names_seen = set()
    for h in heroes:
        name = h.get("name", "")
        hero_names_seen.add(name)
        if name not in auth_by_name:
            errors.append(f"[{h.get('slug')}] hero name '{name}' not in heroes.json")
            continue
        auth_sp = auth_by_name[name]["species"].strip().lower()
        got_sp = str(h.get("species", "")).strip().lower()
        if auth_sp != got_sp:
            errors.append(f"[{h.get('slug')}] species '{got_sp}' != heroes.json '{auth_sp}'")

    for name in auth_by_name:
        if name not in hero_names_seen:
            errors.append(f"Missing hero from heroes.json: {name}")

    # Hero primary color ΔE >= 20 and reserved villain palette protection
    for i, h1 in enumerate(heroes):
        p1 = h1["palette"]["primary"]
        if p1.upper() == VILLAIN_CHROME or p1.upper() in VILLAIN_GLOWS:
            errors.append(f"[{h1['slug']}] hero primary {p1} uses reserved villain palette")
        for h2 in heroes[i + 1 :]:
            p2 = h2["palette"]["primary"]
            de = ciede2000(p1, p2)
            if de < 20.0:
                errors.append(
                    f"ΔE={de:.2f} < 20.0 between {h1['slug']} ({p1}) and {h2['slug']} ({p2})"
                )

    # Villain palette & same-species ΔE >= 35
    for v in villains:
        pal = v["palette"]
        if pal.get("primary", "").upper() != VILLAIN_CHROME and pal.get("secondary", "").upper() != VILLAIN_CHROME:
            errors.append(f"[{v['slug']}] villain must use chrome {VILLAIN_CHROME} in primary or secondary")
        if pal.get("accent", "").upper() not in VILLAIN_GLOWS:
            errors.append(f"[{v['slug']}] villain accent {pal.get('accent')} must be one of {sorted(VILLAIN_GLOWS)}")
        v_sp = re.sub(r"^(robo-|cyber-|mecha\s+)", "", v["species"].lower())
        for h in heroes:
            h_sp = h["species"].lower()
            if v_sp in h_sp or h_sp in v_sp:
                de_acc = ciede2000(h["palette"]["primary"], pal["accent"])
                if de_acc < 35.0:
                    errors.append(
                        f"Same-species villain {v['slug']} glow {pal['accent']} too close to {h['slug']} ({h['palette']['primary']}), ΔE={de_acc:.2f} < 35"
                    )

    return errors


def main() -> int:
    errs = validate_bible()
    if errs:
        print(f"FAIL: {len(errs)} bible validation error(s):", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("OK: character bible passed all schema, species, safety, and CIEDE2000 ΔE checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
