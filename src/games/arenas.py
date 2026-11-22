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
        sim.finish_x = end_x - 450
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

    def start(self, first_gap: bool = True) -> None:
        """Spawn ledge -> compact drop-gate -> steep launch chute -> tilted run-out -> first lethal gap within 300 px
        (v4.3: `first_gap=False` swaps the instant-kill gap for a gentle run-in so dummies reach the first hazards)."""
        r = self.sim.rng
        self.seg(360, 12)
        self.add_gate(self.x - 26, top=self.LEDGE_Y - 155)
        self.seg(380, 320)                       # steep chute (40 deg)
        self.seg(220, 210)                       # continuous downhill run-out
        self.seg(r.uniform(90, 145), 14)
        if first_gap:
            self.gap(r.uniform(115, 155), 24)    # first blood: within ~300 px of the drop zone
        else:
            self.seg(r.uniform(170, 230), 36)    # gentle run-in straight into crusher bay #1

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
        n = self.count("islands", 12, 15)
        for i in range(n):
            if i % 2 == 0:
                self.seg(r.uniform(95, 130), r.uniform(10, 22), material="bouncy")
            self.gap(r.uniform(80, 140) * self.ramp(i, n), r.uniform(18, 54))
            self.seg(r.uniform(195, 320), r.uniform(36, 74))
            if i % 2 == 1:
                self.pegs(2, (62, 108))
        self.gap(r.uniform(95, 135), 28)
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
        n = self.count("planks", 26, 32)
        breakaway = set(r.sample(range(n // 5, n - 2), k=max(4, n // 4)))   # fragile breakaway planks
        for i in range(n):
            w = r.uniform(115, 150)
            dy = r.uniform(16, 30)
            s = self.seg(w, dy, material="plank")
            self.planks.append({"shape": s, "x0": self.x - w, "x1": self.x, "break": i in breakaway, "hit": None})
            if i % 7 == 3:
                self.sim.static_circle((self.x - w * 0.5, self.y - r.uniform(68, 102)), 16, "bumper")
            self.x += 6      # visible plank gaps
        self.finish(700)
        self.sim.kill_y = self.low + 300
        self.sim.hooks_frame.append(self._tick)

    def _tick(self, t: float):
        ot = bool(getattr(self.sim, "overtime", False))
        min_x = min((c.pos[0] for c in self.sim.alive()), default=-1e9) if ot else -1e9
        for p in self.planks:
            if p["shape"] is None:
                continue
            if ot and p["hit"] is None and p["x1"] <= min_x + 55:
                p["hit"] = t - 0.38
            if not p["break"] and not ot:
                continue
            if p["hit"] is None and any(c.alive and p["x0"] <= c.pos[0] <= p["x1"] and abs(c.pos[1] - self.ground_y_at(c.pos[0])) < 60
                                        for c in self.sim.contestants):
                p["hit"] = t
            if p["hit"] is not None and t - p["hit"] > (0.24 if ot else 0.6):
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
        n = self.count("belts", 10, 13)
        for i in range(n):
            w = r.uniform(290, 430)
            dy = r.uniform(32, 66)
            speed = (1 if i == 0 else r.choice([-1, 1, 1])) * r.uniform(135, 235)
            s = self.seg(w, dy, material="conveyor", surface_velocity=(-speed, 0))
            self.sim.statics[-2]["belt"] = speed
            belts.append(s)
            if i == 0 or r.random() < 0.52:
                self.gap(r.uniform(85, 135) * self.ramp(i, n), r.uniform(16, 40))
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
        self.omega = self.p.setdefault("omega", round(r.uniform(0.90, 1.18), 2)) * r.choice([-1, 1])
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

    true_finish = True       # v3.3: never resolve while > 1 contestant is alive (until the 38 s cap)

    def shrink_target(self, t: float) -> float:
        """Combined radius scale: 1.0 until 3 s, then down to min_radius_px / R by shrink_end_s (held after)."""
        dc = self.sim.cfg["disc"]
        kmin = float(dc["min_radius_px"]) / self.R
        p = min(1.0, max(0.0, (t - 3.0) / (float(dc["shrink_end_s"]) - 3.0)))
        return 1.0 - (1.0 - kmin) * p ** 1.1

    def push_progress(self) -> float:
        dc = self.sim.cfg["disc"]
        start = float(dc["shrink_end_s"]) - float(dc["final_push_s"]) + 1.0
        return min(1.0, max(0.0, (self.sim.t - start) / float(dc["final_push_s"])))

    def _carry(self, dt: float):
        dc = self.sim.cfg["disc"]
        p = self.push_progress()
        k_edge = self.sim.edge_k
        w = self.omega * self.sim.speed_mult * (1.0 + float(dc["spin_ramp"]) * p)
        self.disc.angular_velocity = w
        tw = getattr(self.sim, "twist", None)
        k_all = k_edge * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        cur_r = max(1.0, self.R * k_all)
        falls = []
        for idx, bm in enumerate(getattr(self, "bumpers", [])):
            if bm["fall_t"] is None and bm["base"].length > 0.78 * cur_r:
                bm["fall_t"] = self.sim.t
                if bm["shape"] in self.sim.space.shapes:
                    self.sim.space.remove(bm["shape"])
            falls.append(round(self.sim.t - bm["fall_t"], 3) if bm["fall_t"] is not None else -1.0)
        if falls:
            self.sim.zones["bumper_falls"] = falls
        slosh_a = self.sim.t * 2.6
        survivors = self.sim.alive()
        calm = len(survivors) <= 1               # champion's victory hold: no more shoving forces
        for c in survivors:
            x, y = c.pos
            tv = pymunk.Vec2d(-y * w, x * w)          # tangential surface velocity at the rider
            dv = tv - c.body.velocity
            # friction coupling scales with traction: Grumble clings, Dash skates off (Magneto +30% adherence)
            grip = c.traction * (1.3 if c.hero is not None and c.hero.trait == "traction" else 1.0)
            k = 4.0 * grip
            c.body.apply_force_at_world_point((dv.x * c.body.mass * k, dv.y * c.body.mass * k), c.body.position)
            c.body.torque += (w - c.body.angular_velocity) * c.body.moment * 3.0 * grip   # riders spin with the disc
            m = c.body.mass
            if calm:
                # champion's victory hold: brake and settle toward the hub so the winner never slips off
                c.body.velocity = c.body.velocity * 0.82
                c.body.apply_force_at_world_point((-x * 14.0 * m, -y * 14.0 * m), c.body.position)
                continue
            if self.sim.t > 2.6:
                # tilt-slosh breaks up huddles early so first blood triggers <= 4 s
                sf = (210.0 + 320.0 * p) * self.sim.speed_mult * m
                c.body.apply_force_at_world_point((math.cos(slosh_a) * sf, math.sin(slosh_a) * sf), c.body.position)
            if p > 0.0:
                # v3.3 final push: centrifugal outward drift grows with radius and over the final seconds
                d = math.hypot(x, y)
                ux, uy = (x / d, y / d) if d > 1.0 else (math.cos(slosh_a), math.sin(slosh_a))
                a = float(dc["centrifugal"]) * p * (0.35 + min(1.5, d / cur_r))
                if c.hero is not None and c.hero.trait == "bowling":
                    a *= 1.45                      # cast iron slides on the spinning metal plate
                c.body.apply_force_at_world_point((ux * a * m, uy * a * m), c.body.position)


class MazeCorridors(TopArena):
    key = "maze_corridors"

    def build(self):
        r = self.sim.rng
        half = self.p.setdefault("half", round(r.uniform(400, 440)))
        self.spawn_r = half * 0.78
        self.sim.walkable = lambda x, y: abs(x) < half and abs(y) < half
        self.sim.statics.append({"type": "square", "c": (0, 0), "half": half})
        rings = self.p.setdefault("rings", 2)
        self.ring_props: list[tuple] = []
        for k in range(rings):
            rr = half * (0.60 - k * 0.25)
            gap_a = r.uniform(0, 2 * math.pi)
            n = 10
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            segs = []
            for i in range(n):
                a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
                if abs(((a0 + a1) / 2 - gap_a + math.pi) % (2 * math.pi) - math.pi) < 0.7:
                    continue
                if i % 3 == 1:
                    continue
                segs.append(pymunk.Segment(body, (math.cos(a0) * rr, math.sin(a0) * rr),
                                           (math.cos(a1) * rr, math.sin(a1) * rr), 8))
            if segs:
                mp = self.sim.add_prop(body, segs, "maze_wall", material="wall")
                omega = (0.20 if k % 2 == 0 else -0.26)
                self.ring_props.append((mp, rr, omega))
        self.half = half
        self.sim.hooks_step.append(self._step_maze)
        self.frame_top(half)

    def _step_maze(self, dt: float) -> None:
        tw = getattr(self.sim, "twist", None)
        k_all = self.sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        max_r = self.half * k_all * 0.85
        for mp, rr, omega in self.ring_props:
            if rr > max_r:
                mp.body.position = (4500.0, 4500.0)
                mp.body.angular_velocity = 0.0
            else:
                mp.body.position = (0.0, 0.0)
                w = omega * self.sim.hazard_mult
                mp.body.angular_velocity = w
                mp.body.angle += w * dt


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
        # 3 compact pinball bumpers on the inner ring keep rivals colliding across hex islands (retract in tiny endgame)
        self.hex_bumpers: list[tuple] = []
        for idx in range(3):
            ang = idx * 2 * math.pi / 3 + 0.52
            bbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            bbody.position = (math.cos(ang) * 118.0, math.sin(ang) * 118.0)
            bsh = pymunk.Circle(bbody, 20.0)
            bp = self.sim.add_prop(bbody, [bsh], "piston_bumper", material="bumper")
            bsh.elasticity = 1.25
            self.hex_bumpers.append((bp, ang))
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

    CRACK_LOAD = 1.65     # contestant-seconds of standing weight before a tile cracks

    def _tick(self, t: float):
        # weight on a tile accumulates (crowds crack tiles faster); cracked tiles vanish 0.55 s later and regrow
        # after 3.8 s until overtime, after which the honeycomb collapses for good
        tw = getattr(self.sim, "twist", None)
        k_all = self.sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        for bp, ang in self.hex_bumpers:
            bx, by = math.cos(ang) * 118.0 * k_all, math.sin(ang) * 118.0 * k_all
            if k_all < 0.44 or not self._walkable(bx / max(0.2, self.sim.edge_k), by / max(0.2, self.sim.edge_k)):
                bp.body.position = (4500.0, 4500.0)
            else:
                bp.body.position = (bx, by)
        dt = 1 / 30
        if t < 1.6:
            return
        counts: dict = {}
        for c in self.sim.alive():
            k = self._axial(*c.pos)
            counts[k] = counts.get(k, 0) + 1
        need = self.CRACK_LOAD / (self.sim.speed_mult * max(0.25, self.sim.pressure))
        for key, tile in self.tiles.items():
            if tile["gone"]:
                if t < TIMELINE.escalation[2][0] and t - tile.get("gone_t", t) > 3.8 and key not in counts:
                    tile.update(gone=False, hit=None, load=0.0)
                continue
            n = counts.get(key, 0)
            if tile["hit"] is None:
                tile["load"] = tile.get("load", 0.0) + dt * n if n else max(0.0, tile.get("load", 0.0) - dt * 0.6)
                if tile["load"] >= need:
                    tile["hit"] = t
            elif t - tile["hit"] > 0.55 / self.sim.speed_mult:
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
        self.R0 = self.p.setdefault("radius", round(r.uniform(415, 450)))
        self.R = float(self.R0)
        self.spawn_r = self.R0 * 0.64
        n_b = self.p.setdefault("bumpers", r.randint(5, 7))
        self.ring_bumpers: list[tuple] = []
        for k in range(n_b):
            a = 2 * math.pi * k / n_b + r.uniform(-0.18, 0.18)
            d = r.uniform(105.0, self.R0 * 0.56)
            rad = r.uniform(24.0, 32.0)
            bbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            bbody.position = (math.cos(a) * d, math.sin(a) * d)
            bsh = pymunk.Circle(bbody, rad)
            bp = self.sim.add_prop(bbody, [bsh], "piston_bumper", material="bumper")
            bsh.elasticity = 1.24
            self.ring_bumpers.append((bp, a, d))
        self.sim.walkable = lambda x, y: x * x + y * y < self.R * self.R
        self.sim.statics.append({"type": "ring", "c": (0, 0), "r": self.R0})
        self.sim.zones["ring_r"] = self.R0
        self.sim.hooks_step.append(self._step_ring)
        self.frame_top(self.R0)

    def _step_ring(self, dt: float) -> None:
        tw = getattr(self.sim, "twist", None)
        k_all = self.sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        t = self.sim.t
        for idx, (bp, a0, d0) in enumerate(self.ring_bumpers):
            if k_all < 0.38:
                bp.body.position = (4500.0, 4500.0)
                bp.body.velocity = (0.0, 0.0)
            else:
                ang = a0 + t * 0.38 * (1 if idx % 2 == 0 else -1)
                d = d0 * k_all
                bp.body.position = (math.cos(ang) * d, math.sin(ang) * d)
        self.sim.zones["ring_r"] = self.R0


class CrumblingBridge(Course):
    """v4.0: High-altitude segmented castle suspension bridge where each stone/timber tile shakes for 0.45 s once
    touched and then drops into the abyss, paired with overhead swinging hammers and bouncy spring launch pads."""
    key = "crumbling_bridge"
    chase_scale = 0.9        # holes open behind the pack; give stragglers a fair shot before the wall arrives

    def __init__(self, sim):
        super().__init__(sim)
        self.tiles: list[dict] = []
        self.hammers: list[tuple] = []

    def build(self):
        r = self.sim.rng
        self.start()
        n_spans = self.count("bridge_spans", 8, 10)
        for sp_i in range(n_spans):
            # Steep stone descent (Ramp-Descent profile) so the pack keeps real pace
            self.seg(r.uniform(420, 560), r.uniform(165, 235))
            if sp_i % 2 == 0:
                # Crumbling bridge: 2-3 discrete 90-110 px stone slabs over the abyss. First contact -> CRACKING
                # (>= 0.45 s, 3 px vibration, jagged cracks) -> slab detaches once the pack has crossed -> real holes
                self.seg(r.uniform(90, 120), r.uniform(10, 20), material="bouncy")
                n_tiles = 2 if sp_i < n_spans - 3 else 3
                for _ in range(n_tiles):
                    tw = r.uniform(90, 110)
                    dy = r.uniform(8, 16)
                    cx, cy = self.x + tw * 0.5, self.y + dy * 0.5 + 13.0
                    body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
                    body.position = (cx, cy)
                    box = pymunk.Poly.create_box(body, (tw - 2, 26), radius=3)
                    p = self.sim.add_prop(body, [box], "bridge_tile", material="plank")
                    self.tiles.append({"prop": p, "x0": self.x, "x1": self.x + tw, "cx": cx, "cy": cy,
                                       "tilt": r.choice([-1.0, 1.0]), "hit": None, "dropped": False, "regrow": False})
                    self.span(self.x, self.y, self.x + tw, self.y + dy)
                    self.x += tw
                    self.y += dy
                    self.low = max(self.low, self.y)
                self.seg(r.uniform(150, 210), r.uniform(30, 55))
                if sp_i % 4 == 0:
                    hx = self.x - 90.0
                    gy = self.ground_y_at(hx)
                    piv = (hx, gy - 335.0)
                    hbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
                    hbody.position = piv
                    arm = pymunk.Segment(hbody, (0, 0), (0, 252), 5)
                    head = pymunk.Poly(hbody, [(-36, 236), (36, 236), (36, 278), (-36, 278)], radius=6)
                    hp = self.sim.add_prop(hbody, [arm, head], "hammer", hazard=True)
                    self.hammers.append((hp, r.uniform(0, 6.28), r.uniform(1.5, 2.0)))
                    self.sim.statics.append({"type": "post", "c": piv})
            else:
                self.sim.static_circle((self.x + 26, self.y - 22), 17, "bumper")
                self.seg(r.uniform(150, 230), r.uniform(35, 70))
                if r.random() < 0.45:
                    self.gap(r.uniform(80, 120) * self.ramp(sp_i, n_spans), r.uniform(25, 60))

        self.finish(700)
        self.sim.hooks_frame.append(self._tick)

    def _tick(self, t: float):
        for hp, ph, w in self.hammers:
            ang = 0.76 * math.sin(t * w * self.sim.hazard_mult + ph)
            hp.body.angle = ang
            hp.body.angular_velocity = 0.76 * math.cos(t * w * self.sim.hazard_mult + ph) * w * self.sim.hazard_mult

        states = []
        ot = bool(getattr(self.sim, "overtime", False))
        min_x = min((c.pos[0] for c in self.sim.alive()), default=-1e9) if ot else -1e9
        for tl in self.tiles:
            p = tl["prop"]
            if tl["hit"] is None and ot and tl["x1"] <= min_x + 65:
                tl["hit"] = t - 0.35
            elif tl["hit"] is None and t >= 0.4:
                for c in self.sim.alive():
                    x, y = c.pos
                    if tl["x0"] - 12 <= x <= tl["x1"] + 12 and abs(y - (tl["cy"] - 13)) < 46:
                        tl["hit"] = t
                        break
            if tl["hit"] is None:
                states.append(0)
                continue
            age = t - tl["hit"]
            near = [c for c in self.sim.alive() if abs(c.pos[1] - (tl["cy"] - 13)) < 140]
            loaded = any(tl["x0"] - 4 <= c.pos[0] <= tl["x1"] + 4 for c in near)
            approaching = any(tl["x0"] - 260 <= c.pos[0] < tl["x0"] for c in near)
            if not tl["dropped"] and (age < (0.20 if ot else 0.45) or (not ot and (loaded or approaching) and age < 2.4)):
                # CRACKING: >= 0.45 s of 3 px vibration + jagged cracks, then the slab detaches the moment it is
                # unloaded (hard cap 1.0 s) -> real holes open right behind the pack
                jx = math.sin(t * 74.0 + tl["cx"]) * 3.0
                jy = math.cos(t * 58.0 + tl["cy"]) * 1.5
                p.body.position = (tl["cx"] + jx, tl["cy"] + jy)
                p.body.angle = 0.0
                states.append(1)
            else:
                if not tl["dropped"]:
                    tl["dropped"] = True
                    tl["drop_t"] = t
                    self.pits.append((tl["x0"], tl["x1"]))
                dt_f = t - tl["drop_t"]
                if dt_f < 1.35:
                    p.body.position = (tl["cx"], tl["cy"] + 860.0 * dt_f * dt_f)
                    p.body.velocity = (0.0, 1720.0 * dt_f)
                    p.body.angle = tl["tilt"] * min(1.1, dt_f * 1.5)
                    states.append(2)
                elif tl["regrow"] and not self.sim.overtime and dt_f >= 1.35:
                    tl["hit"] = None
                    tl["dropped"] = False
                    if (tl["x0"], tl["x1"]) in self.pits:
                        self.pits.remove((tl["x0"], tl["x1"]))
                    p.body.position = (tl["cx"], tl["cy"])
                    p.body.velocity = (0.0, 0.0)
                    p.body.angle = 0.0
                    states.append(0)
                else:
                    p.body.position = (tl["cx"], tl["cy"] + 5000.0)
                    p.body.velocity = (0.0, 0.0)
                    states.append(3)
        self.sim.zones["bridge_states"] = states


class CollapseTower(Course):
    """v4.0: Multi-story zig-zag castle drop tower alternating L->R and R->L with shaking trapdoor segments, bouncy turn
    deflectors at each drop shaft, a rising themed lava/plasma floor below, and a descending ceiling purge wave so
    stragglers burn visibly on screen."""
    key = "collapse_tower"
    vertical_tower = True
    SHAFT_W = 2020.0
    STORY_Ys = (-1260.0, -910.0, -560.0, -210.0, +140.0)

    def __init__(self, sim):
        super().__init__(sim)
        self.trapdoors: list[dict] = []
        self.floor_bands: list[tuple[float, int]] = []
        self.purge_y = self.STORY_Ys[0] - 900.0       # starts well above the camera -> zero slime on heads at 00:00
        self.lava_y = self.STORY_Ys[-1] + 400.0
        self.hammers: list[tuple] = []
        self.spike_pockets: list[tuple[float, float, float, float]] = []

    def floor_y(self, x: float) -> float | None:
        return None

    def spawn_points(self, n: int, rng) -> list[tuple[float, float]]:
        cols, step = 4, 62
        return [(56 + (i % cols) * step + rng.uniform(-4, 4), self.STORY_Ys[0] - 45 - (i // cols) * 66 + rng.uniform(-4, 4))
                for i in range(n)]

    def _add_trapdoor(self, x0: float, y0: float, x1: float, y1: float, fatal_pit: bool = False) -> None:
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5 + 10.0
        w = abs(x1 - x0)
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = (cx, cy)
        box = pymunk.Poly.create_box(body, (w, 24), radius=4)
        p = self.sim.add_prop(body, [box], "bridge_tile", material="plank")
        self.trapdoors.append({
            "prop": p,
            "x0": min(x0, x1),
            "x1": max(x0, x1),
            "cx": cx,
            "cy": cy,
            "hit": None,
            "tilt": 1.0 if x1 > x0 else -1.0,
            "fatal": fatal_pit,
        })

    def build(self):
        r = self.sim.rng
        W_SH = self.SHAFT_W
        # Outer castle shaft containment walls
        bot = self.STORY_Ys[-1] + 500.0
        self.sim.static_segment((-28, -1660), (-28, bot), "wall", radius=14)
        self.sim.static_segment((W_SH + 28, -1660), (W_SH + 28, bot), "wall", radius=14)

        floors = [(y0, +1 if i % 2 == 0 else -1) for i, y0 in enumerate(self.STORY_Ys)]
        for idx, (y_start, d) in enumerate(floors):
            is_last = idx == len(floors) - 1
            self.floor_bands.append((y_start + 175.0, d))
            if d > 0:
                x_a = -24.0
                x_end = W_SH + 24.0 if is_last else (W_SH - 230.0)
                if idx == 0:
                    self.ground((x_a, y_start), (315.0, y_start + 10.0))
                    self.add_gate(292.0, top=y_start - 155.0)
                    # Steep opening chute + 108 px void pocket at x=640..748 so 1 slow dummy plunges at t ~ 1.8-2.8s!
                    self.ground((315.0, y_start + 10.0), (640.0, y_start + 145.0))
                    pk_y = y_start + 145.0
                    self.pits.append((640.0, 748.0))
                    self.spike_pockets.append((642.0, 746.0, pk_y + 52.0, pk_y + 135.0))
                    self.ground((748.0, pk_y + 22.0), (1220.0, pk_y + 60.0))
                    self._add_trapdoor(1228.0, pk_y + 60.0, 1362.0, pk_y + 70.0)
                    self.ground((1370.0, pk_y + 70.0), (x_end, pk_y + 98.0))
                elif is_last:
                    # Bottom sprint over the rising themed lava/plasma abyss (y = 840..960; lava stays >= 1065!)
                    self.ground((x_a, y_start), (510.0, y_start + 32.0))
                    self._add_trapdoor(518.0, y_start + 32.0, 665.0, y_start + 42.0, fatal_pit=True)
                    self.ground((672.0, y_start + 42.0), (1220.0, y_start + 78.0), material="bouncy")
                    self._add_trapdoor(1228.0, y_start + 78.0, 1380.0, y_start + 88.0, fatal_pit=True)
                    self.ground((1388.0, y_start + 88.0), (x_end, y_start + 122.0))
                else:
                    self.ground((x_a, y_start), (520.0, y_start + 34.0))
                    self._add_trapdoor(528.0, y_start + 34.0, 672.0, y_start + 44.0)
                    self.ground((680.0, y_start + 44.0), (1260.0, y_start + 84.0), material="bouncy")
                    self._add_trapdoor(1268.0, y_start + 84.0, 1412.0, y_start + 94.0)
                    self.ground((1420.0, y_start + 94.0), (x_end, y_start + 126.0))

                if not is_last:
                    self.sim.static_circle((W_SH - 85.0, y_start + 185.0), 22.0, "bumper")
                    self.sim.static_circle((W_SH - 165.0, y_start + 265.0), 19.0, "bumper")
            else:
                # Right-to-left story (x = W_SH+24 -> 230)
                self.ground((1520.0, y_start + 34.0), (W_SH + 24.0, y_start))
                self._add_trapdoor(1368.0, y_start + 44.0, 1512.0, y_start + 34.0)
                self.ground((790.0, y_start + 84.0), (1360.0, y_start + 44.0), material="bouncy")
                self._add_trapdoor(638.0, y_start + 94.0, 782.0, y_start + 84.0)
                self.ground((230.0, y_start + 126.0), (630.0, y_start + 94.0))
                # Swinging iron hammer mid-story for hero impacts & knockbacks
                hx, piv_y = 1060.0, y_start - 210.0
                hbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
                hbody.position = (hx, piv_y)
                arm = pymunk.Segment(hbody, (0, 0), (0, 210), 5)
                head = pymunk.Poly(hbody, [(-38, 194), (38, 194), (38, 236), (-38, 236)], radius=6)
                hp = self.sim.add_prop(hbody, [arm, head], "hammer", hazard=True)
                self.hammers.append((hp, r.uniform(0, 6.28), r.uniform(1.7, 2.2)))
                self.sim.statics.append({"type": "post", "c": (hx, piv_y)})
                # Left drop-shaft bouncy turn bumpers
                self.sim.static_circle((85.0, y_start + 185.0), 22.0, "bumper")
                self.sim.static_circle((165.0, y_start + 265.0), 19.0, "bumper")

        self.sim.finish_x = W_SH - 140.0
        self.sim.kill_y = self.STORY_Ys[-1] + 500.0
        self.sim.bounds = (-120.0, -1560.0, W_SH + 120.0, self.sim.kill_y)
        self.sim.statics.append({"type": "finish", "x": self.sim.finish_x, "y": self.STORY_Ys[-1] + 118.0})
        self.sim.hooks_frame.append(self._tick)

    def _story_index(self, y: float) -> int:
        for idx in range(len(self.STORY_Ys) - 1):
            mid = (self.STORY_Ys[idx] + self.STORY_Ys[idx + 1]) * 0.5 + 50.0
            if y < mid:
                return idx
        return len(self.STORY_Ys) - 1

    def drive_dir(self, c: "Contestant") -> float:
        return 1.0 if self._story_index(c.pos[1]) % 2 == 0 else -1.0

    def progress(self, c: "Contestant") -> float:
        x, y = c.pos
        st = self._story_index(y)
        along = x if st % 2 == 0 else (self.SHAFT_W - x)
        return st * (self.SHAFT_W + 100.0) + max(0.0, min(self.SHAFT_W + 50.0, along))

    def at_finish(self, c: "Contestant") -> bool:
        """Full-height pass-through finish sensor across the bottom-floor exit: first hero through wins instantly."""
        return self._story_index(c.pos[1]) == len(self.STORY_Ys) - 1 and c.pos[0] >= (self.sim.finish_x or (self.SHAFT_W - 140.0))

    def _tick(self, t: float):
        for hp, ph, w in self.hammers:
            ang = 0.85 * math.sin(t * w * self.sim.hazard_mult + ph)
            hp.body.angle = ang
            hp.body.angular_velocity = 0.85 * math.cos(t * w * self.sim.hazard_mult + ph) * w * self.sim.hazard_mult

        # 1. Shaking & dropping trapdoors (upper stories regrow after 3.2s so trailing racers stay in the hunt)
        for td in self.trapdoors:
            p = td["prop"]
            if td["hit"] is None and t >= 0.45:
                for c in self.sim.alive():
                    x, y = c.pos
                    if td["x0"] - 14 <= x <= td["x1"] + 14 and abs(y - (td["cy"] - 12)) < 48:
                        td["hit"] = t
                        break
            if td["hit"] is not None:
                age = t - td["hit"]
                if age < 0.42:
                    p.body.position = (td["cx"] + math.sin(t * 75.0 + td["cx"]) * 4.5, td["cy"])
                elif age < 2.2:
                    dt_f = age - 0.42
                    p.body.position = (td["cx"], td["cy"] + min(260.0, 680.0 * dt_f * dt_f))
                    p.body.angle = td["tilt"] * min(0.95, dt_f * 1.8)
                elif not td["fatal"] and not self.sim.overtime and age > 3.2:
                    td["hit"] = None
                    p.body.position = (td["cx"], td["cy"])
                    p.body.angle = 0.0
                else:
                    p.body.position = (td["cx"], td["cy"] + 3200.0)

        # 2. Rising lava/plasma pit strictly below Story 6 floor (y >= 1065) + Descending ceiling purge wave!
        if t > 3.0:
            self.lava_y = max(self.STORY_Ys[-1] + 225.0, self.lava_y - (9.5 * self.sim.speed_mult) / 30.0)
        alive = self.sim.alive()
        if t > 2.0 and alive:
            ys = sorted(c.pos[1] for c in alive)
            cluster_y = ys[len(ys) // 2]
            rate = 104.0 * self.sim.speed_mult
            if self.purge_y < cluster_y - 700.0:
                rate *= 2.6                      # fast catch-up so the hazard is always on screen chasing stragglers
            self.purge_y += rate / 30.0
            # Never overtake the median of the racing pack (hunts stragglers from behind/above)
            self.purge_y = min(self.purge_y, cluster_y - (150.0 if self.sim.overtime else 185.0))
            hero_ys = [c.pos[1] for c in alive if c.hero is not None]
            if len(hero_ys) == 1:
                self.purge_y = min(self.purge_y, hero_ys[0] - 170.0)   # the last hero must earn it at the finish

        for c in list(self.sim.alive()):
            x, y = c.pos
            if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in self.spike_pockets):
                self.sim.eliminate(c, "fell")
            elif y + c.radius >= self.lava_y:
                self.sim.eliminate(c, "lava")
            elif t > 2.2 and (y - c.radius) <= self.purge_y:
                self.sim.eliminate(c, "left_behind")

        self.sim.zones["lava_y"] = round(self.lava_y, 1)
        self.sim.zones["tower_fire_y"] = round(self.purge_y, 1)


class CrusherGauntlet(Course):
    """v4.3: Stone gauntlet whose slope-parallel crusher pistons (115-130 px heads) hang from ONE continuous riveted
    iron ceiling girder on castle pillars. Brutal uneven stroke (0.22 s yellow telegraph -> 0.18 s smash -> 0.32 s floor
    hold -> 0.65 s lift), sticky grip strips under select crushers so heroes genuinely get squished/stalled/punted,
    big textured desert boulders rolling against traffic or dropping from ceiling chutes, and a gentle opening run-in
    so the Golden Dummies survive into the first crushers. Ends at a visible checkered FINISH arch."""
    key = "crusher_gauntlet"
    chase_scale = 0.78

    TOP_OFF = 189.0      # head centre above floor at the top of the stroke
    BOT_OFF = 39.0       # head centre above floor at full stroke -> head bottom sits 6 px above the track
    GIRDER_DY = 470.0    # girder centreline above each crusher's floor
    TELE_S, SMASH_S, HOLD_S, LIFT_S = 0.22, 0.18, 0.32, 0.65

    def __init__(self, sim):
        super().__init__(sim)
        self.crushers: list[dict] = []
        self.boosts: list[tuple[str, float, float]] = []
        self.grips: list[tuple[str, float, float]] = []
        self.boulders: list = []
        self.next_boulder = 3.6
        self.chute_flip = False
        self._last_t: float | None = None

    def build(self):
        r = self.sim.rng
        self.start(first_gap=False)

        n = self.count("gauntlet_bays", 6, 7)
        pillar_xs: list[float] = []
        for i in range(n):
            # 1. Speed-boost approach slab with flush chevrons
            bx0 = self.x + 25.0
            ax0 = self.x
            self.seg(r.uniform(380, 470), r.uniform(150, 205))
            if i % 3 == 0:
                self.boosts.append(("rect", bx0, self.x - 20.0))
            pillar_xs.append((ax0 + self.x) / 2.0)

            # 2. Timed overhead crusher bay; head parallel to the local track slope
            bay_w = r.uniform(250, 310)
            bay_dy = r.uniform(32, 62)
            cx = self.x + bay_w * 0.5
            self.seg(bay_w, bay_dy)
            gy = self.ground_y_at(cx)
            theta = math.atan2(bay_dy, bay_w)
            head_w = r.uniform(115.0, 130.0)
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            body.position = (cx, gy - self.TOP_OFF)
            body.angle = theta
            c_, s_ = math.cos(-theta), math.sin(-theta)

            def loc(wx: float, wy: float, c_=c_, s_=s_) -> tuple[float, float]:
                return (wx * c_ - wy * s_, wx * s_ + wy * c_)

            head = pymunk.Poly.create_box(body, (head_w, 66), radius=6)
            # telescoping shaft stays world-vertical and ends inside the girder's hydraulic sleeve
            shaft = pymunk.Segment(body, loc(0, -33), loc(0, -(self.GIRDER_DY - self.TOP_OFF)), 12)
            cp = self.sim.add_prop(body, [shaft, head], "crusher", hazard=True)
            head.sensor = shaft.sensor = True        # crush/launch resolved by script -> zero floor tunnelling
            base_period = r.uniform(2.3, 3.0)
            self.crushers.append({"cp": cp, "cx": cx, "gy": gy, "theta": theta, "hw": head_w / 2.0,
                                  "cyc": r.uniform(0.0, 1.0), "period": base_period})
            # 3. sticky grip strip right under every other crusher (heroes slow down IN the smash zone)
            if i % 2 == 0:
                self.grips.append(("rect", cx - head_w * 0.85, cx + head_w * 0.35))

            # 4. Bouncy kicker + periodic downhill jump gap
            if i % 4 == 3:
                self.seg(r.uniform(115, 145), r.uniform(8, 20), material="bouncy")
                self.gap(r.uniform(68, 92) * self.ramp(i, n), r.uniform(42, 76))
            else:
                self.wave(r.uniform(220, 310), 24, 48)

        self.finish(700)
        # ONE continuous ceiling girder through every piston mount (+ lead-in/out), carried by castle pillars
        mounts = [(c["cx"], c["gy"] - self.GIRDER_DY) for c in self.crushers]
        if mounts:
            (x0, y0), (x1, y1) = mounts[0], mounts[-1]
            slope0 = (mounts[1][1] - y0) / max(1.0, mounts[1][0] - x0) if len(mounts) > 1 else 0.0
            slope1 = (y1 - mounts[-2][1]) / max(1.0, x1 - mounts[-2][0]) if len(mounts) > 1 else 0.0
            pts = [(x0 - 420.0, y0 - 420.0 * slope0)] + mounts + [(x1 + 420.0, y1 + 420.0 * slope1)]

            def girder_y(x: float) -> float:
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    if ax <= x <= bx:
                        return ay + (by - ay) * (x - ax) / max(1.0, bx - ax)
                return pts[-1][1]

            pillars = []
            for px in [pts[0][0] + 60.0] + pillar_xs[1:] + [pts[-1][0] - 60.0]:
                fy = self.floor_y(px)
                if fy is not None and fy - girder_y(px) > 120.0:
                    pillars.append((px, girder_y(px), fy))
            self.sim.statics.append({"type": "ceiling_girder", "pts": pts, "mounts": mounts, "pillars": pillars})
        self.sim.surface_mods.append(self._surface_mod)
        self.sim.hooks_frame.append(self._tick)

    def _surface_mod(self, c: "Contestant") -> float:
        x = c.pos[0]
        if any(g[1] <= x <= g[2] for g in self.grips):
            return 0.55
        return 1.32 if any(b[1] <= x <= b[2] for b in self.boosts) else 1.0

    def _stroke(self, s: float, period: float) -> tuple[float, float, str]:
        """(head-centre offset above floor, shake px, phase) for s seconds into a cycle of `period` seconds."""
        busy = self.TELE_S + self.SMASH_S + self.HOLD_S + self.LIFT_S
        idle = max(0.15, period - busy)
        if s < idle:
            return self.TOP_OFF, 0.0, "idle"
        s -= idle
        if s < self.TELE_S:                            # 0.22 s yellow flash + shake telegraph
            return self.TOP_OFF, 3.0 * math.sin(s * 140.0), "tele"
        s -= self.TELE_S
        if s < self.SMASH_S:                           # FAST 0.18 s smash (ease-in)
            k = s / self.SMASH_S
            return self.TOP_OFF - (self.TOP_OFF - self.BOT_OFF) * k * k, 0.0, "smash"
        s -= self.SMASH_S
        if s < self.HOLD_S:                            # 0.32 s floor hold
            return self.BOT_OFF, 0.0, "hold"
        s -= self.HOLD_S
        k = min(1.0, s / self.LIFT_S)                  # slower 0.65 s hydraulic lift
        k = k * k * (3 - 2 * k)
        return self.BOT_OFF + (self.TOP_OFF - self.BOT_OFF) * k, 0.0, "lift"

    def _tick(self, t: float):
        dt = 1.0 / 30.0 if self._last_t is None else max(0.0, min(0.1, t - self._last_t))
        self._last_t = t
        hm = max(0.5, float(self.sim.hazard_mult))
        warn: list[float] = []
        for c in self.crushers:
            period = max(1.6, c["period"] / hm)
            c["cyc"] = (c["cyc"] + dt / period) % 1.0
            s = c["cyc"] * period
            off, shake, phase = self._stroke(s, period)
            off_prev, _, _ = self._stroke(max(0.0, s - dt), period)
            cx, gy = c["cx"], c["gy"]
            c["cp"].body.position = (cx + shake, gy - off)
            c["cp"].body.velocity = (0.0, (off_prev - off) / max(1e-3, dt))
            if phase == "tele":
                warn.append(cx)
            if phase not in ("smash", "hold"):
                continue
            head_bottom = gy - off + 33.0
            for v in list(self.sim.alive()):
                dx = v.pos[0] - cx
                if abs(dx) > c["hw"] + v.radius or v.pos[1] - v.radius > head_bottom or v.pos[1] < gy - self.TOP_OFF:
                    continue
                if v.pos[1] + v.radius < head_bottom - 10.0 and v.pos[1] < gy - 2.0 * v.radius - 10.0:
                    continue                           # airborne above the head's path
                if v.hero is None and t >= 4.6:
                    self.sim.eliminate(v, "crushed")   # dummies are genuinely flattened
                elif v.stun <= 0.0:
                    # heroes get SQUASHED: flattened + stunned, then stalled / punted forward-low / punted backward
                    v.squash = 1.0
                    v.stun = 0.55 * (v.hero.stun_mult if v.hero else 1.0)
                    roll = self.sim.rng.random()
                    vx = v.body.velocity.x
                    if roll < 0.45:
                        v.body.velocity = (vx * 0.15, 60.0)                      # pancaked & stalled
                        how = "stall"
                    elif roll < 0.80:
                        v.body.velocity = (max(320.0, vx) + 120.0, -160.0)      # punted forward-low
                        how = "punt"
                    else:
                        v.body.velocity = (-240.0, -220.0)                      # spat back out behind
                        how = "spit"
                    self.sim.event("crush_hit", [v.key], v.pos, how=how, hero=v.hero is not None)
        # sticky grip strips: grounded balls inside a strip bleed speed (they linger in the smash zone)
        for v in self.sim.alive():
            if v.grounded and any(g[1] <= v.pos[0] <= g[2] for g in self.grips):
                vx, vy = v.body.velocity
                v.body.velocity = (vx * 0.93, vy)

        # Big textured desert boulders: rolling against traffic, alternating with ceiling-chute drops
        if t >= self.next_boulder:
            self.next_boulder = t + self.sim.rng.uniform(3.4, 4.8) / hm
            ahead = self.sim.cam_x + 780.0
            if self.sim.finish_x is None or ahead < self.sim.finish_x - 240.0:
                gy = self.ground_y_at(ahead)
                rad = self.sim.rng.uniform(38.0, 44.0)
                mass = 26.0 * (rad / 34.0) ** 2
                bbody = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, rad))
                self.chute_flip = not self.chute_flip
                if self.chute_flip:
                    bbody.position = (ahead, gy - 185.0)
                    bbody.velocity = (-255.0 * hm, 0.0)
                else:                                   # dropped from a ceiling chute just ahead of the pack
                    drop_x = self.sim.cam_x + self.sim.rng.uniform(380.0, 560.0)
                    bbody.position = (drop_x, self.ground_y_at(drop_x) - self.GIRDER_DY + 70.0)
                    bbody.velocity = (-60.0, 80.0)
                bsh = pymunk.Circle(bbody, rad)
                bsh.friction, bsh.elasticity = 0.82, 0.32
                bp = self.sim.add_prop(bbody, [bsh], "boulder", hazard=True)
                self.boulders.append(bp)
        for bp in list(self.boulders):
            if bp.body.position.y > self.sim.kill_y + 180 or bp.body.position.x < self.sim.cam_x - 1800:
                self.sim.remove_prop(bp)
                self.boulders.remove(bp)

        self.sim.zones["boost_zones"] = list(self.boosts)
        self.sim.zones["grip_zones"] = list(self.grips)
        self.sim.zones["crusher_warn"] = warn


class SumoPoolPit(TopArena):
    """v4.0 TOP_DOWN octagonal sumo pool table: 4 high-elasticity bouncy bumper rails on N/S/E/W walls, 4 open diagonal
    corner void pockets, and oscillating center piston bumpers that widen pocket Knockouts until ALIVE: 1/X."""
    key = "sumo_pool_pit"
    true_finish = True

    def build(self):
        self.R = self.p.setdefault("radius", 435)
        self.spawn_r = self.R * 0.56
        self.sim.walkable = self._walkable
        self.sim.statics.append({"type": "octagon_pool", "c": (0, 0), "r": self.R})

        # 4 kinematic high-elasticity bouncy rails along N, S, E, W straight walls (shrink inward with edge_k!)
        self.rails = []
        rail_half = self.R * 0.36
        for side_ang in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            nx, ny = math.cos(side_ang), math.sin(side_ang)
            tx, ty = -ny, nx
            body.position = (nx * self.R * 0.87, ny * self.R * 0.87)
            seg = pymunk.Segment(body, (-tx * rail_half, -ty * rail_half), (tx * rail_half, ty * rail_half), 12)
            rp = self.sim.add_prop(body, [seg], "pool_rail", material="bouncy")
            seg.elasticity = 1.42
            self.rails.append((rp, nx, ny))

        # Center hub + 4 radial pop-up piston bumpers
        self.pistons = []
        cbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        cbody.position = (0.0, 0.0)
        csh = pymunk.Circle(cbody, 30.0)
        cp = self.sim.add_prop(cbody, [csh], "piston_bumper", material="bumper")
        csh.elasticity = 1.30
        self.center_piston = cp
        for k in range(4):
            ang = k * math.pi / 2 + math.pi / 4   # aimed right toward the 4 diagonal corner pockets!
            pbody = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            pbody.position = (math.cos(ang) * 125.0, math.sin(ang) * 125.0)
            psh = pymunk.Circle(pbody, 22.0)
            pp = self.sim.add_prop(pbody, [psh], "piston_bumper", material="bumper")
            psh.elasticity = 1.32
            self.pistons.append((pp, ang))

        self.sim.hooks_step.append(self._step_arena)
        self.frame_top(self.R)

    def shrink_target(self, t: float) -> float:
        dc = self.sim.cfg["disc"]
        kmin = 48.0 / self.R
        p = min(1.0, max(0.0, (t - 3.0) / (float(dc["shrink_end_s"]) - 3.0)))
        return 1.0 - (1.0 - kmin) * (p ** 1.24)

    def push_progress(self) -> float:
        dc = self.sim.cfg["disc"]
        start = float(dc["shrink_end_s"]) - float(dc["final_push_s"]) + 1.0
        return min(1.0, max(0.0, (self.sim.t - start) / float(dc["final_push_s"])))

    def _pocket_radius(self) -> float:
        return 76.0 + 54.0 * self.push_progress()

    def _walkable(self, x: float, y: float) -> bool:
        ax, ay = abs(x), abs(y)
        R = self.R
        # Octagon interior
        if ax > R * 0.88 or ay > R * 0.88 or (ax + ay) > R * 1.26:
            return False
        # 4 open corner void pockets at (±0.67R, ±0.67R)
        pk = R * 0.67
        pr = self._pocket_radius()
        if math.hypot(ax - pk, ay - pk) < pr:
            return False
        return True

    def _step_arena(self, dt: float):
        tw = getattr(self.sim, "twist", None)
        k_all = self.sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)
        p = self.push_progress()
        t = self.sim.t

        # Keep N/S/E/W bouncy rails aligned with shrinking octagon; retract rails when tiny so final 2 fall cleanly
        for rp, nx, ny in self.rails:
            if k_all < 0.34:
                rp.body.position = (nx * 4000.0, ny * 4000.0)
            else:
                rp.body.position = (nx * self.R * 0.87 * k_all, ny * self.R * 0.87 * k_all)

        # Oscillate diagonal piston bumpers to knock balls into the 4 corner pockets; retract in tiny endgame
        for idx, (pp, ang) in enumerate(self.pistons):
            if k_all < 0.44:
                pp.body.position = (4000.0, 4000.0)
                pp.body.velocity = (0.0, 0.0)
            else:
                ph = t * 3.1 * self.sim.hazard_mult + idx * 1.57
                rad = (112.0 + 44.0 * math.sin(ph)) * k_all
                vr = 44.0 * 3.1 * self.sim.hazard_mult * math.cos(ph) * k_all
                pp.body.position = (math.cos(ang) * rad, math.sin(ang) * rad)
                pp.body.velocity = (math.cos(ang) * vr, math.sin(ang) * vr)

        if k_all < 0.26:
            self.center_piston.body.position = (4000.0, 4000.0)
        else:
            self.center_piston.body.position = (0.0, 0.0)

        survivors = self.sim.alive()
        calm = len(survivors) <= 1
        slosh_a = t * 2.7
        cur_r = max(24.0, self.R * k_all)
        for c in survivors:
            x, y = c.pos
            m = c.body.mass
            if calm:
                c.body.velocity = c.body.velocity * 0.82
                c.body.apply_force_at_world_point((-x * 14.0 * m, -y * 14.0 * m), c.body.position)
                continue
            if t > 2.8:
                sf = (195.0 + 330.0 * p) * self.sim.speed_mult * m
                c.body.apply_force_at_world_point((math.cos(slosh_a) * sf, math.sin(slosh_a) * sf), c.body.position)
            if p > 0.0:
                d = math.hypot(x, y)
                ux, uy = (x / d, y / d) if d > 1.0 else (math.cos(slosh_a), math.sin(slosh_a))
                acc = 960.0 * p * (0.35 + min(1.5, d / cur_r))
                c.body.apply_force_at_world_point((ux * acc * m, uy * acc * m), c.body.position)


ARENA_CLASSES = {
    c.key: c
    for c in (
        FlatTrack, RampDescent, PitPlatforms, TieredTower, NarrowBridge, BouncyPadField,
        SeesawGauntlet, ConveyorChaos, PachinkoDrop, CrumblingBridge, CollapseTower, CrusherGauntlet,
        RotatingDisc, SumoPoolPit, MazeCorridors, HexTileDrop, BumperRing,
    )
}


def arena_class(key: str):
    if key in ARENA_CLASSES:
        return ARENA_CLASSES[key]
    from src.games import arenas_v6  # noqa: F401  (registers the v6 arenas)
    from src.games.arena_kit import REGISTRY
    return REGISTRY[key]


def build(sim: "Sim") -> Arena:
    a = arena_class(sim.recipe.arena)(sim)
    a.build()
    return a
