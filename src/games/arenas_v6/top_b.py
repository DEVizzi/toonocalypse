"""v6 TOP_DOWN group B: Gravity Wells, Giant Ball Brawl, Duel Dome (Qualifier 1 special), Triangle Throne (Grand Final).

All randomness comes from `self.sim.rng` inside build() (stored in `self.p`), so every race replays exactly.
Per-frame visual state is published in `self.sim.zones` for the renderers in src/rendering/arena_art/top_b.py.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymunk

from src.games.arena_kit import TOP, V6Top, kin_circle, register

if TYPE_CHECKING:
    from src.physics.engine import Contestant


def _k_all(sim) -> float:
    tw = getattr(sim, "twist", None)
    return sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)


def move_kin(prop, x: float, y: float, dt: float, angle: float | None = None) -> None:
    """Drive a kinematic prop so it lands exactly on (x, y) after this substep's space.step (velocity only).
    NOTE: arena_kit.move_kin also sets position, and pymunk then integrates the kinematic body once more, so calling
    it every substep makes the body oscillate around its target with an ever-growing velocity."""
    b = prop.body
    if dt <= 0:
        b.position = (x, y)
        b.velocity = (0.0, 0.0)
        if angle is not None:
            b.angle = angle
        return
    b.velocity = ((x - b.position.x) / dt, (y - b.position.y) / dt)
    if angle is not None:
        b.angular_velocity = (angle - b.angle) / dt


def _ring_spawns(n: int, rng, rad: float, ok) -> list[tuple[float, float]]:
    """TopArena's two-ring spawn layout, but each point slides around its ring until `ok(x, y)` (clear of props)."""
    pts = []
    for i in range(n):
        ring = 0 if i < n * 0.6 else 1
        k = n * 0.6 if ring == 0 else n * 0.4
        a = 2 * math.pi * (i if ring == 0 else i - n * 0.6) / k + ring * 0.3
        rr = rad * (1.0 if ring == 0 else 0.62)
        jx, jy = rng.uniform(-6, 6), rng.uniform(-6, 6)
        x, y = math.cos(a) * rr + jx, math.sin(a) * rr + jy
        for tries in range(30):
            x, y = math.cos(a) * rr + jx, math.sin(a) * rr + jy
            if ok(x, y) and all(math.hypot(x - px, y - py) > 46 for px, py in pts):
                break
            a += 0.19
            if tries % 6 == 5:
                rr *= 0.92
        pts.append((x, y))
    return pts


def _calm(sim) -> bool:
    """Champion's victory hold: once one ball remains, brake it so it never slips off during the victory delay."""
    alive = sim.alive()
    if len(alive) <= 1:
        for c in alive:
            c.body.velocity = c.body.velocity * 0.80
            c.body.angular_velocity *= 0.8
        return True
    return False


def _slosh(sim, amp: float, t: float, rate: float = 2.6) -> None:
    """Rotating 'arena tilt' force that keeps huddles moving (same idea as the legacy disc/sumo endgames)."""
    a = t * rate
    ca, sa = math.cos(a), math.sin(a)
    for c in sim.alive():
        m = c.body.mass * amp
        sim.push(c, ca * m, sa * m)


# ============================================================================================ 1. GRAVITY WELLS
@register("gravity_wells", TOP, "Gravity Wells",
          "space arena where planet gravity slingshots balls into the void",
          ("Planets love hugs. Then they fling you into deep space!",
           "Gravity is free today. So is falling forever."),
          goals=("last_one_standing", "hold_a_zone", "collect_items", "push_others_out"),
          hazards=(), twists=("slippery_floor", "reversed_controls"))
