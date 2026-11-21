"""Game recipe pools and the Recipe type (§11, v4.0).
Includes the 7 signature showcase arenas + full procedural arena/goal/hazard/twist pools."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SIDE, TOP, BOTH = "SIDE_VIEW", "TOP_DOWN", "BOTH"
WIDESCREEN = "widescreen_finale"

# Part 6: Exclusive 16:9-Native Season Finale Mega-Event (3-Round 20-Participant Championship)
WIDESCREEN_FINALE_ROUNDS: tuple[dict[str, Any], ...] = (
    {
        "round": 1,
        "key": "royal_gauntlet",
        "title": "ROUND 1 • 20-BALL ROYAL GAUNTLET",
        "arenas": ("crusher_gauntlet", "ramp_descent", "pachinko_drop"),
        "goal": "reach_finish",
        "heroes_in": 10,
        "dummies_in": 10,
        "heroes_advance": 6,
    },
    {
        "round": 2,
        "key": "shrinking_crucible",
        "title": "ROUND 2 • SHRINKING SUMO CRUCIBLE",
        "arenas": ("rotating_disc", "sumo_pool_pit"),
        "goal": "last_one_standing",
        "heroes_in": 6,
        "dummies_in": 4,
        "heroes_advance": 3,
    },
    {
        "round": 3,
        "key": "championship_bridge",
        "title": "GRAND FINAL • CHAMPIONSHIP BRIDGE",
        "arenas": ("crumbling_bridge", "narrow_bridge"),
        "goal": "reach_finish",
        "heroes_in": 3,
        "dummies_in": 6,
        "heroes_advance": 1,
    },
)

# 7 core showcase arenas + procedural variety pool
SHOWCASE_ARENAS: tuple[str, ...] = (
    "rotating_disc",
    "ramp_descent",
    "pachinko_drop",
    "sumo_pool_pit",
    "crumbling_bridge",
    "collapse_tower",
    "crusher_gauntlet",
)

ARENAS: dict[str, str] = {
    "ramp_descent": SIDE,
    "pachinko_drop": SIDE,
    "crumbling_bridge": SIDE,
    "collapse_tower": SIDE,
    "crusher_gauntlet": SIDE,
    "flat_track": SIDE,
    "pit_platforms": SIDE,
    "tiered_tower": SIDE,
    "narrow_bridge": SIDE,
    "bouncy_pad_field": SIDE,
    "seesaw_gauntlet": SIDE,
    "conveyor_chaos": SIDE,
    "rotating_disc": TOP,
    "sumo_pool_pit": TOP,
    "maze_corridors": TOP,
    "hex_tile_drop": TOP,
    "bumper_ring": TOP,
}

GOALS: dict[str, str] = {
    "reach_finish": SIDE,
    "last_one_standing": BOTH,
    "collect_items": BOTH,
    "hold_a_zone": TOP,
    "push_others_out": TOP,
    "survive_timer": BOTH,
    "hot_potato_bomb": BOTH,
}

HAZARDS: dict[str, str] = {
    "spinning_bars": BOTH,
    "swinging_hammers": SIDE,
    "falling_floor_tiles": BOTH,
    "rolling_boulders": SIDE,
    "wind_gusts": BOTH,
    "lava_floor": SIDE,
    "moving_walls": BOTH,
    "cannon_balls": BOTH,
    "slippery_ice": BOTH,
    "sticky_mud": BOTH,
}

TWISTS: dict[str, str] = {
    "low_gravity": BOTH,
    "heavy_gravity": BOTH,
    "slippery_floor": BOTH,
    "giant_ball": BOTH,
    "shrinking_arena": TOP,
    "reversed_controls": BOTH,
    "speed_boost_zones": BOTH,
    "random_teleport_pads": BOTH,
}

TWIST_ARENA_EXTRA = {"shrinking_arena": {"pit_platforms", "crumbling_bridge"}}
INCOMPATIBLE = {("slippery_ice", "slippery_floor"), ("lava_floor", "falling_floor_tiles")}
GOAL_ARENA_EXCLUDE = {
    "reach_finish": {"rotating_disc", "sumo_pool_pit", "maze_corridors", "hex_tile_drop", "bumper_ring"},
    "collect_items": {"rotating_disc", "sumo_pool_pit"},
    "hold_a_zone": {"rotating_disc", "sumo_pool_pit"},
    "survive_timer": {"rotating_disc", "sumo_pool_pit"},
}
ARENA_HAZARD_EXCLUDE = {
    "collapse_tower": {"lava_floor", "rolling_boulders", "falling_floor_tiles"},
    "crumbling_bridge": {"falling_floor_tiles", "lava_floor", "wind_gusts", "cannon_balls", "swinging_hammers"},
    "crusher_gauntlet": {"rolling_boulders", "lava_floor", "spinning_bars", "wind_gusts", "cannon_balls", "swinging_hammers"},
    "conveyor_chaos": {"lava_floor"},
    "rotating_disc": {"moving_walls", "falling_floor_tiles", "spinning_bars"},
    "sumo_pool_pit": {"moving_walls", "falling_floor_tiles", "spinning_bars"},
}


def fits(kind_mode: str, mode: str) -> bool:
    return kind_mode in (mode, BOTH)


def twist_fits(twist: str, mode: str, arena: str) -> bool:
    if twist == "random_teleport_pads" and arena in {"collapse_tower", "rotating_disc", "sumo_pool_pit"}:
        return False
    if twist in ("reversed_controls", "low_gravity") and arena in {"collapse_tower", "crusher_gauntlet"}:
        return False
    return fits(TWISTS[twist], mode) or arena in TWIST_ARENA_EXTRA.get(twist, set())


@dataclass
class Recipe:
    seed: int
    mode: str
    arena: str
    goal: str
    hazards: list[str]
    twist: str | None
    theme: str
    params: dict[str, Any] = field(default_factory=dict)
    two_stage: bool = False
    flash_forward: bool = False
    episode_kind: str = "spotlight"
    finale: bool = False

    def key(self) -> tuple:
        return (self.arena, self.goal, tuple(sorted(self.hazards)), self.twist)

    def core_combo(self) -> tuple:
        return (self.arena, self.goal, self.twist)

    def fingerprint(self) -> str:
        blob = json.dumps({"arena": self.arena, "params": self.params}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        return self.arena.replace("_", " ").upper()
