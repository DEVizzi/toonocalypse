"""v6 side-view arenas, group B: Sweeper Circuit, Knock-Knock Doors, Swing Canyon, Clockwork Cogs, Inferno Ascent.

All randomness is drawn from `self.sim.rng` inside `build()`; per-frame dynamic state lives in `self.sim.zones`
(always re-assigned, never mutated in place, because zones are shallow-copied per recorded frame).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymunk

from src.games.arena_kit import (SIDE, ClimbTower, V6Course, kin_body, kin_box, kin_circle, move_kin, park,
                                 register, riders, zap)

if TYPE_CHECKING:
    from src.physics.engine import Contestant

_SIDE_TWISTS = ("low_gravity", "heavy_gravity", "speed_boost_zones", "reversed_controls", "giant_ball")


def _hold(sim, c: "Contestant") -> None:
    """A deliberately waiting ball must not trigger the engine's anti-stuck eject hop."""
    c.last_unstick_t = sim.t


def _patient(c: "Contestant") -> bool:
    """Heroes wait for their moment; ~40% of crash dummies never do (fodder that leaps blindly)."""
    return c.is_hero or (sum(map(ord, c.key)) % 5) >= 2


# ================================================================================================ 1. SWEEPER CIRCUIT
@register("sweeper_circuit", SIDE, "Sweeper Circuit", "giant sweeper arms over bottomless pits",
          quips=("Jump the low bar, duck the high bar, cry later!",
                 "The sweeper does not care about your feelings."),
          goals=("reach_finish", "last_one_standing"), hazards=(), twists=_SIDE_TWISTS)
class SweeperCircuit(V6Course):
    """Platforms over pits, each patrolled by a sweeper arm: a hub post with an arm whose tip sweeps back and forth
    across the deck (the side-on projection of Wipeout's rotating Sweeper). LOW bars (~19 px up) must be jumped,
    HIGH bars (~84 px up) punt anyone who jumps into them. Arm speed scales with sim.hazard_mult (2x in overtime)."""

    def __init__(self, sim):
        super().__init__(sim)
        self.arms: list[dict] = []
        self.hit_cd: dict[tuple[int, str], float] = {}

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.p.setdefault("stations", r.randint(10, 11))
        kinds, prev = [], []
        for i in range(n):
            if i == 0:
                k = "low"
            elif len(prev) >= 2 and prev[-1] == prev[-2]:
                k = "high" if prev[-1] == "low" else "low"
            else:
                k = "low" if r.random() < 0.55 else "high"
            kinds.append(k)
            prev.append(k)
        for i in range(n):
            self.seg(r.uniform(90, 150), r.uniform(10, 24))
            lp = r.uniform(520, 640)
            x0, fy = self.x, self.y
            self.seg(lp, 0.0)
            self._arm(len(self.arms), x0, x0 + lp, fy, kinds[i] == "low")
            self.gap(r.uniform(95, 140) * self.ramp(i, n), r.uniform(18, 40))
        self.seg(r.uniform(170, 230), 24)
        self.finish(700)
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._tick)

    def _arm(self, idx: int, x0: float, x1: float, fy: float, low: bool) -> None:
        r = self.sim.rng
        hx = (x0 + x1) * 0.5
        L = (x1 - x0) * 0.5 - 26.0
        h = r.uniform(17.0, 21.0) if low else r.uniform(80.0, 88.0)
        br = 7.0 if low else 9.0
        w = r.uniform(1.55, 1.95) if low else r.uniform(1.25, 1.6)
        ph = r.uniform(0.0, 2 * math.pi)
        y = fy - h
        tip = hx + L * math.sin(ph)
        body = kin_body(self.sim, (tip, y))
        seg = pymunk.Segment(body, (0, 0), (self._span(hx - tip), 0), br)
        p = self.sim.add_prop(body, [seg], "sweeper_arm", material="prop")
        p.shapes[0].update(hub=(hx, fy), h=h, low=low, L=L, idx=idx)
        self.sim.statics.append({"type": "sweeper_hub", "x": hx, "y": fy, "h": h, "low": low})
        self.arms.append({"prop": p, "seg": seg, "hx": hx, "fy": fy, "y": y, "L": L, "w": w, "ph": ph, "low": low,
                          "br": br, "x0": x0, "x1": x1, "tip": tip, "vt": 0.0})

    @staticmethod
    def _span(d: float) -> float:
        return d if abs(d) > 0.5 else 0.5

    def _step(self, dt: float) -> None:
        m = self.sim.hazard_mult
        for a in self.arms:
            a["ph"] += a["w"] * m * dt
            tip = a["hx"] + a["L"] * math.sin(a["ph"])
            move_kin(a["prop"], tip, a["y"], dt)
            a["seg"].unsafe_set_endpoints((0, 0), (self._span(a["hx"] - tip), 0))
            a["tip"] = tip
            a["vt"] = a["L"] * math.cos(a["ph"]) * a["w"] * m

    def _tick(self, t: float) -> None:
        sim = self.sim
        for ai, a in enumerate(self.arms):
            tip, vt = a["tip"], a["vt"]
            lo, hi = min(tip, a["hx"]), max(tip, a["hx"])
            for c in sim.alive():
                x, y = c.pos
                if not (a["x0"] - 60 <= x <= a["x1"] + 60):
                    continue
                px = min(hi, max(lo, x))
                if math.hypot(x - px, y - a["y"]) > c.radius + a["br"] + 4:
                    continue
                k = (ai, c.key)
                if t < self.hit_cd.get(k, -9.0):
                    continue
                sgn = math.copysign(1.0, vt) if abs(vt) > 1 else math.copysign(1.0, x - a["hx"])
                mk = 1.0 / max(1.0, float(c.body.mass)) ** 0.3
                if a["low"]:
                    if abs(vt) < 60 or abs(x - tip) > c.radius + a["br"] + 6:
                        continue                       # only the sweeping tip knocks (riding on top is fine)
                    zap(sim, c, sgn * (140 + 0.3 * abs(vt)) * mk, -190 * mk, stun=0.4, name="sweeper", low=True)
                else:
                    zap(sim, c, sgn * (170 + 0.25 * abs(vt)) * mk, 160 * mk, stun=0.5, name="sweeper", low=False)
                self.hit_cd[k] = t + 0.7
        sim.zones["sweep"] = tuple((round(a["tip"], 1), round(a["vt"], 1)) for a in self.arms)

    def jump_hint(self, c: "Contestant"):
        x, y = c.pos
        vx = float(c.body.velocity.x)
        for a in self.arms:
            if not (a["x0"] - 50 <= x <= a["x1"] + 50) or y < a["fy"] - 160:
                continue
            tip, hx = a["tip"], a["hx"]
            inside = (x - hx) * (tip - hx) > 0 and abs(x - hx) < abs(tip - hx)
            if a["low"]:
                if inside:
                    continue
                d = x - tip
                closing = (a["vt"] - vx) * math.copysign(1.0, d)
                if closing > 20:
                    ttc = (abs(d) - c.radius - a["br"]) / closing
                    if -0.05 < ttc < 0.3:
                        return True
            else:
                if a["x1"] - 80 <= x <= a["x1"] + 50:
                    return None                         # still free to hop the pit at the platform end
                if inside or abs(x - tip) < 190:
                    return False
        return None