class GravityWells(V6Top):
    """Round space platform (open edge = fall into space). 2-3 planets (kinematic, bouncy) pull every ball with a
    softened, capped inverse-square force so paths curve and balls slingshot; 2-3 asteroids drift on slow orbits."""
    DRAG = 0.25        # 1/s extra velocity damping on balls (space dust): knocked balls don't glide forever
    G = 2.4e6          # px^3/s^2: accel = G / (d^2 + SOFT^2)
    SOFT = 80.0
    AMAX = 420.0       # px/s^2 cap
    RANGE = 520.0

    def build(self):
        sim, r = self.sim, self.sim.rng
        R = self.R = float(self.p.setdefault("radius", round(r.uniform(430, 460))))
        self.spawn_r = R * 0.64
        n_pl = self.p.setdefault("planets", r.choice([2, 3]))
        a0 = r.uniform(0, 2 * math.pi)
        self.planets: list[dict] = []
        for i in range(n_pl):
            a = a0 + 2 * math.pi * i / n_pl + r.uniform(-0.25, 0.25)
            d = R * (r.uniform(0.40, 0.48) if n_pl == 3 else r.uniform(0.34, 0.44))
            pr = r.uniform(44.0, 56.0) if n_pl == 3 else r.uniform(50.0, 60.0)
            bx, by = math.cos(a) * d, math.sin(a) * d
            prop = kin_circle(sim, (bx, by), pr, "gw_planet", material="wall")
            for s in prop.body.shapes:
                s.elasticity = 0.85
            self.planets.append({"prop": prop, "bx": bx, "by": by, "r": pr, "g": (pr / 52.0) ** 1.5})
        n_as = self.p.setdefault("asteroids", r.choice([2, 3]))
        self.asteroids: list[dict] = []
        orbit = R * r.uniform(0.70, 0.78)
        om = r.uniform(0.30, 0.42) * r.choice([-1, 1])
        ph0 = r.uniform(0, 2 * math.pi)
        for i in range(n_as):
            ar = r.uniform(20.0, 27.0)
            ph = ph0 + 2 * math.pi * i / n_as + r.uniform(-0.3, 0.3)
            prop = kin_circle(sim, (math.cos(ph) * orbit, math.sin(ph) * orbit), ar, "gw_asteroid", material="bumper")
            for s in prop.body.shapes:
                s.elasticity = 1.0
            self.asteroids.append({"prop": prop, "orbit": orbit * r.uniform(0.94, 1.06), "ph": ph,
                                   "om": om * r.uniform(0.9, 1.1), "ecc": r.uniform(0.86, 1.0), "r": ar})
        sim.walkable = lambda x, y: x * x + y * y < R * R
        sim.zones["gw_R"] = R
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self.frame_top(R)
        self._place(0.0, 1.0)
        self._tk = -1.5

    def spawn_points(self, n, rng):
        def ok(x, y):
            return all(math.hypot(x - p["bx"], y - p["by"]) > p["r"] + 44 for p in self.planets) and \
                   all(math.hypot(x - a["prop"].body.position.x, y - a["prop"].body.position.y) > a["r"] + 40
                       for a in self.asteroids)
        return _ring_spawns(n, rng, self.spawn_r, ok)

    def shrink_target(self, t: float) -> float:
        p = min(1.0, max(0.0, (t - 3.0) / 21.0))
        return 1.0 - 0.50 * p ** 1.05

    def _place(self, dt: float, k: float) -> None:
        self._tk = getattr(self, "_tk", -1.5) + dt     # per-substep clock (sim.t only ticks once per frame)
        t = self._tk
        for p in self.planets:
            move_kin(p["prop"], p["bx"] * k, p["by"] * k, dt)
        for a in self.asteroids:
            ang = a["ph"] + a["om"] * t
            orb = a["orbit"] * k
            move_kin(a["prop"], math.cos(ang) * orb, math.sin(ang) * orb * a["ecc"], dt, angle=ang * 2.0)

    def _step(self, dt: float) -> None:
        self._place(dt, _k_all(self.sim))
        if not _calm(self.sim):
            f = max(0.0, 1.0 - self.DRAG * dt)
            for c in self.sim.alive():
                c.body.velocity = c.body.velocity * f

    def _frame(self, t: float) -> None:
        sim = self.sim
        alive = sim.alive()
        pl = [(float(p["prop"].body.position.x), float(p["prop"].body.position.y), p["r"], p["g"]) for p in self.planets]
        if len(alive) > 1:
            for c in alive:
                x, y = c.pos
                fx = fy = 0.0
                for px, py, pr, g in pl:
                    dx, dy = px - x, py - y
                    d = math.hypot(dx, dy)
                    if d < pr + c.radius + 3 or d > self.RANGE:
                        continue                  # touching: the planet just bounces it
                    acc = min(self.AMAX, self.G * g / (d * d + self.SOFT * self.SOFT))
                    fx += dx / d * acc
                    fy += dy / d * acc
                if fx or fy:
                    sim.push(c, fx * c.body.mass, fy * c.body.mass)
        goal = sim.goal
        if goal.key == "collect_items":              # never leave a crown buried inside a planet
            for it in goal.items:
                for px, py, pr, _ in pl:
                    dx, dy = it[0] - px, it[1] - py
                    d = math.hypot(dx, dy)
                    if d < pr + 28:
                        if d < 1:
                            dx, dy, d = -px, -py, max(1.0, math.hypot(px, py))
                        it[0], it[1] = px + dx / d * (pr + 36), py + dy / d * (pr + 36)
        k = _k_all(sim)
        sim.zones["gw_pl"] = [(round(px, 1), round(py, 1), round(pr, 1)) for px, py, pr, _ in pl]
        sim.zones["gw_orb"] = round(self.asteroids[0]["orbit"] * k, 1) if self.asteroids else 0.0


