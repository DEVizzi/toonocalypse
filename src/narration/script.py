"""M5/v4.0 Natural Broadcast Commentary for MC Tuno.

- Natural Fall Guys / Wipeout caster voice with contractions ("Gravity's off—good luck!", "Juggernaut just deleted Pip!").
- Bans robotic "I see...", "I am...", third-person "Lord Tuno", and stiff "[Adj] [Hero] [verb] [Adj] [Hero]" phrasing.
- Dynamic contestant count (14 League, 11 Play-In, 8 Q1, 9 Q2/Grand Final — never hardcoded "Fifteen").
- On-screen-only event filter (+40px viewport margin) so off-camera KOs/hits are never narrated.
- Multi-KO Finale detection (DOUBLE / TRIPLE WIPEOUT! {Winner} steals it! when >=2 finalists drop within 0.8s of finish).
- Season League standings context (current_leader, points_gap, races_remaining, lead_changed) + Anti-Dead-Air filler pool.
- Tight 7-10 word outro budget with exact verbatim CTA text synced to the Winner Card."""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field

from src.characters.roster import HERO_BY_KEY

WORDS_PER_S = 3.2      # edge-tts at +20% rate with -40 dB silence trimming

NUMBER_WORDS: dict[int, str] = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
    9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen",
    15: "Fifteen", 16: "Sixteen",
}

HERO_LORE: dict[str, str] = {
    "bonk": "heavy orange bowling ball",
    "juggernaut": "massive cast-iron wrecking cube / freight train (NEVER call a bowling ball)",
    "boing": "hyper-bouncy pink rubber pinball",
    "dash": "frictionless cyan ice puck with zero brakes",
    "floater": "drifting white helium beach ball",
    "glitch": "laggy corrupted-physics ball with packet loss",
    "grumble": "spiteful sticky blue velcro ball",
    "magneto": "purple magnetic hex bolt with iron grip",
    "pip": "tiny featherweight ping-pong ball",
    "sly": "calculating green billiard cue ball",
}

HERO_KILL_LINES: dict[str, list[str]] = {
    "bonk": ["Bonk just bowled {victim} clean off!", "Strike! Bonk sends {victim} flying!"],
    "juggernaut": ["Juggernaut just flattened {victim}!", "Make way—Juggernaut deleted {victim}!"],
    "boing": ["Boing ricochets {victim} into orbit!", "Pinball shot! Boing launches {victim}!"],
    "dash": ["No brakes! Dash body-checks {victim}!", "Dash slides straight through {victim}!"],
    "floater": ["Wait—Floater just bumped {victim} off!", "Even airy Floater shoves {victim} out!"],
    "glitch": ["Packet loss! Glitch deletes {victim}!", "Glitch just lagged right through {victim}!"],
    "grumble": ["Grumble drags {victim} off the edge!", "Pure spite—Grumble peels {victim} off!"],
    "magneto": ["Magneto slams {victim} into the void!", "Repelled! Magneto launches {victim}!"],
    "pip": ["Tiny Pip just sniped {victim}!", "Huge upset—Pip knocks out {victim}!"],
    "sly": ["Corner pocket! Sly banks {victim} out!", "Dirty bank shot from Sly on {victim}!"],
}

HERO_FALL_LINES: dict[str, list[str]] = {
    "bonk": ["Gutter ball! Bonk sinks like lead!", "Too heavy—Bonk's gone!"],
    "juggernaut": ["The iron cube just derailed!", "Heavy fall—Juggernaut's out!"],
    "boing": ["One bounce too high for Boing!", "Boing ricocheted straight into the pit!"],
    "dash": ["Zero brakes! Dash slid clean off!", "Dash forgot corners exist!"],
    "floater": ["Helium couldn't save Floater there!", "Floater drifted way past the ledge!"],
    "glitch": ["Four hundred ping—Glitch disconnected!", "Glitch just lagged off the map!"],
    "grumble": ["Velcro gave out—Grumble's gone!", "Grumble ran completely out of ledge!"],
    "magneto": ["Nothing magnetic down there, Magneto!", "Magneto lost grip at the rim!"],
    "pip": ["Featherweight Pip got blown away!", "Pip's launched straight into the void!"],
    "sly": ["Scratch! Sly misread that angle!", "Cue ball Sly drops in the pocket!"],
}

