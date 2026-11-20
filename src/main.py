"""Toon Toon Castle CLI (§22.4).

    python -m src.main --dry-run --seed 42 --arena flat_track --goal reach_finish

Pipeline (M4 scope): recipe -> simulate N seeds -> score -> pick the best real run -> silent render.
Dry-run never uploads and never mutates state/. Later milestones add beats/script/TTS/audio, state and publishing.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from src.characters.roster import HEROES, make_extras
from src.config import settings
from src.games import recipe_generator
from src.games.base import Recipe
from src.physics import scorer
from src.physics.engine import Sim
from src.physics.trace import Event, Trace

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def _load(name: str, default):
    p = STATE / name
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def pick_cast(kind: str, rng: random.Random) -> tuple[list, list]:
    cast = settings()["cast"]
    if kind == "rumble":
        return list(HEROES), make_extras(cast["mega_extras"], rng)
    heroes = rng.sample(list(HEROES), cast["spotlight_heroes"])
    return heroes, make_extras(rng.randint(*cast["extras_range"]), rng)


def simulate_best(recipe: Recipe, heroes: list, extras: list, seed: int, history: dict | None = None,
                  log=print) -> tuple[Trace, scorer.Score, list[dict]]:
    """Best-of-N (§12): 8 seeds, 8 more if none reaches min_score (max 16). Outcomes are real physics."""
    sc = settings()["scorer"]
    results: list[tuple[float, int, Trace, scorer.Score]] = []
    report = []
    t_all = time.time()
    for i in range(sc["max_seeds"]):
        if i == sc["seeds_per_batch"] and max(r[0] for r in results) >= scorer.min_score():
            break
        s = seed * 1000 + i
        t0 = time.time()
        tr = Sim(recipe, heroes, extras, s).run()
        res = scorer.score(tr, history)
        dt = time.time() - t0
        results.append((res.total, s, tr, res))
        report.append({"seed": s, "score": res.total, "winner": tr.meta["winner"],
                       "resolved_at": tr.meta["resolved_at"], "sim_s": round(dt, 2)})
        log(f"  seed {s}: score={res.total:+.0f} winner={tr.meta['winner']} t={tr.meta['resolved_at']:.1f}s sim={dt:.1f}s")
    log(f"  {len(results)} sims in {time.time() - t_all:.1f}s")
    results.sort(key=lambda r: r[0], reverse=True)
    best = results[0]
    return best[2], best[3], report


def flash_event(tr: Trace) -> Event | None:
    """The episode's biggest disaster for the flash-forward cold open (needs >= 2 s of lead-in)."""
    def rank(e: Event) -> float:
        if e.kind == "elimination" and e.data.get("hero"):
            return 3 + (1 if e.data.get("by_hero") else 0)
        if e.kind == "trait":
            return 2
        if e.kind == "impact" and e.data.get("hero_pair"):
            return 1 + min(1.0, e.data.get("impulse", 0) / 4000)
        return 0
    end = tr.meta.get("resolved_at") or 0
    cands = [e for e in tr.events if 2.0 <= e.t <= end - 2.0 and e.actors and rank(e) > 0]
    return max(cands, key=rank) if cands else None


def comment_prompt(heroes: list, winner: str | None, rng: random.Random) -> str:
    pool = [h for h in heroes if h.key != winner] or heroes
    a, b = rng.sample(pool, 2) if len(pool) >= 2 else (pool[0], pool[0])
    return f"{a.name} or {b.name} tomorrow?"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Toon Toon Castle episode pipeline")
    ap.add_argument("--dry-run", action="store_true", help="render only: no uploads, no state mutation")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--arena", default=None)
    ap.add_argument("--goal", default=None)
    ap.add_argument("--mode", choices=["SIDE_VIEW", "TOP_DOWN"], default=None)
    ap.add_argument("--kind", choices=["spotlight", "rumble"], default="spotlight")
    ap.add_argument("--flash-forward", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--episode", type=int, default=None, help="episode number shown on the badge")
    ap.add_argument("--out", default="output/episode.mp4")
    ap.add_argument("--no-render", action="store_true", help="simulate and score only")
    a = ap.parse_args(argv)

    if not a.dry_run:
        print("Only --dry-run is available until M7/M8 (publishing). Re-run with --dry-run.", file=sys.stderr)
        return 2
    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    rng = random.Random(seed)
    history = _load("episode_history.json", [])
    entries = history.get("entries", []) if isinstance(history, dict) else history
    day = (entries[-1]["day"] + 1) if entries else 1
    recipe, relaxed = recipe_generator.generate(entries, day, seed, mode=a.mode, arena=a.arena, goal=a.goal)
    if a.flash_forward != "auto":
        recipe.flash_forward = a.flash_forward == "on"
    recipe.episode_kind = "rumble_final" if a.kind == "rumble" else "spotlight"
    heroes, extras = pick_cast(a.kind, rng)
    print(f"recipe: {recipe.mode} {recipe.arena} / {recipe.goal} / {recipe.hazards} / twist={recipe.twist} / "
          f"{recipe.theme} two_stage={recipe.two_stage} flash={recipe.flash_forward} relaxed={relaxed}")
    print(f"cast: {[h.key for h in heroes]} + {len(extras)} extras")
    trace, best, report = simulate_best(recipe, heroes, extras, seed)
    print(f"best: seed={trace.meta['seed']} score={best.total:+.0f} {best.parts} winner={trace.meta['winner']}")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {"recipe": recipe.to_dict(), "cast": [h.key for h in heroes], "extras": len(extras),
               "best_seed": trace.meta["seed"], "score": best.total, "score_parts": best.parts,
               "winner": trace.meta["winner"], "resolved_at": trace.meta["resolved_at"], "candidates": report}
    if not a.no_render:
        from src.rendering import pipeline   # pygame import is deferred so simulation-only runs need no SDL

        num = a.episode or day
        label = f"EP. {num} - {'SUNDAY RUMBLE' if a.kind == 'rumble' else recipe.label()}"
        ep = pipeline.Episode(trace, label, prompt=comment_prompt(heroes, trace.meta["winner"], rng),
                              flash_event=flash_event(trace))
        t0 = time.time()
        info = pipeline.encode(ep, out)
        info["render_s"] = round(time.time() - t0, 1)
        print(f"rendered {out} frames={info['frames']} duration={info['duration']:.1f}s in {info['render_s']}s")
        summary.update(video=str(out), duration=info["duration"], frames=info["frames"], render_s=info["render_s"])
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
