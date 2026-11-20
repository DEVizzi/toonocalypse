"""v4.2 MC Tuno comedy engine — unhinged Takeshi's Castle / Ozzy Man energy.

- 110+ punchy offline lines (5-9 words) grouped into template FAMILIES with stable line IDs (`family:index`).
- Never reuses a family twice in one episode; rolling 7-day line-ID cooldown (ids persisted in episode_history.json).
- Strict alive + on-camera verification for every KO/collision call (victim alive just before t, killer alive at t,
  both inside the viewport +40 px).
- Per-beat prosody style: `hype` (KO/betrayal/climax/winner), `deadpan` (self-KO/dummy roast), `normal` (intro/filler).
- Hard bans: raw character metadata, "I see/I am", "Zero room for error", "Pure chaos in the pack",
  "Double wipeout! X steals it!", "Down to N, who blinks first?".
- Single source of truth: winner/leader lines read the league outcome snapshot passed in `league_ctx`.
- Live LLM punch-up (Gemini Flash, optional Groq) with LOUD status logging — never a silent fallback."""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field

from src.characters.roster import HERO_BY_KEY

WORDS_PER_S = 3.2
FPS_ = 30.0

NUMBER_WORDS: dict[int, str] = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
    9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen",
    15: "Fifteen", 16: "Sixteen",
}

# Reference only for the LLM prompt (NEVER placed into beat facts and NEVER spoken verbatim)
HERO_LORE: dict[str, str] = {
    "bonk": "heavy bowling ball", "juggernaut": "iron wrecking cube (not a bowling ball)",
    "boing": "rubber pinball", "dash": "brakeless ice puck", "floater": "helium beach ball",
    "glitch": "laggy glitchy ball", "grumble": "grumpy velcro ball", "magneto": "magnetic hex bolt",
    "pip": "tiny ping-pong ball", "sly": "sneaky cue ball",
}