TEMPLATES: dict[str, list[str]] = {
    "intro": [
        "{count_word} drop into {arena}—one takes it!",
        "Gates drop! {count_word} enter {arena}!",
        "{count_word} balls, one crown on {arena}!",
        "Chaos time! {count_word} enter {arena}!",
    ],
    "intro_playoff": [
        "{stage_title}! {count_word} enter {arena}!",
        "Playoff stakes! {count_word} battle on {arena}!",
        "{stage_title} on {arena}—season's on the line!",
    ],
    "intro_final": [
        "Grand Final! {count_word} enter {arena}!",
        "Season Finale on {arena}—for the trophy!",
        "It's the Grand Final on {arena}!",
    ],
    "first_blood_hero": [
        "First blood! {victim}'s out in seconds!",
        "Ouch—early exit for {victim}!",
        "Blink and {victim}'s already gone!",
    ],
    "first_blood_dummy": [
        "First dummy's down—right on cue!",
        "One crash dummy sacrificed to gravity!",
        "Dummy down! Test failed immediately!",
    ],
    "betrayal": [
        "{killer} just deleted {victim}!",
        "Cold-blooded! {killer} launches {victim}!",
        "No mercy—{killer} shoves {victim} off!",
        "{killer} evicts {victim} from the ledge!",
    ],
    "multi": [
        "Total wipeout! Bodies flying everywhere!",
        "Domino disaster—three gone in a blink!",
        "Massive pileup at the ledge!",
    ],
    "hero_fall": [
        "{victim} ran right out of floor!",
        "Gravity wins that round, {victim}!",
        "Down goes {victim} into the abyss!",
    ],
    "torched": [
        "Crispy! {victim}'s cooked by the wall!",
        "Too slow—the wall roasts {victim}!",
        "{victim} just got vaporized!",
    ],
    "speed": [
        "I'm cranking the speed way up!",
        "Too easy—hitting turbo mode!",
        "Let's speed this chaos up!",
    ],
    "overtime": [
        "Overtime! Cranking hazards to max!",
        "Sudden death—safety limiter's off!",
        "Overtime chaos! Hang on tight!",
    ],
    "twist": [
        "Flipping on {twist}—good luck!",
        "Plot twist! Dropping {twist} right now!",
        "{twist_cap}'s live—watch this!",
    ],
    "final3": [
        "Down to three: {a}, {b}, {c}!",
        "Final three: {a}, {b}, and {c}!",
        "Three left fighting for it!",
    ],
    "final2": [
        "One on one—{a} versus {b}!",
        "Final duel: {a} against {b}!",
        "Only room for one—{a} or {b}!",
    ],
    "lead": [
        "{name} steals first place!",
        "{name} surges to the front!",
        "Look at {name} taking over!",
    ],
    "trait_bowling": [
        "Juggernaut's ploughing right through everyone!",
        "Watch out—wrecking cube coming through!",
    ],
    "trait_wall_slam": [
        "Zero brakes—Dash ricochets full speed!",
        "Dash slams the rail at top speed!",
    ],
    "trait_wind_launch": [
        "{name} catches a massive gust!",
        "Airborne! {name} goes sky high!",
    ],
    "trait_double_ricochet": [
        "Wild double ricochet from Boing!",
        "Boing's bouncing everywhere like a pinball!",
    ],
    "trait_spite_save": [
        "Grumble clings on out of pure spite!",
        "Velcro save! Grumble refuses to drop!",
    ],
    "winner": [
        "{winner} takes the crown!",
        "{winner} steals the win!",
        "{winner} claims the victory!",
    ],
    "winner_new_leader": [
        "{winner} wins and grabs the season lead!",
        "{winner} takes it—new league leader!",
    ],
    "winner_champion": [
        "{winner} is our Season {season} Champion!",
        "{winner} wins the Season {season} Trophy!",
    ],
    "multi_ko_2": [
        "DOUBLE WIPEOUT! {winner} steals it!",
        "DOUBLE KNOCKOUT! {winner} survives it!",
    ],
    "multi_ko_3": [
        "TRIPLE WIPEOUT! {winner} steals it!",
        "MASSIVE WIPEOUT! {winner} steals it!",
    ],
    "outro": [
        "{a} or {b} tomorrow? Drop your pick!",
        "{a} or {b} next race? Vote below!",
        "Backing {a} or {b} next? Comment below!",
    ],
    "outro_final": [
        "Season {next_season} starts tomorrow! Who's your pick?",
        "New season drops tomorrow! Who takes Season {next_season}?",
    ],
}

