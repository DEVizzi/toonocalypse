"""M5 comedy commentary script for MC Tuno.

Beats come ONLY from real trace events (first blood, betrayals, wipeouts, twists, overtime, final 3, winner...).
Each beat gets a deterministic templated line; if GOOGLE_API_KEY is set, Gemini Flash (free tier) punches the lines
up in one batched call, constrained per beat to a max word count that fits the time slot. Any invalid/missing Gemini
line falls back to its template, so the pipeline never depends on the API being available."""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field

from src.characters.roster import HERO_BY_KEY
from src.config import settings

WORDS_PER_S = 2.7      # edge-tts at +14% rate


@dataclass
class Beat:
    t: float                      # desired output time (s)
    kind: str
    prio: int                     # 10 = must play (intro/winner/outro)
    ctx: dict = field(default_factory=dict)
    max_words: int = 9
    text: str = ""


TEMPLATES: dict[str, list[str]] = {
    "intro": ["Welcome to Toon Toon Castle! Fifteen balls, one crown!",
              "It's {arena} time! Who survives?",
              "Toon Toon Castle is open! Let them roll!"],
    "first_blood_hero": ["And {victim} is out first! Ouch!", "{victim} takes the express elevator down!",
                         "Bye bye, {victim}! That was quick!"],
    "first_blood_dummy": ["First crash dummy down. Working as designed!", "A crash dummy goes splat. Science!"],
    "betrayal": ["{killer} just yeeted {victim}! Friendship over!", "Betrayal! {killer} shoves {victim} off!",
                 "{killer} said goodbye to {victim}. Rudely!"],
    "multi": ["Double knockout! Somebody call the janitor!", "Wipeout! They're dropping like popcorn!",
              "Whoa, a whole pile just vanished!"],
    "hero_fall": ["{victim} forgot to steer!", "{victim} takes the scenic route down!", "Gravity one, {victim} zero!"],
    "torched": ["{victim} got toasted by the wall!", "Too slow, {victim}! Extra crispy!"],
    "speed": ["Speed up! Lord Tuno is getting impatient!", "Faster, faster! Hold on to your faces!"],
    "overtime": ["Overtime chaos! Anything can happen!", "It's overtime! Grab your snacks!"],
    "twist": ["Twist time: {twist}!", "Uh oh. {twist}! This changes everything!"],
    "final3": ["Final three! {a}, {b}, and {c}!", "Down to three! Who wants the crown?"],
    "final2": ["One on one! Only one ball fits!", "It's {a} versus {b}! Push!"],
    "lead": ["{name} takes the lead!", "{name} sneaks into first!"],
    "trait_bowling": ["{name} is a bowling ball of doom!"],
    "trait_wall_slam": ["Dash has no brakes. None!"],
    "trait_wind_launch": ["{name} is just floating away!"],
    "trait_double_ricochet": ["Boing bounces twice for the price of one!"],
    "trait_spite_save": ["Grumble refuses to fall out of pure spite!"],
    "winner": ["{winner} wins it! What a champion!", "And the crown goes to... {winner}!",
               "{winner} is the last ball standing!"],
    "outro": ["Who wins tomorrow, {a} or {b}? Comment below!", "Comment your pick for tomorrow!"],
}

ARENA_NAMES = {"rotating_disc": "Rotating Disc", "ramp_descent": "Ramp Descent", "pachinko_drop": "Pachinko Drop"}


def _name(key: str | None) -> str:
    if not key:
        return "Somebody"
    h = HERO_BY_KEY.get(key)
    return h.name if h else "a crash dummy"


