"""Validators for plans, scripts and titles. Pure functions: easy to test, no API calls."""
from __future__ import annotations

import re
from typing import Any

from src.common.config import settings

CONNECTORS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of", "on", "or", "the", "to", "when", "with"}
POSITIONS = {"left", "center", "right"}
LOCK_FIELDS = ["name", "age", "gender", "region", "build", "face_shape", "eyes", "eyebrows", "hair",
               "skin_tone", "outfit", "accessory", "signature_color", "anchors", "visual_prompt"]


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def validate_title(title: str, part: int, total: int) -> list[str]:
    errs = []
    max_len = settings()["story"]["title_max_chars"]
    suffix = f"| Pt {part}/{total}"
    if len(title) > max_len:
        errs.append(f"title longer than {max_len} chars")
    if not title.endswith(suffix):
        errs.append(f"title must end with '{suffix}'")
    head = title[: -len(suffix)].strip().rstrip("…").rstrip(".").strip() if title.endswith(suffix) else title
    if words(head) < 3:
        errs.append("title phrase too short")
    last = re.findall(r"[A-Za-z']+", head.lower())
    if last and last[-1] in CONNECTORS:
        errs.append(f"title ends with connector '{last[-1]}'")
    return errs


def validate_plan(plan: dict[str, Any]) -> list[str]:
    s = settings()["story"]
    errs = []
    for k in ["title", "category", "logline", "moral", "parts", "setting", "cast", "beats"]:
        if not plan.get(k):
            errs.append(f"plan missing '{k}'")
    if errs:
        return errs
    if not s["parts"]["min"] <= int(plan["parts"]) <= s["parts"]["max"]:
        errs.append("part count out of range")
    if words(plan["moral"]) > s["moral_max_words"]:
        errs.append("moral too long")
    cast = plan["cast"]
    if not s["cast_size"]["min"] <= len(cast) <= s["cast_size"]["max"]:
        errs.append("cast size out of range")
    for c in cast:
        missing = [f for f in LOCK_FIELDS if not c.get(f)]
        if missing:
            errs.append(f"{c.get('name', '?')} lock card missing {missing}")
        if len(c.get("visual_prompt", "")) > s["visual_prompt_max_chars"]:
            errs.append(f"{c.get('name')} visual_prompt > {s['visual_prompt_max_chars']} chars")
        if len(c.get("anchors", [])) != 3:
            errs.append(f"{c.get('name')} needs exactly 3 anchors")
    for key in ["signature_color", "hair"]:
        vals = [str(c.get(key, "")).lower() for c in cast]
        if len(set(vals)) != len(vals):
            errs.append(f"cast members share the same {key}")
    if len(plan["beats"]) != int(plan["parts"]):
        errs.append("beats count != parts")
    for b in plan["beats"][:-1]:
        if b.get("cliffhanger_type") not in s["cliffhanger_types"]:
            errs.append(f"part {b.get('part')} has invalid cliffhanger_type")
        if not b.get("payoff_next"):
            errs.append(f"part {b.get('part')} has no payoff for its cliffhanger")
    return errs


def validate_part(part: dict[str, Any], total: int, cast_names: set[str]) -> list[str]:
    s = settings()["story"]
    n = part.get("part")
    errs = validate_title(part.get("title", ""), n, total)
    panels = part.get("panels", [])
    if not s["panels_per_part"]["min"] <= len(panels) <= s["panels_per_part"]["max"]:
        errs.append(f"part {n}: {len(panels)} panels")
    if words(part.get("hook_text", "")) > s["hook_line_max_words"]:
        errs.append(f"part {n}: hook line > {s['hook_line_max_words']} words")
    dur = sum(float(p.get("duration", 0)) for p in panels)
    if not s["part_seconds"]["min"] <= dur <= s["part_seconds"]["hard_cap"]:
        errs.append(f"part {n}: duration {dur:.1f}s outside {s['part_seconds']['min']}-{s['part_seconds']['hard_cap']}s")
    for p in panels:
        chars = p.get("characters", [])
        if len(chars) > s["max_chars_per_panel"]:
            errs.append(f"part {n} panel {p.get('id')}: more than {s['max_chars_per_panel']} characters")
        for c in chars:
            if c.get("name") not in cast_names:
                errs.append(f"part {n} panel {p.get('id')}: unknown character {c.get('name')}")
            if c.get("position") not in POSITIONS:
                errs.append(f"part {n} panel {p.get('id')}: bad position {c.get('position')}")
        for d in p.get("dialogue", []):
            if words(d.get("line", "")) > s["spoken_line_max_words"]:
                errs.append(f"part {n} panel {p.get('id')}: line > {s['spoken_line_max_words']} words")
            if d.get("speaker") not in cast_names:
                errs.append(f"part {n} panel {p.get('id')}: unknown speaker {d.get('speaker')}")
        if not p.get("image_prompt"):
            errs.append(f"part {n} panel {p.get('id')}: empty image_prompt")
    if n == total and not part.get("moral_card"):
        errs.append("final part has no moral_card")
    if n > 1 and not part.get("previously"):
        errs.append(f"part {n}: missing 'previously' line")
    return errs
