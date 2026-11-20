"""v4.0 IPL-Style 30-Episode Season League & Autonomous Multi-Season State Engine.

Manages `state/season_state.json`, `state/hall_of_fame.json`, and `state/episode_history.json` with atomic `.tmp` +
`os.replace` writes so 180+ daily executions never corrupt state:
- Races 1-26 (League Stage): All 10 Heroes + 4 Crash Dummies. Points: 1st +10, 2nd +5, 3rd +3, Most KOs +2.
  Tie-breakers: Total Wins -> Total KOs -> Average Finish Rank.
- Race 27 (Play-In Wildcard): Ranks #4-#10 (7 Heroes) + 4 Dummies -> winner claims #4 Playoff Seed.
- Race 28 (Qualifier 1): Ranks #1 vs #2 + 6 Dummies -> winner to Grand Final, loser to Qualifier 2.
- Race 29 (Qualifier 2): Loser of Q1 vs #3 vs #4 (Wildcard) + 6 Dummies -> Top 2 Heroes advance to Grand Final.
- Race 30 (THE GRAND FINAL): 3 Finalist Heroes + 6 Golden Crash Dummies on gold-trimmed finale arena -> Season Champion!
- Automatic Day-31 Rollover: Archives champion & table to `hall_of_fame.json`, grants reigning Champion a persistent Gold
  Champion Star (★) throughout Season N+1, resets points to 0, increments season_number, activates next SeasonTheme."""
from __future__ import annotations

import copy
import json
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.characters.roster import HERO_BY_KEY, HEROES, Extra, Hero, make_extras
from src.config import STATE_DIR
from src.games.themes import for_season
from src.physics.trace import Trace

SEASON_LEN = 30
LEAGUE_RACES = 26
POINTS_TABLE = {0: 10, 1: 5, 2: 3}
KO_BONUS_PTS = 2


def atomic_write_json(path: Path, payload: Any) -> None:
    """Atomic JSON write (.tmp + fsync + os.replace) safe against power/runner interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(default)


def fresh_stats() -> dict[str, dict[str, Any]]:
    return {
        h.key: {"points": 0, "wins": 0, "kos": 0, "races": 0, "rank_sum": 0}
        for h in HEROES
    }


def fresh_season_state(season_number: int = 1, reigning_champion: str | None = None, total_day: int = 1) -> dict[str, Any]:
    return {
        "season_number": season_number,
        "race_number": 1,
        "total_day": total_day,
        "theme": for_season(season_number).key,
        "reigning_champion": reigning_champion,
        "stats": fresh_stats(),
        "playoff": {
            "seeds": [],            # [#1, #2, #3] locked after Race 26
            "wildcard_winner": None,
            "q1_winner": None,
            "q1_loser": None,
            "q2_advancers": [],
            "finalists": [],
            "champion": None,
        },
    }


def load_season_state(state_dir: Path = STATE_DIR) -> dict[str, Any]:
    st = load_json(state_dir / "season_state.json", None)
    if not isinstance(st, dict) or "season_number" not in st or "stats" not in st:
        return fresh_season_state(1, None, 1)
    for h in HEROES:
        st["stats"].setdefault(h.key, {"points": 0, "wins": 0, "kos": 0, "races": 0, "rank_sum": 0})
    st.setdefault("playoff", {})
    st["theme"] = for_season(int(st["season_number"])).key
    return st


def sorted_standings(stats: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Sorts heroes by Points DESC -> Total Wins DESC -> Total KOs DESC -> Avg Finish Rank ASC."""
    def key_fn(item: tuple[str, dict[str, Any]]) -> tuple:
        k, s = item
        avg_rank = s["rank_sum"] / max(1, s["races"]) if s["races"] > 0 else 99.0
        return (-int(s["points"]), -int(s["wins"]), -int(s["kos"]), round(avg_rank, 4), k)

    return sorted(stats.items(), key=key_fn)