# ============================================================================================ 2. GIANT BALL BRAWL
@register("giant_ball_brawl", TOP, "Giant Ball Brawl",
          "floating pitch with four goal mouths and one giant ball",
          ("One giant ball, four goals, zero referees. Good luck!",
           "Kick the big ball, not the void. Mostly the ball."),
          goals=("push_others_out",), hazards=(), twists=())
class GiantBallBrawl(V6Top):
    """Square floating pitch with a goal mouth (hole) in the middle of each edge and one GIANT ball. The last hero to
    touch the ball when it drops into a mouth scores; first to 2 goals wins. Balls still fall off edges/mouths."""
    BALL_R = 70.0
    BALL_M = 6.0
    MOUTH_D = 118.0
    WIN_GOALS = 2
    CHASERS = 4

    def build(self):
        sim, r = self.sim, self.sim.rng
        self.half = float(self.p.setdefault("half", round(r.uniform(405, 430))))
        self.mw = float(self.p.setdefault("mouth_w", round(r.uniform(98, 108))))   # mouth half-width
        self.spawn_r = self.half * 0.66
        body = pymunk.Body(self.BALL_M, pymunk.moment_for_circle(self.BALL_M, 0, self.BALL_R))
        body.position = (0.0, 0.0)
        shape = pymunk.Circle(body, self.BALL_R)
        self.ball = sim.add_prop(body, [shape], "gbb_ball", material="prop")
        shape.friction, shape.elasticity = 0.25, 0.55
        self.posts = []
        for mouth in range(4):
            for side in (-1, 1):
                pp = kin_circle(sim, (0.0, 0.0), 11.0, "gbb_post", material="wall")
                self.posts.append((pp, mouth, side))
        self.goals: dict[str, int] = {}
        self.toucher: str | None = None
        self.touch_t = -9.0
        self.ball_on = True
        self.respawn_t = 0.0
        self.last_goal: list | None = None
        self.last_out = -9.0
        self.drop_t = -9.0
        self._chase_t = -1.0
        self._chasers: set[str] = set()
        sim.walkable = lambda x, y: self._walk(x * sim.edge_k, y * sim.edge_k)
        sim.zones.update(gbb_half=self.half, gbb_mw=self.mw, gbb_md=self.MOUTH_D)
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self.frame_top(self.half)
        self._place_posts(0.0)

    # ---- geometry (ACTUAL world coordinates: the pitch shrinks, the mouths keep their width)
    def _hk(self) -> float:
        return self.half * self.sim.edge_k

    def _walk(self, xa: float, ya: float) -> bool:
        hk = self._hk()
        ax, ay = abs(xa), abs(ya)
        if ax >= hk or ay >= hk:
            return False
        md = min(self.MOUTH_D, hk * 0.45)
        if ax < self.mw and ay > hk - md:
            return False
        if ay < self.mw and ax > hk - md:
            return False
        return True

    def _mouths(self) -> list[tuple[float, float]]:
        hk = self._hk()
        return [(0.0, -hk), (hk, 0.0), (0.0, hk), (-hk, 0.0)]

    def _place_posts(self, dt: float) -> None:
        hk = self._hk()
        for pp, mouth, side in self.posts:
            if mouth % 2 == 0:
                x, y = side * (self.mw + 6), (-hk if mouth == 0 else hk)
            else:
                x, y = (hk if mouth == 1 else -hk), side * (self.mw + 6)
            move_kin(pp, x, y, dt)

    def spawn_points(self, n, rng):
        return _ring_spawns(n, rng, self.spawn_r,
                            lambda x, y: math.hypot(x, y) > self.BALL_R + 46 and self._walk(x * 0.8, y * 0.8))

    def shrink_target(self, t: float) -> float:
        p = min(1.0, max(0.0, (t - 4.0) / 20.0))
        return 1.0 - 0.40 * p ** 1.1

    # ---- AI + ranking hooks
    def ball_pos(self) -> tuple[float, float]:
        b = self.ball.body.position
        return (float(b.x), float(b.y)) if self.ball_on else (0.0, 0.0)

    def progress(self, c: "Contestant") -> float:
        bx, by = self.ball_pos()
        return c.score * 1000.0 - math.hypot(c.pos[0] - bx, c.pos[1] - by) * 0.1

    def safe_target(self, c: "Contestant"):
        if c.extra is not None or not self.ball_on or self.sim.t < 0.3:
            return None
        sim = self.sim
        if self._chase_t != sim.t:
            self._chase_t = sim.t
            bx, by = self.ball_pos()
            hs = sorted((h for h in sim.alive() if h.is_hero), key=lambda h: math.hypot(h.pos[0] - bx, h.pos[1] - by))
            self._chasers = {h.key for h in hs[:self.CHASERS]}
        if c.key not in self._chasers:
            return None
        bx, by = self.ball_pos()
        mx, my = min(self._mouths(), key=lambda m: math.hypot(m[0] - bx, m[1] - by))
        ux, uy = mx - bx, my - by
        d = math.hypot(ux, uy) or 1.0
        ux, uy = ux / d, uy / d
        x, y = c.pos
        back = self.BALL_R + c.radius + 8
        px, py = bx - ux * back, by - uy * back
        rel = (x - bx) * ux + (y - by) * uy
        if rel > -self.BALL_R * 0.4:                 # wrong side of the ball: swing around it
            perp = (-uy, ux)
            sgn = 1.0 if (x - bx) * perp[0] + (y - by) * perp[1] >= 0 else -1.0
            sw = self.BALL_R + c.radius + 34
            px, py = bx + perp[0] * sgn * sw - ux * 30, by + perp[1] * sgn * sw - uy * 30
        hk = self._hk() - 40
        return max(-hk, min(hk, px)), max(-hk, min(hk, py))

    # ---- simulation hooks
    def _step(self, dt: float) -> None:
        self._place_posts(dt)
        b = self.ball.body
        if self.ball_on:
            drag = max(0.0, 1.0 - 0.55 * dt)
            b.velocity = b.velocity * drag
            b.angular_velocity *= max(0.0, 1.0 - 1.2 * dt)
        else:
            b.velocity = (0.0, 0.0)
            b.angular_velocity = 0.0
        _calm(self.sim)

    def _park(self) -> None:
        b = self.ball.body
        b.position = (9000.0, 9000.0)
        b.velocity = (0.0, 0.0)
        self.sim.space.reindex_shapes_for_body(b)
        self.ball_on = False

    def _frame(self, t: float) -> None:
        sim = self.sim
        b = self.ball.body
        if self.ball_on:
            bx, by = float(b.position.x), float(b.position.y)
            for c in sim.alive():
                if c.is_hero and math.hypot(c.pos[0] - bx, c.pos[1] - by) < self.BALL_R + c.radius + 4:
                    self.toucher, self.touch_t = c.key, t
            if not self._walk(bx, by) and t > 0:
                hk = self._hk()
                md = min(self.MOUTH_D, hk * 0.45)
                mouth = None
                if abs(bx) < self.mw + 12 and abs(by) > hk - md - 4:
                    mouth = 0 if by < 0 else 2
                elif abs(by) < self.mw + 12 and abs(bx) > hk - md - 4:
                    mouth = 1 if bx > 0 else 3
                if mouth is not None:
                    who = self.toucher if (self.toucher and sim.by_key[self.toucher].alive) else None
                    self.last_goal = [round(t, 2), who or "", mouth, round(bx, 1), round(by, 1)]
                    if who:
                        c = sim.by_key[who]
                        c.score += 1
                        self.goals[who] = self.goals.get(who, 0) + 1
                        c.happy_until = t + 1.5
                        sim.event("goal", [who], (bx, by), mouth=mouth, total=self.goals[who])
                    else:
                        sim.event("goal", [], (bx, by), mouth=mouth, total=0)
                    self._park()
                    self.respawn_t = t + 1.0
                    if who and self.goals[who] >= self.WIN_GOALS:
                        sim.goal.declare(who, t, "goals")
                else:
                    self.last_out = t
                    self._park()
                    self.respawn_t = t + 1.0
        elif t >= self.respawn_t and not sim.winner:
            spot = (0.0, 0.0)
            for rr, a in [(0, 0)] + [(60, i * math.pi / 3) for i in range(6)]:
                cand = (math.cos(a) * rr, math.sin(a) * rr)
                if all(math.hypot(c.pos[0] - cand[0], c.pos[1] - cand[1]) > self.BALL_R + c.radius + 2 for c in sim.alive()):
                    spot = cand
                    break
            b.position = spot
            b.velocity = (0.0, 0.0)
            sim.space.reindex_shapes_for_body(b)
            self.ball_on = True
            self.toucher = None
            self.drop_t = t
        sim.zones["gbb_goal"] = self.last_goal
        sim.zones["gbb_out"] = round(self.last_out, 2)
        sim.zones["gbb_drop"] = round(self.drop_t, 2)
        sim.zones["gbb_goals"] = dict(self.goals)
        sim.zones["gbb_k"] = round(sim.edge_k, 4)


