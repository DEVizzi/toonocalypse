"""Per-mode micro-AI (§10.1, §10.7). Force-based: capped forces toward the target while directional speed < max.
Personalities come from Behaviour(aggression, caution, jumpiness, edge_awareness) and hero traits.
"""
from __future__ import annotations

import math

import pymunk

from src.games.base import SIDE
from src.physics.engine import CT_BODY, Contestant, Sim

ACCEL = 900.0          # px/s^2 at full drive
AIR_CONTROL = 0.35
JUMP_V = 470.0


class Brain:
    def __init__(self, sim: Sim) -> None:
        self.sim = sim
        self.ray_filter = pymunk.ShapeFilter()

    def think(self, sim: Sim) -> None:
        for c in sim.contestants:
            if not c.alive:
                continue
            c.jump_cd = max(0.0, c.jump_cd - 1 / 30)
            c.shove_cd = max(0.0, c.shove_cd - 1 / 30)
            c.trait_cd -= 1 / 30
            self._grounded(sim, c)
            if c.hero is not None:
                self._traits(sim, c)
            if c.stun > 0 or c.finished:
                continue
            if sim.mode == SIDE:
                self._side(sim, c)
            else:
                self._top(sim, c)

    # ------------------------------------------------------------------ shared
    def _grounded(self, sim: Sim, c: Contestant) -> None:
        grounded = False

        def check(arb):
            nonlocal grounded
            other = arb.shapes[1] if arb.shapes[0].body is c.body else arb.shapes[0]
            if other.collision_type != CT_BODY or True:
                n = arb.normal if arb.shapes[0].body is c.body else -arb.normal
                if n.y > 0.45:
                    grounded = True

        c.body.each_arbiter(check)
        c.grounded = grounded if sim.mode == SIDE else True
        c.air_time = 0.0 if c.grounded else c.air_time + 1 / 30

    def _drive(self, sim: Sim, c: Contestant, dx: float, dy: float, mult: float = 1.0) -> None:
        """Apply a capped force toward (dx, dy) only while speed in that direction < max_speed."""
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return
        dx, dy = dx / n, dy / n
        if sim.reversed_until > sim.t and (c.hero is None or c.hero.trait != "glitch"):
            dx, dy = -dx, -dy
        surf = 1.0
        for mod in sim.surface_mods:
            surf *= mod(c)
        vmax = c.max_speed * sim.speed_mult * surf
        v = c.body.velocity
        along = v.x * dx + v.y * dy
        if along >= vmax:
            return
        k = mult * (1.0 if c.grounded else AIR_CONTROL) * min(1.0, (vmax - along) / max(1.0, vmax * 0.35))
        c.body.apply_force_at_world_point((dx * ACCEL * c.body.mass * k, dy * ACCEL * c.body.mass * k), c.body.position)

    def _jump(self, c: Contestant, vx_boost: float = 0.0, k: float = 1.0) -> None:
        if c.jump_cd > 0 or not c.grounded:
            return
        c.body.apply_impulse_at_world_point((vx_boost * c.body.mass, -JUMP_V * k * c.body.mass), c.body.position)
        c.jump_cd = 0.55

    def _ray(self, sim: Sim, a, b):
        return sim.space.segment_query_first(a, b, 2, self.ray_filter)

    # ------------------------------------------------------------------ SIDE_VIEW
    def _side(self, sim: Sim, c: Contestant) -> None:
        bh = c.behaviour
        x, y = c.pos
        target_dx = 1.0
        goal_dir = sim.goal.direction(c) if hasattr(sim.goal, "direction") else None
        if goal_dir is not None:
            target_dx = goal_dir
        look = 120.0 if (c.hero and c.hero.trait == "lookahead") else 60.0 + 40.0 * bh.caution
        ahead = x + math.copysign(look + c.radius, target_dx)
        # gap ahead: no ground under a point in front
        ground_ahead = self._ray(sim, (ahead, y), (ahead, y + 260))
        wall_ahead = self._ray(sim, (x + math.copysign(c.radius + 4, target_dx), y - c.radius * 0.3),
                               (ahead, y - c.radius * 0.3))
        danger = sim.arena.danger(c, look + 40)
        wants_jump = (ground_ahead is None) or (wall_ahead is not None and getattr(wall_ahead.shape, "contestant", None) is None) or danger
        if wants_jump and c.grounded:
            if sim.rng.random() < 0.35 + 0.6 * bh.jumpiness:
                self._jump(c, vx_boost=60 * target_dx, k=1.0 + (0.15 if ground_ahead is None else 0.0))
        caution = 1.0 - 0.35 * bh.caution if danger else 1.0
        self._drive(sim, c, target_dx, 0.0, caution)
        # shove a rival that is level and close, weighted by aggression
        if c.shove_cd <= 0 and sim.rng.random() < 0.04 * bh.aggression:
            rival = self._nearest(sim, c, 70)
            if rival is not None:
                rx, ry = rival.pos
                d = math.hypot(rx - x, ry - y) or 1
                k = 260 * c.body.mass
                c.body.apply_impulse_at_world_point(((rx - x) / d * k, -40 * c.body.mass), c.body.position)
                c.shove_cd = 1.4

    # ------------------------------------------------------------------ TOP_DOWN
    def _top(self, sim: Sim, c: Contestant) -> None:
        bh = c.behaviour
        x, y = c.pos
        tx, ty = sim.goal.target(c)
        dx, dy = tx - x, ty - y
        # edge avoidance: steer inward when close to the walkable boundary
        edge = sim.arena.edge_distance(x, y)
        margin = 60 + 120 * bh.edge_awareness
        if edge < margin:
            cx, cy = sim.arena.center
            inward = (cx - x, cy - y)
            w = (margin - edge) / margin * (1.5 + bh.edge_awareness)
            dx, dy = dx + inward[0] * w, dy + inward[1] * w
        jitter = sim.rng.uniform(-0.3, 0.3)
        dx, dy = dx * math.cos(jitter) - dy * math.sin(jitter), dx * math.sin(jitter) + dy * math.cos(jitter)
        self._drive(sim, c, dx, dy)
        # shove attempts weighted by aggression
        if c.shove_cd <= 0 and sim.rng.random() < 0.06 * bh.aggression:
            rival = self._nearest(sim, c, 90)
            if rival is not None:
                rx, ry = rival.pos
                d = math.hypot(rx - x, ry - y) or 1
                k = 300 * c.body.mass
                c.body.apply_impulse_at_world_point(((rx - x) / d * k, (ry - y) / d * k), c.body.position)
                c.shove_cd = 1.6

    def _nearest(self, sim: Sim, c: Contestant, rng: float) -> Contestant | None:
        best, bd = None, rng
        x, y = c.pos
        for o in sim.contestants:
            if o is c or not o.alive:
                continue
            d = math.hypot(o.pos[0] - x, o.pos[1] - y) - o.radius - c.radius
            if d < bd:
                best, bd = o, d
        return best

    # ------------------------------------------------------------------ hero traits
    def _traits(self, sim: Sim, c: Contestant) -> None:
        h = c.hero
        assert h is not None
        if h.trait == "auto_hop" and c.grounded and c.jump_cd <= 0 and sim.mode == SIDE:
            self._jump(c, vx_boost=90, k=0.8)
            c.jump_cd = 0.35
            if c.air_time == 0 and sim.rng.random() < 0.02:
                sim.trait(c, "double_ricochet")
        elif h.trait == "glitch" and c.trait_cd <= 0:
            c.trait_cd = 2.2
            roll = sim.rng.random()
            if roll < 0.4:
                c.body.mass = sim.rng.uniform(*(h.mass_range or (1.5, 6.5)))
                c.shape.elasticity = sim.rng.uniform(0.2, 0.95)
                c.max_speed = sim.rng.uniform(*(h.speed_range or (160, 400)))
                sim.event("glitch", [c.key], c.pos, kind="mutate")
            else:
                danger_before = sim.arena.danger(c, 90)
                ang = sim.rng.uniform(0, 2 * math.pi)
                d = sim.rng.uniform(25, 60)
                c.body.position = (c.body.position.x + math.cos(ang) * d, c.body.position.y + (math.sin(ang) * d if sim.mode != SIDE else -abs(math.sin(ang)) * d))
                sim.event("glitch", [c.key], c.pos, kind="blink")
                if danger_before and not sim.arena.danger(c, 90):
                    sim.trait(c, "blink_save")
        elif h.trait == "spite":
            # +15% recovery impulse near elimination boundaries
            if sim.arena.danger(c, 70) and c.stun <= 0:
                if sim.mode == SIDE:
                    c.body.apply_force_at_world_point((0.15 * ACCEL * c.body.mass, -0.15 * 980 * c.body.mass), c.body.position)
                else:
                    cx, cy = sim.arena.center
                    x, y = c.pos
                    d = math.hypot(cx - x, cy - y) or 1
                    c.body.apply_force_at_world_point(((cx - x) / d * 0.15 * ACCEL * 2 * c.body.mass,
                                                       (cy - y) / d * 0.15 * ACCEL * 2 * c.body.mass), c.body.position)
                c.score += 0  # spite meter is computed from survival near edges in beats
                if sim.rng.random() < 0.01:
                    sim.trait(c, "spite_save")
        elif h.trait == "bowling":
            recent = {k for t, k in c.contacts if sim.t - t < 1.2}
            if len(recent) >= 4:
                sim.trait(c, "bowling", pins=len(recent))