# ---------------------------------------------------------------------------------------------- offline line bank
BANK: dict[str, list[str]] = {
    # Elemental roasts (victim's own flavour; deadpan)
    "roast.glitch": ["Glitch's Wi-Fi just died mid-air!", "Glitch lagged straight out of existence!"],
    "roast.floater": ["Floater's ignoring gravity like it's rent day!", "Floater just drifted into early retirement!"],
    "roast.dash": ["Dash has zero brakes and zero braincells!", "Dash forgot corners were a thing!"],
    "roast.bonk": ["Bonk sank like a dropped fridge!", "Bonk just bowled himself into the bin!"],
    "roast.boing": ["Boing bounced clean out of the postcode!", "Boing pinballed straight into the void!"],
    "roast.juggernaut": ["Juggernaut tripped over his own ego!", "The big fella finally ran out of floor!"],
    "roast.grumble": ["Grumble's too angry to... oh, he fell.", "Grumble's sulking all the way down!"],
    "roast.magneto": ["Magneto's magnets just filed for divorce!", "Nothing to stick to down there, Magneto!"],
    "roast.pip": ["Pip got sent into next Tuesday!", "Pip's gone—somebody fetch a butterfly net!"],
    "roast.sly": ["Sly's big-brain plan just scratched!", "Sly calculated everything except falling!"],
    # Killer flavour lines (hype)
    "kill.bonk": ["Bonk just parked a bowling ball on {B}'s dreams!", "Bonk flattened {B} like a pancake!"],
    "kill.boing": ["Boing's playing pinball with {B}'s face!", "Boing ricocheted {B} into next week!"],
    "kill.juggernaut": ["Juggernaut didn't dodge—he just paved through {B}!", "Juggernaut bulldozed {B}, zero apologies!"],
    "kill.dash": ["Dash skated straight through {B}, no brakes!", "Dash body-checked {B} into orbit!"],
    "kill.floater": ["Floater floated over and booted {B}!", "Sneaky Floater just nudged {B} off!"],
    "kill.glitch": ["Glitch phased through {B}—hacker behaviour!", "Glitch deleted {B} mid-frame!"],
    "kill.grumble": ["Grumble dragged {B} down out of spite!", "Grumble chose violence against {B}!"],
    "kill.magneto": ["Magneto yeeted {B} with pure magnetism!", "Magneto repelled {B} straight off the map!"],
    "kill.pip": ["Tiny Pip just evicted {B}! Outrageous!", "Pip's punching above weight—bye, {B}!"],
    "kill.sly": ["Sly banked {B} into the corner pocket!", "Cheeky Sly hustled {B} right off!"],
    # Petty drama & betrayals (hype)
    "drama": [
        "Personal beef alert—{A} meant that shove!", "Friendship cancelled, {A} just mugged {B}!",
        "That wasn't racing, {A}, that was a felony!", "{A} sent {B} a one-way ticket!",
        "Cold-blooded! {A} just binned {B}!", "{B} trusted {A}. Big mistake.",
    ],
    # Unhinged booth host (deadpan)
    "host": [
        "Oops, leaned on the chaos button—my bad!", "Half the cast is toast already, love it!",
        "Somebody check {B}'s pulse!", "Insurance won't cover that one, {B}!",
        "And {B} has officially left the building!", "Ooh, {B} felt that in their soul!",
        "Gravity: undefeated. {B}: very defeated.",
    ],
    "host_dummy": ["A crash dummy outlasted {B}. Brutal.", "Even the dummies are beating {B}. Tragic."],
    # Dummy roasts (deadpan)
    "dummy": [
        "Crash dummy down—doing its one job!", "That dummy took one for the team!",
        "Dummy deployed... and immediately destroyed.", "Crash test result: absolutely not.",
        "RIP dummy, you were mostly useless.",
    ],
    "first_hero": ["First blood! {B}'s already packing up!", "{B} out first—that's embarrassing, mate!",
                   "Speedrun elimination from {B}! Wow!"],
    "torched": ["{B} got toasted like cheap bread!", "Too slow, {B}—extra crispy now!",
                "The wall ate {B} for lunch!", "{B} just became a campfire snack!"],
    "multi": ["Bodies everywhere! Call the cleaners!", "Bowling alley carnage—strike, strike, strike!",
              "Mass exodus! Half the pack evaporated!"],
    "speed": ["Speeding up—hold onto your eyebrows!", "Turbo button pressed. Zero regrets."],
    "overtime": ["Overtime! I've deleted every safety rule!", "Sudden death—someone's crying tonight!"],
    "twist": ["Flipping on {twist}—good luck, idiots!", "Twist time! {twist_cap} incoming!"],
    "final3": ["Three left, one crown, zero friends!", "Final three: {a}, {b}, {c}—fight!"],
    "final2": ["{a} versus {b}—only one survives this!", "Last two standing—{a} or {b}?"],
    "lead": ["{name} just snatched first place!", "{name} storms to the front!"],
    "trait": ["{name} is showing off now!", "Look at {name} doing absolute nonsense!"],
    # Openers (~1.4 s, spoken over the live starting gate)
    "intro": ["{L}'s clinging to first, {R} wants blood!", "{L} leads, {R} is hunting—drop 'em!",
              "{R}'s chasing {L}'s crown—gates up!", "Title on the line—{L} versus {R}!"],
    "intro_playoff": ["Playoffs! Lose here and you're done!", "Knockout time—no second chances, drop 'em!"],
    "intro_final": ["Grand Final! One trophy, three lunatics!", "Season decider! Somebody's going home crying!"],
    # Winner (hype)
    "winner": ["{winner} takes it! Absolute scenes!", "{winner} wins! Somebody frame that!",
               "{winner} survives the madness and wins!"],
    "winner_lead_self": ["{winner} wins and steals first place!", "{winner} wins—and takes the season lead!"],
    "winner_lead_other": ["{winner} wins, {leader} grabs top spot!"],
    "winner_champion": ["{winner} is your Season {season} Champion!", "Crown them! {winner} wins Season {season}!"],
    "winner_carnage": ["Last-second carnage—{winner} walks away!", "Everyone else exploded—{winner} wins!"],
    # Outro CTA (<= 9 words)
    "outro": ["{a} or {b} next? Comment below!", "{a} or {b} tomorrow? Pick one!", "Team {a} or Team {b}? Comment!"],
    "outro_final": ["Season {next_season} starts tomorrow—who's your pick?"],
    # Title-race suspense fillers (normal)
    "filler": [
        "Nobody's blinking—points leader's sweating!", "One shove changes the whole season!",
        "Sweaty palms in the booth right now!", "This is getting properly spicy!",
        "Somebody's about to get absolutely binned!", "I can't watch... okay, I'm watching!",
    ],
    "filler_lead": ["{L}'s title lead is on the line!", "{L} needs this one badly!"],
    "filler_disc": ["Disc is the size of a coaster now!", "That floor's shrinking like cheap jeans!"],
}

