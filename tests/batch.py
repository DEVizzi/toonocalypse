"""Dev harness: many seeds -> duration/elimination/winner-type stats.  python -m tests.batch MODE N"""
from __future__ import annotations

import statistics
import sys
from collections import Counter

from src.games.base import ARENAS
from tests.simstat import run

mode = sys.argv[1] if len(sys.argv) > 1 else "SIDE_VIEW"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
durs, rates, wins, bad = [], [], Counter(), Counter()
for a, m in ARENAS.items():
    if m != mode:
        continue
    for s in range(n):
        rec, tr, rate, dt = run(a, 100 + s)
        d = tr.meta["resolved_at"] or 0
        durs.append(d)
        rates.append(rate)
        w = tr.meta["winner"] or "none"
        wins["extra" if w.startswith("extra") else w] += 1
        if not (26 <= d <= 38):
            bad[f"{a}/{rec.goal}:{d:.0f}s"] += 1
print("dur mean", round(statistics.mean(durs), 1), "min", round(min(durs), 1), "max", round(max(durs), 1))
print("elim mean", round(statistics.mean(rates), 2), "min", round(min(rates), 2))
print("winners", dict(wins.most_common()))
print("out-of-range", dict(bad))
