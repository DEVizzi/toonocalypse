"""Story & 6-panel motion-comic script generator (§4, §9, §10)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from src.common.config import display_name, load_all_characters, load_models, load_settings
from src.common.quota import QuotaTracker
from src.moderation.gate import check_script
from src.story.hook_gate import judge_script


def _build_offline_part(
    story_id: str,
    title: str,
    part_num: int,
    part_count: int,
    heroes: list[str],
    villain: str,
    setting: str,
    idea: str,
    cliffhanger_type: str | None,
) -> dict[str, Any]:
    chars = load_all_characters()
    settings = load_settings()
    lead = heroes[0]
    sup = heroes[1] if len(heroes) > 1 else lead
    lead_name = display_name(lead, settings)
    sup_name = display_name(sup, settings)
    vil_name = display_name(villain, settings)
    lead_cp = chars[lead]["catchphrase"]
    vil_cp = chars[villain]["catchphrase"]

    is_final = part_num == part_count
    prev_caption = f"Previously: {vil_name} launched a goofy scheme at {setting}!" if part_num > 1 else ""

    panels = [
        {
            "panel_id": 1,
            "camera": "zoom_in",
            "impact": True,
            "sfx": "ZOOM!",
            "characters": [lead, villain],
            "action": f"{lead_name} leaps into {setting} as {vil_name} triggers a silly gadget.",
            "narrator": prev_caption if part_num > 1 else f"Trouble strikes {setting}!",
            "dialogue": [{"speaker": villain, "line": f"{vil_cp}"}],
        },
        {
            "panel_id": 2,
            "camera": "pan_right",
            "impact": False,
            "sfx": "",
            "characters": [lead, sup],
            "action": f"{lead_name} and {sup_name} trade determined grins behind a counter.",
            "narrator": "",
            "dialogue": [
                {"speaker": lead, "line": f"Quick, {sup_name}, check the power switch!"},
                {"speaker": sup, "line": "On it!"},
            ],
        },
        {
            "panel_id": 3,
            "camera": "pan_left",
            "impact": True,
            "sfx": "BOING!",
            "characters": [sup, villain],
            "action": f"{sup_name} bounces a giant foam cushion across {setting} into {vil_name}'s gizmo.",
            "narrator": "",
            "dialogue": [{"speaker": villain, "line": "Hey, watch the chrome polish!"}],
        },
        {
            "panel_id": 4,
            "camera": "zoom_in",
            "impact": False,
            "sfx": "",
            "characters": [lead, sup],
            "action": f"{lead_name} spots the silly flaw in {vil_name}'s plan and points eagerly.",
            "narrator": "",
            "dialogue": [{"speaker": lead, "line": f"{lead_cp} Look, it isn't even plugged in!"}],
        },
        {
            "panel_id": 5,
            "camera": "zoom_out",
            "impact": True,
            "sfx": "SPLAT!",
            "characters": [lead, villain],
            "action": f"{vil_name}'s gadget backfires in harmless rainbow foam all over {setting}.",
            "narrator": "",
            "dialogue": [{"speaker": villain, "line": "Wait… why does it smell like marshmallows?"}],
        },
        {
            "panel_id": 6,
            "camera": "zoom_in" if not is_final else "static_loop",
            "impact": False,
            "sfx": "DING!" if is_final else "WHOOSH!",
            "characters": [lead, sup] if is_final else [lead, villain],
            "action": (
                f"{lead_name} and {sup_name} share a warm high-five laughing at {setting}."
                if is_final
                else f"A mysterious glowing button blinks behind {vil_name} as {lead_name} gasps."
            ),
            "narrator": "",
            "dialogue": [
                {
                    "speaker": sup if is_final else lead,
                    "line": "Best teamwork ever!" if is_final else "Uh oh… what does THAT button do?!",
                }
            ],
        },
    ]

    return {
        "story_id": story_id,
        "part_num": part_num,
        "part_count": part_count,
        "title": title,
        "logline": idea,
        "setting": setting,
        "heroes": heroes,
        "villain": villain,
        "hook_panel_id": 1,
        "on_screen_hook": f"{vil_name}'s Wacky Plan!",
        "cliffhanger_type": cliffhanger_type,
        "panels": panels,
    }


def generate_part_script(
    story_id: str,
    title: str,
    part_num: int,
    part_count: int,
    heroes: list[str],
    villain: str,
    setting: str,
    idea: str,
    cliffhanger_type: str | None,
    offline: bool = False,
    quota: QuotaTracker | None = None,
) -> dict[str, Any]:
    """Generate a 6-panel script and pass moderation + Hook & Retention gates."""
    chars = load_all_characters()
    qt = quota or QuotaTracker()

    for attempt in range(3):
        script: dict[str, Any] | None = None
        from src.common.gemini import call_with_key_failover, has_gemini_keys

        if not offline and has_gemini_keys() and qt.can_spend("text", 1):
            try:
                model = load_models().get("text_models", ["gemini-2.5-flash"])[0]
                cast_desc = "\n".join(
                    f"- slug={s}, name={chars[s]['name']}, catchphrase={chars[s]['catchphrase']}"
                    for s in heroes + [villain]
                )
                prompt = (
                    f"Write Part {part_num}/{part_count} of a family-friendly all-ages Toonocalypse motion comic.\n"
                    f"Premise: {idea}\nSetting: {setting}\nCliffhanger type: {cliffhanger_type or 'satisfying funny resolution'}\n"
                    f"Cast:\n{cast_desc}\n\n"
                    "Rules:\n"
                    "- Exactly 6 panels (panel_id 1..6).\n"
                    "- Panel 1 is the cold-open HOOK mid-action.\n"
                    "- Narrator speaks <=25% of total words.\n"
                    "- Panel 'action' <=180 chars and MUST NOT mention character colors, outfits, or body features.\n"
                    "- on_screen_hook <=6 words.\n"
                    "Return ONLY valid JSON with keys: on_screen_hook, hook_panel_id, panels (list of {panel_id, camera, impact, sfx, characters, action, narrator, dialogue:[{speaker, line}]})."
                )
                resp = call_with_key_failover(
                    lambda client: client.models.generate_content(model=model, contents=prompt)
                )
                qt.spend("text", 1)
                m = re.search(r"\{[\s\S]*\}", resp.text or "")
                if m:
                    parsed = json.loads(m.group(0))
                    if len(parsed.get("panels", [])) == 6:
                        script = {
                            "story_id": story_id,
                            "part_num": part_num,
                            "part_count": part_count,
                            "title": title,
                            "logline": idea,
                            "setting": setting,
                            "heroes": heroes,
                            "villain": villain,
                            "hook_panel_id": int(parsed.get("hook_panel_id", 1)),
                            "on_screen_hook": str(parsed.get("on_screen_hook", "Hold On!"))[:60],
                            "cliffhanger_type": cliffhanger_type,
                            "panels": parsed["panels"],
                        }
            except Exception:
                script = None

        if script is None:
            script = _build_offline_part(story_id, title, part_num, part_count, heroes, villain, setting, idea, cliffhanger_type)

        mod = check_script(script, use_llm=not offline)
        if not mod.passed:
            continue
        gate = judge_script(script, offline=offline, quota=qt)
        if gate.passed or attempt == 2:
            script["hook_gate"] = {"avg": gate.avg_score, "scores": gate.scores, "passed": gate.passed}
            return script

    raise RuntimeError("Failed to generate a family-safe script after 3 attempts")
