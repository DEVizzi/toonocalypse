"""Arena lab: tune a v6 arena without rendering video (local Pymunk sims are cheap; never needs ffmpeg).

    .venv/bin/python tests/arena_lab.py glass_bridge                 # 12 seeds x every allowed goal
    .venv/bin/python tests/arena_lab.py glass_bridge -n 20 -g reach_finish
    .venv/bin/python tests/arena_lab.py glass_bridge --sheet out.png  # 6-frame contact sheet of one race (PNG)

Reports per goal: rejection rate (the daily episode needs >= 1 accepted run out of 8-16), median gameplay length,
first blood, eliminations, hero KOs, winner spread and the most common rejection reasons.
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import statistics
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.characters.roster import HEROES, make_extras  # noqa: E402
from src.games import recipe_generator  # noqa: E402
from src.physics import scorer  # noqa: E402
from src.physics.engine import Sim  # noqa: E402


def run_one(arena: str, goal: str | None, seed: int, n_heroes: int = 10):
    recipe, _ = recipe_generator.generate([], 400, seed, arena=arena, goal=goal, season_theme="royal_classic")
    rng = random.Random(seed)
    heroes = list(HEROES)[:n_heroes]
    extras = make_extras(max(2, 14 - len(heroes)), rng)
    t0 = time.time()
    tr = Sim(recipe, heroes, extras, seed).run()
    sc = scorer.score(tr, {})
    return recipe, tr, sc, time.time() - t0


def lab(arena: str, goals: list[str], n: int, n_heroes: int) -> None:
    from src.games.arena_kit import v6_info
    info = v6_info(arena)
    goals = goals or list(info.get("goals") or [None])
    for g in goals:
        rows, reasons, winners, errors = [], collections.Counter(), collections.Counter(), 0
        for k in range(n):
            seed = 1000 + k * 7919
            try:
                recipe, tr, sc, dt = run_one(arena, g, seed, n_heroes)
            except Exception:  # noqa: BLE001
                errors += 1
                if errors == 1:
                    traceback.print_exc()
                continue
            ev = tr.events
            elims = [e for e in ev if e.kind == "elimination"]
            first = min((e.t for e in elims), default=99.0)
            end = tr.meta.get("resolved_at") or 99.0
            hero_ko = sum(1 for e in elims if e.data.get("hero"))
            rej = scorer.rejected(sc)
            for kk, vv in sc.parts.items():
                if vv < 0:
                    reasons[kk] += 1
            winners[str(tr.meta.get("winner"))] += 1
            rows.append((rej, end, first, len(elims), hero_ko, dt, recipe.goal, sc.total))
        if not rows:
            print(f"{arena} / {g}: ALL {n} RUNS CRASHED")
            continue
        acc = [r for r in rows if not r[0]]
        print(f"\n== {arena} / {rows[0][6]}  ({len(rows)} runs, {errors} crashed)")
        print(f"   accepted {len(acc)}/{len(rows)}  | median len {statistics.median(r[1] for r in rows):.1f}s"
              f"  first blood {statistics.median(r[2] for r in rows):.1f}s  elims {statistics.median(r[3] for r in rows):.0f}"
              f"  hero KOs {statistics.median(r[4] for r in rows):.0f}  sim {statistics.median(r[5] for r in rows):.2f}s"
              f"  score {statistics.median(r[7] for r in rows):.0f}")
        print(f"   winners {dict(winners.most_common(6))}")
        print(f"   penalties {dict(reasons.most_common())}")


def sheet(arena: str, goal: str | None, seed: int, out: str, n_heroes: int) -> None:
    import pygame

    from src.rendering import pipeline
    recipe, tr, sc, _ = run_one(arena, goal, seed, n_heroes)
    ep = pipeline.Episode(tr, "", league_ctx={"season_number": 1, "episode_number": 3})
    r = pipeline.Renderer(ep)
    pre = r.pre
    end_f = min(tr.n_frames - 1, pre + int((tr.meta.get("resolved_at") or 10) * 30))
    picks = [pre + int((end_f - pre) * u) for u in (0.02, 0.2, 0.4, 0.6, 0.8, 1.0)]
    tiles = []
    for i, f in enumerate(picks):
        surf = r.render_shot(pipeline.Shot(float(f), "play", (f - pre) / 30.0), 100 + i)
        tiles.append(pygame.transform.smoothscale(surf, (360, 640)))
    grid = pygame.Surface((360 * 3, 640 * 2))
    for i, t in enumerate(tiles):
        grid.blit(t, ((i % 3) * 360, (i // 3) * 640))
    pygame.image.save(grid, out)
    print(f"saved {out}  winner={tr.meta.get('winner')} len={tr.meta.get('resolved_at')} rejected={scorer.rejected(sc)}"
          f" parts={ {k: v for k, v in sc.parts.items() if v} }")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arena")
    ap.add_argument("-n", type=int, default=12)
    ap.add_argument("-g", "--goal", action="append", default=[])
    ap.add_argument("--heroes", type=int, default=10)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--seed", type=int, default=1000)
    a = ap.parse_args()
    if a.sheet:
        sheet(a.arena, (a.goal or [None])[0], a.seed, a.sheet, a.heroes)
    else:
        lab(a.arena, a.goal, a.n, a.heroes)


if __name__ == "__main__":
    main()
