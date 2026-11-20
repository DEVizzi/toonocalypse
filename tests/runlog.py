"""Dev harness: one line per run with causes and alive-count timeline.  python -m tests.runlog MODE N [goal]"""
from __future__ import annotations

import sys
from collections import Counter

from src.games.base import ARENAS, GOALS, fits
from tests.simstat import run

mode = sys.argv[1] if len(sys.argv) > 1 else "SIDE_VIEW"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
only = sys.argv[3] if len(sys.argv) > 3 else None
goals = [g for g, m in GOALS.items() if fits(m, mode) and not (g == "reach_finish" and mode != "SIDE_VIEW")]
k = 0
for a, m in ARENAS.items():
    if m != mode:
        continue
    for s in range(n):
        g = only or goals[k % len(goals)]
        k += 1
        rec, tr, rate, dt = run(a, 100 + s * 7 + k, g)
        el = [e for e in tr.events if e.kind == "elimination"]
        causes = Counter(e.data.get("cause") for e in el)
        total = len(tr.keys)
        alive_at = [total - sum(1 for e in el if e.t < t) for t in (5, 10, 15, 20, 25, 30)]
        w = tr.meta["winner"] or "-"
        he = [f"{e.actors[0][:3]}@{e.t:.0f}:{e.data.get('cause')[:4]}{'*' if len(e.actors) > 1 else ''}"
              for e in el if e.data.get("hero")]
        print(f"{a:16s} {g:17s} t={tr.meta['resolved_at'] or 0:4.1f} win={w:10s} alive@5..30={alive_at} "
              f"tw={rec.twist} hz={rec.hazards} heroes_out={he}")
