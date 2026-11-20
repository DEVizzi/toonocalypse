"""Twists (§11.4): triggered visibly by Lord Tuno's lever (a 'twist' event the renderer turns into a lever pull)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pymunk

from src.games.base import SIDE

if TYPE_CHECKING:
    from src.physics.engine import Sim


class Twist:
    key = ""
    at = 5.0                 # owner pacing override (was 8 s)

    def __init__(self, sim: "Sim") -> None:
        self.sim = sim
        self.r = sim.rng
        self.on = False
        self.at = sim.recipe.params.setdefault("twist_at", round(self.r.uniform(7.0, 11.0), 1))
        sim.hooks_frame.append(self._frame)
        self.setup()

    def setup(self) -> None: ...

    def _frame(self, t: float) -> None:
        if not self.on and t >= self.at:
            self.on = True
            self.sim.event("twist", [], None, twist=self.key)
            self.trigger()
        if self.on:
            self.tick(t)

    def trigger(self) -> None: ...

    def tick(self, t: float) -> None: ...

    def zone_state(self) -> dict[str, Any]:
        return {"twist_on": self.on}


class LowGravity(Twist):
    key = "low_gravity"

    def trigger(self):
        self.sim.set_gravity_scale(0.55)


class HeavyGravity(Twist):
    key = "heavy_gravity"

    def trigger(self):
        self.sim.set_gravity_scale(1.55)


class SlipperyFloor(Twist):
    key = "slippery_floor"

    def trigger(self):
        self.sim.friction_scale = 0.2

    def tick(self, t):
        for c in self.sim.alive():
            if c.hero and c.hero.trait == "traction":
                continue
            base = c.hero.friction if c.hero else 0.6
            c.shape.friction = min(c.shape.friction, base * 0.2)
        if self.sim.mode != "SIDE_VIEW":
            self.sim.space.damping = 0.97


class GiantBall(Twist):
    key = "giant_ball"

    def setup(self):
        self.at = self.sim.recipe.params["twist_at"] = 7.0

    def trigger(self):
        body = pymunk.Body(40, pymunk.moment_for_circle(40, 0, 70))
        if self.sim.mode == SIDE:
            x = self.sim.cam_x + self.r.uniform(-100, 300)
            body.position = (x, self.sim.arena.ground_y_at(x) - 700)
            body.velocity = (self.r.uniform(-60, 120), 0)
        else:
            body.position = (self.r.uniform(-120, 120), self.r.uniform(-120, 120))
            body.velocity = (self.r.uniform(-260, 260), self.r.uniform(-260, 260))
        shape = pymunk.Circle(body, 70)
        self.ball = self.sim.add_prop(body, [shape], "giant_ball")
        shape.elasticity, shape.friction = 0.5, 0.6


class ShrinkingArena(Twist):
    key = "shrinking_arena"

    def setup(self):
        self.at = self.sim.recipe.params["twist_at"] = 3.0
        self.k = 1.0

    def trigger(self):
        base = self.sim.walkable
        self.base = base
        if self.sim.mode == SIDE:   # pit_platforms: the abyss creeps upward
            return
        self.sim.walkable = lambda x, y: base(x / self.k, y / self.k) if base else True

    def tick(self, t):
        if self.sim.mode == SIDE:
            self.sim.kill_y -= 3.0 * self.sim.speed_mult / 30
        else:
            self.k = max(0.4, self.k - 0.012 * self.sim.speed_mult / 30 * 2)

    def zone_state(self):
        return {"twist_on": self.on, "shrink": self.k, "kill_y": self.sim.kill_y}


class ReversedControls(Twist):
    key = "reversed_controls"

    def tick(self, t):
        ph = (t - self.at) % 8.0
        if ph < 0.05:
            self.sim.event("reverse", [], None)
        if ph < 2.2:
            self.sim.reversed_until = t + 1 / 30


class SpeedBoostZones(Twist):
    key = "speed_boost_zones"

    def trigger(self):
        self.zones = []
        if self.sim.mode == SIDE:
            for i in range(5):
                x = self.sim.cam_x + 300 + i * 700 + self.r.uniform(-100, 100)
                self.zones.append(("rect", x, x + 200))
        else:
            for k in range(3):
                a = self.r.uniform(0, 6.28)
                self.zones.append(("circle", (math.cos(a) * 200, math.sin(a) * 200), 70))
        self.sim.surface_mods.append(self.mod)

    def mod(self, c):
        x, y = c.pos
        for z in self.zones:
            if (z[0] == "rect" and z[1] <= x <= z[2]) or (z[0] == "circle" and math.hypot(x - z[1][0], y - z[1][1]) < z[2]):
                return 2.4
        return 1.0

    def zone_state(self):
        return {"twist_on": self.on, "boost_zones": getattr(self, "zones", [])}


class RandomTeleportPads(Twist):
    key = "random_teleport_pads"

    def trigger(self):
        self.pads = []
        if self.sim.mode == SIDE:
            for i in range(4):
                x = self.sim.cam_x + 350 + i * 650
                self.pads.append((x, self.sim.arena.ground_y_at(x)))
        else:
            for k in range(4):
                a = 2 * math.pi * k / 4 + 0.4
                self.pads.append((math.cos(a) * 220, math.sin(a) * 220))
        self.cd: dict[str, float] = {}

    def tick(self, t):
        for c in self.sim.alive():
            if self.cd.get(c.key, -9) > t:
                continue
            x, y = c.pos
            for px, py in self.pads:
                if abs(x - px) < 40 and abs(y - py) < 50:
                    self.cd[c.key] = t + 2.0
                    if self.sim.mode == SIDE:
                        back = self.r.random() < 0.35
                        nx = 300.0 if back else x + self.r.uniform(400, 800)
                        c.body.position = (nx, self.sim.arena.ground_y_at(nx) - 80)
                    else:
                        tx, ty = self.r.choice(self.pads)
                        c.body.position = (tx * 0.4, ty * 0.4)
                        back = False
                    self.sim.event("teleport", [c.key], c.pos, back=back)
                    break

    def zone_state(self):
        return {"twist_on": self.on, "pads": getattr(self, "pads", [])}


TWIST_CLASSES = {t.key: t for t in (LowGravity, HeavyGravity, SlipperyFloor, GiantBall, ShrinkingArena, ReversedControls,
                                     SpeedBoostZones, RandomTeleportPads)}


def make(key: str, sim: "Sim") -> Twist:
    return TWIST_CLASSES[key](sim)
