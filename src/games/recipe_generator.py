"""Recipe generator (§11.6, §17.2): compatible + feasible recipes under cooldowns that scale with pool size.
Never deadlocks: after 500 failed attempts it relaxes rules in reverse priority order (6 -> 5 -> 4) and logs it."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from src.config import TIMELINE, settings
from src.games.base import (ARENAS, GOAL_ARENA_EXCLUDE, GOALS, HAZARDS, INCOMPATIBLE, SIDE, TOP, TWISTS, Recipe, fits,
                            twist_fits)
from src.games.themes import THEMES

MAX_ATTEMPTS = 500


@dataclass
class History:
    """Episode history entries: dicts with day, mode, arena, goal, hazards, twist, theme, fingerprint."""
    entries: list[dict] = field(default_factory=list)


def _violations(r: Recipe, hist: list[dict], day: int) -> set[int]:
    v: set[int] = set()
    same_mode = [h for h in hist if h["mode"] == r.mode]
    # 1. exact recipe never within 365 days
    key = list(r.key())
    if any(h["day"] > day - 365 and [h["arena"], h["goal"], sorted(h["hazards"]), h["twist"]] ==
           [key[0], key[1], list(key[2]), key[3]] for h in hist):
        v.add(1)
    # 2. arena not within the last ceil(P_arena/2) episodes of the same mode
    p_arena = sum(1 for m in ARENAS.values() if m == r.mode)
    if r.arena in [h["arena"] for h in same_mode[-math.ceil(p_arena / 2):]]:
        v.add(2)
    # 3. goal never consecutive; <= 2 times in the last 6 episodes
    if hist and hist[-1]["goal"] == r.goal:
        v.add(3)
    if sum(1 for h in hist[-6:] if h["goal"] == r.goal) >= 2:
        v.add(3)
    # 4. exact hazard set not within the last 60 episodes
    if any(sorted(h["hazards"]) == sorted(r.hazards) for h in hist[-60:]):
        v.add(4)
    # 5. theme not within the last 6 episodes; (theme, arena) pair not within the last 60
    if r.theme in [h["theme"] for h in hist[-6:]]:
        v.add(5)
    if any(h["theme"] == r.theme and h["arena"] == r.arena for h in hist[-60:]):
        v.add(5)
    # 6. layout fingerprint never repeated
    if r.fingerprint() in {h.get("fingerprint") for h in hist}:
        v.add(6)
    return v


def _sample(rng: random.Random, mode: str, weights: dict | None, seed: int) -> Recipe:
    w = weights or {}
    arenas = [a for a, m in ARENAS.items() if m == mode]
    arena = rng.choices(arenas, [w.get("arena", {}).get(a, 1.0) for a in arenas])[0]
    goals = [g for g, m in GOALS.items() if fits(m, mode) and arena not in GOAL_ARENA_EXCLUDE.get(g, set())]
    goal = rng.choices(goals, [w.get("goal", {}).get(g, 1.0) for g in goals])[0]
    hz_pool = [h for h, m in HAZARDS.items() if fits(m, mode)]
    hazards: list[str] = []
    for _ in range(rng.choice([1, 2, 2, 3])):
        cands = [h for h in hz_pool if h not in hazards and not any(tuple(sorted((h, o))) in
                 {tuple(sorted(p)) for p in INCOMPATIBLE} for o in hazards)]
        if cands:
            hazards.append(rng.choice(cands))
    twists = [t for t in TWISTS if twist_fits(t, mode, arena) and not any(tuple(sorted((t, h))) in
              {tuple(sorted(p)) for p in INCOMPATIBLE} for h in hazards)]
    twist = rng.choice(twists) if twists and rng.random() < 0.75 else None
    theme = rng.choice(THEMES).key
    params = {"layout_seed": rng.randint(0, 2**31)}
    r = Recipe(seed, mode, arena, goal, sorted(hazards), twist, theme, params)
    r.two_stage = goal in ("last_one_standing", "survive_timer") and rng.random() < TIMELINE.two_stage_chance / 0.4
    r.flash_forward = rng.random() < TIMELINE.flash_forward_chance
    return r


def generate(history: list[dict], day: int, seed: int, weights: dict | None = None, mode: str | None = None,
             arena: str | None = None, goal: str | None = None) -> tuple[Recipe, list[int]]:
    """Returns (recipe, relaxed_rules)."""
    rng = random.Random(seed)
    mix = settings()["mode_mix"]
    if mode is None:
        mode = SIDE if rng.random() < mix["SIDE_VIEW"] else TOP
    if arena:
        mode = ARENAS[arena]
    relaxed: list[int] = []
    for relax_level in range(4):          # 0: all rules; 1: drop 6; 2: drop 6,5; 3: drop 6,5,4
        ignore = {6, 5, 4} if relax_level == 3 else {6, 5} if relax_level == 2 else {6} if relax_level == 1 else set()
        for _ in range(MAX_ATTEMPTS):
            r = _sample(rng, mode, weights, seed)
            if arena:
                r.arena = arena
            if goal:
                r.goal = goal
            v = _violations(r, history, day) - ignore
            if arena or goal:      # manual overrides (workflow_dispatch) skip arena/goal cooldowns
                v -= {1, 2, 3}
            if not v:
                return r, sorted(ignore)
        relaxed = sorted(ignore)
    raise RuntimeError(f"recipe generator could not satisfy hard rules 1-3 (relaxed {relaxed})")


def history_entry(r: Recipe, day: int) -> dict:
    return {"day": day, "mode": r.mode, "arena": r.arena, "goal": r.goal, "hazards": sorted(r.hazards), "twist": r.twist,
            "theme": r.theme, "fingerprint": r.fingerprint()}
