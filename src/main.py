"""Toon Toon Castle v4.0 Autonomous Season League CLI (§22.4).

Examples:
    # Preview / Showcase dry-run (synthesizes realistic season standings, never mutates state/):
    python -m src.main --dry-run --seed 101 --season 1 --race 12 --arena rotating_disc --goal last_one_standing

    # Autonomous daily Season League production run (updates state/*.json atomically, auto-rolls over after Race 30):
    python -m src.main --commit-state
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from src.characters.roster import HERO_BY_KEY, HEROES, make_extras
from src.config import settings
from src.games import recipe_generator
from src.games.base import Recipe
from src.games.themes import for_season
from src.physics import scorer
from src.physics.engine import Sim
from src.physics.trace import Event, Trace
from src.state import league

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def _load(name: str, default):
    return league.load_json(STATE / name, default)


def pick_cast(kind: str, rng: random.Random) -> tuple[list, list]:
    """Legacy fallback cast helper."""
    cast = settings()["cast"]
    if kind == "rumble":
        return list(HEROES), make_extras(cast["mega_extras"], rng)
    heroes = rng.sample(list(HEROES), cast["spotlight_heroes"])
    return heroes, make_extras(rng.randint(*cast["extras_range"]), rng)


def simulate_best(recipe: Recipe, heroes: list, extras: list, seed: int, history: dict | None = None,
                  log=print) -> tuple[Trace, scorer.Score, list[dict]]:
    """Best-of-N (§12): 8 seeds, 8 more if none reaches min_score (max 16). Outcomes are 100% real physics."""
    sc = settings()["scorer"]
    results: list[tuple[float, int, Trace, scorer.Score]] = []
    report = []
    t_all = time.time()
    for i in range(sc["max_seeds"]):
        if i == sc["seeds_per_batch"] and any(r[0] >= scorer.min_score() and not scorer.rejected(r[3]) for r in results):
            break
        s = seed * 1000 + i
        t0 = time.time()
        tr = Sim(recipe, heroes, extras, s).run()
        res = scorer.score(tr, history)
        dt = time.time() - t0
        results.append((res.total, s, tr, res))
        report.append({
            "seed": s,
            "score": res.total,
            "rejected": scorer.rejected(res),
            "winner": tr.meta["winner"],
            "resolved_at": tr.meta["resolved_at"],
            "sim_s": round(dt, 2),
        })
        log(f"  seed {s}: score={res.total:+.0f} rej={scorer.rejected(res)} winner={tr.meta['winner']} "
            f"t={tr.meta['resolved_at']:.1f}s sim={dt:.1f}s")
    log(f"  {len(results)} sims in {time.time() - t_all:.1f}s")
    # Rank non-rejected runs first, then prefer Hero winners if all runs had minor duration edge cases
    results.sort(
        key=lambda r: (
            not scorer.rejected(r[3]),
            not str(r[2].meta.get("winner") or "").startswith("extra"),
            16.0 <= float(r[2].meta.get("resolved_at") or 0) <= 28.0,
            r[0],
        ),
        reverse=True,
    )
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
    pool = [h for h in heroes if h.key != winner] or list(HEROES)
    a, b = rng.sample(pool, 2) if len(pool) >= 2 else (pool[0], pool[0])
    return f"{a.name} or {b.name} tomorrow? Drop your pick!"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Toon Toon Castle v4.0 IPL Season League pipeline")
    ap.add_argument("--dry-run", action="store_true", help="render only: no uploads, no state/ mutation")
    ap.add_argument("--commit-state", action="store_true", help="git pull --rebase + commit + push state/ after run")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--season", type=int, default=None, help="override season number (synthesizes mock table in --dry-run)")
    ap.add_argument("--race", type=int, default=None, help="override race number 1..30 (synthesizes mock table in --dry-run)")
    ap.add_argument("--arena", default=None)
    ap.add_argument("--goal", default=None)
    ap.add_argument("--mode", choices=["SIDE_VIEW", "TOP_DOWN"], default=None)
    ap.add_argument("--kind", choices=["spotlight", "rumble"], default="spotlight")
    ap.add_argument("--hazards", default=None, help="comma-separated hazard override (test renders)")
    ap.add_argument("--twist", default=None, help="twist override, or 'none'")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--flash-forward", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--episode", type=int, default=None, help="legacy alias for --race")
    ap.add_argument("--out", default="output/episode.mp4")
    ap.add_argument("--no-render", action="store_true", help="simulate and score only")
    ap.add_argument("--stills", type=int, default=0, help="also save N half-size PNG stills for review")
    ap.add_argument("--no-audio", action="store_true", help="silent render (skip narration, SFX and music)")
    a = ap.parse_args(argv)

    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    rng = random.Random(seed)
    history = _load("episode_history.json", {"entries": []})
    entries = list(history.get("entries", []) if isinstance(history, dict) else history)
    hof = _load("hall_of_fame.json", {"seasons": []})

    race_override = a.race or a.episode
    if a.dry_run and (a.season is not None or race_override is not None):
        s_num = max(1, int(a.season or 1))
        r_num = max(1, min(league.SEASON_LEN, int(race_override or 1)))
        season_state = league.mock_season_state(s_num, r_num, seed=seed)
    else:
        season_state = league.load_season_state(STATE)
        if a.season is not None:
            season_state["season_number"] = max(1, int(a.season))
            season_state["theme"] = for_season(season_state["season_number"]).key
        if race_override is not None:
            season_state["race_number"] = max(1, min(league.SEASON_LEN, int(race_override)))

    season_num = int(season_state["season_number"])
    race_num = int(season_state["race_number"])
    day = int(season_state.get("total_day") or ((entries[-1]["day"] + 1) if entries else 1))

    heroes, extras, is_grand_final = league.select_cast_for_race(season_state, rng)
    pre_table = [k for k, _ in league.sorted_standings(season_state["stats"])]
    pre_rank = {k: i + 1 for i, k in enumerate(pre_table)}
    cast_sorted = sorted([h.key for h in heroes], key=lambda k: pre_rank.get(k, 99))
    prev_winner = next((e.get("winner") for e in reversed(entries) if isinstance(e, dict) and e.get("winner")), None)
    wild_pool = [k for k in cast_sorted[2:]]
    wildcard = prev_winner if prev_winner in wild_pool else (rng.choice(wild_pool) if wild_pool else None)
    spotlights = []
    if cast_sorted:
        spotlights.append({"key": cast_sorted[0], "kind": "leader",
                           "label": f"#{pre_rank.get(cast_sorted[0], 1)} {HERO_BY_KEY[cast_sorted[0]].name.upper()}"})
    if len(cast_sorted) > 1:
        spotlights.append({"key": cast_sorted[1], "kind": "rival",
                           "label": f"#{pre_rank.get(cast_sorted[1], 2)} {HERO_BY_KEY[cast_sorted[1]].name.upper()}"})
    if wildcard:
        spotlights.append({"key": wildcard, "kind": "wildcard", "label": f"WILDCARD: {HERO_BY_KEY[wildcard].name.upper()}"})
    recent_ids: set[str] = set()
    for e in entries:
        if isinstance(e, dict) and int(e.get("day", -999)) > day - 7:
            recent_ids.update(e.get("line_ids") or [])
    recent_cliches: set[str] = set()
    for e in [x for x in entries if isinstance(x, dict)][-7:]:      # v4.3: each cliché max once every 7 episodes
        recent_cliches.update(e.get("cliches") or [])
    recipe, relaxed = recipe_generator.generate(
        entries,
        day,
        seed,
        mode=a.mode,
        arena=a.arena,
        goal=a.goal,
        season_theme=for_season(season_num).key,
    )
    if a.hazards:
        recipe.hazards = sorted(a.hazards.split(","))
    if a.twist:
        recipe.twist = None if a.twist == "none" else a.twist
    if a.theme:
        recipe.theme = a.theme
    if a.flash_forward != "auto":
        recipe.flash_forward = a.flash_forward == "on"
    recipe.finale = is_grand_final
    recipe.episode_kind = "rumble_final" if is_grand_final else "spotlight"

    recent_winners = [e.get("winner") for e in entries[-6:] if isinstance(e, dict) and e.get("winner")]
    sim_hist = {"recent_winners": recent_winners}

    print(
        f"season: S{season_num} Race {race_num}/30 ({league.stage_for_race(race_num)}) | "
        f"theme={recipe.theme} finale={recipe.finale}"
    )
    print(
        f"recipe: {recipe.mode} {recipe.arena} / {recipe.goal} / {recipe.hazards} / "
        f"twist={recipe.twist} relaxed={relaxed}"
    )
    print(f"cast ({len(heroes)}H+{len(extras)}D): {[h.key for h in heroes]} + {'GOLDEN' if is_grand_final else 'std'} dummies")

    trace, best, report = simulate_best(recipe, heroes, extras, seed, history=sim_hist)
    outcome, next_state, next_hof = league.evaluate_and_advance(
        season_state, trace, hall_of_fame=hof, mutate=not a.dry_run
    )
    print(
        f"best: seed={trace.meta['seed']} score={best.total:+.0f} winner={outcome.winner_key} "
        f"leader={outcome.leader_key}({outcome.leader_pts}pts) lead_changed={outcome.lead_changed}"
    )

    league_ctx = {
        "season_number": outcome.season_number,
        "episode_number": outcome.race_number,
        "stage": outcome.stage,
        "current_leader": outcome.leader_key,
        "current_leader_name": outcome.leader_name,
        "points_gap": outcome.points_gap,
        "races_remaining": outcome.races_remaining,
        "lead_changed": outcome.lead_changed,
        "pre_leader": cast_sorted[0] if cast_sorted else None,
        "pre_leader_name": HERO_BY_KEY[cast_sorted[0]].name if cast_sorted else "",
        "rival_name": HERO_BY_KEY[cast_sorted[1]].name if len(cast_sorted) > 1 else "",
        "spotlights": spotlights,
        "finalists": [h.key for h in heroes] if is_grand_final else [],
        "recent_line_ids": sorted(recent_ids),
        "recent_cliches": sorted(recent_cliches),
    }

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "season": outcome.season_number,
        "race": outcome.race_number,
        "stage": outcome.stage,
        "ribbon": outcome.ribbon_text,
        "recipe": recipe.to_dict(),
        "cast": [h.key for h in heroes],
        "extras": len(extras),
        "golden_extras": is_grand_final,
        "best_seed": trace.meta["seed"],
        "score": best.total,
        "score_parts": best.parts,
        "winner": outcome.winner_key,
        "leader": outcome.leader_key,
        "leader_pts": outcome.leader_pts,
        "top3": outcome.top3,
        "top4": outcome.top4,
        "ko_bonus": outcome.ko_bonus_key,
        "lead_changed": outcome.lead_changed,
        "resolved_at": trace.meta["resolved_at"],
        "candidates": report,
    }
    line_ids: list[str] = []
    cliches: list[str] = []
    if not a.no_render:
        from src.rendering import pipeline

        arena_short = recipe.arena.replace("_", " ").upper()
        ep_label = league.header_label(outcome.season_number, outcome.race_number, arena_short)
        ep = pipeline.Episode(
            trace,
            ep_label,
            season_line=outcome.winner_points_pill,
            prompt=comment_prompt(list(HEROES), outcome.winner_key, rng),
            flash_event=flash_event(trace),
            outcome=outcome,
            league_ctx=league_ctx,
        )
        t0 = time.time()
        info = pipeline.encode(ep, out, stills=a.stills, sound=not a.no_audio)
        info["render_s"] = round(time.time() - t0, 1)
        print(f"rendered {out} frames={info['frames']} duration={info['duration']:.1f}s in {info['render_s']}s")
        if info.get("sound"):
            line_ids = list(info["sound"].get("line_ids") or [])
            cliches = list(info["sound"].get("cliches") or [])
            print(f"sound: {info['sound']}")
        summary.update(
            video=str(out),
            duration=info["duration"],
            frames=info["frames"],
            render_s=info["render_s"],
            prompt_cta=ep.prompt,
            sound=info.get("sound"),
        )
    if not a.dry_run:
        entry = recipe_generator.history_entry(recipe, day)
        entry.update({
            "season": outcome.season_number,
            "race": outcome.race_number,
            "stage": outcome.stage,
            "winner": outcome.winner_key,
            "line_ids": list(line_ids),
            "cliches": list(cliches),
        })
        entries.append(entry)
        league.save_all_state(next_state, next_hof, entries, state_dir=STATE)
        if a.commit_state:
            ok = league.git_commit_state_safe(
                f"chore(league): S{outcome.season_number} R{outcome.race_number}/30 ({outcome.winner_key} wins)",
                ROOT,
            )
            print(f"git_commit_state_safe: {ok}")

    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
