"""M5/v3.4 comedy commentary script for MC Tuno.

- First-person broadcaster persona ("I'm cranking the speed up!" — never third-person "Lord Tuno").
- Strict character-accurate lore across both Gemini prompts and rich non-repeating fallback pools:
  Bonk = heavy bowling ball, Juggernaut = cast-iron wrecking cube / freight train, Boing = hyper rubber pinball,
  Dash = no-brakes ice puck, Floater = helium balloon / beach ball, Glitch = laggy/corrupted physics ball,
  Grumble = spiteful sticky velcro ball, Magneto = magnetic hex bolt, Pip = featherweight ping-pong ball,
  Sly = sneaky billiard cue ball.
- Reaction beats target `event_t - 0.15s` for anticipation sync; winner shoutout fires `0.4s` before Winner Card;
  outro CTA names the exact 2 heroes printed on the Winner Card."""
from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field

from src.characters.roster import HERO_BY_KEY
from src.config import settings

WORDS_PER_S = 3.2      # edge-tts at +20% rate with -40 dB silence trimming

HERO_LORE: dict[str, str] = {
    "bonk": "heavy orange bowling ball",
    "juggernaut": "massive cast-iron wrecking cube / freight train (NEVER call a bowling ball)",
    "boing": "hyper-bouncy pink rubber pinball",
    "dash": "frictionless cyan ice puck with zero brakes",
    "floater": "drifting white helium balloon beach ball",
    "glitch": "laggy corrupted-physics ball with packet loss",
    "grumble": "spiteful sticky blue velcro ball",
    "magneto": "purple magnetic hex bolt with iron grip",
    "pip": "tiny featherweight ping-pong ball",
    "sly": "calculating green billiard cue ball",
}

HERO_KILL_LINES: dict[str, list[str]] = {
    "bonk": ["Bonk bowls a ruthless strike on {victim}!", "Heavy bowling ball Bonk clears {victim}!"],
    "juggernaut": ["Freight train Juggernaut flattens {victim}!", "Iron cube Juggernaut wrecks {victim}!"],
    "boing": ["Pinball Boing ricochets {victim} off!", "Boing bounces {victim} into orbit!"],
    "dash": ["No-brakes Dash body-checks {victim}!", "Ice puck Dash slides through {victim}!"],
    "floater": ["Helium Floater bumps {victim} off!", "Even airy Floater shoves {victim} down!"],
    "glitch": ["Glitch lags right through {victim}!", "Corrupted hitbox! Glitch deletes {victim}!"],
    "grumble": ["Spiteful Grumble drags {victim} to the edge!", "Velcro Grumble peels {victim} off!"],
    "magneto": ["Magneto repels {victim} into the pit!", "Hex bolt Magneto slams {victim} out!"],
    "pip": ["Tiny ping-pong Pip upsets {victim}!", "Featherweight Pip snipes {victim}!"],
    "sly": ["Cue ball Sly banks {victim} into the pocket!", "Sneaky bank shot by Sly on {victim}!"],
}

HERO_FALL_LINES: dict[str, list[str]] = {
    "bonk": ["Bowling ball Bonk gutter-balled!", "Too heavy! Bonk sinks like lead!"],
    "juggernaut": ["The iron cube tumbles off the ledge!", "Freight train Juggernaut derailed!"],
    "boing": ["Pinball Boing bounced way too high!", "Boing ricocheted straight into the abyss!"],
    "dash": ["Zero brakes! Dash slid clean off!", "Ice puck Dash forgot corners exist!"],
    "floater": ["Helium couldn't save Floater there!", "Floater drifted past the landing!"],
    "glitch": ["Glitch lagged right off the map!", "Four hundred ping! Glitch disconnected!"],
    "grumble": ["Even velcro couldn't save Grumble!", "Grumble's spite ran out of ledge!"],
    "magneto": ["Nothing magnetic down there, Magneto!", "Hex bolt Magneto lost traction!"],
    "pip": ["Ping-pong Pip got blown off course!", "Featherweight Pip flew into the void!"],
    "sly": ["Cue ball Sly scratched into the pit!", "Sly misread the geometry!"],
}

