"""Best-of-N excitement scorer (§12). Scores a finished trace from its real events; the system only picks."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config import TIMELINE, settings
from src.physics.trace import Trace

SIGNATURE = {"wind_launch", "bowling", "blink_save", "double_ricochet", "wall_slam", "spite_save"}


@dataclass
class Score:
    total: float
    parts: dict[str, float] = field(default_factory=dict)


def score(trace: Trace, history: dict | None = None) -> Score:
    """history: {'recent_winners': [...last 6], 'losing_streak': {key: n}, 'nemesis': {winner: [rivals]}}"""
    history = history or {}
    ev = trace.events
    end = trace.meta.get("resolved_at") or trace.duration
    heroes = set(trace.meta.get("heroes", []))
    winner = trace.meta.get("winner")
    p: dict[str, float] = {}
    # +25 per lead change in the final 6 s
    p["late_lead_changes"] = 25 * sum(1 for e in ev if e.kind == "lead_change" and e.t >= end - 6)
    # +18 per hero-on-hero elimination
    p["hero_on_hero"] = 18 * sum(1 for e in ev if e.kind == "elimination" and e.data.get("hero") and e.data.get("by_hero"))
    # +15 per mass wipeout (>=5 eliminations from one cause within 1.5 s)
    elims = sorted((e for e in ev if e.kind == "elimination"), key=lambda e: e.t)
    wipeouts, i = 0, 0
    while i < len(elims):
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.5:
            j += 1
        same = [e for e in elims[i:j] if e.data.get("cause") == elims[i].data.get("cause")]
        if len(same) >= 5:
            wipeouts += 1
            i = j
        else:
            i += 1
    p["mass_wipeouts"] = 15 * wipeouts
    # +12 per signature-trait moment
    p["signature"] = 12 * sum(1 for e in ev if e.kind == "trait" and e.data.get("name") in SIGNATURE)
    # +10 underdog / rivalry
    streak = history.get("losing_streak", {}).get(winner, 0)
    nemesis = history.get("nemesis", {}).get(winner, [])
    beat_nemesis = any(k in nemesis for k in trace.meta.get("ranking", [])[1:4])
    p["underdog"] = 10 if (winner in heroes and (streak >= 3 or beat_nemesis)) else 0
    # +8 cult-extra moment
    extra_kills_hero = any(e.kind == "elimination" and e.data.get("hero") and len(e.actors) > 1 and e.actors[1].startswith("extra")
                           for e in ev)
    extra_wins = bool(winner and winner.startswith("extra"))
    p["cult_extra"] = 8 if (extra_kills_hero or extra_wins) else 0
    # +6 winner variety
    p["variety"] = 6 if winner and winner not in history.get("recent_winners", [])[-6:] else 0
    # penalties
    hero_elims = [e.t for e in elims if e.data.get("hero")]
    p["all_heroes_early"] = -40 if heroes and len(hero_elims) >= len(heroes) and max(hero_elims) < 10 else 0
    lo, hi = TIMELINE.gameplay_target_min_s, TIMELINE.hard_stop_s
    rules = trace.meta.get("arena_rules") or {}
    true_ko = trace.meta.get("recipe", {}).get("arena") in ("rotating_disc", "sumo_pool_pit") or bool(rules.get("true_ko"))
    if true_ko:
        hi = 30.0                      # v3.3/v4.0: plays to genuine ALIVE: 1/X finish (natural 19-26 s)
    if rules.get("max_s"):
        hi = float(rules["max_s"])
    if (trace.meta.get("recipe", {}).get("params") or {}).get("single_winner"):
        hi = float(settings()["scorer"].get("single_winner_cap_s", 75))   # v6: plays to ALIVE: 1, any length
    p["duration"] = -50 if not (lo <= end <= hi) else 0
    how = next((e.data.get("how") for e in ev if e.kind == "win"), None)
    p["forced_finish"] = settings()["scorer"]["reject_penalty"] if (true_ko and how != "last_standing") else 0
    rate = len(elims) / max(1, len(trace.keys))
    goal = trace.meta.get("recipe", {}).get("goal")
    target_rate = 0.6 if goal not in ("reach_finish", "collect_items", "hold_a_zone") else 0.35
    p["elimination_rate"] = -30 if rate < target_rate else 0
    hero_ev = sorted(e.t for e in ev if e.actors and any(a in heroes for a in e.actors)
                     and e.kind in ("elimination", "impact", "trait", "lead_change", "teleport", "collect", "bomb_pass"))
    min_ev = 1 if len(heroes) <= 3 else 2
    dull = any(sum(1 for t in hero_ev if w <= t < w + 10) < min_ev for w in range(0, max(1, int(end) - 9), 2))
    p["dull_window"] = -25 if dull else 0
    # v3.0 hard locks (owner): a named hero must win; first blood by 3.5 s; no dead 5 s stretch mid-episode
    sc = settings()["scorer"]
    p["dummy_win"] = sc["dummy_win_penalty"] if winner and winner.startswith("extra") else 0
    first = min((e.t for e in elims), default=99.0)
    fb_limit = sc["first_blood_s"] * (1.35 if len(trace.keys) <= 10 else 1.0)
    if rules.get("first_blood_s"):
        fb_limit = max(fb_limit, float(rules["first_blood_s"]))
    crushes = [e.t for e in ev if e.kind == "crush_hit"]
    if trace.meta.get("recipe", {}).get("arena") == "crusher_gauntlet":
        # v4.3: the opening run-in deliberately keeps Golden Dummies alive into the first crushers -> the first
        # on-screen SQUASH counts as first blood, inside a 5.2 s window
        first = min([first] + crushes)
        fb_limit = max(fb_limit, sc["first_blood_s"] + 1.7)
    p["late_first_blood"] = sc["reject_penalty"] if first > fb_limit else 0
    imp_floor = sc["major_impulse"] * (0.65 if len(trace.keys) <= 10 else 1.0)
    action = sorted(
        [e.t for e in elims] + crushes
        + [e.t for e in ev if e.kind == "impact" and e.data.get("impulse", 0) >= imp_floor]
        + ([e.t for e in ev if e.kind in ("trait", "lead_change")] if len(trace.keys) <= 10 else [])
    )
    max_gap = sc["dead_stretch_s"] * (1.3 if len(trace.keys) <= 10 else 1.0)
    gaps = [b - a for a, b in zip([0.0] + action, action + [end])]
    p["dead_stretch"] = sc["reject_penalty"] if any(g > max_gap for g in gaps[1:-1]) else 0
    return Score(sum(p.values()), p)


def rejected(s: Score) -> bool:
    """Hard-rule violations (Best-of-N never picks these if any valid run exists)."""
    return any(s.parts.get(k, 0) < 0 for k in ("dummy_win", "late_first_blood", "dead_stretch", "duration", "forced_finish"))


def min_score() -> float:
    return float(settings()["scorer"]["min_score"])
