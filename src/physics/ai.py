"""Per-mode micro-AI (§10, v3.0 ball physics). Everything is a real rolling body: no velocity overwrites, ever.

SIDE_VIEW: rolling torque (grip-limited by traction) + a mild slope-tangent push, only while grounded. Airborne or
knocked (stun) bodies get zero propulsion: pure ballistics, spin and bounce. Cooldown-gated physics hops at gaps and
low walls. TOP_DOWN: steering forces scaled by traction x mass, so slippery balls drift and grippy balls cling.
Personalities come from Behaviour(aggression, caution, jumpiness, edge_awareness) and hero traits.
"""
from __future__ import annotations

import math

import pymunk

from src.games.base import SIDE
from src.physics.engine import CT_BODY, Contestant, Sim

ACCEL = 900.0          # TOP steering px/s^2 at full drive (before traction)
ROLL_ACCEL = 620.0     # SIDE rolling acceleration from torque at traction 1.0
PUSH_ACCEL = 240.0     # SIDE slope-tangent push px/s^2 (not traction-limited: Dash still glides forward)
JUMP_V = 440.0


class Brain:
    def __init__(self, sim: Sim) -> None:
        self.sim = sim
        self.ray_filter = pymunk.ShapeFilter()

    def think(self, sim: Sim) -> None:
        for c in sim.contestants:
            c.drive = (0.0, 0.0)
            c.drive_torque = 0.0
            if not c.alive:
                continue
            c.jump_cd = max(0.0, c.jump_cd - 1 / 30)
            c.shove_cd = max(0.0, c.shove_cd - 1 / 30)
            c.trait_cd -= 1 / 30
            self._grounded(sim, c)
            if c.hero is not None:
                self._traits(sim, c)
            if c.stun > 0 or c.finished or sim.t < c.panic_until:
                continue
            if sim.mode == SIDE:
                self._side(sim, c)
            else:
                self._top(sim, c)

    # ------------------------------------------------------------------ shared
    def _grounded(self, sim: Sim, c: Contestant) -> None:
        best = None

        def check(arb):
            nonlocal best
            n = arb.normal if arb.shapes[0].body is c.body else -arb.normal
            if n.y > 0.30 and (best is None or n.y > best.y):     # a supporting surface below the ball
                best = n

        c.body.each_arbiter(check)
        c.grounded = (best is not None) if sim.mode == SIDE else True
        c.ground_n = best if best is not None else pymunk.Vec2d(0, 1)  # type: ignore[attr-defined]
        c.air_time = 0.0 if c.grounded else c.air_time + 1 / 30

    @staticmethod
    def reversed(sim: Sim, c: Contestant) -> bool:
        return sim.reversed_until > sim.t and (c.hero is None or c.hero.trait != "glitch")

    def _panic(self, sim: Sim, c: Contestant) -> None:
        """Crash dummies sometimes freeze in cartoon panic at a drop or hazard."""
        if c.extra is not None and sim.rng.random() < sim.cfg["extras"]["panic_per_s"] / 30:
            c.panic_until = sim.t + sim.rng.uniform(*sim.cfg["extras"]["panic_s"])

    def _vmax(self, sim: Sim, c: Contestant) -> float:
        surf = 1.0
        for mod in sim.surface_mods:
            surf *= mod(c)
        v = c.max_speed * sim.speed_mult * surf
        if c.hero is not None and c.hero.trait == "bowling" and sim.mode == SIDE:
            # v3.2: slow lumbering flat roll, crushing downhill momentum when slope tilts downward
            gn = getattr(c, "ground_n", pymunk.Vec2d(0, 1))
            downhill = max(0.0, float(gn.x))
            if downhill > 0.14:
                v *= 1.0 + sim.cfg["juggernaut_momentum"] * min(1.3, max(0.2, c.body.velocity.x / max(1.0, c.max_speed)))
        return v

    def _jump(self, c: Contestant, vx_boost: float = 0.0, k: float = 1.0) -> None:
        if c.jump_cd > 0 or not c.grounded:
            return
        if c.hero is not None and c.hero.trait == "glide":
            k *= 1.12
            vx_boost *= 1.35
        c.body.apply_impulse_at_world_point((vx_boost * c.body.mass, -JUMP_V * k * c.body.mass), c.body.position)
        c.jump_cd = 0.6

    def _ray(self, sim: Sim, a, b):
        return sim.space.segment_query_first(a, b, 2, self.ray_filter)

    # ------------------------------------------------------------------ SIDE_VIEW
    def _side(self, sim: Sim, c: Contestant) -> None:
        bh = c.behaviour
        x, y = c.pos
        dirx = 1.0
        goal_dir = sim.goal.direction(c) if hasattr(sim.goal, "direction") else None
        if goal_dir is not None:
            dirx = goal_dir
        if self.reversed(sim, c):
            dirx = -dirx
        vx = abs(c.body.velocity.x)
        look = 120.0 if (c.hero and c.hero.trait == "lookahead") else max(40.0, vx * 0.22) + 25.0 * bh.caution
        ahead = x + math.copysign(look + c.radius, dirx)
        ground_ahead = self._ray(sim, (ahead, y), (ahead, y + 300))
        wall = self._ray(sim, (x + math.copysign(c.radius + 4, dirx), y - c.radius * 0.2), (ahead, y - c.radius * 0.2))
        wall_ahead = wall is not None and getattr(wall.shape, "contestant", None) is None
        danger = any(h.near(c, look + 40) for h in sim.hazards)
        if not c.grounded:
            if c.hero is not None and c.hero.trait == "glide" and c.body.velocity.x * dirx < c.max_speed * 1.15:
                # v3.2: Floater catches a gentle forward breeze while gliding high in 0.24x gravity
                sim.push(c, dirx * PUSH_ACCEL * sim.cfg.get("floater_air_control", 0.55) * c.body.mass, 0.0)
            return                                   # airborne: pure ballistic / glide flight
        if ground_ahead is None or wall_ahead or danger:
            self._panic(sim, c)
            p = (0.45 + 0.5 * bh.jumpiness) if c.is_hero else (0.1 + 0.3 * bh.jumpiness)
            if sim.rng.random() < p and sim.t >= c.panic_until:
                k = (1.0 if c.is_hero else sim.cfg["extras"]["jump_k"]) + (0.12 if ground_ahead is None else 0.0)
                self._jump(c, vx_boost=70 * dirx, k=k)
        # Juggernaut recovers propulsion speed on steep downhills, stays 0.65x on flats
        gn = c.ground_n  # type: ignore[attr-defined]
        pm = c.prop_mult
        if c.hero is not None and c.hero.trait == "bowling" and gn.x * dirx > 0.16:
            pm = min(1.05, pm + gn.x * dirx * 0.9)
        vmax = self._vmax(sim, c) * pm * ((1.0 - 0.3 * bh.caution) if danger else 1.0)
        v = c.body.velocity
        along = v.x * dirx
        if along >= vmax:
            return
        k = min(1.0, (vmax - along) / max(1.0, vmax * 0.3))
        # rolling torque toward the target spin (grip-limited: slippery balls just spin their wheels)
        w_target = dirx * vmax / max(8.0, c.radius)
        tau_cap = c.body.mass * c.radius * ROLL_ACCEL * 1.5 * c.traction * pm * k
        err = w_target - c.body.angular_velocity
        c.drive_torque = max(-tau_cap, min(tau_cap, err * c.body.moment * 10.0))
        # mild push along the surface tangent
        tx, ty = (gn.y, -gn.x) if dirx > 0 else (-gn.y, gn.x)
        f = PUSH_ACCEL * c.body.mass * pm * k
        if c.hero is not None and c.hero.trait == "traction":
            sim.push(c, 0.0, sim.cfg["magneto_downforce"] * abs(sim.space.gravity.y) * c.body.mass)
        sim.push(c, tx * f, ty * f)
        # nudge a level rival, weighted by aggression (ball bump)
        if c.shove_cd <= 0 and sim.rng.random() < 0.03 * bh.aggression:
            rival = self._nearest(sim, c, 50)
            if rival is not None:
                rx, ry = rival.pos
                d = math.hypot(rx - x, ry - y) or 1
                kk = 180 * c.body.mass * pm
                c.body.apply_impulse_at_world_point(((rx - x) / d * kk, -30 * c.body.mass), c.body.position)
                c.shove_cd = 1.5

    # ------------------------------------------------------------------ TOP_DOWN
    def _top(self, sim: Sim, c: Contestant) -> None:
        bh = c.behaviour
        x, y = c.pos
        tx, ty = sim.goal.target(c)
        if c.extra is not None and math.hypot(tx - x, ty - y) > sim.cfg["extras"]["goal_sight_px"]:
            from src.games.goals import Goal
            tx, ty = Goal.target(sim.goal, c)
        safe = sim.arena.safe_target(c) if hasattr(sim.arena, "safe_target") else None
        for h in sim.hazards:
            if safe is None and hasattr(h, "flee"):
                safe = h.flee(c)
        if safe is not None:
            tx, ty = safe
        dx, dy = tx - x, ty - y
        if self.reversed(sim, c):
            dx, dy = -dx, -dy
        edge, ux, uy = sim.arena.edge_vector(x, y)
        tw = getattr(sim, "twist", None)
        ek = sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        margin = (55 + 105 * bh.edge_awareness) * (sim.cfg["hero_edge_margin"] if c.is_hero else 0.78) * min(1.0, ek)
        if sim.overtime:
            margin *= 0.55
        if edge < margin * 0.6:
            self._panic(sim, c)
        if edge < margin:
            n = math.hypot(dx, dy) or 1.0
            ew = 1.0 if c.is_hero else 0.55
            w = (margin - edge) / margin * (1.5 + 2 * bh.edge_awareness) * ew * max(n, 80.0)
            dx, dy = dx - ux * w, dy - uy * w
        jitter = sim.rng.uniform(-0.3, 0.3)
        dx, dy = dx * math.cos(jitter) - dy * math.sin(jitter), dx * math.sin(jitter) + dy * math.cos(jitter)
        nrm = math.hypot(dx, dy)
        top_pm = c.prop_mult if c.is_hero else sim.cfg.get("top_dummy_propulsion", 0.60)
        if nrm > 1e-6:
            vmax = self._vmax(sim, c) * (1.0 if c.is_hero else 0.85)
            v = c.body.velocity
            ex, ey = dx / nrm * vmax - v.x, dy / nrm * vmax - v.y
            e = math.hypot(ex, ey)
            if e > 1e-6:
                grip = c.traction * (1.3 if (c.hero and c.hero.trait == "traction") else 1.0)
                if sim.overtime:
                    grip = min(grip, 0.95)
                f = min(ACCEL * 1.3, e * 5.0) * c.body.mass * grip * top_pm
                sim.push(c, ex / e * f, ey / e * f)
        ot_agg = 3.2 if sim.overtime else 1.0
        if c.shove_cd <= 0 and sim.rng.random() < 0.06 * bh.aggression * ot_agg:
            rival = self._nearest(sim, c, 140 if sim.overtime else 90)
            if rival is not None:
                rx, ry = rival.pos
                d = math.hypot(rx - x, ry - y) or 1
                ot_shove = 2.1 if sim.overtime else 1.0
                kk = sim.cfg["shove_top"] * ot_shove * min(c.body.mass, 3.0 * rival.body.mass) * top_pm
                c.body.apply_impulse_at_world_point(((rx - x) / d * kk, (ry - y) / d * kk), c.body.position)
                c.shove_cd = 0.70 if sim.overtime else 1.6

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
        if h.trait == "spite":
            # Grumble: +15% recovery impulse near elimination boundaries
            if sim.arena.danger(c, 70) and c.stun <= 0:
                if sim.mode == SIDE:
                    sim.push(c, 0.15 * ROLL_ACCEL * c.body.mass, -0.15 * 980 * c.body.mass)
                else:
                    cx, cy = sim.arena.center
                    x, y = c.pos
                    d = math.hypot(cx - x, cy - y) or 1
                    sim.push(c, (cx - x) / d * 0.3 * ACCEL * c.body.mass, (cy - y) / d * 0.3 * ACCEL * c.body.mass)
                if sim.rng.random() < 0.01:
                    sim.trait(c, "spite_save")
        elif h.trait == "traction":
            # Magneto: slight magnetic tug toward metal hazards within 90 px
            x, y = c.pos
            for hz in sim.hazards:
                for px, py in hz.points:
                    d = math.hypot(px - x, py - y)
                    if 1.0 < d < 90.0:
                        f = sim.cfg["magneto_tug"] * c.body.mass
                        sim.push(c, (px - x) / d * f, (py - y) / d * f)
        elif h.trait == "bowling":
            recent = {k for t, k in c.contacts if sim.t - t < 1.2}
            if len(recent) >= 4:
                sim.trait(c, "bowling", pins=len(recent))
        elif h.trait == "auto_hop":
            if abs(c.body.velocity.x) > 300 and not c.grounded and sim.rng.random() < 0.01:
                sim.trait(c, "double_ricochet")