TEMPLATES: dict[str, list[str]] = {
    "intro": [
        "Fifteen fearless balls, one golden crown!",
        "Gates are dropping on {arena}!",
        "Fifteen enter {arena}, one leaves crowned!",
        "Buckle up, castle chaos starts right now!",
        "Fifteen contenders, zero mercy on {arena}!",
    ],
    "first_blood_hero": [
        "First blood! {victim} takes the early drop!",
        "Ouch, {victim} is out in seconds!",
        "Blink and {victim} already vanished!",
        "Early exit for {victim}! Rough start!",
    ],
    "first_blood_dummy": [
        "First crash dummy down, working as intended!",
        "Safety test failed for that crash dummy!",
        "One crash dummy sacrificed to gravity!",
        "Crash dummy goes splat right on cue!",
    ],
    "betrayal": [
        "{killer} ruthlessly shoves {victim} into the abyss!",
        "Cold-blooded! {killer} sends {victim} packing!",
        "Zero mercy as {killer} launches {victim}!",
        "{killer} just evicted {victim} off the ledge!",
    ],
    "multi": [
        "Massive pileup! Half the pack just vanished!",
        "Total wipeout! Somebody call castle cleanup!",
        "Domino disaster! Three gone in a blink!",
        "Carnage at the ledge, they're dropping fast!",
    ],
    "hero_fall": [
        "{victim} ran completely out of floor!",
        "Gravity wins that round against {victim}!",
        "{victim} missed the jump by a mile!",
        "Down goes {victim} into the castle pit!",
    ],
    "torched": [
        "Crispy! {victim} got cooked by my fire wall!",
        "Too slow! Fire wall roasts {victim}!",
        "{victim} turned into castle toast!",
    ],
    "speed": [
        "I'm cranking the speed dial way up!",
        "Too easy! I'm hitting turbo mode!",
        "Let's spice this up, faster tempo!",
        "My hand slipped onto the turbo switch!",
    ],
    "overtime": [
        "Overtime chaos! I'm unleashing max speed!",
        "Sudden death! I'm cranking every hazard!",
        "Overtime! I broke the safety limiter!",
        "Final showdown, I'm turning chaos to eleven!",
    ],
    "twist": [
        "I'm flipping the {twist} switch right now!",
        "Plot twist! I just triggered {twist}!",
        "Let's see how they handle {twist}!",
        "Surprise! I'm dropping {twist} on them!",
    ],
    "final3": [
        "Down to three: {a}, {b}, and {c}!",
        "Final three standing: {a}, {b}, {c}!",
        "Three left fighting for one crown!",
    ],
    "final2": [
        "Final duel! {a} versus {b}!",
        "One on one, {a} against {b}!",
        "Only room for one, {a} or {b}!",
    ],
    "lead": [
        "{name} surges into first place!",
        "{name} steals the lead late!",
        "Look at {name} charging to the front!",
    ],
    "trait_bowling": [
        "Freight train Juggernaut ploughs through the pack!",
        "Watch out, cast-iron cube coming through!",
        "Juggernaut flattens everyone like a wrecking cube!",
    ],
    "trait_wall_slam": [
        "Ice puck Dash has zero brakes!",
        "Dash slams full speed with no brakes!",
        "Zero friction, Dash ricochets off the wall!",
    ],
    "trait_wind_launch": [
        "Ping-pong {name} gets launched sky high!",
        "Featherweight {name} catches a massive gust!",
    ],
    "trait_double_ricochet": [
        "Hyper pinball Boing hits a double ricochet!",
        "Boing bounces twice like a wild pinball!",
    ],
    "trait_spite_save": [
        "Velcro Grumble clings on through pure spite!",
        "Sticky Grumble refuses to fall today!",
    ],
    "winner": [
        "{winner} takes the crown!",
        "{winner} claims the castle crown!",
        "{winner} steals the crown!",
        "{winner} rules the castle!",
    ],
    "outro": [
        "{a} or {b} tomorrow? Drop your pick!",
        "{a} or {b} tomorrow? Vote below!",
        "{a} or {b} next? Drop your pick!",
    ],
}

BANNED_PHRASES = (
    "friendship over",
    "what a champion",
    "who survives",
    "lord tuno",
)

ARENA_NAMES = {"rotating_disc": "Rotating Disc", "ramp_descent": "Ramp Descent", "pachinko_drop": "Pachinko Drop"}