def assert_standings_sorted(points: list[int]) -> None:
    """Winner Card guard: standings[i].pts >= standings[i+1].pts must hold for every row before rendering."""
    for i in range(len(points) - 1):
        if points[i] < points[i + 1]:
            raise AssertionError(f"standings out of order at row {i + 1}: {points[i]} < {points[i + 1]} ({points})")


def stage_for_race(race_number: int) -> str:
    if race_number <= LEAGUE_RACES:
        return "league"
    return {
        27: "play_in",
        28: "qualifier_1",
        29: "qualifier_2",
        30: "grand_final",
    }.get(race_number, "league")


def header_label(season_number: int, race_number: int, arena_label: str) -> str:
    st = stage_for_race(race_number)
    if st == "play_in":
        return f"S{season_number} • PLAY-IN • {arena_label}"
    if st == "qualifier_1":
        return f"S{season_number} • QUALIFIER 1"
    if st == "qualifier_2":
        return f"S{season_number} • QUALIFIER 2"
    if st == "grand_final":
        return f"S{season_number} • GRAND FINAL"
    return f"S{season_number} R{race_number}/30 • {arena_label}"


def card_ribbon_label(season_number: int, race_number: int) -> str:
    st = stage_for_race(race_number)
    if st == "play_in":
        return f"SEASON {season_number} • PLAY-IN WILDCARD"
    if st == "qualifier_1":
        return f"SEASON {season_number} • QUALIFIER 1"
    if st == "qualifier_2":
        return f"SEASON {season_number} • QUALIFIER 2"
    if st == "grand_final":
        return f"SEASON {season_number} • GRAND FINAL"
    return f"SEASON {season_number} • RACE {race_number} / 30"


def select_cast_for_race(state: dict[str, Any], rng: random.Random) -> tuple[list[Hero], list[Extra], bool]:
    """Returns (heroes, extras, is_grand_final) according to the exact 30-episode IPL League format."""
    rnum = int(state["race_number"])
    st = stage_for_race(rnum)
    table = [k for k, _ in sorted_standings(state["stats"])]
    po = state.setdefault("playoff", {})

    if st == "league":
        return list(HEROES), make_extras(4, rng, golden=False), False

    if st == "play_in":
        # Ranks #4-#10 (7 Heroes) + 4 Dummies
        keys = table[3:10]
        return [HERO_BY_KEY[k] for k in keys], make_extras(4, rng, golden=False), False

    if st == "qualifier_1":
        # Ranks #1 vs #2 + 6 Crash Dummies
        seeds = po.get("seeds") or table[:3]
        keys = seeds[:2]
        return [HERO_BY_KEY[k] for k in keys], make_extras(6, rng, golden=False), False

    if st == "qualifier_2":
        # Loser of Q1 vs #3 vs #4 (Wildcard Winner) + 6 Dummies
        seeds = po.get("seeds") or table[:3]
        q1_loser = po.get("q1_loser") or seeds[1]
        seed3 = seeds[2] if len(seeds) >= 3 else table[2]
        wc = po.get("wildcard_winner") or table[3]
        keys = list(dict.fromkeys([q1_loser, seed3, wc]))
        for fallback_k in table:
            if len(keys) >= 3:
                break
            if fallback_k not in keys and fallback_k != po.get("q1_winner"):
                keys.append(fallback_k)
        return [HERO_BY_KEY[k] for k in keys[:3]], make_extras(6, rng, golden=False), False

    # Episode 30: THE GRAND FINAL — 3 Finalist Heroes + 6 Golden Crash Dummies!
    finalists = list(po.get("finalists") or [])
    if len(finalists) < 3:
        q1w = po.get("q1_winner") or table[0]
        q2a = po.get("q2_advancers") or [k for k in table if k != q1w][:2]
        finalists = list(dict.fromkeys([q1w] + list(q2a)))
        for k in table:
            if len(finalists) >= 3:
                break
            if k not in finalists:
                finalists.append(k)
    return [HERO_BY_KEY[k] for k in finalists[:3]], make_extras(6, rng, golden=True), True