def build_beats(r, to_out, video_len: float, replay_t: float, card_t: float, prompt_pair: tuple[str, str]) -> list[Beat]:
    """r: pipeline.Renderer; to_out(gameplay_t) -> output seconds or None."""
    tr = r.tr
    ev = sorted(tr.events, key=lambda e: e.t)
    beats: list[Beat] = []
    arena = ARENA_NAMES.get(tr.meta["recipe"]["arena"], tr.meta["recipe"]["arena"].replace("_", " ").title())
    beats.append(Beat(0.05, "intro", 10, {"arena": arena}))
    elims = [e for e in ev if e.kind == "elimination"]
    if elims:
        e = elims[0]
        kind = "first_blood_hero" if e.data.get("hero") else "first_blood_dummy"
        beats.append(Beat(to_out(e.t) or 0, kind, 7, {"victim": _name(e.actors[0])}))
    for e in elims[1:]:
        t = to_out(e.t)
        if t is None:
            continue
        if e.data.get("hero") and e.data.get("by_hero") and len(e.actors) > 1:
            beats.append(Beat(t, "betrayal", 8, {"killer": _name(e.actors[1]), "victim": _name(e.actors[0])}))
        elif e.data.get("hero") and e.data.get("cause") == "left_behind":
            beats.append(Beat(t, "torched", 4, {"victim": _name(e.actors[0])}))
        elif e.data.get("hero"):
            beats.append(Beat(t, "hero_fall", 4, {"victim": _name(e.actors[0])}))
    # wipeouts (>= 3 KOs inside 1.2 s)
    i = 0
    while i < len(elims):
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.2:
            j += 1
        if j - i >= 3:
            t = to_out(elims[j - 1].t)
            if t is not None:
                beats.append(Beat(t, "multi", 7))
            i = j
        else:
            i += 1
    for e in ev:
        t = to_out(e.t)
        if t is None:
            continue
        if e.kind == "escalation" and e.data.get("overtime"):
            beats.append(Beat(t, "overtime", 7))
        elif e.kind == "escalation" and "SPEED" in str(e.data.get("banner", "")):
            beats.append(Beat(t, "speed", 5))
        elif e.kind == "twist":
            beats.append(Beat(t, "twist", 6, {"twist": e.data.get("twist", "").replace("_", " ")}))
        elif e.kind == "trait" and f"trait_{e.data.get('name')}" in TEMPLATES:
            beats.append(Beat(t, f"trait_{e.data.get('name')}", 3, {"name": _name(e.actors[0])}))
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5:
            beats.append(Beat(t, "lead", 3, {"name": _name(e.actors[0])}))
    # final three / final two (from trace flags)
    pre = tr.meta.get("preroll_frames", 0)
    said3 = said2 = False
    for f in range(pre, r.end_f + 1, 3):
        alive = [tr.keys[k] for k in range(len(tr.keys)) if tr.flags[f][k] & 1]
        t = to_out((f - pre) / 30.0)
        if t is None:
            continue
        if len(alive) == 3 and not said3:
            said3 = True
            beats.append(Beat(t, "final3", 6, {"a": _name(alive[0]), "b": _name(alive[1]), "c": _name(alive[2])}))
        if len(alive) == 2 and not said2 and tr.mode == "TOP_DOWN":
            said2 = True
            beats.append(Beat(t, "final2", 7, {"a": _name(alive[0]), "b": _name(alive[1])}))
    winner = _name(tr.meta.get("winner"))
    beats.append(Beat(replay_t + 0.05, "winner", 10, {"winner": winner}))
    beats.append(Beat(card_t + 0.15, "outro", 9, {"a": prompt_pair[0], "b": prompt_pair[1]}))
    # thin out: one beat per 1.6 s window, highest priority first (must-plays always survive); same kind >= 4 s apart
    kept: list[Beat] = []
    for b in sorted(beats, key=lambda b: (-b.prio, b.t)):
        if b.prio >= 9 or (all(abs(b.t - o.t) >= 1.6 for o in kept)
                           and all(not (o.kind == b.kind and abs(b.t - o.t) < 4.0) for o in kept)):
            kept.append(b)
    beats = sorted(kept, key=lambda b: b.t)
    # word budget: what fits before the next higher-or-equal priority beat
    for k, b in enumerate(beats):
        nxt = next((o.t for o in beats[k + 1:] if o.prio >= b.prio and o.t > b.t + 0.2), video_len + 3.0)
        b.max_words = int(max(3, min(11, (nxt - b.t - 0.25) * WORDS_PER_S)))
    rng = random.Random(tr.meta.get("seed", 0))
    for b in beats:
        options = [s for s in TEMPLATES[b.kind] if len(s.split()) <= b.max_words + 1] or TEMPLATES[b.kind]
        try:
            b.text = rng.choice(options).format(**b.ctx)
        except (KeyError, IndexError):
            b.text = TEMPLATES[b.kind][0].format_map({k: "" for k in ("a", "b", "c")} | b.ctx)
    return beats


_SAFE = re.compile(r"^[A-Za-z0-9 ,.!?'\-:]+$")


def punch_up(beats: list[Beat], log=print) -> int:
    """Rewrite lines with Gemini Flash (free tier) in one call. Returns number of lines replaced."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key or not beats:
        return 0
    try:
        from google import genai
    except ImportError:
        return 0
    facts = [{"i": i, "event": b.kind, "facts": b.ctx, "max_words": b.max_words, "draft": b.text}
             for i, b in enumerate(beats)]
    prompt = (
        "You are MC Tuno, a hyped, goofy cartoon game-show commentator for a family-friendly YouTube Shorts series "
        "called Toon Toon Castle, where cartoon balls race and get knocked off castle courses. For each beat, write ONE "
        "short, punchy, funny spoken line. Rules: stay under max_words; use the hero names exactly as given; playful "
        "teasing only (no insults, no violence words beyond cartoon slapstick); no emojis, hashtags or quotes; plain "
        "ASCII punctuation only. Keep the intro and outro meaning. Return ONLY a JSON array of strings, same order and "
        "length as the input.\n\n" + json.dumps(facts)
    )
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=settings()["audio"]["gemini_model"], contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.9})
        lines = json.loads(resp.text or "[]")
    except Exception as exc:  # network / quota / parse: keep the templates
        log(f"  gemini commentary unavailable ({type(exc).__name__}); using templates")
        return 0
    n = 0
    if isinstance(lines, list) and len(lines) == len(beats):
        for b, ln in zip(beats, lines):
            if isinstance(ln, str):
                ln = " ".join(ln.split())
                if 2 <= len(ln.split()) <= b.max_words + 1 and _SAFE.match(ln):
                    b.text = ln
                    n += 1
    log(f"  gemini punched up {n}/{len(beats)} lines")
    return n
