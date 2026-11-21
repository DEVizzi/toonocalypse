"""One-time backfill of replay records for races published before `entry["recap"]` existed (S1 R1).

Re-runs the exact daily pipeline steps (recipe generator -> cast -> Best-of-N physics) for a known supervisor seed,
then refuses to write anything unless ALL of these match the published race:
  1. recipe layout fingerprint == `episode_history.json` fingerprint,
  2. winner == published winner,
  3. post-race league table == `state/season_state.json` from the race's own state commit
     (`git show <sha>:state/season_state.json`, commit "chore(league): S{s} R{r}/30 ...").

    python -m src.recap.backfill --season 1 --race 1 --search            # find the supervisor seed (fingerprint)
    python -m src.recap.backfill --season 1 --race 1 --seed 22959 --code-sha 6938488 --write
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from src.games import recipe_generator
from src.games.themes import for_season
from src.recap import data
from src.recap.record import build_record
from src.state import league

ROOT = Path(__file__).resolve().parents[2]
BACKFILL = ROOT / "state" / "recap_backfill.json"
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def truth_stats_after(season: int, race: int) -> dict:
    """League table committed right after S{season} R{race} (its own `chore(league)` state commit)."""
    log = _git("log", "--format=%H %s", "--", "state/season_state.json")
    pat = re.compile(rf"^([0-9a-f]{{40}}) chore\(league\): S{season} R{race}/30\b")
    sha = next((m.group(1) for m in (pat.match(ln) for ln in log.splitlines()) if m), None)
    if not sha:
        raise data.RecapDataError(f"no state commit found for S{season} R{race}")
    st = json.loads(_git("show", f"{sha}:state/season_state.json"))
    return data._clean_stats(st.get("stats") or {})


def _context(season: int, race: int):
    entries = data.load_entries()
    idx = next((i for i, e in enumerate(entries) if int(e.get("season") or 0) == season
                and int(e.get("race") or 0) == race and e.get("published") is True), None)
    if idx is None:
        raise data.RecapDataError(f"S{season} R{race} not found in episode_history.json")
    prior = entries[:idx]
    if race > 1:
        races, _ = data.rebuild_season(season, upto=race - 1)
        stats = races[-1].stats_after
    else:
        stats = league.fresh_stats()
    pre = league.fresh_season_state(season_number=season, reigning_champion=data._reigning_for(season, data.STATE_DIR))
    pre["stats"] = copy.deepcopy(stats)
    pre["race_number"] = race
    return entries[idx], prior, pre


def _recipe_and_cast(entry: dict, prior: list, pre: dict, seed: int):
    recipe, _ = recipe_generator.generate(prior, int(entry.get("day") or 1), seed,
                                          season_theme=for_season(int(pre["season_number"])).key)
    rng = random.Random(seed)
    heroes, extras, gf = league.select_cast_for_race(copy.deepcopy(pre), rng)
    recipe.finale = gf
    recipe.episode_kind = "rumble_final" if gf else "spotlight"
    return recipe, heroes, extras


def search_seed(season: int, race: int, lo: int = 10000, hi: int = 100000) -> list[int]:
    """Supervisor seeds whose recipe layout fingerprint (incl. arena-sampled params) matches the published race."""
    from src.physics.engine import Sim

    entry, prior, pre = _context(season, race)
    hits = []
    for s in range(lo, hi):
        r, _ = recipe_generator.generate(prior, int(entry.get("day") or 1), s,
                                         season_theme=for_season(season).key)
        if (r.arena, r.goal, sorted(r.hazards), r.twist) != (entry.get("arena"), entry.get("goal"),
                                                              sorted(entry.get("hazards") or []), entry.get("twist")):
            continue
        recipe, heroes, extras = _recipe_and_cast(entry, prior, pre, s)
        Sim(recipe, heroes, extras, s * 1000)
        if recipe.fingerprint() == entry.get("fingerprint"):
            hits.append(s)
    return hits


def backfill(season: int, race: int, seed: int, code_sha: str | None, write: bool, log=print) -> dict:
    from src import main as ep_main

    entry, prior, pre = _context(season, race)
    recipe, heroes, extras = _recipe_and_cast(entry, prior, pre, seed)
    recent = [e.get("winner") for e in prior[-6:] if e.get("winner")]
    trace, best, _ = ep_main.simulate_best(recipe, heroes, extras, seed, history={"recent_winners": recent}, log=log)
    checks = {
        "fingerprint": recipe.fingerprint() == entry.get("fingerprint"),
        "winner": trace.meta.get("winner") == entry.get("winner"),
    }
    _, nxt, _ = league.evaluate_and_advance(pre, trace, hall_of_fame={"seasons": []}, mutate=True)
    try:
        checks["table"] = data._clean_stats(nxt["stats"]) == truth_stats_after(season, race)
    except (data.RecapDataError, subprocess.CalledProcessError, ValueError) as exc:
        log(f"[BACKFILL] table truth unavailable: {exc}")
        checks["table"] = False
    log(f"[BACKFILL] S{season} R{race} seed={seed} best_sim_seed={trace.meta.get('seed')} "
        f"winner={trace.meta.get('winner')} checks={checks}")
    if not all(checks.values()):
        raise data.RecapDataError(f"backfill verification failed: {checks}")
    sha = code_sha if (code_sha and _SHA_RE.match(code_sha)) else None
    rec = build_record(seed, recipe, heroes, extras, trace, code_sha=sha)
    if write:
        raw = league.load_json(BACKFILL, {"records": {}})
        raw.setdefault("records", {})[f"s{season}_r{race}"] = rec
        raw["note"] = ("Replay records for races published before entry.recap existed. Written only by "
                       "`python -m src.recap.backfill --write` after fingerprint + winner + table verification.")
        league.atomic_write_json(BACKFILL, raw)
        log(f"[BACKFILL] wrote {BACKFILL.relative_to(ROOT)} -> s{season}_r{race}")
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill Tuno Report replay records for legacy races")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--code-sha", default=None)
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if a.search:
        print(json.dumps({"hits": search_seed(a.season, a.race)}))
        return 0
    if a.seed is None:
        raise SystemExit("--seed is required (use --search first)")
    backfill(a.season, a.race, a.seed, a.code_sha, a.write)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