FILLER_GENERAL: list[str] = [
    "Nobody's backing down!",
    "One slip ends it all!",
    "Pure chaos in the pack!",
    "Look how tight this pack is!",
    "Zero room for error here!",
]

FILLER_TOP_DOWN: list[str] = [
    "This floor's getting tiny!",
    "Nowhere left to hide!",
    "One shove sends 'em flying!",
]

BANNED_PHRASES = (
    "friendship over",
    "what a champion",
    "who survives",
    "lord tuno",
    "i see ",
    "i am ",
)

# Ban stiff "[Adjective] [Hero] [verb] [Adjective] [Hero]" constructions
_HERO_ALT = "|".join(HERO_BY_KEY.keys())
_STIFF_DOUBLE_ADJ = re.compile(
    rf"\b[a-z\-]+\s+({_HERO_ALT})\s+[a-z\-]+\s+[a-z\-]+\s+({_HERO_ALT})\b",
    re.IGNORECASE,
)

ARENA_NAMES = {
    "rotating_disc": "Rotating Disc",
    "ramp_descent": "Ramp Descent",
    "pachinko_drop": "Pachinko Drop",
    "sumo_pool_pit": "Sumo Pool Pit",
    "crumbling_bridge": "Crumbling Bridge",
    "collapse_tower": "Collapse Tower",
    "crusher_gauntlet": "Crusher Gauntlet",
}


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
    return h.name if h else "a dummy"


def _on_camera(r, gameplay_t: float, pos: tuple[float, float] | list[float] | None, pad: float = 40.0) -> bool:
    """Part A.2 On-Screen-Only Event Filter: only narrate collisions/KOs inside the camera viewport (+40px margin)."""
    if pos is None:
        return True
    fi = min(len(r.cams) - 1, max(0, r.pre + int(round(gameplay_t * 30.0))))
    return bool(r.cams[fi].on_screen(float(pos[0]), float(pos[1]), pad=pad))


def _pick_template(b: Beat, rng: random.Random, used: set[str]) -> str:
    pool = list(TEMPLATES.get(b.kind, ["Pure castle chaos!"]))
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
        defaults = {
            "a": "Bonk", "b": "Pip", "c": "Dash", "winner": "Bonk", "victim": "Somebody",
            "killer": "Bonk", "name": "Bonk", "arena": "the arena", "twist": "chaos",
            "twist_cap": "Chaos", "count_word": "Fourteen", "stage_title": "Playoffs",
            "season": 1, "next_season": 2,
        }
        defaults.update(b.ctx)
        formatted = [pool[0].format_map(defaults)]
    short = [s for s in formatted if len(s.split()) <= b.max_words + 1] or formatted
    choice = rng.choice(short)
    used.add(choice)
    return choice