@dataclass
class Beat:
    t: float                      # desired start time on output timeline (s)
    kind: str
    prio: int                     # 10 = must play (intro/winner/outro)
    ctx: dict = field(default_factory=dict)
    max_words: int = 8
    text: str = ""
    event_t: float = 0.0          # exact output timestamp of physics event (for <= 0.55s lag cap)


def _name(key: str | None) -> str:
    if not key:
        return "Somebody"
    h = HERO_BY_KEY.get(key)
    return h.name if h else "a crash dummy"


def _pick_template(b: Beat, rng: random.Random, used: set[str]) -> str:
    pool = list(TEMPLATES.get(b.kind, ["Chaos in the castle!"]))
    if b.kind == "betrayal" and b.ctx.get("killer_key") in HERO_KILL_LINES:
        pool = HERO_KILL_LINES[b.ctx["killer_key"]] + pool
    elif b.kind in ("hero_fall", "first_blood_hero") and b.ctx.get("victim_key") in HERO_FALL_LINES:
        pool = HERO_FALL_LINES[b.ctx["victim_key"]] + pool
    formatted = []
    for tpl in pool:
        try:
            s = tpl.format(**b.ctx)
        except (KeyError, IndexError):
            continue
        if s not in used:
            formatted.append(s)
    if not formatted:
        formatted = [pool[0].format_map({k: "" for k in ("a", "b", "c", "winner", "victim", "killer", "name", "arena", "twist")} | b.ctx)]
    short = [s for s in formatted if len(s.split()) <= b.max_words + 1] or formatted
    choice = rng.choice(short)
    used.add(choice)
    return choice


