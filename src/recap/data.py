"""The Tuno Report data layer: rebuilds a season race-by-race from `state/` with the EXACT league rules.

Every published race carries a compact replay record (`entry["recap"]`, see `src/recap/record.py`; races published
before records existed live in `state/recap_backfill.json`). The table is recomputed by feeding each race's real
ranking + eliminations back through `league.evaluate_and_advance`, then verified against the live truth
(`state/season_state.json` mid-season, `state/hall_of_fame.json` once the season is archived). Read-only: never
writes `state/`.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.characters.roster import HERO_BY_KEY, HEROES
from src.games.themes import for_season
from src.physics.trace import Event, Trace
from src.recap.schedule import PART_SIZE, SEASON_LEN, part_range
from src.state import league

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state"
STAT_KEYS = ("points", "wins", "kos", "races", "rank_sum")


class RecapDataError(RuntimeError):
    """Raised when a season cannot be rebuilt faithfully (missing records or a table mismatch)."""


@dataclass
class RaceInfo:
    season: int
    race: int
    stage: str
    entry: dict[str, Any]
    record: dict[str, Any]
    arena: str
    goal: str
    hazards: list[str]
    twist: str | None
    mode: str
    winner: str
    heroes: list[str]
    hero_ranking: list[str]
    full_ranking: list[str]
    ko_counts: dict[str, int]
    ko_bonus: str | None
    points: dict[str, int]
    stats_before: dict[str, dict[str, int]]
    stats_after: dict[str, dict[str, int]]
    leader_before: str | None
    leader_after: str
    lead_changed: bool
    outcome: Any
    elims: list[dict[str, Any]]
    first_hero_out: str | None
    behind_dummy: list[str]
    youtube_id: str | None = None

    @property
    def tag(self) -> str:
        return f"s{self.season}_r{self.race:02d}"

    @property
    def standings_after(self) -> list[tuple[str, int]]:
        return [(k, int(v["points"])) for k, v in league.sorted_standings(self.stats_after)]

    @property
    def standings_before(self) -> list[tuple[str, int]]:
        return [(k, int(v["points"])) for k, v in league.sorted_standings(self.stats_before)]


@dataclass
class SeasonRecap:
    season: int
    part: int | None                 # 1..3, or None for an ad-hoc preview
    kind: str                        # part1 | part2 | part3 | preview
    start_race: int
    end_race: int
    races: list[RaceInfo]            # races 1..end_race (whole season so far: tables, title race)
    reigning_champion: str | None
    champion: str | None = None      # set for Part 3 (race 30 played)
    verified: bool = False
    verify_note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def theme(self):
        return for_season(self.season)

    @property
    def part_races(self) -> list[RaceInfo]:
        return [r for r in self.races if self.start_race <= r.race <= self.end_race]

    @property
    def final_stats(self) -> dict[str, dict[str, int]]:
        return self.races[-1].stats_after if self.races else league.fresh_stats()

    @property
    def standings(self) -> list[tuple[str, dict[str, int]]]:
        return league.sorted_standings(self.final_stats)

    def stats_entering(self, race: int) -> dict[str, dict[str, int]]:
        prev = [r for r in self.races if r.race < race]
        return prev[-1].stats_after if prev else league.fresh_stats()


# ---------------------------------------------------------------------------------------------- loading
def _load(path: Path, default: Any) -> Any:
    return league.load_json(path, default)


def load_entries(state_dir: Path = STATE_DIR) -> list[dict]:
    raw = _load(state_dir / "episode_history.json", {"entries": []})
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    return [e for e in entries if isinstance(e, dict)]


def load_backfill(state_dir: Path = STATE_DIR) -> dict[str, dict]:
    raw = _load(state_dir / "recap_backfill.json", {"records": {}})
    recs = raw.get("records", {}) if isinstance(raw, dict) else {}
    return {str(k): v for k, v in recs.items() if isinstance(v, dict)}


def season_entries(entries: list[dict], season: int) -> dict[int, dict]:
    """Published entries of `season` keyed by race (the last published entry wins if a race was ever re-run)."""
    out: dict[int, dict] = {}
    for e in entries:
        try:
            if int(e.get("season") or 0) == season and e.get("published") is True:
                out[int(e.get("race") or 0)] = e
        except (TypeError, ValueError):
            continue
    return out


def record_for(entry: dict, backfill: dict[str, dict]) -> dict | None:
    rec = entry.get("recap") if isinstance(entry.get("recap"), dict) else None
    if rec is None:
        rec = backfill.get(f"s{int(entry.get('season') or 0)}_r{int(entry.get('race') or 0)}")
    if not rec or not rec.get("ranking") or not rec.get("heroes"):
        return None
    return rec


def mini_trace(record: dict) -> Trace:
    """Smallest Trace that `league.evaluate_and_advance` accepts: real ranking, winner, cast and eliminations."""
    keys = [str(k) for k in record.get("ranking") or []]
    tr = Trace(fps=30, mode=str((record.get("recipe") or {}).get("mode") or "SIDE_VIEW"), keys=keys)
    tr.meta = {"heroes": list(record.get("heroes") or []), "ranking": keys, "winner": record.get("winner"),
               "resolved_at": record.get("resolved_at")}
    tr.events = [Event(float(e.get("t") or 0.0), "elimination", [str(a) for a in e.get("actors") or []],
                       {"cause": e.get("cause"), "hero": bool(e.get("hero")), "by_hero": bool(e.get("by_hero"))})
                 for e in record.get("elims") or []]
    return tr


def _clean_stats(stats: dict) -> dict[str, dict[str, int]]:
    out = league.fresh_stats()
    for k, v in (stats or {}).items():
        if k in out and isinstance(v, dict):
            out[k] = {s: int(v.get(s, 0) or 0) for s in STAT_KEYS}
    return out


def _stats_from_hof_standings(rows: list[dict]) -> dict[str, dict[str, int]]:
    out = league.fresh_stats()
    for row in rows or []:
        k = row.get("hero")
        if k in out:
            out[k] = {s: int(row.get(s, 0) or 0) for s in STAT_KEYS}
    return out


def _reigning_for(season: int, state_dir: Path) -> str | None:
    if season <= 1:
        return None
    hof = _load(state_dir / "hall_of_fame.json", {"seasons": []})
    for s in hof.get("seasons", []) if isinstance(hof, dict) else []:
        if int(s.get("season_number") or 0) == season - 1:
            return s.get("champion")
    st = _load(state_dir / "season_state.json", {})
    if isinstance(st, dict) and int(st.get("season_number") or 0) == season:
        return st.get("reigning_champion")
    return None


# ---------------------------------------------------------------------------------------------- rebuild
def _race_info(season: int, race: int, entry: dict, record: dict, state: dict, outcome: Any,
               stats_after: dict[str, dict[str, int]], leader_before: str | None) -> RaceInfo:
    stats_before = _clean_stats(state["stats"])
    tr = mini_trace(record)
    hero_set = set(record.get("heroes") or [])
    ranking_all = list(record.get("ranking") or [])
    hero_ranking = [k for k in ranking_all if k in hero_set and k in HERO_BY_KEY]
    for hk in record.get("heroes") or []:
        if hk in HERO_BY_KEY and hk not in hero_ranking:
            hero_ranking.append(hk)
    winner = outcome.winner_key
    if winner in hero_ranking:
        hero_ranking.remove(winner)
    hero_ranking.insert(0, winner)
    ko_counts: dict[str, int] = {}
    for e in tr.events:
        if len(e.actors) > 1 and e.actors[1] in hero_set and e.actors[1] != e.actors[0]:
            ko_counts[e.actors[1]] = ko_counts.get(e.actors[1], 0) + 1
    points = {k: int(stats_after[k]["points"]) - int(stats_before[k]["points"]) for k in stats_after
              if int(stats_after[k]["points"]) != int(stats_before[k]["points"])}
    elims = sorted((dict(e) for e in record.get("elims") or []), key=lambda e: float(e.get("t") or 0.0))
    first_out = next((e["actors"][0] for e in elims if e.get("hero") and e.get("actors")), None)
    extras_idx = [i for i, k in enumerate(ranking_all) if str(k).startswith("extra")]
    behind = []
    if extras_idx:
        best_dummy = min(extras_idx)
        behind = [k for k in hero_ranking[1:] if k in ranking_all and ranking_all.index(k) > best_dummy]
    recipe = record.get("recipe") or {}
    return RaceInfo(
        season=season, race=race, stage=league.stage_for_race(race), entry=entry, record=record,
        arena=str(entry.get("arena") or recipe.get("arena") or ""), goal=str(entry.get("goal") or recipe.get("goal") or ""),
        hazards=list(entry.get("hazards") or recipe.get("hazards") or []),
        twist=entry.get("twist") if "twist" in entry else recipe.get("twist"),
        mode=str(entry.get("mode") or recipe.get("mode") or "SIDE_VIEW"),
        winner=winner, heroes=list(record.get("heroes") or []), hero_ranking=hero_ranking, full_ranking=ranking_all,
        ko_counts=ko_counts, ko_bonus=outcome.ko_bonus_key, points=points, stats_before=stats_before,
        stats_after=stats_after, leader_before=leader_before, leader_after=outcome.leader_key,
        lead_changed=bool(outcome.lead_changed), outcome=outcome, elims=elims, first_hero_out=first_out,
        behind_dummy=behind, youtube_id=entry.get("youtube_id"),
    )


def rebuild_season(season: int, state_dir: Path = STATE_DIR, upto: int | None = None) -> tuple[list[RaceInfo], dict]:
    """Replays every published race of `season` (1..upto, default = latest published) through the league engine.
    Returns (races, info) where info has `latest`, `champion`, `final_stats`, `reigning`."""
    entries = load_entries(state_dir)
    backfill = load_backfill(state_dir)
    by_race = season_entries(entries, season)
    if not by_race:
        raise RecapDataError(f"season {season} has no published races")
    latest = max(by_race)
    last = min(latest, int(upto)) if upto else latest
    missing = [r for r in range(1, last + 1) if r not in by_race]
    if missing:
        raise RecapDataError(f"season {season} is missing published races {missing}")
    reigning = _reigning_for(season, state_dir)
    state = league.fresh_season_state(season_number=season, reigning_champion=reigning, total_day=1)
    hof: dict = {"seasons": []}
    races: list[RaceInfo] = []
    champion = None
    for r in range(1, last + 1):
        rec = record_for(by_race[r], backfill)
        if rec is None:
            raise RecapDataError(f"S{season} R{r} has no replay record (entry.recap / recap_backfill.json)")
        state["race_number"] = r
        prev = league.sorted_standings(state["stats"])
        leader_before = prev[0][0] if prev and prev[0][1]["races"] > 0 else None
        outcome, nxt, hof = league.evaluate_and_advance(state, mini_trace(rec), hall_of_fame=hof, mutate=True)
        if r >= SEASON_LEN:
            stats_after = _stats_from_hof_standings(hof["seasons"][-1]["standings"])
            champion = outcome.winner_key
        else:
            stats_after = _clean_stats(nxt["stats"])
        races.append(_race_info(season, r, by_race[r], rec, state, outcome, stats_after, leader_before))
        if r < SEASON_LEN:
            state = nxt
    return races, {"latest": latest, "last": last, "champion": champion, "reigning": reigning,
                   "final_stats": races[-1].stats_after}


def verify_against_truth(season: int, races: list[RaceInfo], latest: int, state_dir: Path = STATE_DIR) -> tuple[bool, str]:
    """Compares the rebuilt table after the LATEST published race with the live state / Hall of Fame."""
    if not races or races[-1].race != latest:
        return False, f"rebuilt up to race {races[-1].race if races else 0}, latest published is {latest}"
    rebuilt = races[-1].stats_after
    if latest >= SEASON_LEN:
        hof = _load(state_dir / "hall_of_fame.json", {"seasons": []})
        rows = next((s.get("standings") for s in hof.get("seasons", []) if int(s.get("season_number") or 0) == season), None)
        if rows is None:
            return False, "season archived in history but missing from hall_of_fame.json"
        truth = _stats_from_hof_standings(rows)
        src = "hall_of_fame.json"
    else:
        st = _load(state_dir / "season_state.json", {})
        if not isinstance(st, dict) or int(st.get("season_number") or 0) != season or int(st.get("race_number") or 0) != latest + 1:
            return False, "season_state.json is not at this season's next race"
        truth = _clean_stats(st.get("stats") or {})
        src = "season_state.json"
    bad = [k for k in truth if truth[k] != rebuilt.get(k)]
    if bad:
        return False, f"table mismatch vs {src} for {bad}"
    return True, f"rebuilt table matches {src} after race {latest}"


def build_recap(season: int, kind: str, state_dir: Path = STATE_DIR, end_race: int | None = None,
                strict: bool = True) -> SeasonRecap:
    """kind = part1|part2|part3 (fixed thirds) or preview (races 1..end_race / latest)."""
    full, info = rebuild_season(season, state_dir)
    ok, note = verify_against_truth(season, full, info["latest"], state_dir)
    if strict and not ok:
        raise RecapDataError(f"refusing to build recap: {note}")
    if kind.startswith("part"):
        part = int(kind[-1])
        start, end = part_range(part)
    else:
        part = None
        end = min(int(end_race or info["latest"]), info["latest"])
        start = max(1, end - PART_SIZE + 1)
    if end > info["latest"]:
        raise RecapDataError(f"{kind} needs race {end}, latest published is {info['latest']}")
    races = [r for r in full if r.race <= end]
    return SeasonRecap(
        season=season, part=part, kind=kind, start_race=start, end_race=end, races=races,
        reigning_champion=info["reigning"], champion=(races[-1].winner if end >= SEASON_LEN else None),
        verified=ok, verify_note=note,
    )


# ---------------------------------------------------------------------------------------------- part stats
def part_stats(recap: SeasonRecap) -> dict[str, dict[str, int]]:
    """Per-hero counters over the part's races: wins, seconds, kos, behind_dummy, first_out, eliminated, points."""
    out = {h.key: {"wins": 0, "seconds": 0, "kos": 0, "behind_dummy": 0, "first_out": 0, "eliminated": 0,
                   "points": 0, "races": 0} for h in HEROES}
    for r in recap.part_races:
        for k in r.heroes:
            if k in out:
                out[k]["races"] += 1
        out[r.winner]["wins"] += 1
        if len(r.hero_ranking) > 1:
            out[r.hero_ranking[1]]["seconds"] += 1
        for k, n in r.ko_counts.items():
            out[k]["kos"] += n
        for k in r.behind_dummy:
            out[k]["behind_dummy"] += 1
        if r.first_hero_out in out:
            out[r.first_hero_out]["first_out"] += 1
        for e in r.elims:
            v = (e.get("actors") or [None])[0]
            if e.get("hero") and v in out:
                out[v]["eliminated"] += 1
        for k, p in r.points.items():
            if k in out:
                out[k]["points"] += int(p)
    return out


def deep_copy_recap(recap: SeasonRecap) -> SeasonRecap:
    return copy.deepcopy(recap)


def dump_summary(recap: SeasonRecap) -> str:
    rows = [{"race": r.race, "stage": r.stage, "arena": r.arena, "winner": r.winner, "top3": r.hero_ranking[:3],
             "points": r.points, "leader": r.leader_after} for r in recap.part_races]
    return json.dumps({"season": recap.season, "kind": recap.kind, "range": [recap.start_race, recap.end_race],
                       "verified": recap.verified, "note": recap.verify_note, "races": rows}, indent=2)