# ================================================================================================ 2. KNOCK-KNOCK DOORS
BREAKAWAY, TOUGH, TRAPDOOR = "breakaway", "tough", "trapdoor"


@register("knock_doors", SIDE, "Knock-Knock Doors", "mystery castle doors: smash, bounce or trapdoor",
          quips=("Knock knock. Who is there? A bottomless pit!",
                 "Pick a door, any door. Choose poorly."),
          goals=("reach_finish", "last_one_standing"), hazards=(), twists=_SIDE_TWISTS)
class KnockDoors(V6Course):
    """A corridor sprint through 5-7 castle walls, each with one identical-looking wooden door. BREAKAWAY doors shatter
    on the first hit, TOUGH doors bounce you back and only break after ~3 hits worth of impulse (or one heavy fast
    bash), TRAPDOOR walls drop the floor plank in front of them (a new pit) and swing their door open."""
    DOOR_H = 150.0
    WALL_W = 56.0
    PLANK_W = 150.0
    TOUGH_IMPULSE = 1000.0

    def __init__(self, sim):
        super().__init__(sim)
        self.doors: list[dict] = []
        self.door_cd: dict[tuple[int, str], float] = {}

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.p.setdefault("walls", r.randint(5, 7))
        kinds = [BREAKAWAY, TOUGH, TRAPDOOR] + [r.choice([BREAKAWAY, TOUGH, TOUGH, TRAPDOOR]) for _ in range(n - 3)]
        r.shuffle(kinds)
        for i in range(n):
            self.seg(r.uniform(160, 240), r.uniform(10, 30))
            if i == 0 or r.random() < 0.8:
                self.gap(r.uniform(85, 130) * self.ramp(i, n), r.uniform(10, 30))
            self.seg(r.uniform(190, 280), r.uniform(5, 20))
            self._wall(i, kinds[i])
            self.seg(r.uniform(120, 180), 14)
        self.seg(220, 30)
        self.finish(700)
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._tick)

    def _wall(self, i: int, kind: str) -> None:
        sim = self.sim
        x0, y = self.x, self.y
        pw, dh, ww = self.PLANK_W, self.DOOR_H, self.WALL_W
        plank = kin_box(sim, (x0 + pw / 2, y + 10), pw, 20, "kd_plank", material="ground", radius=2)
        plank.shapes[0]["idx"] = i
        self.span(x0, y, x0 + pw, y)
        self.x += pw
        wx = self.x
        sim.static_poly([(wx, y - dh), (wx + ww, y - dh), (wx + ww, y - 1500), (wx, y - 1500)], "wall")
        sim.statics[-1].update(type="kd_wall", x=wx, w=ww, floor=y, door_h=dh, idx=i)
        door = kin_box(sim, (wx + ww / 2, y - dh / 2), 40, dh, "kd_door", material="wall", radius=3)
        door.shapes[0]["idx"] = i
        self.seg(ww, 0.0)
        self.doors.append({"idx": i, "kind": kind, "door": door, "plank": plank, "wx": wx, "fy": y, "px0": x0,
                           "state": 0, "hits": 0, "acc": 0.0, "t_open": -1.0, "trig": None, "flap_t": None})

    def _open(self, d: dict, how: str, c: "Contestant | None" = None) -> None:
        d["state"] = 2 if how == "trapdoor" else 1
        d["t_open"] = self.sim.t
        park(d["door"])
        self.sim.event("arena_hit", [c.key] if c else [], (d["wx"] + self.WALL_W / 2, d["fy"] - self.DOOR_H / 2),
                       name="door_" + how, door=d["idx"])

    def _step(self, dt: float) -> None:
        sim = self.sim
        t = sim.t
        for d in self.doors:
            if d["state"] != 0:
                continue
            dx0 = d["wx"] + self.WALL_W / 2 - 20
            for c in sim.alive():
                x, y = c.pos
                if y < d["fy"] - self.DOOR_H - c.radius or y > d["fy"] + 6:
                    continue
                gap = dx0 - (x + c.radius)
                vx = float(c.body.velocity.x)
                if not (-7.0 <= gap <= 5.0) or vx < 30:
                    continue
                k = (d["idx"], c.key)
                if t < self.door_cd.get(k, -9.0):
                    continue
                self.door_cd[k] = t + 0.3
                m = float(c.body.mass)
                if d["kind"] == BREAKAWAY:
                    self._open(d, "smash", c)
                    break
                if d["kind"] == TOUGH:
                    d["acc"] += m * vx
                    d["hits"] += 1
                    if (m >= 4.0 and vx > 300) or d["acc"] >= self.TOUGH_IMPULSE:
                        self._open(d, "smash", c)
                        break
                    zap(sim, c, -(170 + 0.5 * vx), -120, stun=0.35, name="door_bounce", door=d["idx"])
                else:
                    d["hits"] += 0                     # trapdoor door: plain solid door until the floor drops

    def _tick(self, t: float) -> None:
        sim = self.sim
        for d in self.doors:
            if d["kind"] != TRAPDOOR:
                continue
            if d["trig"] is None and d["state"] == 0:
                if riders(sim, d["px0"], d["px0"] + self.PLANK_W, d["fy"], tol=16):
                    d["trig"] = t
            if d["trig"] is not None and d["flap_t"] is None and t - d["trig"] >= 0.3:
                d["flap_t"] = t
                self.pits.append((d["px0"], d["px0"] + self.PLANK_W))
                self._open(d, "trapdoor")
            if d["flap_t"] is not None:
                k = min(1.0, (t - d["flap_t"]) / 0.25)
                th = -0.5 * math.pi * k * k
                hx, hy = d["wx"], d["fy"]
                ox, oy = -self.PLANK_W / 2, 10.0
                cx = hx + ox * math.cos(th) - oy * math.sin(th)
                cy = hy + ox * math.sin(th) + oy * math.cos(th)
                move_kin(d["plank"], cx, cy, 1.0 / 30.0, angle=th)
                if k >= 1.0:
                    d["plank"].body.velocity = (0, 0)
                    d["plank"].body.angular_velocity = 0.0
        sim.zones["kd_doors"] = tuple((d["state"], d["hits"], round(d["t_open"], 3),
                                       1 if (d["trig"] is not None and d["state"] == 0) else 0) for d in self.doors)

    def jump_hint(self, c: "Contestant"):
        x, y = c.pos
        for d in self.doors:
            if d["state"] == 0 and d["px0"] - 120 <= x <= d["wx"] and abs(y - d["fy"]) < 90:
                return False                            # hopping into a closed door is pointless
        return None


