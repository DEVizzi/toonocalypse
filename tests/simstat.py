"""Dev harness: run one simulation per arena and print outcome stats. python -m tests.simstat [goal]"""
from __future__ import annotations

import random
import sys
import time

from src.characters.roster import HEROES, make_extras
from src.games.base import ARENAS, GOALS, HAZARDS, TWISTS, Recipe, fits, twist_fits
from src.physics.engine import Sim


def recipe_for(arena: str, seed: int, goal: str | None = None) -> Recipe:
    r = random.Random(seed)
    mode = ARENAS[arena]
    goals = [g for g, m in GOALS.items() if fits(m, mode) and not (g == "reach_finish" and mode != "SIDE_VIEW")]
    hz = [h for h, m in HAZARDS.items() if fits(m, mode)]
    tw = [t for t in TWISTS if twist_fits(t, mode, arena)]
    return Recipe(seed, mode, arena, goal or r.choice(goals), r.sample(hz, r.randint(1, 2)), r.choice(tw + [None]),
                  r.choice(["meadow", "volcano", "candy"]))


def run(arena: str, seed: int, goal: str | None = None):
    rec = recipe_for(arena, seed, goal)
    rng = random.Random(seed)
    heroes = rng.sample(list(HEROES), 6)
    extras = make_extras(rng.randint(24, 30), rng)
    t0 = time.time()
    tr = Sim(rec, heroes, extras, seed).run()
    el = sum(1 for e in tr.events if e.kind == "elimination")
    n = len(tr.keys)
    return rec, tr, el / n, time.time() - t0


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else None
    arenas = sys.argv[2].split(",") if len(sys.argv) > 2 else list(ARENAS)
    for a in arenas:
        try:
            rec, tr, rate, dt = run(a, 11, goal if goal not in (None, "any") else None)
            from collections import Counter
            causes = Counter(e.data.get("cause") for e in tr.events if e.kind == "elimination")
            times = sorted(e.t for e in tr.events if e.kind == "elimination")
            q = [round(times[int(len(times) * k)], 1) for k in (0.1, 0.5, 0.9)] if times else []
            print(f"{a:18s} {rec.goal:16s} dur={tr.meta['resolved_at']:.1f} win={tr.meta['winner']:10s} "
                  f"elim={rate:.0%} t10/50/90={q} {dict(causes)} sim={dt:.1f}s")
        except Exception as e:  # dev harness: keep going
            import traceback
            traceback.print_exc()
            print(f"{a:18s} FAILED {type(e).__name__}: {e}")