def build_beats(r, to_out, video_len: float, replay_t: float, card_t: float, prompt_pair: tuple[str, str]) -> list[Beat]:
    """r: pipeline.Renderer; to_out(gameplay_t) -> output seconds or None."""
    tr = r.tr
    ev = sorted(tr.events, key=lambda e: e.t)
    beats: list[Beat] = []
    arena = ARENA_NAMES.get(tr.meta["recipe"]["arena"], tr.meta["recipe"]["arena"].replace("_", " ").title())

    # 1. Cold-open hook (0.04s)
    beats.append(Beat(0.04, "intro", 10, {"arena": arena}, max_words=6, event_t=0.04))

    # Cutoff so gameplay reactions never collide with the winner shoutout at (card_t - 0.40s)
    react_cutoff = card_t - 1.45
    LEAD_IN = 0.15   # v3.4: schedule reaction clips 0.15s ahead of physics events where space permits

    def add_react(evt_out_t: float | None, kind: str, prio: int, ctx: dict | None = None) -> None:
        if evt_out_t is None or evt_out_t > react_cutoff or evt_out_t < 0.7:
            return
        beats.append(Beat(max(0.85, evt_out_t - LEAD_IN), kind, prio, ctx or {}, event_t=evt_out_t))

    elims = [e for e in ev if e.kind == "elimination"]
    if elims:
        e = elims[0]
        vk = e.actors[0] if e.actors else None
        kind = "first_blood_hero" if e.data.get("hero") else "first_blood_dummy"
        add_react(to_out(e.t), kind, 7, {"victim": _name(vk), "victim_key": vk or ""})

    for e in elims[1:]:
        t = to_out(e.t)
        vk = e.actors[0] if e.actors else None
        if e.data.get("hero") and e.data.get("by_hero") and len(e.actors) > 1:
            kk = e.actors[1]
            add_react(t, "betrayal", 8, {
                "killer": _name(kk), "killer_key": kk, "killer_lore": HERO_LORE.get(kk, ""),
                "victim": _name(vk), "victim_key": vk or "", "victim_lore": HERO_LORE.get(vk or "", ""),
            })
        elif e.data.get("hero") and e.data.get("cause") == "left_behind":
            add_react(t, "torched", 5, {"victim": _name(vk), "victim_key": vk or ""})
        elif e.data.get("hero"):
            add_react(t, "hero_fall", 4, {"victim": _name(vk), "victim_key": vk or ""})

    # Wipeouts (>= 3 KOs inside 1.2 s)
    i = 0
    while i < len(elims):
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.2:
            j += 1
        if j - i >= 3:
            add_react(to_out(elims[j - 1].t), "multi", 7)
            i = j
        else:
            i += 1

    for e in ev:
        t = to_out(e.t)
        if e.kind == "escalation" and e.data.get("overtime"):
            add_react(t, "overtime", 7)
        elif e.kind == "escalation" and "SPEED" in str(e.data.get("banner", "")):
            add_react(t, "speed", 5)
        elif e.kind == "twist":
            add_react(t, "twist", 6, {"twist": e.data.get("twist", "").replace("_", " ")})
        elif e.kind == "trait" and f"trait_{e.data.get('name')}" in TEMPLATES:
            ak = e.actors[0] if e.actors else ""
            add_react(t, f"trait_{e.data.get('name')}", 4, {"name": _name(ak), "actor_key": ak, "lore": HERO_LORE.get(ak, "")})
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5:
            ak = e.actors[0] if e.actors else ""
            add_react(t, "lead", 4, {"name": _name(ak), "actor_key": ak})

    pre = tr.meta.get("preroll_frames", 0)
    said3 = said2 = False
    for f in range(pre, r.end_f + 1, 3):
        alive = [tr.keys[k] for k in range(len(tr.keys)) if tr.flags[f][k] & 1]
        t = to_out((f - pre) / 30.0)
        if len(alive) == 3 and not said3:
            said3 = True
            add_react(t, "final3", 6, {"a": _name(alive[0]), "b": _name(alive[1]), "c": _name(alive[2])})
        if len(alive) == 2 and not said2 and tr.mode == "TOP_DOWN":
            said2 = True
            add_react(t, "final2", 7, {"a": _name(alive[0]), "b": _name(alive[1])})

    # 2. Winner shoutout triggered 0.4s BEFORE the Winner Card appears + synced CTA naming exact 2 heroes
    w_key = tr.meta.get("winner") or ""
    winner = _name(w_key)
    win_t = max(replay_t + 0.05, card_t - 0.40)
    beats.append(Beat(win_t, "winner", 10, {"winner": winner, "winner_key": w_key, "lore": HERO_LORE.get(w_key, "")},
                      max_words=5, event_t=win_t))
    beats.append(Beat(card_t + 0.55, "outro", 10, {"a": prompt_pair[0], "b": prompt_pair[1]},
                      max_words=7, event_t=card_t + 0.55))

    # Thin out: >= 1.55s apart so fast +20% clips never queue up or lag; same reaction kind >= 4.0s apart
    kept: list[Beat] = []
    for b in sorted(beats, key=lambda b: (-b.prio, b.t)):
        if b.prio >= 10 or (
            all(abs(b.t - o.t) >= 1.55 for o in kept)
            and all(not (o.kind == b.kind and abs(b.t - o.t) < 4.0) for o in kept)
        ):
            kept.append(b)
    beats = sorted(kept, key=lambda b: b.t)

    # Compute tight word budget per slot so every clip finishes before the next event
    for k, b in enumerate(beats):
        if b.kind == "winner":
            b.max_words = 5
            continue
        if b.kind == "outro":
            b.max_words = 7
            continue
        nxt = next((o.t for o in beats[k + 1:] if o.prio >= b.prio and o.t > b.t + 0.15), card_t - 0.45)
        b.max_words = int(max(4, min(8, (nxt - b.t - 0.14) * WORDS_PER_S)))

    rng = random.Random(int(tr.meta.get("seed", 0)) ^ hash(tr.meta["recipe"]["arena"]))
    used: set[str] = set()
    for b in beats:
        b.text = _pick_template(b, rng, used)
    return beats


_SAFE = re.compile(r"^[A-Za-z0-9 ,.!?'\-:]+$")


def _valid_llm_line(b: Beat, ln: str) -> bool:
    low = ln.lower()
    words = ln.split()
    if not (2 <= len(words) <= b.max_words + 1) or not _SAFE.match(ln):
        return False
    if any(p in low for p in BANNED_PHRASES):
        return False
    # Enforce strict character-accurate lore (prevent bowling-ball mixups!)
    mentioned_keys = {k for k, h in HERO_BY_KEY.items() if h.name.lower() in low}
    if "bowling" in low and "bonk" not in mentioned_keys:
        return False
    if ("wrecking cube" in low or "iron cube" in low) and "juggernaut" not in mentioned_keys:
        return False
    if "helium" in low and "floater" not in mentioned_keys:
        return False
    if "ice puck" in low and "dash" not in mentioned_keys:
        return False
    if b.kind == "winner" and b.ctx.get("winner", "").lower() not in low:
        return False
    if b.kind == "outro":
        a, bb = b.ctx.get("a", "").lower(), b.ctx.get("b", "").lower()
        if a not in low or bb not in low:
            return False
    return True