FAMILY_STYLE_PREFIX: list[tuple[str, str]] = [
    ("kill.", "hype"), ("drama", "hype"), ("multi", "hype"), ("winner", "hype"), ("overtime", "hype"),
    ("final", "hype"), ("torched", "hype"), ("intro", "hype"), ("first_hero", "hype"),
    ("roast.", "deadpan"), ("host", "deadpan"), ("dummy", "deadpan"),
]


def family_style(family: str) -> str:
    for pref, sty in FAMILY_STYLE_PREFIX:
        if family.startswith(pref):
            return sty
    return "normal"


def bank_size() -> int:
    return sum(len(v) for v in BANK.values())


BANNED_PHRASES = (
    "friendship over", "what a champion", "who survives", "lord tuno", "i see ", "i am ",
    "zero room for error", "pure chaos in the pack", "double wipeout", "who blinks first",
    # raw character metadata leaks
    "heavy orange", "orange bowling ball", "cast-iron", "wrecking cube", "helium beach ball", "frictionless",
    "velcro ball", "hex bolt", "ping-pong ball", "cue ball", "rubber pinball", "corrupted-physics", "packet loss",
)
_DOWN_TO_N = re.compile(r"\bdown to (two|three|four|five|six|\d+)\b", re.IGNORECASE)
_HERO_ALT = "|".join(HERO_BY_KEY.keys())
# v4.2 fact-lock: winner lines must state the league lead truthfully (LLM once said "keeps his lead" on a lead change)
_LEAD_WORD = re.compile(r"\b(lead|leads|leader|top|table|summit|first|throne|number one)\b", re.IGNORECASE)
_LEAD_STAY = re.compile(r"\b(keeps?|kept|stays?|still|holds?|held|remains?|retains?|clings?|safe)\b", re.IGNORECASE)
_LEAD_CLAIM = re.compile(r"\b(new (league |season )?leader|takes? (over )?the (season |league )?lead|grabs? (the )?(lead|top)|"
                         r"top spot|top of the table|first place|steals? (the )?lead|seizes?|dethron\w*|throne)\b",
                         re.IGNORECASE)
_STIFF_DOUBLE_ADJ = re.compile(rf"\b[a-z\-]+\s+({_HERO_ALT})\s+[a-z\-]+\s+[a-z\-]+\s+({_HERO_ALT})\b", re.IGNORECASE)

ARENA_NAMES = {
    "rotating_disc": "Rotating Disc", "ramp_descent": "Ramp Descent", "pachinko_drop": "Pachinko Drop",
    "sumo_pool_pit": "Sumo Pool Pit", "crumbling_bridge": "Crumbling Bridge", "collapse_tower": "Collapse Tower",
    "crusher_gauntlet": "Crusher Gauntlet",
}


@dataclass
class Beat:
    t: float
    kind: str
    prio: int
    ctx: dict = field(default_factory=dict)
    max_words: int = 8
    text: str = ""
    event_t: float = 0.0
    families: list[str] = field(default_factory=list)   # candidate families (in priority order)
    family: str = ""
    line_id: str = ""
    style: str = "normal"