# ============================================================================================ 3. DUEL DOME
@register("duel_dome", TOP, "Duel Dome",
          "gladiator dome duel with bouncy rails and a widening floor pocket",
          ("Two heroes enter. Six dummies panic. One ball leaves!",
           "The floor has a hole and it is getting hungrier."),
          goals=("last_one_standing",), hazards=(), twists=(), playoff="qualifier_1")
class DuelDome(V6Top):
    """Small octagonal dome: bouncy rails on the 4 straight sides, short open diagonal sides (falls), 4 corner
    bumpers and ONE central floor pocket that widens until a genuine last ball stands."""
    true_finish = True
    no_shrink = True
    rules = {"true_ko": True}

    def build(self):
        sim = self.sim
        R = self.R = float(self.p.setdefault("radius", 330))
        self.A = 0.90 * R            # straight-side half-extent
        self.C = 1.50 * R            # |x| + |y| limit (short diagonal sides)
        self.spawn_r = R * 0.55
        self.pr = 0.0
        self.pr_max = R * 0.80
        e = self.C - self.A
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if sx:
                a, b = (sx * (self.A + 5), -e), (sx * (self.A + 5), e)
            else:
                a, b = (-e, sy * (self.A + 5)), (e, sy * (self.A + 5))
            s = sim.static_segment(a, b, "bouncy", radius=12)
            s.elasticity = 1.18
            sim.statics[-1]["type"] = "dd_rail"
        d = R * 0.60
        for sx in (-1, 1):
            for sy in (-1, 1):
                s = sim.static_circle((sx * d, sy * d), 20.0, "bumper")
                s.elasticity = 1.2
                sim.statics[-1]["type"] = "dd_bumper"
        sim.statics.append({"type": "dd_dome", "R": R, "A": self.A, "C": self.C})
        sim.walkable = self._walkable
        sim.zones["dd_pocket"] = 0.0
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self.frame_top(R)

    def spawn_points(self, n, rng):
        d = self.R * 0.60
        return _ring_spawns(n, rng, self.spawn_r,
                            lambda x, y: all(math.hypot(x - sx * d, y - sy * d) > 50 for sx in (-1, 1) for sy in (-1, 1))
                            and math.hypot(x, y) > 70)

    def _walkable(self, x: float, y: float) -> bool:
        ax, ay = abs(x), abs(y)
        if ax > self.A or ay > self.A or ax + ay > self.C:
            return False
        return x * x + y * y >= self.pr * self.pr

    def _pocket(self, t: float) -> float:
        if t < 2.0:
            return 0.0
        p = min(1.0, (t - 2.0) / 23.0)
        return 46.0 + (self.pr_max - 46.0) * p ** 1.15

    def _step(self, dt: float) -> None:
        _calm(self.sim)

    def _frame(self, t: float) -> None:
        sim = self.sim
        n = len(sim.alive())
        if n > 1:
            self.pr = max(self.pr, self._pocket(t))
            if t > 3.0:
                p = min(1.0, max(0.0, (t - 10.0) / 14.0))
                _slosh(sim, (150.0 + 330.0 * p) * sim.speed_mult, t, 2.4)
        sim.zones["dd_pocket"] = round(self.pr, 1)


