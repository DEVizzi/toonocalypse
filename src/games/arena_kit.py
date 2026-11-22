"""v6 arena kit: shared building blocks + the registry for the 23 new arenas (src/games/arenas_v6/*).

Every new arena is a normal `Arena` subclass registered with `@register(...)`. The registry carries everything the rest
of the pipeline needs (display name, SEO feature phrase, MC Tuno quips, allowed goals/hazards/twists, playoff role), so
group modules never edit shared files.

Optional arena hooks (all duck-typed; omit what you don't need):
  progress(c) -> float          ranking/tiebreak "distance" (higher = better). Default: x (SIDE) / -dist (TOP)
  at_finish(c) -> bool          SIDE: custom finish test (gold bin, top of a climb...). Needs sim.finish_x != None
  drive_dir(c) -> +1/-1         SIDE: which way the AI should roll
  safe_target(c) -> (x,y)|None  TOP: steer here instead of the goal target (tile about to drop, beam incoming...)
  brake(c) -> bool              AI: True = no propulsion this frame + friction-limited braking (Red Light)
  jump_hint(c) -> True|False|None   SIDE AI: True = jump now, False = never jump now, None = default behaviour
  no_drive = True               AI never propels (pure physics arenas: Plinko, Pinball)
  fixed_rect = (x0,y0,x1,y1)    Shorts camera locked on this world rect (fixed single-screen arenas)
  vertical_tower = True         no chasing fire wall / LEFT BEHIND (towers + fixed screens)
  ascent = True                 tower camera follows UPWARD quickly (climbs)
  no_shrink = True              TOP: skip the generic edge shrink (arena handles its own squeeze)
  no_quake = True               TOP: skip the 1.35 s opening floor buck
  true_finish = True            only end at a genuine last-ball-standing (until the disc hard stop)
  rules = {...}                 scorer overrides: first_blood_s, max_s, true_ko
All randomness MUST come from `self.sim.rng` (or params stored in `self.p`) so races replay exactly.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pymunk

from src.games.arenas import Course, TopArena
from src.games.base import SIDE, TOP

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Prop, Sim

REGISTRY: dict[str, type] = {}
INFO: dict[str, dict[str, Any]] = {}


def register(key: str, mode: str, name: str, feature: str, quips: tuple[str, ...], goals: tuple[str, ...],
             hazards: tuple[str, ...] = (), twists: tuple[str, ...] | None = None, playoff: str | None = None,
             weight: float = 1.0):
    """Registers an arena class. `goals` = allowed goals (first one is the default). `hazards` = allowed hazard keys
    (empty = none). `twists` = allowed twists (None = any twist that fits the mode). `playoff` = 'qualifier_1' |
    'grand_final' for playoff-only specials (never drawn in league races)."""
    def deco(cls):
        cls.key = key
        REGISTRY[key] = cls
        INFO[key] = {"mode": mode, "name": name, "feature": feature, "quips": tuple(quips), "goals": tuple(goals),
                     "hazards": tuple(hazards), "twists": None if twists is None else tuple(twists),
                     "playoff": playoff, "weight": float(weight)}
        return cls
    return deco


def v6_info(key: str) -> dict[str, Any]:
    """Registry entry for a v6 arena ({} for legacy arenas). Imports the arena package lazily."""
    if not REGISTRY:
        from src.games import arenas_v6  # noqa: F401
    return INFO.get(key, {})


# ---------------------------------------------------------------------------------------------- helpers
def kin_body(sim: "Sim", pos=(0.0, 0.0)) -> pymunk.Body:
    b = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
    b.position = pos
    return b


def kin_box(sim: "Sim", center, w: float, h: float, style: str, material: str = "ground",
            radius: float = 4.0) -> "Prop":
    """Kinematic rectangle prop (platform, raft, door, wall...). Move it via prop.body.position / velocity."""
    b = kin_body(sim, center)
    s = pymunk.Poly.create_box(b, (w, h), radius=radius)
    return sim.add_prop(b, [s], style, material=material)


def kin_circle(sim: "Sim", center, r: float, style: str, material: str = "ground") -> "Prop":
    b = kin_body(sim, center)
    s = pymunk.Circle(b, r)
    return sim.add_prop(b, [s], style, material=material)


def move_kin(prop: "Prop", x: float, y: float, dt: float, angle: float | None = None) -> None:
    """Moves a kinematic prop to (x, y) this step, setting its velocity so riders are carried by friction."""
    b = prop.body
    if dt > 0:
        b.velocity = ((x - b.position.x) / dt, (y - b.position.y) / dt)
    b.position = (x, y)
    if angle is not None:
        if dt > 0:
            b.angular_velocity = (angle - b.angle) / dt
        b.angle = angle


def park(prop: "Prop") -> None:
    """Hide a kinematic prop far away (cheaper than remove/re-add)."""
    prop.body.position = (9000.0, 9000.0)
    prop.body.velocity = (0.0, 0.0)


def riders(sim: "Sim", x0: float, x1: float, top_y: float, tol: float = 14.0) -> list["Contestant"]:
    """Alive contestants resting on a horizontal surface spanning [x0, x1] whose top is at top_y."""
    out = []
    for c in sim.alive():
        x, y = c.pos
        if x0 - 4 <= x <= x1 + 4 and top_y - c.radius - tol <= y <= top_y + tol * 0.5:
            out.append(c)
    return out


def load_mass(cs) -> float:
    return sum(float(c.body.mass) for c in cs)


def in_rect(c: "Contestant", x0: float, y0: float, x1: float, y1: float) -> bool:
    x, y = c.pos
    return x0 <= x <= x1 and y0 <= y <= y1


def polar(r: float, a: float) -> tuple[float, float]:
    return math.cos(a) * r, math.sin(a) * r


def zap(sim: "Sim", c: "Contestant", ix: float, iy: float, stun: float = 0.5, name: str = "zap", **data) -> None:
    """Knock a contestant with an impulse (per unit mass) + stun, and log an arena event the recap can narrate."""
    m = c.body.mass
    c.body.apply_impulse_at_world_point((ix * m, iy * m), c.body.position)
    c.stun = max(c.stun, stun * (c.hero.stun_mult if c.hero else 1.0))
    sim.event("arena_hit", [c.key], c.pos, name=name, **data)


# ---------------------------------------------------------------------------------------------- base classes
class V6Course(Course):
    """Side-view course (scrolling camera + chasing fire wall) for v6 arenas."""
    rules: dict[str, Any] = {}


class FixedScreen(Course):
    """A single locked 9:16 screen (Needle Drop, Plinko, Pinball, Wall Rush). World rect is fixed_rect; no chasing
    wall; the arena eliminates contestants itself (needles, spikes, drains) through `self.kill(c, cause)`."""
    vertical_tower = True
    rules: dict[str, Any] = {"first_blood_s": 6.0}
    RECT = (0.0, 0.0, 1080.0, 1500.0)

    def __init__(self, sim: "Sim") -> None:
        super().__init__(sim)
        self.fixed_rect = self.RECT

    def floor_y(self, x: float):                     # no "fell below the course" rule: arena-specific kills only
        return None

    def setup_screen(self) -> None:
        x0, y0, x1, y1 = self.fixed_rect
        sim = self.sim
        sim.bounds = (x0 - 40, y0 - 40, x1 + 40, y1 + 40)
        sim.kill_y = y1 + 260
        sim.finish_x = 1e9                           # enables the per-substep at_finish() check
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)

    def walls(self, thick: float = 14.0, material: str = "wall", floor: bool = False) -> None:
        x0, y0, x1, y1 = self.fixed_rect
        self.sim.static_segment((x0, y0 - 400), (x0, y1), material, radius=thick)
        self.sim.static_segment((x1, y0 - 400), (x1, y1), material, radius=thick)
        if floor:
            self.sim.static_segment((x0, y1), (x1, y1), "ground", radius=thick)

    def kill(self, c: "Contestant", cause: str) -> None:
        self.sim.eliminate(c, cause)


class ClimbTower(Course):
    """Upward vertical race: tower camera that follows the pack UP, rising danger from below, finish at the top."""
    vertical_tower = True
    ascent = True
    rules: dict[str, Any] = {"first_blood_s": 6.5}

    def floor_y(self, x: float):
        return None


class V6Top(TopArena):
    """Top-down v6 arena base."""
    rules: dict[str, Any] = {}

    def frame_top(self, half: float) -> None:
        super().frame_top(half)


__all__ = ["REGISTRY", "INFO", "register", "kin_body", "kin_box", "kin_circle", "move_kin", "park", "riders",
           "load_mass", "in_rect", "polar", "zap", "V6Course", "FixedScreen", "ClimbTower", "V6Top", "SIDE", "TOP"]