def _name(key: str | None) -> str:
    if not key:
        return "Somebody"
    h = HERO_BY_KEY.get(key)
    return h.name if h else "a dummy"


class Picker:
    """Per-episode template picker: one use per family, 7-day line-ID cooldown, deterministic per seed."""

    def __init__(self, rng: random.Random, recent_ids: set[str] | None = None) -> None:
        self.rng = rng
        self.recent = set(recent_ids or ())
        self.used_families: set[str] = set()
        self.used_ids: list[str] = []
        self.used_text: set[str] = set()

    def pick(self, families: list[str], ctx: dict, max_words: int = 9) -> tuple[str, str, str] | None:
        for fam in families:
            if fam in self.used_families or fam not in BANK:
                continue
            opts = []
            for i, tpl in enumerate(BANK[fam]):
                lid = f"{fam}:{i}"
                try:
                    txt = tpl.format(**ctx)
                except (KeyError, IndexError):
                    continue
                if txt in self.used_text or len(txt.split()) > max(max_words, 9):
                    continue
                opts.append((lid in self.recent, lid, txt))
            if not opts:
                continue
            fresh = [o for o in opts if not o[0]] or opts      # honour 7-day cooldown when possible
            _, lid, txt = self.rng.choice(fresh)
            self.used_families.add(fam)
            self.used_ids.append(lid)
            self.used_text.add(txt)
            return fam, lid, txt
        return None


def _frame_of(r, gameplay_t: float) -> int:
    return min(r.tr.n_frames - 1, max(0, r.pre + int(round(gameplay_t * FPS_))))


def _alive(r, key: str, fi: int) -> bool:
    try:
        return bool(r.tr.flags[fi][r.tr.index(key)] & 1)
    except (ValueError, IndexError):
        return False


def _pos(r, key: str, fi: int) -> tuple[float, float] | None:
    try:
        row = r.tr.frames[fi][r.tr.index(key)]
        return float(row[0]), float(row[1])
    except (ValueError, IndexError):
        return None


def _on_camera(r, gameplay_t: float, pos, pad: float = 40.0) -> bool:
    if pos is None:
        return True
    fi = _frame_of(r, gameplay_t)
    return bool(r.cams[fi].on_screen(float(pos[0]), float(pos[1]), pad=pad))


def verify_ko(r, e) -> bool:
    """Victim alive right before t, killer (if any) alive at t, and both inside the viewport (+40 px) at t."""
    fi = _frame_of(r, e.t)
    victim = e.actors[0] if e.actors else None
    if victim is None or not _alive(r, victim, max(0, fi - 1)):
        return False
    if not _on_camera(r, e.t, e.pos):
        return False
    if len(e.actors) > 1:
        killer = e.actors[1]
        if not _alive(r, killer, fi):
            return False
        if not _on_camera(r, e.t, _pos(r, killer, fi)):
            return False
    return True


def pick_filler(r, gameplay_t: float, picker: Picker, league_ctx: dict | None = None) -> Beat | None:
    """Title-race suspense filler for any >= 3.0 s silent stretch."""
    league_ctx = league_ctx or {}
    fams = []
    if league_ctx.get("pre_leader_name") and int(league_ctx.get("points_gap", 99)) <= 14:
        fams.append("filler_lead")
    if r.tr.mode == "TOP_DOWN" and gameplay_t > 8.0:
        fams.append("filler_disc")
    fams.append("filler")
    ctx = {"L": league_ctx.get("pre_leader_name") or "The leader"}
    got = picker.pick(fams, ctx, max_words=7)
    if got is None:
        return None
    fam, lid, txt = got
    return Beat(gameplay_t, "filler", 3, ctx, 7, txt, gameplay_t, fams, fam, lid, family_style(fam))