# ============================================================================================ 4. TRIANGLE THRONE
@register("triangle_throne", TOP, "Triangle Throne",
          "royal triangle platform shrinking toward a golden throne",
          ("Three finalists, one throne. Nobody sits until everyone falls!",
           "Bow to the throne. Then bonk it. Royally."),
          goals=("last_one_standing",), hazards=(), twists=(), playoff="grand_final")
class TriangleThrone(V6Top):
    """Equilateral royal platform with an open pocket in each corner, shrinking toward a golden throne bumper in the
    centre. True last-ball-standing finish."""
    true_finish = True
    no_quake = True
    rules = {"true_ko": True}

    def build(self):
        sim = self.sim
        Rt = self.Rt = float(self.p.setdefault("radius", 520))
        self.inr = Rt * 0.5
        self.us = [(math.cos(a), math.sin(a)) for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)]
        self.pk_d = Rt * 0.66
        self.pk_r = 0.0
        self.spawn_r = Rt * 0.34
        s = sim.static_circle((0.0, 0.0), 44.0, "bumper")
        s.elasticity = 1.22
        sim.statics[-1]["type"] = "tt_throne"
        sim.statics.append({"type": "tt_tri", "Rt": Rt})
        sim.walkable = self._walkable
        sim.zones["tt_pocket"] = 0.0
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        hw = Rt * 0.866
        sim.bounds = (-hw - 70, -Rt - 150, hw + 70, Rt + 150)

    def spawn_points(self, n, rng):
        return _ring_spawns(n, rng, self.spawn_r, lambda x, y: math.hypot(x, y) > 92 and self._walkable(x * 1.15, y * 1.15))

    def _walkable(self, x: float, y: float) -> bool:
        for ux, uy in self.us:
            if x * ux + y * uy < -self.inr:           # beyond the edge opposite this vertex
                return False
        pr = self.pk_r
        if pr > 0:
            for ux, uy in self.us:
                if x * ux + y * uy > self.pk_d or math.hypot(x - ux * self.pk_d, y - uy * self.pk_d) < pr:
                    return False
        return True

    def shrink_target(self, t: float) -> float:
        p = min(1.0, max(0.0, (t - 3.0) / 21.0))
        return 1.0 - 0.62 * p ** 1.1

    def _step(self, dt: float) -> None:
        _calm(self.sim)

    def _frame(self, t: float) -> None:
        sim = self.sim
        if len(sim.alive()) > 1:
            if t >= 0.0:
                self.pk_r = max(self.pk_r, 62.0 + 40.0 * min(1.0, t / 22.0))
            if t > 3.0:
                p = min(1.0, max(0.0, (t - 10.0) / 14.0))
                _slosh(sim, (140.0 + 300.0 * p) * sim.speed_mult, t, 2.5)
        sim.zones["tt_pocket"] = round(self.pk_r, 1)
