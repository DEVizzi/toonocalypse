"""v4.2 physics benchmark: pass rate, first blood, duration, longest KO-free stretch for the 5 verification arenas."""
from __future__ import annotations

import random
import sys

from src.characters.roster import HEROES, make_extras
from src.games import recipe_generator
from src.physics import scorer
from src.physics.engine import Sim

CASES = [
    ("rotating_disc", "last_one_standing", 10, 4, False, 101),
    ("crumbling_bridge", "reach_finish", 10, 4, False, 505),
    ("crusher_gauntlet", "reach_finish", 3, 6, True, 712),
    ("collapse_tower", "reach_finish", 7, 4, False, 606),
    ("pachinko_drop", "reach_finish", 10, 4, False, 306),
]


def main(n: int = 8, only: str | None = None) -> None:
    for arena, goal, nh, nd, gold, bs in CASES:
        if only and arena != only:
            continue
        rec, _ = recipe_generator.generate([], 1, bs, arena=arena, goal=goal, season_theme="royal_classic")
        rec.finale = gold
        heroes = list(HEROES)[:nh]
        extras = make_extras(nd, random.Random(bs), golden=gold)
        ok, rows = 0, []
        for i in range(n):
            tr = Sim(rec, heroes, extras, bs * 1000 + i).run()
            sc = scorer.score(tr, None)
            el = sorted(e.t for e in tr.events if e.kind == "elimination")
            end = tr.meta["resolved_at"] or 0
            gaps = [b - a for a, b in zip([0.0] + el, el + [end])]
            rej = scorer.rejected(sc)
            ok += not rej
            rows.append((round(el[0], 1) if el else None, round(end, 1), tr.meta["winner"], round(max(gaps[1:-1] or [0]), 1),
                         [k for k, v in sc.parts.items() if v < 0]))
        print(f"{arena:17s} {nh}H+{nd}D hz={rec.hazards} tw={rec.twist}: {ok}/{n} pass")
        for r in rows[:4]:
            print("    fb/end/winner/maxgap/bad:", r)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8, sys.argv[2] if len(sys.argv) > 2 else None)