def build_beats(r, to_out, video_len: float, replay_t: float, card_t: float, prompt_pair: tuple[str, str],
                league_ctx: dict | None = None, picker: Picker | None = None) -> list[Beat]:
    tr = r.tr
    league_ctx = league_ctx or getattr(r.ep, "league_ctx", None) or {}
    ev = sorted(tr.events, key=lambda e: e.t)
    stage = str(league_ctx.get("stage") or "league")
    season_num = int(league_ctx.get("season_number") or 1)
    beats: list[Beat] = []

    def add(t_out, kind: str, prio: int, families: list[str], ctx: dict, event_t: float | None = None, mw: int = 8):
        beats.append(Beat(t_out, kind, prio, ctx, mw, "", event_t if event_t is not None else t_out, families))

    # 1. Opener over the live starting gate (~1.4 s)
    L = league_ctx.get("pre_leader_name") or "The leader"
    R = league_ctx.get("rival_name") or "the pack"
    intro_fams = ["intro_final"] if stage == "grand_final" else (["intro_playoff"] if stage != "league" else ["intro"])
    add(0.04, "intro", 10, intro_fams, {"L": L, "R": R, "count": len(tr.keys)}, 0.04, mw=8)

    react_cutoff = card_t - 1.45
    LEAD_IN = 0.15

    def react(gp_t: float, kind: str, prio: int, families: list[str], ctx: dict) -> None:
        t_out = to_out(gp_t)
        if t_out is None or t_out > react_cutoff or t_out < 1.0:
            return
        add(max(1.0, t_out - LEAD_IN), kind, prio, families, ctx, t_out)

    elims = [e for e in ev if e.kind == "elimination"]
    first_done = False
    for e in elims:
        if not verify_ko(r, e):
            continue
        vk = e.actors[0]
        fi = _frame_of(r, e.t)
        ctx = {"B": _name(vk)}
        if not e.data.get("hero"):
            if not first_done:
                react(e.t, "dummy", 6, ["dummy"], ctx)
                first_done = True
            continue
        if not first_done:
            react(e.t, "first_hero", 7, ["first_hero", f"roast.{vk}"], ctx)
            first_done = True
            continue
        if e.data.get("by_hero") and len(e.actors) > 1:
            kk = e.actors[1]
            ctx.update(A=_name(kk))
            react(e.t, "betrayal", 8, [f"kill.{kk}", "drama"], ctx)
        elif e.data.get("cause") == "left_behind":
            react(e.t, "torched", 5, ["torched", f"roast.{vk}"], ctx)
        else:
            dummies_alive = any(not k in HERO_BY_KEY and _alive(r, k, fi) for k in tr.keys)
            fams = [f"roast.{vk}"] + (["host_dummy"] if dummies_alive else []) + ["host"]
            react(e.t, "hero_fall", 4, fams, ctx)

    # Multi-KO bursts (>= 3 verified, on-camera KOs within 1.2 s)
    ok_elims = [e for e in elims if verify_ko(r, e)]
    i = 0
    while i < len(ok_elims):
        j = i
        while j < len(ok_elims) and ok_elims[j].t - ok_elims[i].t <= 1.2:
            j += 1
        if j - i >= 3:
            react(ok_elims[j - 1].t, "multi", 7, ["multi"], {})
            i = j
        else:
            i += 1

    for e in ev:
        if e.kind == "escalation" and e.data.get("overtime"):
            react(e.t, "overtime", 7, ["overtime"], {})
        elif e.kind == "escalation" and "SPEED" in str(e.data.get("banner", "")):
            react(e.t, "speed", 5, ["speed"], {})
        elif e.kind == "twist":
            tw = e.data.get("twist", "").replace("_", " ")
            react(e.t, "twist", 6, ["twist"], {"twist": tw, "twist_cap": tw.capitalize()})
        elif e.kind == "trait" and e.actors:
            ak = e.actors[0]
            fi = _frame_of(r, e.t)
            if ak in HERO_BY_KEY and _alive(r, ak, fi) and _on_camera(r, e.t, e.pos):
                react(e.t, "trait", 3, ["trait"], {"name": _name(ak)})
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5 and e.actors:
            ak = e.actors[0]
            fi = _frame_of(r, e.t)
            if ak in HERO_BY_KEY and _alive(r, ak, fi) and _on_camera(r, e.t, e.pos):
                react(e.t, "lead", 4, ["lead"], {"name": _name(ak)})

    pre = tr.meta.get("preroll_frames", 0)
    said3 = said2 = False
    for f in range(pre, r.end_f + 1, 3):
        alive = [k for k in tr.keys if _alive(r, k, f) and k in HERO_BY_KEY]
        gp_t = (f - pre) / FPS_
        if len(alive) == 3 and not said3 and len(tr.keys) > 4:
            said3 = True
            react(gp_t, "final3", 6, ["final3"], {"a": _name(alive[0]), "b": _name(alive[1]), "c": _name(alive[2])})
        if len(alive) == 2 and not said2 and tr.mode == "TOP_DOWN":
            said2 = True
            react(gp_t, "final2", 7, ["final2"], {"a": _name(alive[0]), "b": _name(alive[1])})

    # 2. Winner call — reads ONLY the league outcome snapshot (single source of truth)
    w_key = tr.meta.get("winner") or ""
    winner = _name(w_key)
    end_gp_t = float(tr.meta.get("resolved_at") or (r.end_f - pre) / FPS_)
    finale_kos = [e for e in elims if (end_gp_t - 0.80) <= e.t <= (end_gp_t + 0.08)]
    leader_name = league_ctx.get("current_leader_name") or winner
    if stage == "grand_final":
        wf = ["winner_champion"]
    elif league_ctx.get("lead_changed"):
        wf = ["winner_lead_self"] if league_ctx.get("current_leader") == w_key else ["winner_lead_other"]
    elif len(finale_kos) >= 2:
        wf = ["winner_carnage", "winner"]
    else:
        wf = ["winner"]
    win_t = max(replay_t + 0.05, card_t - 0.40)
    add(win_t, "winner", 10, wf, {"winner": winner, "leader": leader_name, "season": season_num}, win_t, mw=8)

    # 3. Outro CTA (<= 9 words)
    of = ["outro_final"] if stage == "grand_final" else ["outro"]
    add(card_t + 0.55, "outro", 10, of, {"a": prompt_pair[0], "b": prompt_pair[1], "next_season": season_num + 1},
        card_t + 0.55, mw=9)

    # Thin out: >= 1.55 s apart; same kind >= 4.0 s apart
    kept: list[Beat] = []
    for b in sorted(beats, key=lambda b: (-b.prio, b.t)):
        if b.prio >= 10 or (all(abs(b.t - o.t) >= 1.55 for o in kept)
                            and all(not (o.kind == b.kind and abs(b.t - o.t) < 4.0) for o in kept)):
            kept.append(b)
    kept.sort(key=lambda b: b.t)

    for k, b in enumerate(kept):
        if b.prio < 10:
            nxt = next((o.t for o in kept[k + 1:] if o.prio >= b.prio and o.t > b.t + 0.15), card_t - 0.45)
            b.max_words = int(max(5, min(9, (nxt - b.t - 0.14) * WORDS_PER_S)))

    rng = random.Random(int(tr.meta.get("seed", 0)) * 7919 + len(tr.events))
    pk = picker or Picker(rng, set(league_ctx.get("recent_line_ids") or ()))
    out: list[Beat] = []
    for b in sorted(kept, key=lambda b: (-b.prio, b.t)):
        got = pk.pick(b.families, b.ctx, b.max_words)
        if got is None:
            continue
        b.family, b.line_id, b.text = got
        b.style = family_style(b.family)
        out.append(b)
    out.sort(key=lambda b: b.t)
    r._picker = pk
    return out


