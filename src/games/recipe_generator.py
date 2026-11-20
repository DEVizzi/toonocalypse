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
    Recipe,
    fits,
    twist_fits,
)
from src.games.themes import THEMES

MAX_ATTEMPTS = 500


@dataclass
class History:
    entries: list[dict] = field(default_factory=list)


def _violations(r: Recipe, hist: list[dict], day: int, lock_theme: bool = False) -> set[int]:
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
    p_arena = sum(1 for m in ARENAS.values() if m == r.mode)
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
            hist: list[dict] | None = None, day: int = 0, smart: bool = False) -> Recipe:
    w = weights or {}
    hist = hist or []
    incomp = {tuple(sorted(p)) for p in INCOMPATIBLE}
    arenas = [a for a, m in ARENAS.items() if m == mode]

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
            for g, gm in GOALS.items():
                if not fits(gm, mode) or a in GOAL_ARENA_EXCLUDE.get(g, set()) or g == last_g or freq_g.get(g, 0) >= 2:
                    continue
                t_opts: list[str | None] = [None] + [t for t in TWISTS if twist_fits(t, mode, a)]
                for tw in t_opts:
                    if (a, g, tw) not in used_triples:
                        valid_triples.append((a, g, tw))
        if valid_triples:
            arena, goal, twist = rng.choice(valid_triples)
        else:
            arena = rng.choice(arenas)
            goals = [g for g, m in GOALS.items() if fits(m, mode) and arena not in GOAL_ARENA_EXCLUDE.get(g, set())]
            goal = rng.choice(goals)
            twist = None
    else:
        a_weights = [w.get("arena", {}).get(a, 1.8 if a in SHOWCASE_ARENAS else 1.0) for a in arenas]
        arena = rng.choices(arenas, a_weights)[0]
        goals = [g for g, m in GOALS.items() if fits(m, mode) and arena not in GOAL_ARENA_EXCLUDE.get(g, set())]
        goal = rng.choices(goals, [w.get("goal", {}).get(g, 1.0) for g in goals])[0]
        twists = [t for t in TWISTS if twist_fits(t, mode, arena)]
        twist = rng.choice([None] + twists)

    excl_hz = ARENA_HAZARD_EXCLUDE.get(arena, set())
    hz_pool = [
        h for h, m in HAZARDS.items()
        if fits(m, mode) and h not in excl_hz and (twist is None or tuple(sorted((twist, h))) not in incomp)
    ]
    hazards: list[str] = []
    for _ in range(rng.choice([1, 2, 2, 3])):
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
    rng = random.Random(seed)
    mix = settings()["mode_mix"]
    explicit_mode = mode is not None or arena is not None
    if arena:
        chosen_mode = ARENAS[arena]
    elif mode:
        chosen_mode = mode
    else:
        chosen_mode = SIDE if rng.random() < mix["SIDE_VIEW"] else TOP

    relaxed: list[int] = []
    for relax_level in range(4):
        ignore = {6, 5, 4} if relax_level == 3 else {6, 5} if relax_level == 2 else {6} if relax_level == 1 else set()
        for attempt in range(MAX_ATTEMPTS):
            smart = attempt >= 12
            cur_mode = chosen_mode if explicit_mode else (
                chosen_mode if attempt < 120 else (SIDE if attempt % 2 == 0 else TOP)
            )
            r = _sample(rng, cur_mode, weights, seed, season_theme=season_theme, hist=history, day=day, smart=smart)
            if arena:
                r.arena = arena
                r.mode = ARENAS[arena]
                valid_goals = [g for g, m in GOALS.items() if fits(m, r.mode) and arena not in GOAL_ARENA_EXCLUDE.get(g, set())]
                if r.goal not in valid_goals and valid_goals:
                    r.goal = rng.choice(valid_goals)
                excl_hz = ARENA_HAZARD_EXCLUDE.get(arena, set())
                r.hazards = [h for h in r.hazards if h not in excl_hz]
                if r.twist and not twist_fits(r.twist, r.mode, arena):
                    r.twist = None
            if goal:
                r.goal = goal
            v = _violations(r, history, day, lock_theme=(season_theme is not None)) - ignore
            if arena or goal:
                v -= {1, 2, 3}
            if not v:
                return r, sorted(ignore)
        relaxed = sorted(ignore)
    raise RuntimeError(f"recipe generator could not satisfy hard rules 1-3 (relaxed {relaxed})")


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
