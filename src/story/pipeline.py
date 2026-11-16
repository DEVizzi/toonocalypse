"""Planner -> scripts for all parts -> judge. Writes the story bible. Never falls back to template text."""
from __future__ import annotations

import json
import random
from typing import Any

from src.common.config import categories, settings
from src.common.gemini import generate_json
from src.common.ids import make_story_id
from src.common.quota import Quota
from src.common.retry import Abort
from src.common.state import load_state, save_state
from src.story.validate import validate_part, validate_plan

SAFETY = (
    "Audience: general, ages 10+. Thrilling but safe: comic-book peril and battles are fine; "
    "no gore, blood, graphic violence, sexual content, real people, real brands, politics or hate. "
    "Mythology focuses on epic heroes, legends and folklore creatures; never write dialogue for worshipped deities, "
    "never mock beliefs, portray sacred figures with dignity."
)
WRITING = (
    "Grade 5-7 reading level, short sentences, no jargon. Show, don't explain. "
    "Every prop mentioned in dialogue must appear in a panel. The moral is shown through a character's CHOICE, never preached."
)


def bible() -> dict[str, Any]:
    return load_state("story_bible.json", {"current": None, "history": [],
                                           "used": {"categories": [], "settings": [], "morals": [], "premises": []}})


def pick_seed_or_category(b: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    used_titles = {h.get("title") for h in b.get("history", [])}
    last_cat = b["used"]["categories"][-1] if b["used"]["categories"] else None
    for seed in categories()["seeds"]:
        if seed["title"] not in used_titles and seed["category"] != last_cat:
            return {"seed": seed, "category": seed["category"]}
    cats = {k: v for k, v in categories()["categories"].items() if k != last_cat}
    cat = rng.choices(list(cats), weights=[c["weight"] for c in cats.values()])[0]
    return {"seed": None, "category": cat}


def plan_story(seed_title: str | None = None, quota: Quota | None = None, rng: random.Random | None = None) -> dict[str, Any]:
    s = settings()["story"]
    b = bible()
    if seed_title:
        seed = next((x for x in categories()["seeds"] if x["title"] == seed_title), None)
        if not seed:
            raise Abort(f"Unknown seed {seed_title!r}")
        choice = {"seed": seed, "category": seed["category"]}
    else:
        choice = pick_seed_or_category(b, rng or random.Random())
    cat = categories()["categories"][choice["category"]]
    window = s["no_repeat_window"]
    avoid = {k: b["used"][k][-window:] for k in ["settings", "morals", "premises"]}
    seed_txt = json.dumps(choice["seed"]) if choice["seed"] else "Invent a fresh story in this category."
    prompt = f"""You plan a {s['parts']['min']}-{s['parts']['max']} part vertical motion-comic story for the series "{settings()['series_name']}".
Category: {cat['label']} — {cat['brief']}
Seed: {seed_txt}  (if a seed is given, keep its title, moral and part count)
Avoid these recent settings/morals/premises: {json.dumps(avoid)}
{SAFETY}
{WRITING}
Cast: {s['cast_size']['min']}-{s['cast_size']['max']} named characters, mostly human, ethnicity/region fitting the setting.
Each character needs a different signature colour, hairstyle and silhouette; no two of similar age+gender+hair.
visual_prompt: <= {s['visual_prompt_max_chars']} chars, describes ONLY that character's fixed look (age, build, face, hair+colour, skin, outfit colours, accessory). No style words.
Part 1: hook + world + problem + cliffhanger. Middle parts: escalation, twist, setback + cliffhanger. Final: climax, the moral CHOICE, payoff.
Cliffhanger types (rotate, no repeats in a row): {s['cliffhanger_types']}. Write each payoff first.
Return JSON: {{"title","category":"{choice['category']}","logline","moral","parts":int,"setting","music_mood":"{cat['music_mood']}",
"cast":[{{"name","age","gender","region","build","face_shape","eyes","eyebrows","hair","skin_tone","outfit","accessory","signature_color","anchors":[3 strings],"visual_prompt","voice":"narrator-style hint e.g. young male warm"}}],
"beats":[{{"part","summary","cliffhanger_type"(null for final),"cliffhanger","payoff_next"(how the next part opens; null for final)}}]}}"""
    last_err = ""
    for _ in range(3):
        plan, model = generate_json(prompt + (f"\nFix this problem from the last draft: {last_err}" if last_err else ""), "planner", quota=quota)
        errs = validate_plan(plan)
        if not errs:
            plan["story_id"] = make_story_id(plan["title"])
            plan["planner_model"] = model
            return plan
        last_err = "; ".join(errs[:6])
        print(f"[planner] rejected: {last_err}", flush=True)
    raise Abort(f"Planner failed validation: {last_err}")


def write_scripts(plan: dict[str, Any], quota: Quota | None = None, feedback: str = "") -> dict[str, Any]:
    s = settings()["story"]
    total = int(plan["parts"])
    cast = [{"name": c["name"], "voice": c.get("voice")} for c in plan["cast"]]
    prompt = f"""Write the scripts for ALL {total} parts of this story. Plan: {json.dumps({k: plan[k] for k in ['title','logline','moral','setting','beats']})}
Cast (refer to characters ONLY by name; never describe their looks, the art system injects that): {json.dumps(cast)}
{SAFETY}
{WRITING}
Per part: {s['panels_per_part']['min']}-{s['panels_per_part']['max']} panels, total duration {s['part_seconds']['min']}-{s['part_seconds']['max']}s (sum of panel durations), new image every 4-7s.
Panel 1 = HOOK: the most dramatic image + a spoken line <= {s['hook_line_max_words']} words (put it in hook_text and as panel 1 dialogue or narration). Never a title or greeting first.
Parts 2+: 'previously' = one short line; panel 1 pays off the previous cliffhanger in the first 5s.
Then 3 escalating tension beats, a mini-payoff, then the cliffhanger (non-final). Final part: climax, the moral CHOICE, payoff, and 'moral_card' = the moral in <= {s['moral_max_words']} words.
Spoken lines <= {s['spoken_line_max_words']} words. Max {s['max_chars_per_panel']} characters per panel; character-free shots (establishing, objects, effects) are encouraged.
image_prompt: scene, action, camera angle, lighting, emotion; characters by name only. Leave the upper 25% as empty sky/wall.
title: <= {s['title_max_chars']} chars, curiosity first, a complete phrase, ending with "| Pt X/{total}" e.g. "He Found Gold in His Rickshaw… | Pt 1/{total}".
caption: hook line + "Part X/{total} — save this so you don't miss the next part" + a question. hashtags: 3-5 relevant.
{('Judge feedback to fix: ' + feedback) if feedback else ''}
Return JSON: {{"parts":[{{"part","title","hook_text","previously"(null for part 1),"description","caption","hashtags":[],"moral_card"(final only),
"panels":[{{"id","image_prompt","characters":[{{"name","position":"left|center|right"}}],"camera","lighting","emotion","narration","dialogue":[{{"speaker","line"}}],"sfx","duration"}}]}}]}}"""
    names = {c["name"] for c in plan["cast"]}
    last_err = ""
    for _ in range(3):
        out, model = generate_json(prompt + (f"\nFix: {last_err}" if last_err else ""), "scripts", quota=quota)
        parts = out.get("parts", [])
        errs = [] if len(parts) == total else [f"expected {total} parts, got {len(parts)}"]
        for p in parts:
            errs += validate_part(p, total, names)
        if not errs:
            return {"parts": parts, "script_model": model}
        last_err = "; ".join(errs[:8])
        print(f"[scripts] rejected: {last_err}", flush=True)
    raise Abort(f"Scripts failed validation: {last_err}")


CRITERIA = ["hook", "clarity", "tension", "twist", "emotion", "cliffhanger", "moral_payoff", "readability", "safety"]


def judge(plan: dict[str, Any], scripts: dict[str, Any], quota: Quota | None = None) -> dict[str, Any]:
    prompt = f"""You are a strict story editor for a general-audience (10+) vertical comic channel. Score 1-10 each: {CRITERIA}.
safety=10 only if fully compliant with: {SAFETY}
Story plan: {json.dumps({k: plan[k] for k in ['title','logline','moral','beats']})}
Scripts: {json.dumps(scripts['parts'])}
Return JSON: {{"scores":{{criterion:int}},"notes":"what to fix, concrete"}}"""
    out, model = generate_json(prompt, "judge", quota=quota)
    return score_verdict(out) | {"judge_model": model}


def score_verdict(out: dict[str, Any]) -> dict[str, Any]:
    cfg = settings()["judge"]
    scores = {k: int(out.get("scores", {}).get(k, 0)) for k in CRITERIA}
    avg = round(sum(scores.values()) / len(scores), 2)
    passed = avg >= cfg["min_avg"] and scores["safety"] >= cfg["safety"] and scores["hook"] >= cfg["min_hook"]
    return {"scores": scores, "avg": avg, "passed": passed, "notes": out.get("notes", "")}


def create_story(seed_title: str | None = None, quota: Quota | None = None) -> dict[str, Any]:
    q = quota or Quota()
    plan = plan_story(seed_title, quota=q)
    feedback = ""
    for attempt in range(settings()["judge"]["max_rewrites"] + 1):
        scripts = write_scripts(plan, quota=q, feedback=feedback)
        verdict = judge(plan, scripts, quota=q)
        print(f"[judge] attempt {attempt + 1}: avg={verdict['avg']} scores={verdict['scores']}", flush=True)
        if verdict["passed"]:
            story = plan | scripts | {"judge": verdict, "status": "SCRIPTED"}
            b = bible()
            b["current"] = story
            save_state("story_bible.json", b)
            return story
        feedback = verdict["notes"]
    raise Abort(f"Judge rejected story after rewrites: {verdict['notes'][:200]}")