_SAFE = re.compile(r"^[A-Za-z0-9 ,.!?'\-:—]+$")


def _valid_llm_line(b: Beat, ln: str) -> bool:
    low = f" {ln.lower()} "
    words = ln.split()
    max_allow = 9 if b.kind.startswith("outro") else (b.max_words + 1)
    if not (2 <= len(words) <= max_allow) or not _SAFE.match(ln):
        return False
    if any(p in low for p in BANNED_PHRASES) or _DOWN_TO_N.search(ln) or _STIFF_DOUBLE_ADJ.search(ln):
        return False
    mentioned = {k for k, h in HERO_BY_KEY.items() if h.name.lower() in low}
    if "bowling" in low and "bonk" not in mentioned:
        return False
    if "helium" in low and "floater" not in mentioned:
        return False
    if b.kind.startswith("intro"):
        cnt = int(b.ctx.get("count", 14))
        for n_num, w_num in NUMBER_WORDS.items():
            if n_num != cnt and f" {w_num.lower()} " in low:
                return False
    if b.kind.startswith(("winner", "multi_ko")) and b.ctx.get("winner", "").lower() not in low:
        return False
    if b.kind == "winner" and b.family == "winner_lead_other" and b.ctx.get("leader", "").lower() not in low:
        return False
    if b.kind == "winner" and b.family in ("winner_lead_self", "winner_lead_other"):
        if not _LEAD_WORD.search(ln) or _LEAD_STAY.search(ln):
            return False
    elif b.kind == "winner" and b.family != "winner_champion" and _LEAD_CLAIM.search(ln):
        return False
    if b.kind == "outro":
        a, bb = b.ctx.get("a", "").lower(), b.ctx.get("b", "").lower()
        if (a and a not in low) or (bb and bb not in low):
            return False
    return True


