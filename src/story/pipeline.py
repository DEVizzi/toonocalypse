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
Design looks the image model can reproduce reliably: ONE dominant signature colour on the main garment (e.g. "bright red kurta"),
neutral secondary clothing (black/white/grey/brown/khaki), ONE large clearly visible accessory in a contrasting colour
(e.g. "yellow headband", "big brass pocket watch"), and a simple distinctive hairstyle. Never put two strong colours on two garments.
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


PANELS_TARGET = 8


def _part_prompt(plan: dict[str, Any], n: int, total: int, done: list[dict[str, Any]], feedback: str) -> str:
    s = settings()["story"]
    cast = [{"name": c["name"], "voice": c.get("voice")} for c in plan["cast"]]
    beat = next((b for b in plan["beats"] if int(b["part"]) == n), {})
    prev = [{"part": p["part"], "title": p["title"], "ends_with": p["panels"][-1]["image_prompt"],
             "cliffhanger": next((b.get("cliffhanger") for b in plan["beats"] if int(b["part"]) == p["part"]), "")} for p in done]
    final = n == total
    prev_ph = '"..."' if n > 1 else "null"
    moral_ph = '"..."' if final else "null"
    skeleton = ",".join(f'{{"id":{i},"image_prompt":"...","characters":[],"camera":"...","lighting":"...","emotion":"...",'
                        f'"narration":"","dialogue":[],"sfx":"","duration":6.5}}' for i in range(1, PANELS_TARGET + 1))
    return f"""Write the script for PART {n} of {total} of this story.
Story plan: {json.dumps({k: plan[k] for k in ['title','logline','moral','setting']})}
This part's beat: {json.dumps(beat)}
Earlier parts (for continuity): {json.dumps(prev)}
Cast (refer to characters ONLY by name; never describe their looks): {json.dumps(cast)}
{SAFETY}
{WRITING}
RULES:
- EXACTLY {PANELS_TARGET} panels with ids 1..{PANELS_TARGET}; each panel duration 5.5-7 seconds (total {s['part_seconds']['min']}-{s['part_seconds']['max']}s).
- Panel 1 = HOOK: the most dramatic image; hook_text = a spoken line of at most {s['hook_line_max_words']} words, also used as panel 1's first line. Never a title or greeting first.
{"- 'previously' = one short recap line; panel 1 pays off the previous cliffhanger." if n > 1 else "- 'previously' = null."}
- Then 3 escalating tension beats, a mini-payoff, then {"the climax, the moral CHOICE, and the payoff" if final else "the cliffhanger: " + str(beat.get("cliffhanger", ""))}.
{f"- moral_card = exactly: {plan['moral']}" if final else "- moral_card = null."}
- Spoken lines <= {s['spoken_line_max_words']} words; speakers must be cast names. Max {s['max_chars_per_panel']} characters per panel (positions left/center/right). Use some character-free shots.
- image_prompt: scene, action, camera angle, lighting, emotion; characters by name only; upper 25% empty sky/wall.
- title <= {s['title_max_chars']} chars, curiosity first, complete phrase, ending with "| Pt {n}/{total}".
- caption: hook line + "Part {n}/{total} — save this so you don't miss the next part" + a question. hashtags: 3-5.
{('Fix these problems: ' + feedback) if feedback else ''}
Return JSON exactly in this shape:
{{"part":{n},"title":"...","hook_text":"...","previously":{prev_ph},"description":"...","caption":"...","hashtags":["..."],"moral_card":{moral_ph},"panels":[{skeleton}]}}"""


def write_scripts(plan: dict[str, Any], quota: Quota | None = None, feedback: str = "") -> dict[str, Any]:
    total = int(plan["parts"])
    names = {c["name"] for c in plan["cast"]}
    parts = [] if feedback else list(plan.get("parts_done", []))
    model = plan.get("script_model", "")
    for n in range(len(parts) + 1, total + 1):
        last_err = ""
        for _ in range(3):
            fb = "; ".join(x for x in [feedback, last_err] if x)
            out, model = generate_json(_part_prompt(plan, n, total, parts, fb), f"scripts_p{n}", quota=quota)
            part = out.get("parts", [out])[0] if isinstance(out, dict) and "parts" in out else out
            part["part"] = n
            for p in part.get("panels", []):
                p["dialogue"] = [{"speaker": d.get("speaker") or d.get("character") or d.get("name"),
                                  "line": (d.get("line") or d.get("text") or "").strip()}
                                 for d in (p.get("dialogue") or []) if isinstance(d, dict) and (d.get("line") or d.get("text"))]
            normalize_durations(part)
            errs = validate_part(part, total, names)
            if not errs:
                parts.append(part)
                b = bible()
                if (b.get("current") or {}).get("story_id") == plan.get("story_id"):
                    b["current"]["parts_done"] = parts
                    b["current"]["script_model"] = model
                    save_state("story_bible.json", b)
                break
            last_err = "; ".join(errs[:8])
            print(f"[scripts] part {n} rejected: {last_err}", flush=True)
        else:
            raise Abort(f"Scripts failed validation (part {n}): {last_err}")
    return {"parts": parts, "script_model": model}


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


def normalize_durations(part: dict[str, Any], lo: float = 4.0, hi: float = 7.0) -> None:
    """Rescale panel durations (planning targets) into the part window; each panel stays 4-7s."""
    s = settings()["story"]["part_seconds"]
    panels = part.get("panels", [])
    if not panels:
        return
    durs = [max(0.5, float(p.get("duration") or lo)) for p in panels]
    total = sum(durs)
    target = min(max(total, s["min"] + 3), s["max"] - 3, hi * len(panels))
    target = max(target, lo * len(panels))
    for p, d in zip(panels, durs):
        p["duration"] = round(min(hi, max(lo, d * target / total)), 2)


def create_story(seed_title: str | None = None, quota: Quota | None = None) -> dict[str, Any]:
    q = quota or Quota()
    b = bible()
    cur = b.get("current")
    if cur and cur.get("status") == "PLANNED" and (not seed_title or cur.get("title") == seed_title):
        plan = cur
        print(f"[planner] resuming saved plan {plan['story_id']} '{plan['title']}'", flush=True)
    else:
        plan = plan_story(seed_title, quota=q) | {"status": "PLANNED"}
        b["current"] = plan
        save_state("story_bible.json", b)
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