# ================================================================================================ 3. SWING CANYON
@register("swing_canyon", SIDE, "Swing Canyon", "pendulum platforms over a bottomless canyon",
          quips=("Timing is everything. Your timing is nothing.",
                 "Swing low, sweet chariot, swing right into the canyon!"),
          goals=("reach_finish", "last_one_standing"), hazards=(), twists=("heavy_gravity", "speed_boost_zones",
                                                                           "giant_ball"))
class SwingCanyon(V6Course):
    """A deep canyon crossed by 5-7 level pendulum decks hanging on chains. Balls wait on the ledge until the deck
    swings back, ride it (relative braking keeps them aboard) and jump off at the forward apex onto the far ledge.
    Mistimed boarding or a shove mid-swing drops you into the canyon."""
    DECK_H = 22.0

    def __init__(self, sim):
        super().__init__(sim)
        self.swings: list[dict] = []
        self._riding: dict[str, dict] = {}

    def build(self):
        r = self.sim.rng
        self.start()
        n = self.p.setdefault("swings", r.randint(5, 7))
        for i in range(n):
            self.seg(r.uniform(200, 280), r.uniform(20, 40))
            self.seg(r.uniform(70, 100), 0.0)
            self._swing(i)
        self.seg(r.uniform(200, 260), 24)
        self.finish(700)
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._tick)

    def _swing(self, i: int) -> None:
        r, sim = self.sim.rng, self.sim
        L = r.uniform(230, 300)
        A = r.uniform(0.42, 0.52)
        w = r.uniform(2.0, 2.45)
        dw = r.uniform(150, 175)
        dh = self.DECK_H
        xA, yA = self.x, self.y
        cx = xA + 14 + dw / 2 + L * math.sin(A)
        G = 28 + dw + 2 * L * math.sin(A)
        py = yA + 4 + dh / 2 - L * math.cos(A)
        ph = r.uniform(0, 2 * math.pi)
        th = A * math.sin(ph)
        deck = kin_box(sim, (cx + L * math.sin(th), py + L * math.cos(th)), dw, dh, "swing_deck", material="plank",
                       radius=3)
        deck.shapes[0].update(pivot=(cx, py), beam=(xA, xA + G, yA), L=L, dw=dw)
        self.gap(G, 0.0)
        self.swings.append({"prop": deck, "cx": cx, "py": py, "L": L, "A": A, "w": w, "ph": ph, "dw": dw,
                            "xA": xA, "xB": xA + G, "yA": yA, "x": cx + L * math.sin(th),
                            "y": py + L * math.cos(th), "vx": 0.0})

    def _step(self, dt: float) -> None:
        m = math.sqrt(self.sim.speed_mult)
        for s in self.swings:
            s["ph"] += s["w"] * m * dt
            th = s["A"] * math.sin(s["ph"])
            x, y = s["cx"] + s["L"] * math.sin(th), s["py"] + s["L"] * math.cos(th)
            move_kin(s["prop"], x, y, dt, angle=0.0)
            s["vx"] = (x - s["x"]) / dt
            s["x"], s["y"] = x, y

    def _deck_of(self, c: "Contestant") -> dict | None:
        x, y = c.pos
        for s in self.swings:
            top = s["y"] - self.DECK_H / 2
            if s["x"] - s["dw"] / 2 - 6 <= x <= s["x"] + s["dw"] / 2 + 6 and top - c.radius - 16 <= y <= top + 6:
                return s
        return None

    def _edge_of(self, c: "Contestant") -> dict | None:
        x, y = c.pos
        for s in self.swings:
            if s["xA"] - 120 <= x <= s["xA"] + 4 and abs(y + c.radius - s["yA"]) < 30:
                return s
        return None

    def _boardable(self, s: dict) -> bool:
        gap = (s["x"] - s["dw"] / 2) - s["xA"]
        return gap < 40 or (s["vx"] < -40 and gap < 95)

    @staticmethod
    def _launch(s: dict) -> bool:
        front = s["x"] + s["dw"] / 2
        return (s["vx"] > 30 and front >= s["xB"] - 75) or front >= s["xB"] - 30

    def brake(self, c: "Contestant") -> bool:
        if not _patient(c):
            return False
        s = self._deck_of(c)
        if s is not None:
            if self._launch(s):
                return False
            self._riding[c.key] = s
            _hold(self.sim, c)
            return True
        e = self._edge_of(c)
        if e is not None and not self._boardable(e):
            _hold(self.sim, c)
            return True
        return False

    def jump_hint(self, c: "Contestant"):
        s = self._deck_of(c)
        if s is not None:
            return True if self._launch(s) else False
        e = self._edge_of(c)
        if e is not None:
            return False
        return None

    def _tick(self, t: float) -> None:
        # relative braking: the Brain brakes against WORLD velocity; riders brake against the moving deck instead
        for key, s in self._riding.items():
            c = self.sim.by_key[key]
            if c.alive:
                self.sim.push(c, s["vx"] * float(c.body.mass) * 7.0 * min(1.0, c.traction), 0.0)
        self._riding = {}
        self.sim.zones["swing_x"] = tuple(round(s["x"], 1) for s in self.swings)