def pick_filler(r, gameplay_t: float, used: set[str], league_ctx: dict | None = None) -> str:
    """Part A.2 Anti-Dead-Air Filler: crisp ~1s suspense or season-standings beat when >= 3.2s of silence occurs."""
    tr = r.tr
    fi = min(tr.n_frames - 1, max(0, r.pre + int(round(gameplay_t * 30.0))))
    alive_n = int(sum(1 for fl in tr.flags[fi] if fl & 1))
    cands: list[str] = []
    if 2 <= alive_n <= 6:
        w = NUMBER_WORDS.get(alive_n, str(alive_n))
        cands.append(f"{w} left—nobody's budging!")
        cands.append(f"Down to {w.lower()}—who blinks first?")
    if tr.mode == "TOP_DOWN" and gameplay_t > 8.0:
        cands.extend(FILLER_TOP_DOWN)
    if league_ctx:
        leader = league_ctx.get("current_leader_name") or ""
        rem = int(league_ctx.get("races_remaining", 99))
        gap = int(league_ctx.get("points_gap", 99))
        if leader and gap <= 12:
            cands.append(f"Title lead's on the line for {leader}!")
            cands.append("Standings are razor-thin right now!")
        if 1 <= rem <= 6:
            cands.append(f"Only {rem} races left this season!")
    cands.extend(FILLER_GENERAL)
    fresh = [c for c in cands if c not in used] or cands
    rng = random.Random(int(gameplay_t * 100) ^ int(tr.meta.get("seed", 0)))
    pick = rng.choice(fresh)
    used.add(pick)
    return pick


