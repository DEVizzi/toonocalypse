"""Dev harness (v3.0): per-arena duration, first blood, win type, dummy wins, hero win shares.
python -m tests.v3stat MODE N"""
from __future__ import annotations

import statistics
import sys
from collections import Counter

from src.games.base import ARENAS, GOALS, fits
from src.physics import scorer
from tests.simstat import run

mode = sys.argv[1] if len(sys.argv) > 1 else "SIDE_VIEW"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
goals = [g for g, m in GOALS.items() if fits(m, mode) and not (g == "reach_finish" and mode != "SIDE_VIEW")]
wins, how, rej = Counter(), Counter(), Counter()
durs, firsts, k = [], [], 0
for a, m in ARENAS.items():
    if m != mode:
        continue
    row = []
    for s in range(n):
        g = goals[k % len(goals)]
        k += 1
        rec, tr, rate, dt = run(a, 500 + s * 13 + k, g)
        el = sorted(e.t for e in tr.events if e.kind == "elimination")
        d = tr.meta["resolved_at"] or 0
        durs.append(d)
        firsts.append(el[0] if el else 99)
        w = tr.meta["winner"] or "-"
        wins["DUMMY" if w.startswith("extra") else w] += 1
        we = [e for e in tr.events if e.kind == "win"]
        how[we[0].data["how"] if we else "-"] += 1
        sc = scorer.score(tr)
        for key in ("dummy_win", "late_first_blood", "dead_stretch", "duration"):
            rej[key] += sc.parts.get(key, 0) < 0
        row.append(f"{g[:8]}:{d:4.1f}s fb={el[0] if el else 99:4.1f} {w[:6]}")
    print(f"{a:16s} " + " | ".join(row))
print(f"dur mean {statistics.mean(durs):.1f}  in16-24 {sum(16 <= d <= 24 for d in durs)}/{len(durs)}  "
      f"firstblood<=3.5 {sum(f <= 3.5 for f in firsts)}/{len(firsts)}")
print("how", dict(how), "rejections", dict(rej))
print("wins", dict(wins.most_common()))