# ================================================================================================ 4. CLOCKWORK COGS
@register("clockwork_cogs", SIDE, "Clockwork Cogs", "giant spinning brass gears over the abyss",
          quips=("Tick tock, you are on the clock... and the clock is spinning!",
                 "These gears grind contestants into fine powder."),
          goals=("reach_finish", "last_one_standing"), hazards=(), twists=_SIDE_TWISTS)
class ClockworkCogs(V6Course):
    """Giant kinematic gears (r 90-140, alternating spin) as stepping stones at varying heights over pits, with steam
    piston pads popping up and down in the wider gaps. Riders are carried by the rim; backward cogs fight you."""

    def __init__(self, sim):
        super().__init__(sim)
        self.gears: list[dict] = []
        self.pistons: list[dict] = []

    def build(self):
        r, sim = self.sim.rng, self.sim
        self.start()
        self.seg(r.uniform(110, 150), 12)
        n = self.p.setdefault("gears", r.randint(10, 12))
        d0 = r.choice([-1, 1])
        for i in range(n):
            R = r.uniform(90, 140)
            piston = i > 0 and r.random() < 0.35
            clear = r.uniform(190, 230) if piston else r.uniform(70, 110) * self.ramp(i, n)
            dy = r.uniform(-35, 55)
            prev_top = self.y
            top = prev_top + dy
            if piston:
                px = self.x + clear / 2
                hi = min(prev_top, top) - 4
                self._piston(px, hi)
            self.gap(clear, dy)
            cx = self.x + R
            spin = (d0 if i % 2 == 0 else -d0) * r.uniform(0.45, 0.85)
            g = kin_circle(sim, (cx, top + R), R, "cog_gear", material="ground")
            g.body.angular_velocity = spin
            g.shapes[0].update(teeth=max(10, int(R / 9)), spin=spin)
            self.gears.append({"prop": g, "cx": cx, "cy": top + R, "R": R, "w": spin, "top": top})
            self.gap(2 * R, 0.0)
        self.gap(r.uniform(80, 110), r.uniform(10, 30))
        self.seg(r.uniform(180, 240), 20)
        self.finish(700)
        self.sim.hooks_step.append(self._step)

    def _piston(self, x: float, hi_top: float) -> None:
        r = self.sim.rng
        w_box, h_box = 96.0, 24.0
        hi = hi_top + h_box / 2
        lo = hi + 150.0
        p = kin_box(self.sim, (x, lo), w_box, h_box, "cog_piston", material="ground", radius=3)
        p.shapes[0].update(base=lo + 60.0, hi=hi, lo=lo)
        self.pistons.append({"prop": p, "x": x, "hi": hi, "lo": lo, "w": 2 * math.pi / r.uniform(1.7, 2.2),
                             "ph": r.uniform(0, 2 * math.pi), "y": lo, "w_box": w_box})

    def _step(self, dt: float) -> None:
        m = 1.0 + 0.5 * (self.sim.hazard_mult - 1.0)
        for g in self.gears:
            g["prop"].body.angular_velocity = g["w"] * m
        for p in self.pistons:
            p["ph"] += p["w"] * m * dt
            s = max(-1.0, min(1.0, 1.3 * math.cos(p["ph"])))
            y = p["hi"] + (p["lo"] - p["hi"]) * (0.5 + 0.5 * s)
            move_kin(p["prop"], p["x"], y, dt)
            p["y"] = y

    def jump_hint(self, c: "Contestant"):
        x, y = c.pos
        for g in self.gears:
            dx, dy = x - g["cx"], y - g["cy"]
            if dy < -0.3 * g["R"] and abs(math.hypot(dx, dy) - g["R"] - c.radius) < 16:
                return True if dx > 0.32 * g["R"] else None
        for p in self.pistons:
            if abs(x - p["x"]) < p["w_box"] / 2 + 6 and -c.radius - 30 < y - (p["y"] - 12) < 8:
                return True if p["y"] < p["hi"] + 25 else False
        return None