def build_beats(
    r,
    to_out,
    video_len: float,
    replay_t: float,
    card_t: float,
    prompt_pair: tuple[str, str],
    league_ctx: dict | None = None,
) -> list[Beat]:
    """r: pipeline.Renderer; to_out(gameplay_t) -> output seconds or None."""
    tr = r.tr
    ev = sorted(tr.events, key=lambda e: e.t)
    beats: list[Beat] = []
    arena = ARENA_NAMES.get(tr.meta["recipe"]["arena"], tr.meta["recipe"]["arena"].replace("_", " ").title())
    league_ctx = league_ctx or getattr(r.ep, "league_ctx", None) or {}

    n_total = len(tr.keys)
    count_word = NUMBER_WORDS.get(n_total, str(n_total))
    stage = str(league_ctx.get("stage") or "league")
    season_num = int(league_ctx.get("season_number") or 1)
    stage_names = {
        "play_in": "Play-In Wildcard",
        "qualifier_1": "Qualifier One",
        "qualifier_2": "Qualifier Two",
        "grand_final": "Grand Final",
    }
    intro_kind = "intro_final" if stage == "grand_final" else ("intro_playoff" if stage != "league" else "intro")

    # 1. Cold-open hook (0.04s) with dynamic contestant count (never hardcoded "Fifteen"!)
    beats.append(Beat(
        0.04,
        intro_kind,
        10,
        {
            "arena": arena,
            "count": n_total,
            "count_word": count_word,
            "stage_title": stage_names.get(stage, "Playoffs"),
            "season": season_num,
        },
        max_words=7,
        event_t=0.04,
    ))

    # Cutoff so gameplay reactions never collide with the winner shoutout at (card_t - 0.40s)
    react_cutoff = card_t - 1.45
    LEAD_IN = 0.15

    def add_react(evt_out_t: float | None, gameplay_t: float, pos, kind: str, prio: int, ctx: dict | None = None) -> None:
        if evt_out_t is None or evt_out_t > react_cutoff or evt_out_t < 0.7:
            return
        if not _on_camera(r, gameplay_t, pos, pad=40.0):
            return
        beats.append(Beat(max(0.85, evt_out_t - LEAD_IN), kind, prio, ctx or {}, event_t=evt_out_t))

    elims = [e for e in ev if e.kind == "elimination"]
    if elims:
        first_on_cam = next((e for e in elims if _on_camera(r, e.t, e.pos, pad=40.0)), None)
        if first_on_cam is not None:
            vk = first_on_cam.actors[0] if first_on_cam.actors else None
            kind = "first_blood_hero" if first_on_cam.data.get("hero") else "first_blood_dummy"
            add_react(to_out(first_on_cam.t), first_on_cam.t, first_on_cam.pos, kind, 7,
                      {"victim": _name(vk), "victim_key": vk or ""})

    for e in elims[1:]:
        t = to_out(e.t)
        vk = e.actors[0] if e.actors else None
        if e.data.get("hero") and e.data.get("by_hero") and len(e.actors) > 1:
            kk = e.actors[1]
            add_react(t, e.t, e.pos, "betrayal", 8, {
                "killer": _name(kk), "killer_key": kk, "killer_lore": HERO_LORE.get(kk, ""),
                "victim": _name(vk), "victim_key": vk or "", "victim_lore": HERO_LORE.get(vk or "", ""),
            })
        elif e.data.get("hero") and e.data.get("cause") == "left_behind":
            add_react(t, e.t, e.pos, "torched", 5, {"victim": _name(vk), "victim_key": vk or ""})
        elif e.data.get("hero"):
            add_react(t, e.t, e.pos, "hero_fall", 4, {"victim": _name(vk), "victim_key": vk or ""})

    # Wipeouts (>= 3 on-screen KOs inside 1.2 s)
    i = 0
    while i < len(elims):
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.2:
            j += 1
        on_cam_cluster = [e for e in elims[i:j] if _on_camera(r, e.t, e.pos, pad=40.0)]
        if len(on_cam_cluster) >= 3:
            last_e = on_cam_cluster[-1]
            add_react(to_out(last_e.t), last_e.t, last_e.pos, "multi", 7)
            i = j
        else:
            i += 1

    for e in ev:
        t = to_out(e.t)
        if e.kind == "escalation" and e.data.get("overtime"):
            add_react(t, e.t, None, "overtime", 7)
        elif e.kind == "escalation" and "SPEED" in str(e.data.get("banner", "")):
            add_react(t, e.t, None, "speed", 5)
        elif e.kind == "twist":
            tw_str = e.data.get("twist", "").replace("_", " ")
            add_react(t, e.t, None, "twist", 6, {"twist": tw_str, "twist_cap": tw_str.capitalize()})
        elif e.kind == "trait" and f"trait_{e.data.get('name')}" in TEMPLATES:
            ak = e.actors[0] if e.actors else ""
            add_react(t, e.t, e.pos, f"trait_{e.data.get('name')}", 4,
                      {"name": _name(ak), "actor_key": ak, "lore": HERO_LORE.get(ak, "")})
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5:
            ak = e.actors[0] if e.actors else ""
            add_react(t, e.t, e.pos, "lead", 4, {"name": _name(ak), "actor_key": ak})

    pre = tr.meta.get("preroll_frames", 0)
    said3 = said2 = False
    for f in range(pre, r.end_f + 1, 3):
        alive = [tr.keys[k] for k in range(len(tr.keys)) if tr.flags[f][k] & 1]
        gp_t = (f - pre) / 30.0
        t = to_out(gp_t)
        if len(alive) == 3 and not said3 and n_total > 4:
            said3 = True
            add_react(t, gp_t, None, "final3", 6, {"a": _name(alive[0]), "b": _name(alive[1]), "c": _name(alive[2])})
        if len(alive) == 2 and not said2 and tr.mode == "TOP_DOWN":
            said2 = True
            add_react(t, gp_t, None, "final2", 7, {"a": _name(alive[0]), "b": _name(alive[1])})

    # 2. Multi-KO Finale Detection (Part A.2): >= 2 finalists eliminated within 0.8s of match end!
    end_gp_t = float(tr.meta.get("resolved_at") or (r.end_f - pre) / 30.0)
    finale_kos = [e for e in elims if (end_gp_t - 0.80) <= e.t <= (end_gp_t + 0.08)]
    w_key = tr.meta.get("winner") or ""
    winner = _name(w_key)
    win_t = max(replay_t + 0.05, card_t - 0.40)

    if stage == "grand_final":
        win_kind = "winner_champion"
        win_max_w = 7
    elif len(finale_kos) >= 3:
        win_kind = "multi_ko_3"
        win_max_w = 6
    elif len(finale_kos) == 2:
        win_kind = "multi_ko_2"
        win_max_w = 6
    elif league_ctx.get("lead_changed"):
        win_kind = "winner_new_leader"
        win_max_w = 7
    else:
        win_kind = "winner"
        win_max_w = 5

    beats.append(Beat(
        win_t,
        win_kind,
        10,
        {
            "winner": winner,
            "winner_key": w_key,
            "lore": HERO_LORE.get(w_key, ""),
            "season": season_num,
            "multi_ko_count": len(finale_kos),
        },
        max_words=win_max_w,
        event_t=win_t,
    ))

    # 3. Tight 7-10 word Outro CTA (synthesized natively at 1.0x pitch/rate, never resampled!)
    outro_kind = "outro_final" if stage == "grand_final" else "outro"
    beats.append(Beat(
        card_t + 0.55,
        outro_kind,
        10,
        {
            "a": prompt_pair[0],
            "b": prompt_pair[1],
            "season": season_num,
            "next_season": season_num + 1,
        },
        max_words=8,
        event_t=card_t + 0.55,
    ))

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
        if b.kind.startswith(("winner", "multi_ko")):
            b.max_words = win_max_w
            continue
        if b.kind.startswith("outro"):
            b.max_words = 8   # strictly 7-9 words max
            continue
        nxt = next((o.t for o in beats[k + 1:] if o.prio >= b.prio and o.t > b.t + 0.15), card_t - 0.45)
        b.max_words = int(max(4, min(7, (nxt - b.t - 0.14) * WORDS_PER_S)))

    rng = random.Random(int(tr.meta.get("seed", 0)) ^ hash(tr.meta["recipe"]["arena"]))
    used: set[str] = set()
    for b in beats:
        b.text = _pick_template(b, rng, used)
    return beats


