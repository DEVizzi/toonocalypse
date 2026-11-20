"""Dev harness: win shares by goal and by hero.  python -m tests.winstat MODE N [seed0]"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

from src.games.base import ARENAS, GOALS, fits
from tests.simstat import run

mode = sys.argv[1] if len(sys.argv) > 1 else "SIDE_VIEW"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
s0 = int(sys.argv[3]) if len(sys.argv) > 3 else 100
goals = [g for g, m in GOALS.items() if fits(m, mode) and not (g == "reach_finish" and mode != "SIDE_VIEW")]
by_goal: dict[str, Counter] = defaultdict(Counter)
heroes, durs, bad, total, k = Counter(), [], 0, 0, 0
for a, m in ARENAS.items():
    if m != mode:
        continue
    for s in range(n):
        g = goals[k % len(goals)]
        k += 1
        rec, tr, rate, dt = run(a, s0 + s * 7 + k, g)
        w = tr.meta["winner"] or "none"
        ex = w.startswith("extra")
        by_goal[g]["extra" if ex else "hero"] += 1
        if not ex:
            heroes[w] += 1
        d = tr.meta["resolved_at"] or 0
        durs.append(d)
        by_goal[g][f"{d:.0f}s"] += 1
        bad += not (26 <= d <= 38)
        total += 1
ext = sum(c["extra"] for c in by_goal.values())
print(f"runs={total} extra_share={ext / total:.0%} dur_mean={statistics.mean(durs):.1f} out_of_range={bad}")
for g, c in by_goal.items():
    print(f"  {g:18s} {dict(c)}")
print("heroes", {h: f"{v / total:.0%}" for h, v in heroes.most_common()})