# ================================================================================================ 5. INFERNO ASCENT
@register("inferno_ascent", SIDE, "Inferno Ascent", "spring-pad climb up a shaft of rising lava",
          quips=("The floor is lava. Soon the ceiling is lava too.",
                 "Up, up and away... or down, down and toasty!"),
          goals=("reach_finish", "last_one_standing"), hazards=(), twists=())
class InfernoAscent(ClimbTower):
    """Vertical climb up a ~3.8k px shaft of zig-zag ledges. Balls cannot climb alone: SPRING PADS at the inner end of
    each ledge launch them up and across to the next ledge, ELEVATORS ride two levels, UPDRAFT columns blow them up.
    Rising lava eats the stragglers; in overtime the ledges crumble behind the leaders."""
    rules = {"first_blood_s": 6.5}
    CX, X0, X1 = 660.0, 210.0, 1110.0
    STEP = 190.0
    LEDGE_W = 350.0
    PAD_W = 90.0
    APEX = 250.0

    def __init__(self, sim):
        super().__init__(sim)
        self.ledges: list[dict] = []
        self.elevs: list[dict] = []
        self.drafts: list[dict] = []
        self.pad_cd: dict[str, float] = {}
        self.lava_y = 300.0
        self.top_y = 0.0
        self.crumble_next = 0.0

    def spawn_points(self, n: int, rng) -> list[tuple[float, float]]:
        cols = (n + 1) // 2
        step = min(56.0, 330.0 / max(1, cols - 1))
        return [(240 + (i % cols) * step + rng.uniform(-3, 3), -42 - (i // cols) * 70 + rng.uniform(-3, 3))
                for i in range(n)]

    # -- geometry
    def _ledge(self, i: int, y: float, side: str, kind: str) -> dict:
        if side == "floor":
            x0, x1, pad, dirn = self.X0, self.X1, (770.0, 910.0), -1.0
        elif side == "L":
            x0, x1, dirn = self.X0, self.X0 + self.LEDGE_W, 1.0
            pad = (x1 - self.PAD_W, x1)
        else:
            x0, x1, dirn = self.X1 - self.LEDGE_W, self.X1, -1.0
            pad = (x0, x0 + self.PAD_W)
        shape = self.ground((x0, y), (x1, y))
        d = {"i": i, "y": y, "x0": x0, "x1": x1, "side": side, "kind": kind, "pad": pad, "dir": dirn,
             "shape": shape, "gone": False, "crumble_t": None}
        if kind == "pad":
            self.sim.statics.append({"type": "ia_pad", "x0": pad[0], "x1": pad[1], "y": y, "i": i, "dir": dirn})
        self.ledges.append(d)
        return d

    def build(self):
        r, sim = self.sim.rng, self.sim
        n = self.p.setdefault("levels", r.randint(18, 20))
        kinds = ["pad"] * (n + 1)
        k = 2
        while k <= n - 3:
            roll = r.random()
            if roll < 0.24:
                kinds[k] = "elev"
                k += 3
            elif roll < 0.44:
                kinds[k] = "draft"
                k += 2
            else:
                k += 1
        self.top_y = -n * self.STEP
        top = self.top_y - 1200
        sim.static_segment((self.X0 - 14, top), (self.X0 - 14, 420), "wall", radius=14)
        sim.static_segment((self.X1 + 14, top), (self.X1 + 14, 420), "wall", radius=14)
        self._ledge(0, 0.0, "floor", "pad")
        for i in range(1, n):
            self._ledge(i, -i * self.STEP, "L" if i % 2 == 1 else "R", kinds[i])
        side_top = "L" if n % 2 == 1 else "R"
        tx0, tx1 = (self.X0, self.X0 + 420.0) if side_top == "L" else (self.X1 - 420.0, self.X1)
        self.ground((tx0, self.top_y), (tx1, self.top_y))
        self.top = (tx0, tx1)
        sim.statics.append({"type": "ia_crown", "x0": tx0, "x1": tx1, "y": self.top_y})
        for d in self.ledges:
            if d["kind"] == "elev":
                self._elevator(d)
            elif d["kind"] == "draft":
                self._draft(d)
        # start gate between the spawn pen and the floor pad
        self.gate = sim.static_segment((640, -160), (640, 0), "wall", radius=10)
        sim.statics[-1]["mat"] = "gate"
        sim.statics.append({"type": "drop_gate", "x": 640.0, "y": 0.0})
        sim.finish_x = 1e9
        sim.kill_y = 420.0
        sim.bounds = (self.X0 - 140, self.top_y - 700, self.X1 + 140, 420.0)
        self.center = (self.CX, -n * self.STEP / 2)
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._tick)

    def _elevator(self, d: dict) -> None:
        r = self.sim.rng
        y_lo, y_hi = d["y"], d["y"] - 2 * self.STEP
        p = kin_box(self.sim, (self.CX, y_lo + 11), 170, 22, "ia_elevator", material="ground", radius=3)
        p.shapes[0].update(y_lo=y_lo, y_hi=y_hi)
        self.elevs.append({"prop": p, "ledge": d, "y_lo": y_lo, "y_hi": y_hi, "ph": r.uniform(0, 2 * math.pi),
                           "w": 2 * math.pi / r.uniform(3.0, 3.6), "top": y_lo, "exit_dir": -d["dir"]})

    def _draft(self, d: dict) -> None:
        y0, y1 = d["y"] - self.STEP - 130.0, d["y"] + 60.0
        dr = {"ledge": d, "x0": 565.0, "x1": 755.0, "y0": y0, "y1": y1, "dir": d["dir"], "y_next": d["y"] - self.STEP}
        self.drafts.append(dr)
        self.sim.statics.append({"type": "ia_updraft", "x0": dr["x0"], "x1": dr["x1"], "y0": y0, "y1": y1,
                                 "dir": d["dir"], "i": d["i"]})

    # -- AI hooks
    def _ledge_of(self, c: "Contestant") -> dict | None:
        x, y = c.pos
        best = None
        for d in self.ledges:
            if d["gone"] or not (d["x0"] - 12 <= x <= d["x1"] + 12):
                continue
            dy = d["y"] - y
            if -8 <= dy <= c.radius + 120 and (best is None or d["y"] < best["y"]):
                best = d
        return best

    def _elev_of(self, c: "Contestant") -> dict | None:
        x, y = c.pos
        for e in self.elevs:
            if abs(x - self.CX) <= 92 and e["top"] - c.radius - 16 <= y <= e["top"] + 6:
                return e
        return None

    def drive_dir(self, c: "Contestant") -> float:
        e = self._elev_of(c)
        if e is not None:
            return e["exit_dir"]
        d = self._ledge_of(c)
        if d is None:
            return 1.0 if c.pos[0] < self.CX else -1.0
        if d["kind"] == "pad":
            tx = (d["pad"][0] + d["pad"][1]) / 2
        else:
            tx = d["x1"] + 40 if d["side"] == "L" else d["x0"] - 40
        dx = tx - c.pos[0]
        return d["dir"] if abs(dx) < 6 else math.copysign(1.0, dx)

    def brake(self, c: "Contestant") -> bool:
        e = self._elev_of(c)
        if e is not None:
            if e["top"] > e["y_hi"] + 22:
                _hold(self.sim, c)
                return True
            return False
        d = self._ledge_of(c)
        if d is not None and d["kind"] == "elev" and _patient(c):
            edge = d["x1"] if d["side"] == "L" else d["x0"]
            ev = next(v for v in self.elevs if v["ledge"] is d)
            if abs(c.pos[0] - edge) < 95 and ev["top"] < ev["y_lo"] - 18:
                _hold(self.sim, c)
                return True
        return False

    def jump_hint(self, c: "Contestant"):
        return False                                    # nobody climbs on their own: pads, lifts and drafts only

    def progress(self, c: "Contestant") -> float:
        return -c.pos[1]

    def at_finish(self, c: "Contestant") -> bool:
        x, y = c.pos
        return y < self.top_y - c.radius * 0.5 and self.top[0] - 10 <= x <= self.top[1] + 10

    # -- per substep: lifts + updrafts
    def _step(self, dt: float) -> None:
        sim = self.sim
        for e in self.elevs:
            if e["ledge"]["gone"]:
                continue
            e["ph"] += e["w"] * dt
            s = max(0.0, min(1.0, 0.5 - 0.62 * math.cos(e["ph"])))
            top = e["y_lo"] + (e["y_hi"] - e["y_lo"]) * s
            move_kin(e["prop"], self.CX, top + 11, dt)
            e["top"] = top
        if not self.drafts:
            return
        gy = float(sim.space.gravity.y)
        for c in sim.alive():
            x, y = c.pos
            for dr in self.drafts:
                if dr["ledge"]["gone"] or not (dr["x0"] <= x <= dr["x1"] and dr["y0"] <= y <= dr["y1"]):
                    continue
                m = float(c.body.mass)
                gm = c.hero.gravity_mult if c.hero else 1.0
                v = c.body.velocity
                fy = -m * (gy * gm + 1150.0) if v.y > -560 else -m * gy * gm * 0.6
                if y < dr["y_next"] - 20:
                    fx = dr["dir"] * m * 900.0 if v.x * dr["dir"] < 320 else 0.0
                else:
                    fx = (self.CX - x) * m * 6.0 - v.x * m * 2.0
                c.body.apply_force_at_world_point((fx, fy), c.body.position)
                break

    # -- per frame: pads, lava, crumble
    def _launch(self, c: "Contestant", dirn: float) -> None:
        g = abs(float(self.sim.space.gravity.y)) * (c.hero.gravity_mult if c.hero else 1.0)
        g = max(60.0, g)
        vy = math.sqrt(2.0 * g * self.APEX)
        t_fl = vy / g + math.sqrt(2.0 * (self.APEX - self.STEP) / g)
        target = self.X1 - self.LEDGE_W + 150.0 if dirn > 0 else self.X0 + self.LEDGE_W - 150.0
        vx_t = (target - c.pos[0]) / t_fl
        vx_t = dirn * min(560.0, max(180.0, vx_t * dirn))
        vy_t = -vy
        v = c.body.velocity
        m = float(c.body.mass)
        c.body.apply_impulse_at_world_point(((vx_t - v.x) * m, (vy_t - v.y) * m), c.body.position)
        c.body.angular_velocity = 0.0
        c.squash = 1.0

    def _tick(self, t: float) -> None:
        sim = self.sim
        alive = sim.alive()
        fired = []
        for d in self.ledges:
            if d["kind"] != "pad" or d["gone"]:
                continue
            p0, p1 = d["pad"]
            for c in alive:
                x, y = c.pos
                if p0 - 4 <= x <= p1 + 4 and d["y"] - c.radius - 18 <= y <= d["y"] + 4 \
                        and t >= self.pad_cd.get(c.key, -9.0) and c.body.velocity.y > -150:
                    self._launch(c, d["dir"])
                    self.pad_cd[c.key] = t + 0.45
                    d["fire_t"] = t
            if d.get("fire_t") is not None and t - d["fire_t"] < 0.35:
                fired.append(d["i"])
        # rising lava (accelerates with speed_mult, catches up when it falls far behind the pack)
        if t > 0.0:
            low = max((c.pos[1] for c in alive), default=self.lava_y)
            rate = 62.0 * sim.speed_mult * (1.9 if self.lava_y - low > 620 else 1.0)
            if sim.overtime:
                rate *= 1.25
            self.lava_y -= rate / 30.0
        for c in list(alive):
            if c.pos[1] - c.radius * 0.2 > self.lava_y:
                sim.eliminate(c, "lava")
        # overtime: ledges crumble behind the leaders
        crumbling = []
        if sim.overtime:
            heroes = [c for c in sim.alive() if c.is_hero] or sim.alive()
            if heroes and t >= self.crumble_next:
                lead = min(c.pos[1] for c in heroes)
                lvl = int(-lead / self.STEP)
                cand = [d for d in self.ledges if not d["gone"] and d["crumble_t"] is None and d["i"] <= lvl - 2]
                if cand:
                    cand[0]["crumble_t"] = t
                    self.crumble_next = t + 0.55
            for d in self.ledges:
                if d["crumble_t"] is not None and not d["gone"]:
                    if t - d["crumble_t"] >= 0.45:
                        d["gone"] = True
                        sim.remove_static(d["shape"])
                        for e in self.elevs:
                            if e["ledge"] is d:
                                park(e["prop"])
                        sim.event("arena_hit", [], (0.5 * (d["x0"] + d["x1"]), d["y"]), name="ledge_crumble")
                    else:
                        crumbling.append(d["i"])
        sim.zones["lava_y"] = round(self.lava_y, 1)
        sim.zones["ia_fired"] = tuple(fired)
        sim.zones["ia_crumble"] = tuple(crumbling)
        sim.zones["ia_gone"] = tuple(d["i"] for d in self.ledges if d["gone"])