_SAFE = re.compile(r"^[A-Za-z0-9 ,.!?'\-:]+$")


def _valid_llm_line(b: Beat, ln: str) -> bool:
    low = f" {ln.lower()} "
    words = ln.split()
    max_allow = 9 if b.kind.startswith("outro") else (b.max_words + 1)
    if not (2 <= len(words) <= max_allow) or not _SAFE.match(ln):
        return False
    if any(p in low for p in BANNED_PHRASES):
        return False
    if _STIFF_DOUBLE_ADJ.search(ln):
        return False
    # Enforce strict character-accurate lore
    mentioned_keys = {k for k, h in HERO_BY_KEY.items() if h.name.lower() in low}
    if "bowling" in low and "bonk" not in mentioned_keys:
        return False
    if ("wrecking cube" in low or "iron cube" in low) and "juggernaut" not in mentioned_keys:
        return False
    if "helium" in low and "floater" not in mentioned_keys:
        return False
    if "ice puck" in low and "dash" not in mentioned_keys:
        return False
    if b.kind.startswith("intro"):
        # Never allow LLM to hallucinate "Fifteen" when cast size != 15!
        cnt = int(b.ctx.get("count", 14))
        for n_num, w_num in NUMBER_WORDS.items():
            if n_num != cnt and f" {w_num.lower()} " in low:
                return False
    if b.kind.startswith(("winner", "multi_ko")) and b.ctx.get("winner", "").lower() not in low:
        return False
    if b.kind == "multi_ko_2" and "double" not in low and "wipeout" not in low:
        return False
    if b.kind == "multi_ko_3" and "triple" not in low and "wipeout" not in low:
        return False
    if b.kind == "outro":
        a, bb = b.ctx.get("a", "").lower(), b.ctx.get("b", "").lower()
        if a not in low or bb not in low or len(words) > 9:
            return False
    if b.kind == "outro_final" and len(words) > 9:
        return False
    return True