@dataclass
class EpisodeOutcome:
    """Snapshot of season standings & race awards AFTER the current race, used by Winner Card & Commentary."""
    season_number: int
    race_number: int
    stage: str
    ribbon_text: str
    winner_key: str
    winner_points_pill: str
    ko_bonus_key: str | None
    winner_got_ko_bonus: bool
    leader_key: str
    leader_name: str
    leader_pts: int
    points_gap: int
    lead_changed: bool
    races_remaining: int
    right_status_text: str
    top3: list[tuple[str, int]]       # [(hero_key, points), ...]
    reigning_champion: str | None     # wears Gold Champion Star (★)
    is_grand_final: bool
    top4: list[tuple[str, int, int]] = None        # [(hero_key, post-race points, points earned THIS race)]
    pre_leader_key: str | None = None
    ko_pill_text: str | None = None                # always "+2 KO: {HERO}"
    podium: list[str] = None                       # Grand Final finish order (champion first), no points shown


def evaluate_and_advance(state: dict[str, Any], trace: Trace, hall_of_fame: dict[str, Any] | None = None,
                         mutate: bool = True) -> tuple[EpisodeOutcome, dict[str, Any], dict[str, Any]]:
    """Computes race points/KO bonus/playoff advancement, builds EpisodeOutcome for Winner Card, and rolls over after Ep 30."""
    st = copy.deepcopy(state)
    hof = copy.deepcopy(hall_of_fame) if hall_of_fame is not None else {"seasons": []}
    snum = int(st["season_number"])
    rnum = int(st["race_number"])
    stage = stage_for_race(rnum)
    reigning = st.get("reigning_champion")

    prev_standings = sorted_standings(st["stats"])
    prev_leader = prev_standings[0][0] if prev_standings and prev_standings[0][1]["races"] > 0 else None

    hero_set = set(trace.meta.get("heroes", []))
    ranking_all = list(trace.meta.get("ranking") or [])
    hero_ranking = [k for k in ranking_all if k in hero_set and k in HERO_BY_KEY]
    for hk in hero_set:
        if hk in HERO_BY_KEY and hk not in hero_ranking:
            hero_ranking.append(hk)
    winner_key = trace.meta.get("winner")
    if not winner_key or winner_key not in HERO_BY_KEY:
        winner_key = hero_ranking[0] if hero_ranking else HEROES[0].key
    if winner_key in hero_ranking:
        hero_ranking.remove(winner_key)
    hero_ranking.insert(0, winner_key)

    # Attribution of Hero KOs in this race
    ko_counts: dict[str, int] = {k: 0 for k in hero_ranking}
    for e in trace.events:
        if e.kind == "elimination" and len(e.actors) > 1:
            killer = e.actors[1]
            if killer in ko_counts and killer != e.actors[0]:
                ko_counts[killer] += 1
    for k, cnt in ko_counts.items():
        st["stats"][k]["kos"] += cnt

    max_kos = max(ko_counts.values(), default=0)
    ko_bonus_key: str | None = None
    if max_kos >= 1:
        # Tie-break KO bonus by better finish order in this race
        ko_bonus_key = next(k for k in hero_ranking if ko_counts.get(k, 0) == max_kos)

    po = st.setdefault("playoff", {})
    winner_pts_earned = 0
    race_delta: dict[str, int] = {}

    if stage == "league":
        for idx, hk in enumerate(hero_ranking):
            pts = POINTS_TABLE.get(idx, 0)
            st["stats"][hk]["points"] += pts
            st["stats"][hk]["races"] += 1
            st["stats"][hk]["rank_sum"] += (idx + 1)
            if pts:
                race_delta[hk] = race_delta.get(hk, 0) + pts
            if idx == 0:
                st["stats"][hk]["wins"] += 1
                winner_pts_earned = pts
        if ko_bonus_key is not None:
            st["stats"][ko_bonus_key]["points"] += KO_BONUS_PTS
            race_delta[ko_bonus_key] = race_delta.get(ko_bonus_key, 0) + KO_BONUS_PTS
        if rnum == LEAGUE_RACES:
            locked = [k for k, _ in sorted_standings(st["stats"])]
            po["seeds"] = locked[:3]
        win_pill = f"+{winner_pts_earned} PTS"
    elif stage == "play_in":
        st["stats"][winner_key]["wins"] += 1
        po["wildcard_winner"] = winner_key
        win_pill = "#4 PLAYOFF SEED!"
    elif stage == "qualifier_1":
        st["stats"][winner_key]["wins"] += 1
        po["q1_winner"] = winner_key
        losers = [k for k in hero_ranking if k != winner_key]
        po["q1_loser"] = losers[0] if losers else sorted_standings(st["stats"])[1][0]
        win_pill = "GRAND FINAL BERTH!"
    elif stage == "qualifier_2":
        st["stats"][winner_key]["wins"] += 1
        adv = hero_ranking[:2]
        po["q2_advancers"] = adv
        q1w = po.get("q1_winner") or sorted_standings(st["stats"])[0][0]
        po["finalists"] = list(dict.fromkeys([q1w] + adv))[:3]
        adv_names = " & ".join(HERO_BY_KEY[k].name.upper() for k in adv)
        win_pill = f"ADVANCE: {adv_names}"
    else:  # grand_final
        st["stats"][winner_key]["wins"] += 1
        po["champion"] = winner_key
        win_pill = "SEASON CHAMPION!"

    # v4.3 P0: ALL post-race points (+10/+5/+3 & +2 KO) are applied above BEFORE this sort; re-assert strict order
    new_standings = sorted_standings(st["stats"])
    assert_standings_sorted([int(s["points"]) for _, s in new_standings])
    leader_key, leader_stat = new_standings[0]
    runner_pts = int(new_standings[1][1]["points"]) if len(new_standings) > 1 else 0
    leader_pts = int(leader_stat["points"])
    points_gap = max(0, leader_pts - runner_pts)
    # Strict: only when the sorted post-race #1 differs from the sorted pre-race #1 (league races only)
    lead_changed = bool(stage == "league" and prev_leader is not None and leader_key != prev_leader)
    races_rem = max(0, SEASON_LEN - rnum)

    if rnum == 26:
        right_txt = "PLAYOFFS NEXT!"
    elif rnum == 27:
        right_txt = "QUALIFIER 1 NEXT!"
    elif rnum == 28:
        right_txt = "QUALIFIER 2 NEXT!"
    elif rnum == 29:
        right_txt = "GRAND FINAL NEXT!"
    elif rnum == 30:
        right_txt = "SEASON CHAMPION!"
    else:
        right_txt = f"{races_rem} RACES LEFT"

    ko_key_out = ko_bonus_key if stage == "league" else None
    outcome = EpisodeOutcome(
        season_number=snum,
        race_number=rnum,
        stage=stage,
        ribbon_text=card_ribbon_label(snum, rnum),
        winner_key=winner_key,
        winner_points_pill=win_pill,
        ko_bonus_key=ko_key_out,
        winner_got_ko_bonus=bool(ko_key_out is not None and ko_key_out == winner_key),
        leader_key=leader_key,
        leader_name=HERO_BY_KEY[leader_key].name,
        leader_pts=leader_pts,
        points_gap=points_gap,
        lead_changed=lead_changed,
        races_remaining=races_rem,
        right_status_text=right_txt,
        top3=[(k, int(s["points"])) for k, s in new_standings[:3]],
        reigning_champion=reigning,
        is_grand_final=(stage == "grand_final"),
        top4=[(k, int(s["points"]), int(race_delta.get(k, 0))) for k, s in new_standings[:4]],
        pre_leader_key=prev_leader,
        ko_pill_text=(f"+{KO_BONUS_PTS} KO: {HERO_BY_KEY[ko_key_out].name.upper()}" if ko_key_out else None),
        podium=list(hero_ranking[:3]) if stage == "grand_final" else None,
    )

    if mutate:
        st["total_day"] = int(st.get("total_day", 1)) + 1
        if rnum >= SEASON_LEN:
            # Automatic Day-31 Season Rollover!
            hof.setdefault("seasons", []).append({
                "season_number": snum,
                "theme": st.get("theme"),
                "champion": winner_key,
                "finalists": po.get("finalists", hero_ranking[:3]),
                "standings": [
                    {"rank": idx + 1, "hero": k, **vals}
                    for idx, (k, vals) in enumerate(new_standings)
                ],
            })
            st = fresh_season_state(
                season_number=snum + 1,
                reigning_champion=winner_key,
                total_day=st["total_day"],
            )
        else:
            st["race_number"] = rnum + 1

    return outcome, st, hof


