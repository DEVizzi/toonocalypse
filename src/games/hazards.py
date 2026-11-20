"""Hazards (§11.3). Each hazard builds its objects, steps them (scaled by escalation), exposes `near()` for AI fear
and expressions, and a per-frame zone state for the renderer."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pymunk

from src.games.base import SIDE

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Prop, Sim


class Hazard:
    key = ""

    def __init__(self, sim: "Sim") -> None:
        self.sim = sim
        self.r = sim.rng
        self.points: list[tuple[float, float]] = []    # danger anchor points (for near())
        self.build()
        sim.hooks_frame.append(self.frame)

    def build(self) -> None: ...

    def frame(self, t: float) -> None: ...

    def near(self, c: "Contestant", dist: float) -> bool:
        x, y = c.pos
        return any(abs(px - x) < dist and abs(py - y) < dist for px, py in self.points)

    def zone_state(self) -> dict[str, Any]:
        return {}

    # placement helpers
    def side_spots(self, n: int, lo: float = 900, hi_pad: float = 600) -> list[float]:
        fx = self.sim.finish_x or 4000
        span = (fx - hi_pad) - lo
        return [lo + span * (i + 0.5) / n + self.r.uniform(-80, 80) for i in range(n)]

    def top_spots(self, n: int, rad: float = 230) -> list[tuple[float, float]]:
        off = self.r.uniform(0, 6.28)
        return [(math.cos(off + 2 * math.pi * i / n) * rad, math.sin(off + 2 * math.pi * i / n) * rad) for i in range(n)]

    def kinematic(self, pos, shapes_fn, style: str, hazard: bool = True) -> "Prop":
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = pos
        return self.sim.add_prop(body, shapes_fn(body), style, hazard=hazard)


def _pt_seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-6:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


class SpinningBars(Hazard):
    key = "spinning_bars"

    def _side_clearance(self, cx: float, cy: float) -> float:
        """Minimum distance from hub (cx, cy) to any rendered track slab (incl. 68px masonry depth), peg, wall or seesaw."""
        best = 1e9
        track_mats = ("ground", "ice", "mud", "bouncy", "conveyor", "plank")
        for s in self.sim.statics:
            st = s["type"]
            if st == "seg" and s["mat"] in track_mats:
                (ax, ay), (bx, by) = s["a"], s["b"]
                if max(ax, bx) < cx - 260 or min(ax, bx) > cx + 260:
                    continue
                for dy in (-10.0, 28.0, 68.0):
                    best = min(best, _pt_seg_dist(cx, cy, ax, ay + dy, bx, by + dy))
                best = min(best, _pt_seg_dist(cx, cy, ax, ay - 10.0, ax, ay + 68.0))
                best = min(best, _pt_seg_dist(cx, cy, bx, by - 10.0, bx, by + 68.0))
            elif st == "seg" and s["mat"] in ("wall", "gate"):
                (ax, ay), (bx, by) = s["a"], s["b"]
                if abs(ax - cx) < 260:
                    gy = self.sim.arena.ground_y_at(ax + 30)
                    best = min(best, _pt_seg_dist(cx, cy, ax, gy - 148.0, ax, gy) - 40.0)
            elif st == "circle":
                ox, oy = s["c"]
                if abs(ox - cx) < 260:
                    best = min(best, math.hypot(cx - ox, cy - oy) - float(s["r"]))
        for p in getattr(self.sim, "props", []):
            if p.style == "seesaw":
                px, py = float(p.body.position.x), float(p.body.position.y)
                if abs(px - cx) < 420:
                    best = min(best, _pt_seg_dist(cx, cy, px - 210.0, py, px + 210.0, py) - 115.0)
        return best

    def _place_side_bar(self, x0: float) -> tuple[float, float, float] | None:
        """Finds (cx, cy, L) near x0 with >= 40px clearance everywhere while keeping the bar sweep active above the track."""
        bar_r = 9.0
        min_clear = 40.0       # strictly > 35px spec
        track_mats = ("ground", "ice", "mud", "bouncy", "conveyor", "plank")
        for L in (116.0, 96.0, 78.0):
            sweep = L + bar_r + min_clear
            for dx in (0.0, -35.0, 35.0, -70.0, 70.0, -105.0, 105.0, -140.0, 140.0, -180.0, 180.0, -230.0, 230.0, -290.0, 290.0, -350.0, 350.0):
                cx = x0 + dx
                if cx < 520 or (self.sim.finish_x and cx > self.sim.finish_x - 320):
                    continue
                if any(abs(cx - px) < 280 for px, _ in self.points):
                    continue
                # Find the active shelf surface at cx (not an unrelated overhang 240px above)
                gy_center = None
                segs_near = []
                for s in self.sim.statics:
                    if s["type"] == "seg" and s["mat"] in track_mats:
                        (ax, ay), (bx, by) = s["a"], s["b"]
                        if abs(bx - ax) <= 1.0:
                            continue
                        if min(ax, bx) <= cx <= max(ax, bx):
                            y_here = ay + (by - ay) * (cx - ax) / (bx - ax)
                            gy_center = y_here if gy_center is None else max(gy_center, y_here)
                        if max(ax, bx) >= cx - (L + 48) and min(ax, bx) <= cx + (L + 48):
                            segs_near.append((ax, ay, bx, by))
                if gy_center is None:
                    continue
                local_tops = [gy_center]
                for ax, ay, bx, by in segs_near:
                    sx0 = max(min(ax, bx), cx - (L + 48))
                    sx1 = min(max(ax, bx), cx + (L + 48))
                    for sx in (sx0, (sx0 + sx1) * 0.5, sx1):
                        yy = ay + (by - ay) * (sx - ax) / (bx - ax)
                        if abs(yy - gy_center) < 120.0:
                            local_tops.append(yy)
                base_cy = min(local_tops) - (sweep + 6.0)
                for extra_lift in (0.0, 14.0, 28.0, 42.0):
                    cy = base_cy - extra_lift
                    if gy_center - (cy + L + bar_r) > 140.0:
                        continue
                    if self._side_clearance(cx, cy) >= sweep:
                        return cx, cy, L
        return None

    def build(self):
        self.bars = []
        if self.sim.mode == SIDE:
            for x in self.side_spots(self.r.randint(3, 4)):
                placed = self._place_side_bar(x)
                if placed is None:
                    continue
                bx, by, L = placed
                self.bars.append(self.kinematic((bx, by), lambda b, L=L: [pymunk.Segment(b, (-L, 0), (L, 0), 9)], "bar"))
                self.points.append((bx, by))
        else:
            for i, p in enumerate(self.top_spots(2, 210) + [(0.0, 0.0)]):
                L = self.r.uniform(150, 200) if i < 2 else self.r.uniform(100, 140)
                self.bars.append(self.kinematic(p, lambda b, L=L: [pymunk.Segment(b, (-L, 0), (L, 0), 10)], "bar"))
                self.points.append(p)
        self.spin = [self.r.choice([-1, 1]) * self.r.uniform(1.6, 2.6) for _ in self.bars]

    def frame(self, t):
        spin_up = 1.0 if self.sim.mode == SIDE else min(1.0, 0.3 + t / 8)   # TOP bars wind up after the start
        for p, w in zip(self.bars, self.spin):
            p.body.angular_velocity = w * self.sim.hazard_mult * spin_up


class SwingingHammers(Hazard):
    key = "swinging_hammers"

    def build(self):
        self.hammers = []
        for x in self.side_spots(self.r.randint(3, 4)):
            gy = self.sim.arena.ground_y_at(x)
            pivot = (x, gy - 330)
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            body.position = pivot
            arm = pymunk.Segment(body, (0, 0), (0, 270), 5)
            head = pymunk.Poly(body, [(-46, 250), (46, 250), (46, 300), (-46, 300)], radius=6)
            p = self.sim.add_prop(body, [arm, head], "hammer", hazard=True)
            self.hammers.append((p, self.r.uniform(0, 6.28), self.r.uniform(1.6, 2.4)))
            self.points.append((x, gy - 40))
            self.sim.statics.append({"type": "post", "c": pivot})

    def frame(self, t):
        for p, ph, w in self.hammers:
            a = 1.05 * math.sin(t * w * self.sim.hazard_mult + ph)
            da = 1.05 * math.cos(t * w * self.sim.hazard_mult + ph) * w * self.sim.hazard_mult
            p.body.angle = a
            p.body.angular_velocity = da


class FallingFloorTiles(Hazard):
    key = "falling_floor_tiles"

    def build(self):
        self.tiles: list[dict] = []
        if self.sim.mode == SIDE:
            # replace some ground with crumbling tiles: invisible-to-AI gaps that appear after contact
            for x in self.side_spots(self.r.randint(4, 6)):
                gy = self.sim.arena.ground_y_at(x)
                w = self.r.uniform(120, 180)
                body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
                body.position = (x, gy - 14)
                box = pymunk.Poly.create_box(body, (w, 24), radius=4)
                p = self.sim.add_prop(body, [box], "tile", material="ground")
                self.tiles.append({"prop": p, "x0": x - w / 2, "x1": x + w / 2, "y": gy - 14, "hit": None, "gone_at": None})
        else:
            for p in self.top_spots(self.r.randint(5, 7), self.r.uniform(150, 280)):
                self.tiles.append({"prop": None, "c": p, "r": self.r.uniform(55, 80), "hit": None, "gone_at": None})
            base = self.sim.walkable
            self.sim.walkable = lambda x, y: (base is None or base(x, y)) and not any(
                tl["gone_at"] is not None and math.hypot(x - tl["c"][0], y - tl["c"][1]) < tl["r"] for tl in self.tiles)

    def frame(self, t):
        if t < (2.0 if self.sim.mode == SIDE else 5.0):   # tiles arm once the crowd has left the spawn ring
            return
        for tl in self.tiles:
            if tl["hit"] is None:
                for c in self.sim.alive():
                    x, y = c.pos
                    if self.sim.mode == SIDE:
                        on = tl["x0"] <= x <= tl["x1"] and abs(y - tl["y"]) < 50
                    else:
                        on = math.hypot(x - tl["c"][0], y - tl["c"][1]) < tl["r"]
                    if on:
                        tl["hit"] = t
                        break
            elif tl["gone_at"] is None and t - tl["hit"] > (0.6 if self.sim.mode == SIDE else 1.1) / self.sim.hazard_mult:
                tl["gone_at"] = t
                if tl["prop"] is not None:
                    tl["prop"].body.position = (tl["prop"].body.position.x, tl["prop"].body.position.y + 4000)
            elif tl["gone_at"] is not None and t - tl["gone_at"] > 3.0:
                tl["hit"], tl["gone_at"] = None, None
                if tl["prop"] is not None:
                    tl["prop"].body.position = (tl["prop"].body.position.x, tl["y"])
        self.points = [((tl["x0"] + tl["x1"]) / 2, tl["y"]) if self.sim.mode == SIDE else tl["c"]
                       for tl in self.tiles if tl["hit"] is not None]

    def flee(self, c):
        """TOP: step off a tile that is cracking (away from its centre)."""
        if self.sim.mode == SIDE:
            return None
        x, y = c.pos
        for tl in self.tiles:
            if tl["hit"] is not None and tl["gone_at"] is None and math.hypot(x - tl["c"][0], y - tl["c"][1]) < tl["r"] + 15:
                dx, dy = x - tl["c"][0], y - tl["c"][1]
                d = math.hypot(dx, dy) or 1
                return tl["c"][0] + dx / d * (tl["r"] + 60), tl["c"][1] + dy / d * (tl["r"] + 60)
        return None

    def zone_state(self):
        if self.sim.mode == SIDE:
            return {"tiles_side": [1 if tl["hit"] is not None and tl["gone_at"] is None else 0 for tl in self.tiles]}
        return {"tiles_top": [(tl["c"], tl["r"], 0 if tl["hit"] is None else (1 if tl["gone_at"] is None else 2))
                              for tl in self.tiles]}


class RollingBoulders(Hazard):
    key = "rolling_boulders"

    def build(self):
        self.next = 4.0
        self.live: list[pymunk.Body] = []

    def frame(self, t):
        if t >= self.next:
            self.next = t + self.r.uniform(2.8, 4.2) / self.sim.hazard_mult
            ahead = self.sim.cam_x + self.sim.view_w * 0.9
            gy = self.sim.arena.ground_y_at(ahead)
            body = pymunk.Body(30, pymunk.moment_for_circle(30, 0, 46))
            body.position = (ahead, gy - 260)
            body.velocity = (-260 * self.sim.hazard_mult, 0)
            shape = pymunk.Circle(body, 46)
            p = self.sim.add_prop(body, [shape], "boulder", hazard=True)
            shape.friction, shape.elasticity = 0.9, 0.2
            self.live.append(p)
        for p in list(self.live):
            if p.body.position.y > self.sim.kill_y + 200 or p.body.position.x < self.sim.cam_x - 2500:
                self.sim.remove_prop(p)
                self.live.remove(p)
        self.points = [(p.body.position.x, p.body.position.y) for p in self.live]


class WindGusts(Hazard):
    key = "wind_gusts"

    def build(self):
        self.period = self.r.uniform(5.0, 7.0)
        self.dir = self.r.choice([-1, 1]) if self.sim.mode == SIDE else self.r.uniform(0, 6.28)
        self.active = False
        self.sim.hooks_step.append(self.push)

    def frame(self, t):
        ph = t % self.period
        self.active = t > 4.0 and 1.0 < ph < 3.0
        if self.active and ph < 1.04:
            self.sim.event("wind", [], None)

    def push(self, dt):
        if not self.active:
            return
        f = 900.0 * self.sim.hazard_mult      # mass-independent force: light heroes fly further
        if self.sim.mode == SIDE:
            fx, fy = f * self.dir, -f * 0.35
        else:
            fx, fy = math.cos(self.dir) * f * 0.32, math.sin(self.dir) * f * 0.32   # steering can resist it
        for c in self.sim.alive():
            if c.hero and c.hero.trait == "traction":
                continue
            c.body.apply_force_at_world_point((fx, fy), c.body.position)
            if c.hero and c.hero.trait == "featherweight" and c.body.velocity.length > 520:
                self.sim.trait(c, "wind_launch")

    def near(self, c, dist):
        return False

    def zone_state(self):
        return {"wind": (self.dir if self.sim.mode == SIDE else self.dir) if self.active else None}


class LavaFloor(Hazard):
    key = "lava_floor"

    def build(self):
        self.y = self.sim.kill_y - 60
        self.top = self.sim.arena.ground_y_at(self.sim.finish_x or 0) if self.sim.finish_x else 0

    def frame(self, t):
        rate = 6.0 * (self.sim.hazard_mult ** 2)
        if t > 6:
            self.y -= rate / 30
        for c in self.sim.alive():
            if c.pos[1] + c.radius > self.y:
                self.sim.eliminate(c, "lava")

    def near(self, c, dist):
        return self.y - c.pos[1] < dist + 60

    def zone_state(self):
        return {"lava_y": self.y}


class MovingWalls(Hazard):
    key = "moving_walls"

    def build(self):
        self.walls = []
        if self.sim.mode == SIDE:
            for x in self.side_spots(self.r.randint(3, 4)):
                gy = self.sim.arena.ground_y_at(x)
                p = self.kinematic((x, gy - 70), lambda b: [pymunk.Poly.create_box(b, (40, 140), radius=6)], "wall_block")
                self.walls.append((p, (x, gy - 70), "y", self.r.uniform(0, 6.28)))
        else:
            for k, p0 in enumerate(self.top_spots(3, 180)):
                p = self.kinematic(p0, lambda b: [pymunk.Poly.create_box(b, (150, 34), radius=6)], "wall_block")
                self.walls.append((p, p0, "x" if k % 2 else "y", self.r.uniform(0, 6.28)))

    def frame(self, t):
        for p, base, axis, ph in self.walls:
            w = 1.3 * self.sim.hazard_mult
            if axis == "y":   # SIDE: piston rising out of the ground / TOP: sweep along y
                amp = 90 if self.sim.mode == SIDE else 170
                p.body.velocity = (0, math.cos(t * w + ph) * amp * w)
            else:
                p.body.velocity = (math.cos(t * w + ph) * 170 * w, 0)
        self.points = [(p.body.position.x, p.body.position.y) for p, *_ in self.walls]


class CannonBalls(Hazard):
    key = "cannon_balls"

    def build(self):
        self.next = 3.0
        self.balls: list[pymunk.Body] = []

    def frame(self, t):
        if t >= self.next:
            self.next = t + self.r.uniform(1.6, 2.6) / self.sim.hazard_mult
            body = pymunk.Body(6, pymunk.moment_for_circle(6, 0, 20))
            if self.sim.mode == SIDE:
                x = self.sim.cam_x + self.sim.view_w * 0.75
                gy = self.sim.arena.ground_y_at(x)
                body.position = (x, gy - self.r.uniform(40, 120))
                body.velocity = (-620 * self.sim.hazard_mult, -60)
            else:
                a = self.r.uniform(0, 6.28)
                body.position = (math.cos(a) * 560, math.sin(a) * 560)
                body.velocity = (-math.cos(a) * 520 * self.sim.hazard_mult, -math.sin(a) * 520 * self.sim.hazard_mult)
                self.sim.event("cannon", [], (math.cos(a) * 520, math.sin(a) * 520))
            shape = pymunk.Circle(body, 20)
            p = self.sim.add_prop(body, [shape], "cannonball", hazard=True)
            shape.elasticity = 0.6
            self.balls.append(p)
            if self.sim.mode != SIDE:
                body.velocity_func = lambda b, g, d, dt: pymunk.Body.update_velocity(b, (0, 0), 1.0, dt)
        for p in list(self.balls):
            x, y = p.body.position
            if abs(x - self.sim.cam_x) > 2600 or abs(y) > 2600 or (self.sim.mode == SIDE and y > self.sim.kill_y + 200):
                self.sim.remove_prop(p)
                self.balls.remove(p)
        self.points = [(p.body.position.x, p.body.position.y) for p in self.balls[-6:]]


class _Zone(Hazard):
    """Rect (SIDE) / circle (TOP) floor zones that change movement or friction."""
    mult = 1.0
    style = ""

    def build(self):
        self.zones = []
        if self.sim.mode == SIDE:
            for x in self.side_spots(self.r.randint(3, 5), lo=800):
                w = self.r.uniform(240, 380)
                self.zones.append(("rect", x - w / 2, x + w / 2))
        else:
            # v3.3: mid-to-outer radial offsets (0.45R-0.75R) so patches peel off as the arena shrinks
            R = float(getattr(self.sim.arena, "R", 430.0))
            base_off = 0.35 if self.style == "ice_zones" else (0.35 + math.pi * 0.5)
            for i in range(2):
                a = base_off + i * math.pi + self.r.uniform(-0.22, 0.22)
                rad = self.r.uniform(0.45, 0.75) * R
                self.zones.append(("circle", (math.cos(a) * rad, math.sin(a) * rad), self.r.uniform(58, 74)))
        self.sim.surface_mods.append(self.modifier)

    def _fade(self) -> float:
        """TOP: patches shrink to nothing within 1 s of OVERTIME so the final duel is clean high-knockback combat."""
        if self.sim.mode == SIDE or not self.sim.overtime:
            return 1.0
        return max(0.0, 1.0 - (self.sim.t - self.sim.overtime_t) / 1.0)

    def inside(self, c) -> bool:
        x, y = c.pos
        k = self._fade()
        for z in self.zones:
            if z[0] == "rect" and z[1] <= x <= z[2]:
                return True
            if z[0] == "circle" and math.hypot(x - z[1][0], y - z[1][1]) < z[2] * k:
                return True
        return False

    def modifier(self, c) -> float:
        if c.hero and c.hero.trait == "traction":
            return 1.0
        return self.mult if self.inside(c) else 1.0

    def near(self, c, dist):
        return False

    def zone_state(self):
        k = self._fade()
        if k >= 1.0:
            return {self.style: self.zones}
        return {self.style: [(z[0], z[1], z[2] * k) if z[0] == "circle" else z for z in self.zones if k > 0.05]}


class SlipperyIce(_Zone):
    key = "slippery_ice"
    style = "ice_zones"
    mult = 1.25

    def frame(self, t):
        # friction 0.01 inside ice zones (Magneto immune)
        for c in self.sim.alive():
            base = c.hero.friction if c.hero else 0.6
            ice = self.inside(c) and not (c.hero and c.hero.trait == "traction")
            c.shape.friction = 0.01 if ice else base * self.sim.friction_scale


class StickyMud(_Zone):
    key = "sticky_mud"
    style = "mud_zones"
    mult = 0.35

    def frame(self, t):
        for c in self.sim.alive():
            if self.inside(c) and not (c.hero and c.hero.trait == "traction"):
                c.angry_until = max(c.angry_until, t + 0.2)


HAZARD_CLASSES = {h.key: h for h in (SpinningBars, SwingingHammers, FallingFloorTiles, RollingBoulders, WindGusts,
                                      LavaFloor, MovingWalls, CannonBalls, SlipperyIce, StickyMud)}


def make(key: str, sim: "Sim") -> Hazard:
    return HAZARD_CLASSES[key](sim)