def _gemini_http(url: str, key: str, payload: dict | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    """Bounded-timeout HTTPS call to Gemini v1beta API using x-goog-api-key header (never in URL)."""
    import urllib.error
    import urllib.request

    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            body = {"error": {"message": str(e)}}
        return e.code, body
    except Exception as exc:
        return 0, {"error": {"message": f"{type(exc).__name__}: {exc}"}}


def punch_up(beats: list[Beat], league_ctx: dict | None = None, log=print) -> int:
    """Rewrite lines with Gemini Flash (v1beta, strict 8s timeout, dynamic Flash model discovery).
    Enforces natural Fall Guys / Wipeout caster voice, contractions, exact cast counts, and lore accuracy."""
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        log("  gemini skipped: GOOGLE_API_KEY is empty/unset; using lore-accurate templates")
        return 0
    if not beats:
        return 0

    lore_ref = "; ".join(f"{HERO_BY_KEY[k].name} = {desc}" for k, desc in HERO_LORE.items())
    stakes_note = ""
    if league_ctx:
        stakes_note = (
            f"SEASON CONTEXT: Season {league_ctx.get('season_number', 1)} Race {league_ctx.get('episode_number', 1)}/30 "
            f"(stage={league_ctx.get('stage', 'league')}, leader={league_ctx.get('current_leader_name', '')}, "
            f"gap={league_ctx.get('points_gap', 0)} pts, races_left={league_ctx.get('races_remaining', 0)}, "
            f"lead_changed={league_ctx.get('lead_changed', False)}).\n"
        )
    facts = [{"i": i, "event": b.kind, "facts": b.ctx, "max_words": b.max_words, "draft": b.text}
             for i, b in enumerate(beats)]
    prompt = (
        "You are MC Tuno, a sharp, natural, hyper-energetic Fall Guys / Wipeout live sports caster for Toon Toon Castle "
        "(YouTube Shorts). Use crisp contractions and punchy natural calls (e.g. \"Gravity's off-good luck!\", "
        "\"Juggernaut just deleted Pip!\").\n"
        "STRICT VOICE BANS:\n"
        "- NEVER say 'I see...', 'I am...', or 'Lord Tuno'.\n"
        "- NEVER write stiff '[Adjective] [Hero] [verb] [Adjective] [Hero]' sentences.\n"
        "- NEVER say 'Friendship over!', 'What a champion!', 'Who survives?', or wrong contestant counts (use exact facts.count_word!).\n"
        f"STRICT CHARACTER LORE: {lore_ref}.\n"
        f"{stakes_note}"
        "RULES PER BEAT:\n"
        "- Stay strictly <= max_words words.\n"
        "- For 'multi_ko_2'/'multi_ko_3': call 'DOUBLE WIPEOUT! [Winner] steals it!' or 'TRIPLE WIPEOUT! [Winner] steals it!'.\n"
        "- For 'outro': 6 to 8 words MAX, MUST include BOTH facts.a and facts.b asking viewers to comment their pick.\n"
        "- Plain ASCII letters/punctuation only (no emojis, no hashtags, no quotes).\n"
        "Return ONLY a JSON array of strings, exact same length and order as input.\n\n"
        + json.dumps(facts)
    )

    base = "https://generativelanguage.googleapis.com/v1beta"
    st_list, m_body = _gemini_http(f"{base}/models?pageSize=100", key, timeout=5.0)
    candidates: list[str] = []
    if st_list == 200:
        for item in m_body.get("models", []):
            mname = str(item.get("name", "")).replace("models/", "")
            low_m = mname.lower()
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            if "flash" in low_m and all(sk not in low_m for sk in ("tts", "image", "audio", "live", "thinking", "8b")):
                candidates.append(mname)
        candidates.sort(key=lambda s: ("lite" not in s, "3" not in s and "latest" not in s, s))
    if not candidates:
        candidates = ["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview", "gemini-2.5-flash"]

    lines = None
    used_model = ""
    for model in candidates[:4]:
        gen_cfg: dict = {"responseMimeType": "application/json", "temperature": 0.82}
        if model.startswith(("gemini-2.5", "gemini-3")):
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
        code, body = _gemini_http(f"{base}/models/{model}:generateContent", key, payload=payload, timeout=9.0)
        if code != 200 and "thinkingConfig" in str(body):
            gen_cfg.pop("thinkingConfig", None)
            code, body = _gemini_http(f"{base}/models/{model}:generateContent", key, payload=payload, timeout=9.0)
        if code == 200:
            try:
                parts = body["candidates"][0]["content"]["parts"]
                raw = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
                lines = json.loads(raw or "[]")
                used_model = model
                break
            except Exception as exc:
                log(f"  gemini {model} parse error ({type(exc).__name__})")
        else:
            err_msg = str(body.get("error", {}).get("message", body))
            err_msg = re.sub(r"AIza[0-9A-Za-z_\-]+", "[REDACTED]", err_msg)[:110]
            log(f"  gemini {model} HTTP {code}: {err_msg}")
            if code in (400, 401, 403) and "API_KEY" in err_msg.upper():
                break

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
