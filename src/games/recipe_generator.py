"""Recipe generator (§11.6, §17.2, v4.0):
- Never repeats an identical (arena, goal, twist) recipe within 365 days (12 months).
- Never repeats the same arena within 5 days (rotates cleanly across all 7+ arenas).
- Never deadlocks: after 500 failed attempts it relaxes soft rules (6 -> 5 -> 4) in reverse priority order."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from src.config import TIMELINE, settings
from src.games.base import (
    ARENA_HAZARD_EXCLUDE,
    ARENAS,
    GOAL_ARENA_EXCLUDE,
    GOALS,
    HAZARDS,
    INCOMPATIBLE,
    SHOWCASE_ARENAS,
    SIDE,
    TOP,
    TWISTS,
    WIDESCREEN,
    WIDESCREEN_FINALE_ROUNDS,
    Recipe,
    fits,
    twist_fits,
)
from src.games.themes import THEMES

MAX_ATTEMPTS = 500
# v6 arenas whose races still run short in the lab (0/6 accepted): drawn rarely until tuned.
V6_LOW_WEIGHT = {"big_bubble": 0.3, "lily_pads": 0.3, "swing_canyon": 0.3, "inferno_ascent": 0.3,
                 "clockwork_cogs": 0.3, "glass_bridge": 0.5}


# ---------------------------------------------------------------------------------------------- v6 arena pool
def _v6_info() -> dict:
    from src.games import arenas_v6  # noqa: F401  (registers the v6 arenas)
    from src.games.arena_kit import INFO
    return INFO


def v6_from_day() -> int:
    return int(settings().get("v6_from_day", 10 ** 9))


def arena_pool(day: int) -> dict[str, str]:
    """Arenas the generator may draw on `day`. Days before `v6_from_day` keep the exact legacy pool so every published
    race (and its seed backfill) regenerates identically; from that day the 21 league v6 arenas join."""
    pool = dict(ARENAS)
    if day >= v6_from_day():
        pool.update({k: v["mode"] for k, v in _v6_info().items() if not v.get("playoff")})
    return pool


def all_arena_modes() -> dict[str, str]:
    return {**ARENAS, **{k: v["mode"] for k, v in _v6_info().items()}}


def goals_for(arena: str, mode: str) -> list[str]:
    if arena in ARENAS:
        return [g for g, m in GOALS.items() if fits(m, mode) and arena not in GOAL_ARENA_EXCLUDE.get(g, set())]
    info = _v6_info().get(arena, {})
    return [g for g in info.get("goals", ()) if g in GOALS and fits(GOALS[g], mode)]


def hazards_allowed(arena: str, mode: str) -> list[str]:
    if arena in ARENAS:
        excl = ARENA_HAZARD_EXCLUDE.get(arena, set())
        return [h for h, m in HAZARDS.items() if fits(m, mode) and h not in excl]
    info = _v6_info().get(arena, {})
    return [h for h in info.get("hazards", ()) if h in HAZARDS and fits(HAZARDS[h], mode)]


def twists_for(arena: str, mode: str) -> list[str]:
    if arena in ARENAS:
        return [t for t in TWISTS if twist_fits(t, mode, arena)]
    info = _v6_info().get(arena, {})
    allowed = info.get("twists")
    return [t for t in TWISTS if fits(TWISTS[t], mode) and (allowed is None or t in allowed)]


def generate_widescreen_finale_rounds(season: int, seed: int, season_theme: str | None = None) -> list[Recipe]:
    """Part 6: Generates the 3 stage Recipes for the 16:9-native Season Finale mega-event (Race 30)."""
    rng = random.Random(seed)
    theme = season_theme or THEMES[(max(1, season) - 1) % len(THEMES)].key
    out: list[Recipe] = []
    for idx, spec in enumerate(WIDESCREEN_FINALE_ROUNDS):
        arenas = spec["arenas"]
        arena = arenas[(max(1, season) + idx - 1) % len(arenas)]
        r_seed = seed * 10 + idx + 1
        rec, _ = generate([], 30 + idx, r_seed, arena=arena, goal=spec["goal"], season_theme=theme)
        rec.finale = True
        rec.episode_kind = WIDESCREEN
        rec.flash_forward = False
        rec.params = {
            **rec.params,
            "widescreen": True,
            "round": spec["round"],
            "round_title": spec["title"],
            "heroes_in": spec["heroes_in"],
            "dummies_in": spec["dummies_in"],
            "heroes_advance": spec["heroes_advance"],
            "course_scale_override": 2.2 if rec.mode == SIDE else 1.0,
        }
        if arena in ("rotating_disc", "sumo_pool_pit") and rec.twist is None:
            rec.twist = "shrinking_arena"
        elif rec.mode == SIDE and idx == 2 and rec.twist is None:
            rec.twist = rng.choice(["speed_boost_zones", "heavy_gravity"])
        out.append(rec)
    return out


@dataclass
class History:
    entries: list[dict] = field(default_factory=list)


def _violations(r: Recipe, hist: list[dict], day: int, lock_theme: bool = False,
                pool: dict[str, str] | None = None) -> set[int]:
    v: set[int] = set()
    same_mode = [h for h in hist if h["mode"] == r.mode]
    # 1. Never repeat (arena, goal, twist) within 365 episodes (12 months daily) OR full recipe within 365 days
    key = list(r.key())
    for h in hist:
        if h["day"] > day - 365 and [h["arena"], h["goal"], sorted(h["hazards"]), h.get("twist")] == [
            key[0], key[1], list(key[2]), key[3]
        ]:
            v.add(1)
            break
    for h in hist[-365:]:
        if (h["arena"], h["goal"], h.get("twist")) == (r.arena, r.goal, r.twist):
            v.add(1)
            break
    # 2. Arena never repeated within 5 days AND not within last ceil(P_arena / 2) same-mode episodes
    if any(h["day"] > day - 5 and h["arena"] == r.arena for h in hist) or r.arena in [h["arena"] for h in hist[-4:]]:
        v.add(2)
    p_arena = sum(1 for m in (pool or ARENAS).values() if m == r.mode)
    if r.arena in [h["arena"] for h in same_mode[-min(4, math.ceil(p_arena / 2)):]]:
        v.add(2)
    # 3. Goal never consecutive; <= 2 times in the last 6 episodes
    if hist and hist[-1]["goal"] == r.goal:
        v.add(3)
    if sum(1 for h in hist[-6:] if h["goal"] == r.goal) >= 2:
        v.add(3)
    # 4. Exact hazard set not within the last 60 episodes
    if any(sorted(h["hazards"]) == sorted(r.hazards) for h in hist[-60:]):
        v.add(4)
    # 5. Theme diversity (skipped when Seasonal Theme is locked for the active 30-race season)
    if not lock_theme:
        if r.theme in [h["theme"] for h in hist[-6:]]:
            v.add(5)
        if any(h["theme"] == r.theme and h["arena"] == r.arena for h in hist[-60:]):
            v.add(5)
    # 6. Layout fingerprint never repeated
    if r.fingerprint() in {h.get("fingerprint") for h in hist}:
        v.add(6)
    return v


def _sample(rng: random.Random, mode: str, weights: dict | None, seed: int, season_theme: str | None = None,
            hist: list[dict] | None = None, day: int = 0, smart: bool = False,
            pool: dict[str, str] | None = None) -> Recipe:
    w = weights or {}
    hist = hist or []
    incomp = {tuple(sorted(p)) for p in INCOMPATIBLE}
    arenas = [a for a, m in (pool or ARENAS).items() if m == mode]

    if smart:
        same_mode = [h for h in hist if h["mode"] == mode]
        p_arena = len(arenas)
        recent_a = (
            {h["arena"] for h in hist if h["day"] > day - 5}
            | {h["arena"] for h in hist[-4:]}
            | {h["arena"] for h in same_mode[-min(4, math.ceil(p_arena / 2)):]}
        )
        last_g = hist[-1]["goal"] if hist else None
        freq_g = {g: sum(1 for h in hist[-6:] if h["goal"] == g) for g in GOALS}
        used_triples = {(h["arena"], h["goal"], h.get("twist")) for h in hist[-365:]}
        valid_triples: list[tuple[str, str, str | None]] = []
        for a in arenas:
            if a in recent_a:
                continue
            for g in goals_for(a, mode):
                if g == last_g or freq_g.get(g, 0) >= 2:
                    continue
                t_opts: list[str | None] = [None] + twists_for(a, mode)
                for tw in t_opts:
                    if (a, g, tw) not in used_triples:
                        valid_triples.append((a, g, tw))
        if valid_triples:
            arena, goal, twist = rng.choice(valid_triples)
        else:
            arena = rng.choice(arenas)
            goal = rng.choice(goals_for(arena, mode))
            twist = None
    else:
        v6 = _v6_info() if any(a not in ARENAS for a in arenas) else {}
        a_weights = [w.get("arena", {}).get(a, 1.8 if a in SHOWCASE_ARENAS else
                                           (V6_LOW_WEIGHT.get(a, v6[a]["weight"]) if a in v6 else 1.0))
                     for a in arenas]
        arena = rng.choices(arenas, a_weights)[0]
        goals = goals_for(arena, mode)
        goal = rng.choices(goals, [w.get("goal", {}).get(g, 1.0) for g in goals])[0]
        twists = twists_for(arena, mode)
        twist = rng.choice([None] + twists)

    hz_pool = [h for h in hazards_allowed(arena, mode) if twist is None or tuple(sorted((twist, h))) not in incomp]
    hazards: list[str] = []
    n_hz = rng.choice([1, 2, 2, 3])
    if arena not in ARENAS:
        n_hz = min(n_hz, 2)                 # v6 arenas carry their own signature mechanic: 0-2 extra hazards
    for _ in range(n_hz):
        cands = [h for h in hz_pool if h not in hazards and not any(tuple(sorted((h, o))) in incomp for o in hazards)]
        if cands:
            hazards.append(rng.choice(cands))

    if season_theme:
        theme = season_theme
    else:
        recent_th = {h["theme"] for h in hist[-6:]}
        th_pool = [t.key for t in THEMES if t.key not in recent_th] or [t.key for t in THEMES]
        theme = rng.choice(th_pool)

    params = {"layout_seed": rng.randint(0, 2**31)}
    r = Recipe(seed, mode, arena, goal, sorted(hazards), twist, theme, params)
    r.two_stage = False
    r.flash_forward = rng.random() < TIMELINE.flash_forward_chance
    return r


def generate(history: list[dict], day: int, seed: int, weights: dict | None = None, mode: str | None = None,
             arena: str | None = None, goal: str | None = None, season_theme: str | None = None) -> tuple[Recipe, list[int]]:
    """Returns (recipe, relaxed_rules)."""
    if mode == WIDESCREEN or arena == WIDESCREEN:
        rounds = generate_widescreen_finale_rounds(max(1, (day - 1) // 30 + 1), seed, season_theme=season_theme)
        theme = rounds[0].theme
        rec = Recipe(
            seed=seed,
            mode=WIDESCREEN,
            arena=WIDESCREEN,
            goal=goal or "three_round_championship",
            hazards=sorted({h for r in rounds for h in r.hazards}),
            twist="shrinking_arena",
            theme=theme,
            params={
                "aspect": "16:9",
                "resolution": [1920, 1080],
                "participant_count": 20,
                "rounds": [r.to_dict() for r in rounds],
            },
            two_stage=False,
            flash_forward=False,
            episode_kind=WIDESCREEN,
            finale=True,
        )
        return rec, []
    rng = random.Random(seed)
    mix = settings()["mode_mix"]
    explicit_mode = mode is not None or arena is not None
    pool = arena_pool(day)
    if arena:
        chosen_mode = all_arena_modes()[arena]
    elif mode:
        chosen_mode = mode
    else:
        chosen_mode = SIDE if rng.random() < mix["SIDE_VIEW"] else TOP
        # v5.1 variety: never three races in a row from the same camera mode (RNG consumption unchanged)
        last_modes = [h.get("mode") for h in (history or [])[-2:]]
        if len(last_modes) == 2 and last_modes[0] == last_modes[1] == chosen_mode:
            chosen_mode = TOP if chosen_mode == SIDE else SIDE

    relaxed: list[int] = []
    for relax_level in range(4):
        ignore = {6, 5, 4} if relax_level == 3 else {6, 5} if relax_level == 2 else {6} if relax_level == 1 else set()
        for attempt in range(MAX_ATTEMPTS):
            smart = attempt >= 12
            cur_mode = chosen_mode if explicit_mode else (
                chosen_mode if attempt < 120 else (SIDE if attempt % 2 == 0 else TOP)
            )
            r = _sample(rng, cur_mode, weights, seed, season_theme=season_theme, hist=history, day=day, smart=smart,
                        pool=pool)
            if arena:
                r.arena = arena
                r.mode = all_arena_modes()[arena]
                valid_goals = goals_for(arena, r.mode)
                if r.goal not in valid_goals and valid_goals:
                    r.goal = rng.choice(valid_goals)
                ok_hz = set(hazards_allowed(arena, r.mode))
                r.hazards = [h for h in r.hazards if h in ok_hz]
                if r.twist and r.twist not in twists_for(arena, r.mode):
                    r.twist = None
            if goal and (goal in goals_for(r.arena, r.mode) or r.arena in ARENAS):
                r.goal = goal
            if r.arena == "rotating_disc" and not ({"slippery_ice", "sticky_mud"} & set(r.hazards)):
                # v4.2: always show peeling outer-ring ice/mud patches on the Rotating Disc
                r.hazards = sorted(set(r.hazards) | {"slippery_ice"})
            v = _violations(r, history, day, lock_theme=(season_theme is not None), pool=pool) - ignore
            if arena or goal:
                v -= {1, 2, 3}
            if not v:
                if not explicit_mode and goal is None and day >= v6_from_day():
                    _apply_favour(r, history, day, season_theme)
                return r, sorted(ignore)
        relaxed = sorted(ignore)
    raise RuntimeError(f"recipe generator could not satisfy hard rules 1-3 (relaxed {relaxed})")


# v5.1 "built for X" arenas: some twists naturally suit one ball type. ~25% of league races pick a favoured ball and
# (when the arena allows it) swap in the matching twist. Uses its own RNG stream; recipe fingerprints are unchanged.
FAVOUR_TWISTS: dict[str, tuple[str, ...]] = {
    "low_gravity": ("floater", "pip", "boing"),
    "heavy_gravity": ("juggernaut", "bonk", "comet"),
    "speed_boost_zones": ("dash", "blaze", "zap"),
    "slippery_floor": ("magneto", "grumble", "frosty"),
}
FAVOUR_RATE = 0.25


def _apply_favour(r: Recipe, history: list[dict], day: int, season_theme: str | None) -> None:
    frng = random.Random((int(r.seed) * 2654435761 + 0xFA5) & 0xFFFFFFFF)
    if r.twist in FAVOUR_TWISTS:
        r.favour = frng.choice(FAVOUR_TWISTS[r.twist][:2])
        return
    if frng.random() >= FAVOUR_RATE:
        return
    opts = [t for t in FAVOUR_TWISTS if t in twists_for(r.arena, r.mode)]
    if not opts:
        return
    tw = frng.choice(opts)
    old = r.twist
    r.twist = tw
    if _violations(r, history, day, lock_theme=(season_theme is not None), pool=arena_pool(day)):
        r.twist = old
        return
    r.favour = frng.choice(FAVOUR_TWISTS[tw][:2])


def history_entry(r: Recipe, day: int) -> dict:
    return {
        "day": day,
        "mode": r.mode,
        "arena": r.arena,
        "goal": r.goal,
        "hazards": sorted(r.hazards),
        "twist": r.twist,
        "theme": r.theme,
        "fingerprint": r.fingerprint(),
    }