def _http_json(url: str, headers: dict, payload: dict | None, timeout: float) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"},
                                 method="POST" if data is not None else "GET")
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


def _gemini_http(url: str, key: str, payload: dict | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    """Bounded-timeout Gemini v1beta call (key in x-goog-api-key header, never in the URL)."""
    return _http_json(url, {"x-goog-api-key": key}, payload, timeout)


def _prompt(beats: list[Beat], league_ctx: dict | None) -> str:
    lore_ref = "; ".join(f"{HERO_BY_KEY[k].name}: {d}" for k, d in HERO_LORE.items())
    facts = [{"i": i, "event": b.kind, "facts": {k: v for k, v in b.ctx.items() if k != "count"},
              "max_words": b.max_words, "draft": b.text} for i, b in enumerate(beats)]
    stakes = ""
    if league_ctx:
        stakes = (f"Season {league_ctx.get('season_number')} race {league_ctx.get('episode_number')}/30, "
                  f"stage {league_ctx.get('stage')}, leader after race {league_ctx.get('current_leader_name')}. "
                  + ("The season lead CHANGED HANDS this race: the winner line must say "
                     f"{league_ctx.get('current_leader_name')} TAKES the lead (never 'keeps'/'still').\n"
                     if league_ctx.get("lead_changed") else
                     "The season lead did NOT change: never claim a new leader.\n"))
    return (
        "You are MC Tuno, an unhinged Takeshi's Castle / Ozzy Man Reviews style booth caster for a cartoon ball-race "
        "YouTube Short. Rewrite each draft to be FUNNIER: cheeky, punchy, roasty, 5-9 words, contractions, "
        "pub-banter energy.\n"
        f"Characters (for vibe only, NEVER describe them literally): {lore_ref}.\n{stakes}"
        "HARD BANS: never describe a character's material/colour/shape; never say 'I see', 'I am', 'zero room for "
        "error', 'pure chaos in the pack', 'double wipeout', 'who blinks first', 'down to N', 'Lord Tuno'.\n"
        "Keep every name from facts EXACTLY as given. 'winner' lines must name facts.winner. 'outro' lines must "
        "name BOTH facts.a and facts.b and ask viewers to comment. Plain ASCII punctuation only, no emojis.\n"
        "Return ONLY a JSON array of strings, same length and order as input.\n\n" + json.dumps(facts)
    )


def _parse_lines(raw: str) -> list | None:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
    try:
        out = json.loads(raw or "[]")
        if isinstance(out, dict):
            out = next((v for v in out.values() if isinstance(v, list)), None)
        return out if isinstance(out, list) else None
    except Exception:
        return None


def punch_up(beats: list[Beat], league_ctx: dict | None = None, log=print) -> int:
    """Live LLM punch-up. Logs status LOUDLY: `[LLM LIVE]` on success, `[LLM WARNING]` on any fallback."""
    if not beats:
        return 0
    prompt = _prompt(beats, league_ctx)
    lines, used = None, ""
    gkey = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if gkey:
        base = "https://generativelanguage.googleapis.com/v1beta"
        st, body = _gemini_http(f"{base}/models?pageSize=100", gkey, timeout=5.0)
        cands = []
        if st == 200:
            for item in body.get("models", []):
                mname = str(item.get("name", "")).replace("models/", "")
                lm = mname.lower()
                if "generateContent" in (item.get("supportedGenerationMethods") or []) and "flash" in lm and \
                        all(x not in lm for x in ("tts", "image", "audio", "live", "thinking", "8b")):
                    cands.append(mname)
            cands.sort(key=lambda s: ("lite" not in s, "3" not in s and "latest" not in s, s))
        else:
            log(f"  [LLM WARNING] Gemini model list HTTP {st}")
        for model in (cands or ["gemini-2.5-flash-lite", "gemini-2.5-flash"])[:4]:
            cfg: dict = {"responseMimeType": "application/json", "temperature": 0.95}
            if model.startswith(("gemini-2.5", "gemini-3")):
                cfg["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
            code, body = _gemini_http(f"{base}/models/{model}:generateContent", gkey, payload, 9.0)
            if code != 200 and "thinkingConfig" in str(body):
                cfg.pop("thinkingConfig", None)
                code, body = _gemini_http(f"{base}/models/{model}:generateContent", gkey, payload, 9.0)
            if code == 200:
                try:
                    parts = body["candidates"][0]["content"]["parts"]
                    lines = _parse_lines("".join(p.get("text", "") for p in parts if not p.get("thought")))
                    used = f"gemini/{model}"
                    if lines is not None:
                        break
                except Exception as exc:
                    log(f"  [LLM WARNING] Gemini {model} parse error ({type(exc).__name__})")
            else:
                msg = re.sub(r"AIza[0-9A-Za-z_\-]+", "[REDACTED]", str(body.get("error", {}).get("message", body)))[:110]
                log(f"  [LLM WARNING] Gemini {model} HTTP {code}: {msg}")
                if code in (400, 401, 403) and "API_KEY" in msg.upper():
                    break
    else:
        log("  [LLM WARNING] GOOGLE_API_KEY not set")

    qkey = (os.environ.get("GROQ_API_KEY") or "").strip()
    if lines is None and qkey:
        code, body = _http_json("https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {qkey}"},
                                {"model": "llama-3.1-8b-instant", "temperature": 0.95,
                                 "messages": [{"role": "user", "content": prompt}]}, 10.0)
        if code == 200:
            try:
                lines = _parse_lines(body["choices"][0]["message"]["content"])
                used = "groq/llama-3.1-8b-instant"
            except Exception:
                lines = None
        else:
            log(f"  [LLM WARNING] Groq HTTP {code}")

    if not isinstance(lines, list) or len(lines) != len(beats):
        log(f"  [LLM WARNING] live punch-up unavailable -> using {bank_size()}-line offline comedy bank")
        return 0
    n = 0
    seen: set[str] = {b.text for b in beats}
    for b, ln in zip(beats, lines):
        if isinstance(ln, str):
            ln = " ".join(ln.replace("\u2014", "—").split())
            if ln not in seen and _valid_llm_line(b, ln):
                seen.add(ln)
                b.text = ln
                n += 1
    log(f"  [LLM LIVE] {used} punched up {n}/{len(beats)} lines")
    return n
