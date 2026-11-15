"""Strict image prompt builder and panel-text linter (§7.3 & §7.6)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.common.config import ROOT, load_all_characters, load_style_guide

COLOR_OR_OUTFIT_WORDS = re.compile(
    r"\b("
    r"red|blue|green|yellow|orange|purple|violet|pink|brown|grey|gray|black|white|silver|gold|teal|cyan|magenta|"
    r"neon|scarf|hoodie|jacket|apron|cape|helmet|goggles|lab coat|monocle|duster|sash|hat|crown|armor|tuxedo"
    r")\b",
    re.IGNORECASE,
)


def lint_panel_action(action: str) -> list[str]:
    """Reject LLM-written panel action that describes character colors or outfits."""
    if len(action) > 200:
        return [f"panel action exceeds 200 chars ({len(action)})"]
    hits = COLOR_OR_OUTFIT_WORDS.findall(action)
    if hits:
        return [f"panel action contains forbidden color/outfit word(s): {sorted(set(w.lower() for w in hits))}"]
    return []


def build_scale_line(slugs: list[str], chars: dict[str, dict[str, Any]] | None = None) -> str:
    chars = chars or load_all_characters()
    present = [chars[s] for s in slugs if s in chars]
    if len(present) < 2:
        if len(present) == 1:
            c = present[0]
            return f"Scale: {c['name']} height={c['height_units']}x ({c['size_class']})."
        return "Scale: standard comic proportions."
    ordered = sorted(present, key=lambda c: float(c["height_units"]), reverse=True)
    largest, smallest = ordered[0], ordered[-1]
    ratio = float(largest["height_units"]) / max(0.1, float(smallest["height_units"]))
    parts = [f"{largest['name']} is {ratio:.1f}x taller than {smallest['name']}"]
    for c in ordered:
        if c["size_class"] == "XS":
            parts.append(f"{c['name']} (XS) sits on a prop, table, or shoulder and is always >=4% of panel height")
        elif c["size_class"] == "XL":
            parts.append(f"{c['name']} (XL) is framed knee-up or crouching in group shots and never shrunk")
    return "Scale rules: " + "; ".join(parts) + "."


def build_page_prompt(
    script: dict[str, Any],
    chars: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[Path]]:
    """Assemble the frozen prompt in exact §7.6 block order + up to 4 reference sheet paths."""
    chars = chars or load_all_characters()
    style_guide = load_style_guide()
    cast_slugs = list(dict.fromkeys(list(script.get("heroes", [])) + ([script["villain"]] if script.get("villain") else [])))[:4]

    grid_block = (
        "LAYOUT GRID: Draw a single comic page with a FIXED 2-column x 3-row grid (6 equal panels) "
        "separated by uniform 24px solid white (#FFFFFF) gutters and crisp outer margins. "
        "Leave breathing room around the focal action so both 9:16 and 16:9 crops work. "
        "STRICTLY NO text, NO speech bubbles, NO letters, NO sound effects, and NO signage anywhere in the artwork."
    )

    char_blocks = []
    ref_paths: list[Path] = []
    for slug in cast_slugs:
        c = chars[slug]
        anchors = "; ".join(c["anchors"])
        forbidden = ", ".join(c["forbidden"])
        char_blocks.append(
            f"- {c['name']}: {c['visual_prompt']} | MUST HAVE: {anchors} | FORBIDDEN: {forbidden}."
        )
        rp = ROOT / c["reference_sheet"]
        if rp.exists() and len(ref_paths) < 4:
            ref_paths.append(rp)

    scale_line = build_scale_line(cast_slugs, chars)

    panel_lines = []
    for idx, p in enumerate(script["panels"][:6], start=1):
        row = (idx - 1) // 2 + 1
        col = (idx - 1) % 2 + 1
        action = str(p["action"]).strip()[:200]
        panel_lines.append(f"Panel {idx} (row {row}, col {col}): {action}")

    full_prompt = "\n\n".join(
        [
            style_guide,
            grid_block,
            "CHARACTERS (follow verbatim):\n" + "\n".join(char_blocks),
            scale_line,
            "PANEL ACTIONS:\n" + "\n".join(panel_lines),
        ]
    )
    return full_prompt, ref_paths