def mock_season_state(season_number: int, race_number: int, seed: int = 101) -> dict[str, Any]:
    """Deterministically synthesizes realistic IPL standings up to `race_number` for showcase/audit renders."""
    rng = random.Random(season_number * 1009 + seed)
    reigning = rng.choice(HEROES).key if season_number > 1 else None
    st = fresh_season_state(season_number=season_number, reigning_champion=reigning,
                            total_day=(season_number - 1) * SEASON_LEN + race_number)
    st["race_number"] = race_number

    n_prior_league = min(LEAGUE_RACES, max(0, race_number - 1))
    keys = [h.key for h in HEROES]
    # Give each hero a slight seasonal form bias so realistic title races emerge
    weights = {k: rng.uniform(0.75, 1.45) for k in keys}
    for _ in range(n_prior_league):
        order = sorted(keys, key=lambda k: rng.random() * weights[k], reverse=True)
        for idx, hk in enumerate(order):
            pts = POINTS_TABLE.get(idx, 0)
            st["stats"][hk]["points"] += pts
            st["stats"][hk]["races"] += 1
            st["stats"][hk]["rank_sum"] += (idx + 1)
            if idx == 0:
                st["stats"][hk]["wins"] += 1
        ko_leader = rng.choice(order[:5])
        st["stats"][ko_leader]["kos"] += rng.randint(2, 4)
        st["stats"][ko_leader]["points"] += KO_BONUS_PTS
        for hk in rng.sample(keys, 4):
            st["stats"][hk]["kos"] += 1

    table = [k for k, _ in sorted_standings(st["stats"])]
    po = st["playoff"]
    if race_number > LEAGUE_RACES:
        po["seeds"] = table[:3]
    if race_number > 27:
        po["wildcard_winner"] = rng.choice(table[3:7])
    if race_number > 28:
        q1_pair = list(po["seeds"][:2])
        rng.shuffle(q1_pair)
        po["q1_winner"], po["q1_loser"] = q1_pair[0], q1_pair[1]
    if race_number > 29:
        q2_pool = [po["q1_loser"], po["seeds"][2], po["wildcard_winner"]]
        rng.shuffle(q2_pool)
        po["q2_advancers"] = q2_pool[:2]
        po["finalists"] = [po["q1_winner"]] + po["q2_advancers"]
    return st


def save_all_state(state: dict[str, Any], hall_of_fame: dict[str, Any], history_entries: list[dict],
                   state_dir: Path = STATE_DIR) -> None:
    atomic_write_json(state_dir / "season_state.json", state)
    atomic_write_json(state_dir / "hall_of_fame.json", hall_of_fame)
    atomic_write_json(state_dir / "episode_history.json", {"entries": history_entries})


def git_commit_state_safe(message: str, repo_dir: Path) -> bool:
    """Pulls with `--rebase` before committing `state/` so 180+ scheduled CI runs never conflict."""
    try:
        subprocess.run(["git", "pull", "--rebase"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "state/"], cwd=repo_dir, check=True, capture_output=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
        if diff.returncode == 0:
            return True
        subprocess.run(["git", "commit", "-m", message], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
