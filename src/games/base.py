"""Game recipe pools and the Recipe type (§11). Recipe = Arena + Goal + Hazards(1-3) + Twist(0-1) + Theme."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SIDE, TOP, BOTH = "SIDE_VIEW", "TOP_DOWN", "BOTH"

ARENAS: dict[str, str] = {
    "flat_track": SIDE, "ramp_descent": SIDE, "pit_platforms": SIDE, "tiered_tower": SIDE, "narrow_bridge": SIDE,
    "bouncy_pad_field": SIDE, "seesaw_gauntlet": SIDE, "conveyor_chaos": SIDE,
    "rotating_disc": TOP, "maze_corridors": TOP, "hex_tile_drop": TOP, "bumper_ring": TOP,
}
GOALS: dict[str, str] = {
    "reach_finish": SIDE, "last_one_standing": BOTH, "collect_items": BOTH, "hold_a_zone": TOP,
    "push_others_out": TOP, "survive_timer": BOTH, "hot_potato_bomb": BOTH,
}
HAZARDS: dict[str, str] = {
    "spinning_bars": BOTH, "swinging_hammers": SIDE, "falling_floor_tiles": BOTH, "rolling_boulders": SIDE,
    "wind_gusts": BOTH, "lava_floor": SIDE, "moving_walls": BOTH, "cannon_balls": BOTH, "slippery_ice": BOTH,
    "sticky_mud": BOTH,
}
TWISTS: dict[str, str] = {
    "low_gravity": SIDE, "heavy_gravity": SIDE, "slippery_floor": BOTH, "giant_ball": BOTH, "shrinking_arena": TOP,
    "reversed_controls": BOTH, "speed_boost_zones": BOTH, "random_teleport_pads": BOTH,
}
# Extra arena-specific compatibility (shrinking_arena also works on pit_platforms per §11.4).
TWIST_ARENA_EXTRA = {"shrinking_arena": {"pit_platforms"}}
# Combos that don't make sense physically or visually.
INCOMPATIBLE = {("slippery_ice", "sticky_mud"), ("slippery_ice", "slippery_floor"), ("lava_floor", "falling_floor_tiles")}
# Goals that need a finish line vs. goals that need an elimination mechanic.
GOAL_ARENA_EXCLUDE = {"reach_finish": {"rotating_disc", "maze_corridors", "hex_tile_drop", "bumper_ring"}}


def fits(kind_mode: str, mode: str) -> bool:
    return kind_mode in (mode, BOTH)


def twist_fits(twist: str, mode: str, arena: str) -> bool:
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
    params: dict[str, Any] = field(default_factory=dict)   # procedural arena parameters
    two_stage: bool = False
    flash_forward: bool = False
    episode_kind: str = "spotlight"                       # spotlight | rivalry | rumble_qualifier | rumble_final

    def key(self) -> tuple:
        return (self.arena, self.goal, tuple(sorted(self.hazards)), self.twist)

    def fingerprint(self) -> str:
        blob = json.dumps({"arena": self.arena, "params": self.params}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        return self.arena.replace("_", " ").upper()
