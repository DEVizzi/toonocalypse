"""Arenas (§11.1). Each builder sets geometry, kill rules and camera bounds on the Sim; procedural parameters are
sampled per episode (stored in recipe.params) so the same arena looks and plays differently.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymunk

from src.config import TIMELINE
from src.games.base import SIDE

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Sim

GROUND_DEPTH = 420.0


class Arena:
    key = ""
    center = (0.0, 0.0)

    def __init__(self, sim: "Sim") -> None:
        self.sim = sim
        self.p = sim.recipe.params
        self.pits: list[tuple[float, float]] = []   # SIDE: x ranges with no ground
        self.gate: pymunk.Shape | None = None

    # -- geometry helpers (SIDE)
    def ground(self, a, b, material: str = "ground", **kw):
        s = self.sim.static_segment(a, b, material, **kw)
        self.sim.statics.append({"type": "fill", "verts": [a, b, (b[0], b[1] + GROUND_DEPTH), (a[0], a[1] + GROUND_DEPTH)],
                                 "mat": material, "id": id(s)})
        return s

    def spawn_points(self, n: int, rng) -> list[tuple[float, float]]:
        cols = math.ceil(math.sqrt(n * 2.2))
        pts = []
        for i in range(n):
            r, c = divmod(i, cols)
            pts.append((60 + c * 52 + rng.uniform(-6, 6), -40 - r * 56 + rng.uniform(-6, 6)))
        return pts

    def danger(self, c: "Contestant", dist: float) -> bool:
        x, y = c.pos
        if self.sim.mode == SIDE:
            if any(a - dist < x < b for a, b in self.pits) and y > -30:
                return True
            if y > self.sim.kill_y - 300:
                return True
        else:
            if self.edge_distance(x, y) < dist * 0.6:
                return True
        return any(h.near(c, dist) for h in getattr(self.sim, "hazards", []))

    def edge_vector(self, x: float, y: float) -> tuple[float, float, float]:
        """(distance, ux, uy): nearest drop (edge or hole) and the unit direction toward it."""
        w = self.sim.walkable
        if w is None:
            return 999.0, 0.0, 0.0
        k = self.sim.edge_k
        for d in range(20, 241, 25):
            sx = sy = 0.0
            for i in range(12):
                a = i * math.pi / 6
                if not w((x + math.cos(a) * d) / k, (y + math.sin(a) * d) / k):
                    sx += math.cos(a)
                    sy += math.sin(a)
            n = math.hypot(sx, sy)
            if n > 0:
                return float(d), sx / n, sy / n
            if sx or sy:
                break
        return 999.0, 0.0, 0.0

    def edge_distance(self, x: float, y: float) -> float:
        return self.edge_vector(x, y)[0]

    def add_gate(self, x: float, top: float = -420.0) -> None:
        gy = self.ground_y_at(x - 4)
        self.gate = self.sim.static_segment((x, gy - 155), (x, gy), "wall", radius=10)
        self.sim.statics[-1]["mat"] = "gate"
        self.sim.statics.append({"type": "drop_gate", "x": x, "y": gy})

    def open_gate(self) -> None:
        if self.gate is not None:
            self.sim.remove_static(self.gate)
            self.gate = None

    def finalize_side(self, end_x: float, low_y: float, high_y: float) -> None:
        sim = self.sim
        sim.finish_x = end_x - 220
        sim.kill_y = low_y + 380
        sim.bounds = (-400.0, high_y - 1100, end_x + 600, low_y + 500)
        # back wall + finish banner posts
        sim.static_segment((-20, -1600), (-20, 40), "wall", radius=12)
        sim.statics.append({"type": "finish", "x": sim.finish_x, "y": self.ground_y_at(sim.finish_x)})

    def ground_y_at(self, x: float) -> float:
        best = 0.0
        for s in self.sim.statics:
            if s["type"] == "seg" and s["mat"] in ("ground", "ice", "mud", "conveyor", "bouncy", "plank"):
                (ax, ay), (bx, by) = s["a"], s["b"]
                if min(ax, bx) <= x <= max(ax, bx) and ax != bx:
                    return ay + (by - ay) * (x - ax) / (bx - ax)
        return best


class Course(Arena):
    """SIDE_VIEW course composer: sections laid left to right from a cursor."""

    LEDGE_Y = -560.0      # v3.0: every side-view course starts on a high ledge above a steep launch chute

    def __init__(self, sim: "Sim") -> None:
        super().__init__(sim)
        self.x, self.y = -20.0, self.LEDGE_Y
        self.low, self.high = 0.0, self.LEDGE_Y
        self.spans: list[tuple[float, float, float, float]] = []   # course floor profile incl. virtual pit spans

    def span(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if x1 < x0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        self.spans.append((x0, y0, x1, y1))

    def floor_y(self, x: float) -> float | None:
        """Lowest course surface (or pit line) at x. Falling well below it means the contestant fell off the course."""
        best = None
        for x0, y0, x1, y1 in self.spans:
            if x0 <= x <= x1:
                y = y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0.0)
                best = y if best is None else max(best, y)
        return best

    def spawn_points(self, n: int, rng) -> list[tuple[float, float]]:
        cols, step = 4, 74
        return [(70 + (i % cols) * step + rng.uniform(-5, 5), self.LEDGE_Y - 44 - (i // cols) * 78 + rng.uniform(-5, 5))
                for i in range(n)]

    def seg(self, dx: float, dy: float = 0.0, material: str = "ground", **kw):
        a, b = (self.x, self.y), (self.x + dx, self.y + dy)
        s = self.ground(a, b, material, **kw)
        self.span(a[0], a[1], b[0], b[1])
        self.x, self.y = b
        self.low, self.high = max(self.low, self.y), min(self.high, self.y)
        return s

    def wave(self, length: float, amp: float = 36.0, drift: float = 42.0) -> None:
        """Undulating net-downhill ground: crests stay mild (dy >= -14) so rolling balls never stall in V-pockets."""
        r = self.sim.rng
        n = max(2, int(length / 150))
        for i in range(n):
            dy = (amp * r.uniform(0.55, 1.0) if i % 2 == 0 else -amp * r.uniform(0.25, 0.45)) + drift / n
            self.seg(length / n, max(-14.0, dy))

    def pegs(self, count: int, height: tuple[float, float] = (70, 130)) -> None:
        """Pinball pegs/bumpers above the floor ahead of the cursor: balls ricochet off them."""
        r = self.sim.rng
        for i in range(count):
            px = self.x + 60 + i * r.uniform(70, 110)
            self.sim.static_circle((px, self.y - r.uniform(*height)), r.uniform(14, 20), "bumper")

    def count(self, key: str, lo: int, hi: int) -> int:
        """Section count, scaled so fast heroes need ~30 s of gameplay to reach the finish."""
        return self.p.setdefault(key, round(self.sim.rng.randint(lo, hi) * self.sim.cfg["course_length_scale"]))

    def ramp(self, i: int, n: int) -> float:
        """Course difficulty ramp: gaps start narrow and widen toward the finish so eliminations spread out."""
        lo, hi = self.sim.cfg["course_ramp"]
        return lo + (hi - lo) * i / max(1, n - 1)

    def gap(self, w: float, dy: float = 0.0) -> None:
        self.pits.append((self.x, self.x + w))
        self.span(self.x, self.y, self.x + w, self.y + dy)
        self.x += w
        self.y += dy
        self.low, self.high = max(self.low, self.y), min(self.high, self.y)

    def block(self, w: float, h: float) -> None:
        x, y = self.x, self.y
        self.sim.static_poly([(x, y), (x + w, y), (x + w, y - h), (x, y - h)], "wall")
        self.seg(w)

    def start(self) -> None:
        """Spawn ledge -> compact drop-gate -> steep launch chute -> tilted run-out -> first lethal gap within 300 px."""
        r = self.sim.rng
        self.seg(360, 12)
        self.add_gate(self.x - 26, top=self.LEDGE_Y - 155)
        self.seg(380, 320)                       # steep chute (40 deg)
        self.seg(220, 210)                       # continuous downhill run-out
        self.seg(r.uniform(90, 145), 14)
        self.gap(r.uniform(115, 155), 24)        # first blood: within ~300 px of the drop zone

    def finish(self, length: float = 700) -> None:
        self.seg(length)
        self.sim.static_segment((self.x, self.y - 900), (self.x, self.y), "wall", radius=12)
        self.finalize_side(self.x, self.low, self.high)


# ---------------------------------------------------------------------- SIDE arenas
class FlatTrack(Course):
    key = "flat_track"

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("sections", 10, 13)
        for i in range(n):
            kind = r.choice(["kicker", "crest", "gap", "roll", "kicker"])
            if kind == "kicker":
                self.seg(r.uniform(160, 260), r.uniform(15, 35))
                self.seg(r.uniform(85, 115), -18, material="bouncy")
                self.gap(r.uniform(85, 135) * self.ramp(i, n), r.uniform(25, 55))
            elif kind == "crest":
                self.seg(r.uniform(200, 300), -26)
                self.sim.static_circle((self.x, self.y - 24), 16, "bumper")
                self.seg(r.uniform(260, 360), r.uniform(75, 120))
            elif kind == "gap":
                self.seg(r.uniform(200, 320), r.uniform(20, 45))
                self.gap(r.uniform(90, 150) * self.ramp(i, n), r.uniform(20, 45))
            if r.random() < 0.45:
                self.pegs(r.randint(2, 4))
            self.wave(r.uniform(260, 440))
        self.finish(800)


class RampDescent(Course):
    key = "ramp_descent"

    def build(self):
        """v3.2: continuous downhill slope continuity + spring launch lips & dip bumpers (zero V-pocket traffic jams)."""
        r = self.sim.rng
        self.start()
        n = self.count("ramps", 8, 10)
        for i in range(n):
            self.seg(r.uniform(420, 580), r.uniform(165, 245))
            if r.random() < 0.55:
                self.pegs(r.randint(2, 3), (65, 115))
            if i % 2 == 0:
                # bouncy spring launch pad at ramp foot -> launches pack cleanly across downhill gap
                self.seg(r.uniform(110, 150), r.uniform(16, 34), material="bouncy")
                self.gap(r.uniform(90, 140) * self.ramp(i, n), r.uniform(35, 75))
            else:
                # smooth downhill connector + embedded spring bumper at the joint so zero balls can stall
                self.sim.static_circle((self.x + 26, self.y - 22), 17, "bumper")
                self.seg(r.uniform(150, 230), r.uniform(35, 70))
                if r.random() < 0.45:
                    self.gap(r.uniform(80, 125) * self.ramp(i, n), r.uniform(25, 60))
        self.finish(700)


class PitPlatforms(Course):
    key = "pit_platforms"

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("islands", 14, 18)
        for i in range(n):
            self.gap(r.uniform(80, 150) * self.ramp(i, n), r.uniform(-50, 50))
            self.seg(r.uniform(180, 340))
        self.gap(r.uniform(100, 150))
        self.finish(700)


class TieredTower(Course):
    key = "tiered_tower"

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("tiers", 13, 16)
        for i in range(n):              # v3.0: a descending tower of drops, launch pads and gaps (balls can't climb)
            if i % 3 == 2:
                self.seg(r.uniform(90, 130), material="bouncy")    # launch pad
                self.gap(r.uniform(60, 110) * self.ramp(i, n), r.uniform(40, 90))
            else:
                self.wave(r.uniform(260, 380), 30, 20)
                drop = r.uniform(90, 150)
                self.span(self.x, self.y, self.x + 1, self.y + drop)
                self.y += drop                  # ledge drop onto the next tier
                self.low = max(self.low, self.y)
        self.finish(700)


class NarrowBridge(Course):
    key = "narrow_bridge"

    def __init__(self, sim):
        super().__init__(sim)
        self.planks: list[dict] = []

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("planks", 34, 42)
        breakaway = set(r.sample(range(n // 4, n - 2), k=max(3, n // 5)))   # the far end is the fragile part
        for i in range(n):
            w = r.uniform(110, 150)
            s = self.seg(w, material="plank")
            self.planks.append({"shape": s, "x0": self.x - w, "x1": self.x, "break": i in breakaway, "hit": None})
            self.x += 6      # visible plank gaps
        self.finish(700)
        self.sim.kill_y = self.low + 300
        self.sim.hooks_frame.append(self._tick)

    def _tick(self, t: float):
        for p in self.planks:
            if not p["break"] or p["shape"] is None:
                continue
            if p["hit"] is None and any(c.alive and p["x0"] <= c.pos[0] <= p["x1"] and abs(c.pos[1] - self.ground_y_at(c.pos[0])) < 60
                                        for c in self.sim.contestants):
                p["hit"] = t
            if p["hit"] is not None and t - p["hit"] > 0.6:
                self.sim.remove_static(p["shape"])
                self.pits.append((p["x0"], p["x1"]))
                p["shape"] = None
        self.sim.zones["cracking"] = [(p["x0"], p["x1"]) for p in self.planks if p["hit"] is not None and p["shape"] is not None]


class BouncyPadField(Course):
    key = "bouncy_pad_field"

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("pads", 15, 19)
        for i in range(n):
            self.seg(r.uniform(120, 200), material="bouncy")
            if r.random() < 0.6:
                self.gap(r.uniform(80, 160) * self.ramp(i, n), r.uniform(-40, 40))
            else:
                self.seg(r.uniform(80, 160))
        self.finish(700)


class SeesawGauntlet(Course):
    key = "seesaw_gauntlet"

    def build(self):
        r = self.sim.rng
        self.start()
        for _ in range(self.count("seesaws", 8, 10)):
            span = r.uniform(380, 520)
            px, py = self.x + span / 2, self.y + 14
            self.pits.append((self.x, self.x + span))
            self.span(self.x, self.y, self.x + span, self.y)
            body = pymunk.Body(14.0, pymunk.moment_for_box(14.0, (span, 30)))
            body.position = (px, py)
            plank = pymunk.Poly.create_box(body, (span + 40, 30), radius=6)
            self.sim.add_prop(body, [plank], "seesaw", material="plank")
            pivot = pymunk.PivotJoint(self.sim.space.static_body, body, (px, py))
            limit = pymunk.RotaryLimitJoint(self.sim.space.static_body, body, -0.45, 0.45)
            self.sim.space.add(pivot, limit)
            self.x += span
            self.seg(r.uniform(160, 260), r.uniform(15, 35))
        self.finish(700)


class ConveyorChaos(Course):
    key = "conveyor_chaos"

    def build(self):
        r = self.sim.rng
        self.start()
        belts = []
        n = self.count("belts", 11, 14)
        for i in range(n):
            w = r.uniform(300, 460)
            speed = r.choice([-1, 1, 1]) * r.uniform(120, 220)
            s = self.seg(w, material="conveyor", surface_velocity=(-speed, 0))
            self.sim.statics[-2]["belt"] = speed
            belts.append(s)
            if r.random() < 0.5:
                self.gap(r.uniform(90, 140) * self.ramp(i, n))
        self.finish(700)


class PachinkoDrop(Course):
    """v3.0 diagonal drop: downhill shelves stacked like a staircase, peg fields at every drop, seesaws, spring pads
    and lethal mid-shelf holes. Shows off material contrast (Boing ricochets, Floater drifts, Juggernaut ploughs)."""
    key = "pachinko_drop"

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.count("shelves", 9, 12)
        for i in range(n):
            length = r.uniform(320, 440)
            kind = r.choice(["plain", "hole", "spring", "seesaw", "hole"])
            if kind == "hole" and i > 0:
                a = length * r.uniform(0.35, 0.55)
                self.seg(a, a * 0.16)
                self.gap(r.uniform(80, 120) * self.ramp(i, n), 14)
                rest = length - a
                self.seg(rest, rest * 0.16)
            elif kind == "spring":
                self.seg(length * 0.6, length * 0.1)
                self.seg(110, 8, material="bouncy")
                self.seg(length * 0.4 - 110, length * 0.06)
            elif kind == "seesaw":
                self.seg(length * 0.35, length * 0.06)
                span = r.uniform(300, 380)
                px, py = self.x + span / 2, self.y + 14
                self.pits.append((self.x, self.x + span))
                self.span(self.x, self.y, self.x + span, self.y)
                body = pymunk.Body(12.0, pymunk.moment_for_box(12.0, (span, 30)))
                body.position = (px, py)
                self.sim.add_prop(body, [pymunk.Poly.create_box(body, (span + 40, 30), radius=6)], "seesaw", material="plank")
                self.sim.space.add(pymunk.PivotJoint(self.sim.space.static_body, body, (px, py)),
                                   pymunk.RotaryLimitJoint(self.sim.space.static_body, body, -0.45, 0.45))
                self.x += span
                self.seg(length * 0.25, length * 0.04)
            else:
                self.seg(length, length * 0.18)
            # the drop to the next shelf: a peg field to bounce through, the next shelf starts underneath
            drop = r.uniform(200, 280)
            for row in range(2):
                for k in range(3 - row):
                    self.sim.static_circle((self.x + 30 + k * 70 + row * 35, self.y + 70 + row * 75), r.uniform(13, 17), "bumper")
            nx, ny = self.x - 70, self.y + drop
            self.span(self.x, self.y, self.x + 1, ny)
            self.x, self.y = nx, ny
            self.low = max(self.low, self.y)
        self.finish(700)


# ---------------------------------------------------------------------- TOP_DOWN arenas
class TopArena(Arena):
    def spawn_points(self, n: int, rng) -> list[tuple[float, float]]:
        pts = []
        rad = self.spawn_r
        for i in range(n):
            ring = 0 if i < n * 0.6 else 1
            k = n * 0.6 if ring == 0 else n * 0.4
            a = 2 * math.pi * (i if ring == 0 else i - n * 0.6) / k + ring * 0.3
            rr = rad * (1.0 if ring == 0 else 0.62)
            pts.append((math.cos(a) * rr + rng.uniform(-6, 6), math.sin(a) * rr + rng.uniform(-6, 6)))
        return pts

    def frame_top(self, half: float) -> None:
        self.sim.bounds = (-half - 120, -half - 220, half + 120, half + 220)


class RotatingDisc(TopArena):
    key = "rotating_disc"

    def build(self):
        r = self.sim.rng
        self.R = self.p.setdefault("radius", round(r.uniform(390, 450)))
        self.omega = self.p.setdefault("omega", round(r.uniform(0.55, 0.8), 2)) * r.choice([-1, 1])
        self.spawn_r = self.R * 0.68
        self.sim.walkable = lambda x, y: x * x + y * y < self.R * self.R
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.disc = body
        spokes = [pymunk.Segment(body, (0, 0), (math.cos(a) * (self.R - 30), math.sin(a) * (self.R - 30)), 2)
                  for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
        p = self.sim.add_prop(body, spokes, "disc_marks")
        for s in spokes:
            s.sensor = True
        # radial pinball bumpers riding on the disc
        nb = self.p.setdefault("disc_bumpers", r.randint(3, 4))
        bumpers = [pymunk.Circle(body, 26, (math.cos(2 * math.pi * k / nb + 0.4) * self.R * 0.52,
                                            math.sin(2 * math.pi * k / nb + 0.4) * self.R * 0.52)) for k in range(nb)]
        self.sim.space.add(*bumpers)
        for b in bumpers:
            self.sim._material(b, "bumper")
        p.shapes += [{"type": "circle", "c": tuple(b.offset), "r": b.radius, "bumper": True} for b in bumpers]
        self.bumpers = [{"shape": b, "base": pymunk.Vec2d(*b.offset), "fall_t": None} for b in bumpers]
        self.sim.statics.append({"type": "disc", "c": (0, 0), "r": self.R})
        self.sim.hooks_step.append(self._carry)
        self.frame_top(self.R)
        del p

    def _carry(self, dt: float):
        k_edge = self.sim.edge_k
        ot_spin = 1.28 if self.sim.overtime else 1.0
        w = (self.omega if self.sim.t >= 1.0 else self.omega * 0.3) * self.sim.speed_mult * ot_spin
        self.disc.angular_velocity = w
        tw = getattr(self.sim, "twist", None)
        k_all = k_edge * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        cur_r = self.R * k_all
        falls = []
        for idx, bm in enumerate(getattr(self, "bumpers", [])):
            if bm["fall_t"] is None and bm["base"].length > 0.78 * cur_r:
                bm["fall_t"] = self.sim.t
                if bm["shape"] in self.sim.space.shapes:
                    self.sim.space.remove(bm["shape"])
            falls.append(round(self.sim.t - bm["fall_t"], 3) if bm["fall_t"] is not None else -1.0)
        if falls:
            self.sim.zones["bumper_falls"] = falls
        for c in self.sim.alive():
            x, y = c.pos
            tv = pymunk.Vec2d(-y * w, x * w)          # tangential surface velocity at the rider
            dv = tv - c.body.velocity
            # friction coupling scales with traction: Grumble clings, Dash skates off (Magneto +30% adherence)
            grip = c.traction * (1.3 if c.hero is not None and c.hero.trait == "traction" else 1.0)
            k = 4.0 * grip
            c.body.apply_force_at_world_point((dv.x * c.body.mass * k, dv.y * c.body.mass * k), c.body.position)
            c.body.torque += (w - c.body.angular_velocity) * c.body.moment * 3.0 * grip   # riders spin with the disc
            if self.sim.t > 7.0:
                # Rotating disc tilt-slosh breaks up dead-center huddles into real 1v1 sumo knockouts
                slosh_a = self.sim.t * 2.6
                slosh_f = (210.0 + (460.0 if self.sim.overtime else 0.0)) * self.sim.speed_mult * c.body.mass
                c.body.apply_force_at_world_point((math.cos(slosh_a) * slosh_f, math.sin(slosh_a) * slosh_f),
                                                  c.body.position)


class MazeCorridors(TopArena):
    key = "maze_corridors"

    def build(self):
        r = self.sim.rng
        half = self.p.setdefault("half", round(r.uniform(400, 440)))
        self.spawn_r = half * 0.8
        self.sim.walkable = lambda x, y: abs(x) < half and abs(y) < half
        self.sim.statics.append({"type": "square", "c": (0, 0), "half": half})
        rings = self.p.setdefault("rings", 2)
        for k in range(rings):
            rr = half * (0.62 - k * 0.27)
            gap_a = r.uniform(0, 2 * math.pi)
            n = 10
            for i in range(n):
                a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
                if abs(((a0 + a1) / 2 - gap_a + math.pi) % (2 * math.pi) - math.pi) < 0.7:
                    continue
                if i % 3 == 1:
                    continue
                self.sim.static_segment((math.cos(a0) * rr, math.sin(a0) * rr), (math.cos(a1) * rr, math.sin(a1) * rr),
                                        "wall", radius=8)
        self.half = half
        self.frame_top(half)


class HexTileDrop(TopArena):
    key = "hex_tile_drop"

    def build(self):
        r = self.sim.rng
        self.size = self.p.setdefault("tile", round(r.uniform(66, 80)))
        radius = self.p.setdefault("radius", 430)
        self.spawn_r = radius * 0.62
        s = self.size
        self.tiles: dict[tuple[int, int], dict] = {}
        rng_q = int(radius / (s * 1.5)) + 2
        for q in range(-rng_q, rng_q + 1):
            for rr in range(-rng_q, rng_q + 1):
                x = s * 1.5 * q
                y = s * math.sqrt(3) * (rr + q / 2)
                if x * x + y * y < radius * radius:
                    self.tiles[(q, rr)] = {"c": (x, y), "hit": None, "gone": False}
        self.sim.walkable = self._walkable
        self.sim.statics.append({"type": "hex_grid", "size": s, "tiles": [t["c"] for t in self.tiles.values()]})
        self.sim.hooks_frame.append(self._tick)
        self.frame_top(radius)

    def _axial(self, x, y):
        s = self.size
        q = (2 / 3 * x) / s
        r = (-1 / 3 * x + math.sqrt(3) / 3 * y) / s
        # cube rounding
        cx, cz = q, r
        cy = -cx - cz
        rx, ry, rz = round(cx), round(cy), round(cz)
        dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        return int(rx), int(rz)

    def _walkable(self, x, y):
        t = self.tiles.get(self._axial(x, y))
        return bool(t and not t["gone"])

    CRACK_LOAD = 2.4      # contestant-seconds of standing weight before a tile cracks

    def _tick(self, t: float):
        # weight on a tile accumulates (crowds crack tiles faster); cracked tiles vanish 0.6 s later and regrow
        # after 4 s until overtime, after which the honeycomb collapses for good
        dt = 1 / 30
        if t < 4.0:
            return
        counts: dict = {}
        for c in self.sim.alive():
            k = self._axial(*c.pos)
            counts[k] = counts.get(k, 0) + 1
        need = self.CRACK_LOAD / (self.sim.speed_mult * max(0.2, self.sim.pressure))
        for key, tile in self.tiles.items():
            if tile["gone"]:
                if t < TIMELINE.escalation[2][0] and t - tile.get("gone_t", t) > 4.0 and key not in counts:
                    tile.update(gone=False, hit=None, load=0.0)
                continue
            n = counts.get(key, 0)
            if tile["hit"] is None:
                tile["load"] = tile.get("load", 0.0) + dt * n if n else max(0.0, tile.get("load", 0.0) - dt * 0.6)
                if tile["load"] >= need:
                    tile["hit"] = t
            elif t - tile["hit"] > 0.6 / self.sim.speed_mult:
                tile["gone"], tile["gone_t"] = True, t
        self.sim.zones["tiles"] = [0 if v["hit"] is None else (1 if not v["gone"] else 2) for v in self.tiles.values()]

    def safe_target(self, c):
        """When my tile is half-loaded or cracking, head for the least-loaded intact tile nearby."""
        tile = self.tiles.get(self._axial(*c.pos))
        if tile is None or tile["gone"]:
            return None
        if tile["hit"] is None and tile.get("load", 0.0) < 0.5 * self.CRACK_LOAD / self.sim.speed_mult:
            return None
        x, y = c.pos
        best, bs = None, 1e9
        for v in self.tiles.values():
            if v["gone"] or v["hit"] is not None or v is tile:
                continue
            d = math.hypot(v["c"][0] - x, v["c"][1] - y)
            if d > self.size * 4:
                continue
            sc = d + v.get("load", 0.0) * 120
            if sc < bs:
                best, bs = v["c"], sc
        return best


class BumperRing(TopArena):
    key = "bumper_ring"

    def build(self):
        r = self.sim.rng
        self.R0 = self.p.setdefault("radius", round(r.uniform(410, 450)))
        self.R = float(self.R0)
        self.spawn_r = self.R0 * 0.66
        for _ in range(self.p.setdefault("bumpers", r.randint(5, 8))):
            a, d = r.uniform(0, 2 * math.pi), r.uniform(80, self.R0 * 0.7)
            self.sim.static_circle((math.cos(a) * d, math.sin(a) * d), r.uniform(28, 42), "bumper")
        self.sim.walkable = lambda x, y: x * x + y * y < self.R * self.R
        self.sim.statics.append({"type": "ring", "c": (0, 0), "r": self.R0})
        self.sim.hooks_frame.append(self._shrink)
        self.frame_top(self.R0)

    def _shrink(self, t: float):
        if t > TIMELINE.escalation[1][0] * 0.5:
            self.R = max(self.R0 * 0.35, self.R - 6.0 * self.sim.speed_mult * self.sim.pressure / 30)
        self.sim.zones["ring_r"] = self.R


ARENA_CLASSES = {c.key: c for c in (FlatTrack, RampDescent, PitPlatforms, TieredTower, NarrowBridge, BouncyPadField,
                                     SeesawGauntlet, ConveyorChaos, PachinkoDrop, RotatingDisc, MazeCorridors, HexTileDrop,
                                     BumperRing)}


def build(sim: "Sim") -> Arena:
    a = ARENA_CLASSES[sim.recipe.arena](sim)
    a.build()
    return a