def punch_up(beats: list[Beat], log=print) -> int:
    """Rewrite lines with Gemini Flash in one batched call (cascading across model IDs on quota/404).
    Validates character lore, first-person voice, word counts, and exact CTA hero names."""
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        log("  gemini skipped: GOOGLE_API_KEY is empty/unset; using lore-accurate templates")
        return 0
    if not beats:
        return 0
    try:
        from google import genai
    except ImportError:
        log("  gemini skipped: google-genai not installed; using lore-accurate templates")
        return 0

    lore_ref = "; ".join(f"{HERO_BY_KEY[k].name} = {desc}" for k, desc in HERO_LORE.items())
    facts = [{"i": i, "event": b.kind, "facts": b.ctx, "max_words": b.max_words, "draft": b.text}
             for i, b in enumerate(beats)]
    prompt = (
        "You are MC Tuno, a hyper-energetic, witty first-person cartoon game-show booth commentator for Toon Toon Castle "
        "(YouTube Shorts). Speak STRICTLY in FIRST PERSON when triggering twists or speed-ups (e.g. 'I am cranking the "
        "speed up!', NEVER refer to 'Lord Tuno' in third person).\n"
        f"STRICT CHARACTER LORE (never mix these up!): {lore_ref}.\n"
        "BANNED CLICHES (never output): 'Friendship over!', 'What a champion!', 'Who survives?', 'It's X time!'.\n"
        "RULES PER BEAT:\n"
        "- Stay strictly <= max_words words.\n"
        "- For 'winner': shout '[Winner] takes the crown!' or similar in <= 5 words.\n"
        "- For 'outro': MUST include BOTH hero names facts.a and facts.b asking viewers to pick for tomorrow in <= 7 words.\n"
        "- Plain ASCII letters/punctuation only (no emojis, no hashtags, no quotes).\n"
        "Return ONLY a JSON array of strings, exact same length and order as input.\n\n"
        + json.dumps(facts)
    )

    a_cfg = settings()["audio"]
    client = genai.Client(api_key=key)
    models: list[str] = ["gemini-flash-latest", "gemini-flash-lite-latest"]
    for m in (a_cfg.get("gemini_models") or [a_cfg["gemini_model"]]):
        if m not in models:
            models.append(m)
    # Dynamically discover active Flash models on this API key so model retirements never cause silent 404 fallback
    try:
        discovered = []
        for m in client.models.list():
            mname = (getattr(m, "name", "") or "").replace("models/", "")
            low_m = mname.lower()
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            if actions and not any("generate" in str(act).lower() for act in actions):
                continue
            if "flash" in low_m and all(skip not in low_m for skip in ("tts", "image", "audio", "live", "thinking", "8b")):
                discovered.append(mname)
        # Prefer newest non-deprecated flash models first
        discovered.sort(reverse=True)
        models = list(dict.fromkeys(["gemini-flash-latest"] + discovered + models))
    except Exception:
        pass

    lines = None
    used_model = ""
    for idx, model in enumerate(models[:6]):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.85},
            )
            raw = (resp.text or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
            lines = json.loads(raw or "[]")
            used_model = model
            break
        except Exception as exc:
            code = getattr(exc, "code", "") or getattr(exc, "status_code", "")
            status = getattr(exc, "status", "")
            msg = re.sub(r"AIza[0-9A-Za-z_\-]+", "[REDACTED]", str(exc))[:120]
            log(f"  gemini {model} unavailable ({type(exc).__name__} {code} {status}: {msg})")
            if str(code) in ("400", "401", "403") and "API_KEY" in msg.upper():
                break
            if idx + 1 < min(6, len(models)):
                time.sleep(0.3)

    if not isinstance(lines, list) or len(lines) != len(beats):
        log("  gemini fallback: keeping lore-accurate templates")
        return 0

    n = 0
    for b, ln in zip(beats, lines):
        if isinstance(ln, str):
            ln = " ".join(ln.split())
            if _valid_llm_line(b, ln):
                b.text = ln
                n += 1
    log(f"  gemini ({used_model}) punched up {n}/{len(beats)} lines")
    return n
