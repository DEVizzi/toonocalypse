"""v6 group side_a: six SIDE_VIEW scrolling course arenas (chasing fire wall stays on all of them).

  glass_bridge   Glass Bridge Gamble   identical glass panels, ~30% fake -> shatter on first touch
  red_light      Red Light Gauntlet    a giant stone eye: GREEN go / YELLOW brake / RED = moving balls get ZAPPED
  big_bubble     Big Bubble Bounce     launcher pads + giant slippery bouncy inflatable domes over the water
  spinning_logs  Spinning Log Pond     river of rotating logs (forward / backward rollers) + small islands
  lily_pads      Lily Pad Pond         pads sink ~0.9 s after load, resurface later; frogs lash their tongues
  raft_rapids    Raft Rapids           ping-pong rafts sink with their load (Juggernaut = instant submarine)

All randomness comes from `self.sim.rng` inside build(); per-frame state the renderer needs goes in sim.zones["sa_*"].
Renderers live in src/rendering/arena_art/side_a.py.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from src.games.arena_kit import SIDE, V6Course, kin_box, kin_circle, register, riders, zap

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Prop

SAFE_SIDE_TWISTS = ("heavy_gravity", "speed_boost_zones", "giant_ball")


def drive_kin(prop: "Prop", x: float, y: float, dt: float, angle: float | None = None) -> None:
    """Steer a kinematic prop to (x, y) by the end of this substep purely through its velocity (pymunk integrates the
    position), so riders are carried smoothly and nothing double-moves."""
    b = prop.body
    if dt <= 0:
        return
    b.velocity = ((x - b.position.x) / dt, (y - b.position.y) / dt)
    if angle is not None:
        b.angular_velocity = (angle - b.angle) / dt


class _SideA(V6Course):
    """Shared helpers: water stretches with splash eliminations + short-lived effect lists for the renderer."""

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.water: list[tuple[float, float, float]] = []      # (x0, x1, surface_y)
        self.splashes: list[tuple[float, float, float]] = []   # (x, y, t)
        self.st = 0.0                                          # substep clock (step hooks)

    # -- water
    def add_water(self, x0: float, x1: float, y: float) -> None:
        self.water.append((x0, x1, y))
        self.pits.append((x0, x1))
        self.sim.statics.append({"type": "sa_water", "x0": x0, "x1": x1, "y": y})

    def water_y(self, x: float) -> float | None:
        for x0, x1, y in self.water:
            if x0 <= x <= x1:
                return y
        return None

    def _water_tick(self, t: float) -> None:
        for c in list(self.sim.alive()):
            x, y = c.pos
            wy = self.water_y(x)
            if wy is not None and y > wy + c.radius * 0.35:
                self.splashes.append((x, wy, t))
                self.sim.eliminate(c, "splash")
        self.splashes = [s for s in self.splashes if t - s[2] < 1.2]
        self.sim.zones["sa_splash"] = [(round(x, 1), round(y, 1), round(t - t0, 3)) for x, y, t0 in self.splashes]

    def _clock(self, dt: float) -> None:
        self.st += dt

    def soft_start(self, gap: tuple[float, float] = (96.0, 116.0), runout: float = 0.0) -> None:
        """Course.start() with a narrower first-blood gap (still within ~300 px of the drop zone) so the opening
        claims 1-2 dummies instead of a third of the field. `runout` adds a flat bleed-off stretch after it."""
        r = self.sim.rng
        self.seg(360, 12)
        self.add_gate(self.x - 26, top=self.LEDGE_Y - 155)
        self.seg(380, 320)
        self.seg(220, 210)
        self.seg(r.uniform(90, 145), 14)
        self.gap(r.uniform(*gap), 24)
        if runout > 0:
            self.seg(runout, 6)


# ================================================================================================ 1. glass bridge
@register(
    "glass_bridge", SIDE, "Glass Bridge Gamble", "a glass bridge where one in three panels is fake",
    ("One of these panels is lying to you. Good luck!", "Step lightly, champs. Glass is NOT your friend."),
    ("reach_finish", "last_one_standing", "survive_timer"),
    hazards=("wind_gusts",), twists=SAFE_SIDE_TWISTS,
)
class GlassBridge(_SideA):
    chase_scale = 0.9
    rules = {"first_blood_s": 4.2}
    PANEL_R = 7.0

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.panels: list[dict] = []
        self.shards: list[tuple[float, float, float, float, float]] = []

    def _panel(self, w: float, dy: float, fake: bool) -> None:
        sim = self.sim
        a, b = (self.x, self.y), (self.x + w, self.y + dy)
        s = sim.static_segment(a, b, "plank", radius=self.PANEL_R)
        # replace the generic track description: glass panels are drawn by arena_art (real and fake look identical)
        sim.statics[-1] = {"type": "sa_glass", "a": a, "b": b, "r": self.PANEL_R, "id": id(s)}
        self.panels.append({"shape": s, "x0": a[0], "y0": a[1], "x1": b[0], "y1": b[1], "fake": fake, "hit": None})
        self.span(a[0], a[1], b[0], b[1])
        self.x, self.y = b
        self.low, self.high = max(self.low, self.y), min(self.high, self.y)

    def build(self):
        r = self.sim.rng
        self.soft_start()
        self.seg(r.uniform(200, 260), 30)
        sections = self.p.setdefault("glass_sections", 4)
        per = self.p.setdefault("glass_per_section", r.randint(6, 8))
        idx, prev_fake = 0, False
        for s_i in range(sections):
            for k in range(per):
                fake = idx >= 3 and not prev_fake and k > 0 and r.random() < 0.32
                self._panel(r.uniform(110, 125), r.uniform(20, 27), fake)
                prev_fake = fake
                idx += 1
                gap = r.uniform(6, 8)
                self.span(self.x, self.y, self.x + gap, self.y)
                self.x += gap
            if s_i < sections - 1:
                # castle pylon rest platform between bridge spans (bumpers / pegs bunch the pack up again)
                self.seg(r.uniform(200, 260), r.uniform(30, 50))
                if r.random() < 0.6:
                    self.sim.static_circle((self.x - 110, self.y - r.uniform(70, 100)), 16, "bumper")
                else:
                    self.pegs(2, (70, 105))
                self.wave(r.uniform(300, 420), 30, 70)
                prev_fake = False
        self.seg(160, 20)
        self.finish(700)
        self.sim.kill_y = self.low + 320
        self.sim.hooks_frame.append(self._tick)

    def _on_panel(self, c: "Contestant", p: dict) -> bool:
        x, y = c.pos
        if not (p["x0"] - 3 <= x <= p["x1"] + 3):
            return False
        k = (x - p["x0"]) / max(1.0, p["x1"] - p["x0"])
        sy = p["y0"] + (p["y1"] - p["y0"]) * min(1.0, max(0.0, k)) - self.PANEL_R
        return -14.0 <= sy - (y + c.radius) <= 16.0

    def _tick(self, t: float) -> None:
        sim = self.sim
        ot = bool(getattr(sim, "overtime", False))
        alive = sim.alive()
        min_x = min((c.pos[0] for c in alive), default=-1e9) if ot else -1e9
        for p in self.panels:
            if p["shape"] is None:
                continue
            if p["hit"] is None:
                if ot and not p["fake"] and p["x1"] <= min_x + 55:
                    p["hit"] = t
                elif (p["fake"] or ot) and any(self._on_panel(c, p) for c in alive):
                    p["hit"] = t
            if p["hit"] is not None and t - p["hit"] >= (0.06 if p["fake"] else 0.24):
                sim.remove_static(p["shape"])
                p["shape"] = None
                self.pits.append((p["x0"], p["x1"]))
                self.shards.append((p["x0"], p["y0"], p["x1"], p["y1"], t))
                if p["fake"]:
                    vic = [c.key for c in alive if p["x0"] - 10 <= c.pos[0] <= p["x1"] + 10
                           and abs(c.pos[1] - p["y0"]) < 90]
                    sim.event("arena_hit", vic[:3], ((p["x0"] + p["x1"]) / 2, p["y0"]), name="glass_shatter")
        self.shards = [s for s in self.shards if t - s[4] < 1.6]
        sim.zones["sa_shards"] = [(s[0], s[1], s[2], s[3], round(t - s[4], 3)) for s in self.shards]


# ================================================================================================ 2. red light
GREEN, YELLOW, RED = 0, 1, 2


@register(
    "red_light", SIDE, "Red Light Gauntlet", "a giant stone eye that zaps anything moving on red",
    ("Red light means STOP. Dash, that includes you!", "The eye sees everything. Especially you, Dash."),
    ("reach_finish", "survive_timer", "hot_potato_bomb"),
    hazards=(), twists=("heavy_gravity", "giant_ball"),
)
class RedLight(_SideA):
    chase_scale = 0.95
    rules = {"first_blood_s": 4.2}
    YELLOW_S, GRACE_S, ZAP_V = 0.5, 0.25, 150.0

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.zap_cd: dict[str, float] = {}
        self.zaps: list[tuple[float, float, float]] = []
        self.sched: list[tuple[float, float, float]] = []      # (green_start, yellow_start, red_start, red_end)

    def build(self):
        r = self.sim.rng
        self.start()
        cyc = self.p.setdefault("light_cycle", [[round(r.uniform(2.0, 3.5), 2), round(r.uniform(1.2, 2.0), 2)]
                                                for _ in range(24)])
        t0 = 0.0
        first = True
        for g, red in cyc:
            g = g + (0.6 if first else 0.0)                 # a slightly longer opening green after the gate
            first = False
            self.sched.append((t0, t0 + g, t0 + g + self.YELLOW_S, t0 + g + self.YELLOW_S + red))
            t0 += g + self.YELLOW_S + red
        length = self.p.setdefault("rl_length", round(r.uniform(5400, 5900)))
        x_goal = self.x + length
        n_gaps = 0
        while self.x < x_goal:
            w = r.uniform(300, 460)
            self.seg(w, w * r.uniform(0.035, 0.07))
            roll = r.random()
            if roll < 0.42:
                self.gap(r.uniform(95, 130) * self.ramp(min(n_gaps, 7), 8), r.uniform(10, 24))
                n_gaps += 1
            elif roll < 0.62:
                self.pegs(r.randint(2, 3), (70, 110))
        self.seg(220, 14)
        self.finish(700)
        self.sim.hooks_frame.append(self._tick)

    def light(self, t: float) -> tuple[int, float]:
        """(state, seconds into the state)."""
        for gs, ys, rs, re in self.sched:
            if t < ys:
                return GREEN, t - gs
            if t < rs:
                return YELLOW, t - ys
            if t < re:
                return RED, t - rs
        return GREEN, 0.0

    def brake(self, c: "Contestant") -> bool:
        if self.sim.t < 0 or self.sim.winner:
            return False
        return self.light(self.sim.t)[0] != GREEN

    def _tick(self, t: float) -> None:
        sim = self.sim
        st, age = self.light(t) if t >= 0 else (GREEN, 0.0)
        if st == RED and age >= self.GRACE_S and not sim.winner:
            for c in sim.alive():
                if c.finished or t < self.zap_cd.get(c.key, -9.0):
                    continue
                vx = float(c.body.velocity.x)
                if abs(vx) > self.ZAP_V:
                    d = 1.0 if vx > 0 else -1.0
                    zap(sim, c, -d * 300.0 - vx * 0.35, -330.0, stun=0.7, name="red_light_zap", speed=round(abs(vx)))
                    self.zap_cd[c.key] = t + 1.1
                    self.zaps.append((c.pos[0], c.pos[1], t))
        self.zaps = [z for z in self.zaps if t - z[2] < 0.6]
        sim.zones["sa_light"] = st
        sim.zones["sa_light_age"] = round(age, 3)
        sim.zones["sa_zaps"] = [(round(x, 1), round(y, 1), round(t - t0, 3)) for x, y, t0 in self.zaps]


# ================================================================================================ 3. big bubble
@register(
    "big_bubble", SIDE, "Big Bubble Bounce", "giant slippery inflatable bubbles over the water",
    ("Land on top or slide into the drink. Physics is cruel.", "Big bubbles, big bounces, bigger splashes!"),
    ("reach_finish", "last_one_standing"),
    hazards=("wind_gusts",), twists=("heavy_gravity", "giant_ball", "speed_boost_zones"),
)
class BigBubble(_SideA):
    chase_scale = 0.55
    lag_scale = 1.7      # a gentler wall: stragglers get more room before LEFT BEHIND
    rules = {"first_blood_s": 5.0}

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.domes: list[dict] = []

    def build(self):
        r = self.sim.rng
        self.start()
        self.seg(r.uniform(160, 220), 24)
        groups = self.p.setdefault("bubble_groups", r.randint(7, 8))
        for g_i in range(groups):
            self.seg(r.uniform(130, 200), r.uniform(14, 30))
            self.seg(r.uniform(95, 120), 8)                                # run-up
            n = 2 if g_i < 2 else r.randint(2, 3)
            deck = self.y
            water = deck + 26 + 12 * (n - 1) + r.uniform(62, 74)
            x_start = self.x
            cx = None
            prev_hc = 0.0
            for i in range(n):
                R = r.uniform(115, 150)
                top = deck + 26 + 12 * i
                cap = water - top
                hc = math.sqrt(max(1.0, R * R - (R - cap) ** 2))
                if cx is None:
                    cx = x_start + r.uniform(15, 30) + hc
                else:
                    cx += prev_hc + r.uniform(5, 20) + hc
                cy = top + R
                pr = kin_circle(self.sim, (cx, cy), R, "sa_dome", material="bouncy")
                for sh in pr.body.shapes:
                    sh.friction, sh.elasticity = 0.75, 0.42
                self.domes.append({"prop": pr, "cx": cx, "cy": cy, "R": R, "ph": r.uniform(0, 6.28),
                                   "w": r.uniform(1.2, 1.8), "amp": r.uniform(5, 8), "rock": r.uniform(0.08, 0.18),
                                   "load": 0})
                prev_hc = hc
            end_x = cx + prev_hc + r.uniform(10, 25)
            land_y = deck + 26 + 12 * (n - 1) + r.uniform(30, 45)
            self.add_water(x_start, end_x, water)
            self.span(x_start, water, end_x, water)
            self.x, self.y = end_x, land_y
            self.low = max(self.low, water)
            self.seg(r.uniform(180, 260), r.uniform(24, 40))
            if r.random() < 0.4:
                self.pegs(2, (70, 100))
        self.seg(160, 20)
        self.finish(700)
        self.sim.kill_y = self.low + 320
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._frame)

    def _step(self, dt: float) -> None:
        self.st += dt
        t = self.st
        for d in self.domes:
            y = d["cy"] + d["amp"] * math.sin(t * d["w"] + d["ph"])
            drive_kin(d["prop"], d["cx"], y, dt)
            d["prop"].body.angular_velocity = d["rock"] * math.sin(t * d["w"] * 0.7 + d["ph"])

    def _frame(self, t: float) -> None:
        self._water_tick(t)
        alive = self.sim.alive()
        out = []
        for d in self.domes:
            bx, by = d["prop"].body.position
            n = sum(1 for c in alive if math.hypot(c.pos[0] - bx, c.pos[1] - by) < d["R"] + c.radius + 6)
            d["load"] = max(n, d["load"] * 0.8)
            out.append(round(min(1.0, d["load"] / 3.0), 2))
        self.sim.zones["sa_domes"] = out


# ================================================================================================ 4. spinning logs
@register(
    "spinning_logs", SIDE, "Spinning Log Pond", "a river of spinning logs that roll you forward or back",
    ("Logs spin forward, logs spin back. Logs do NOT care.", "Lumberjack rules: keep rolling or go swimming!"),
    ("reach_finish", "last_one_standing"),
    hazards=(), twists=("heavy_gravity", "giant_ball"),
)
class SpinningLogs(_SideA):
    chase_scale = 0.9
    rules = {"first_blood_s": 4.2}

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.logs: list[dict] = []

    def build(self):
        r = self.sim.rng
        self.start()
        self.seg(r.uniform(160, 220), 26)
        rivers = self.p.setdefault("log_rivers", r.randint(3, 4))
        fwd = True
        for rv in range(rivers):
            deck = self.y
            water = deck + 58
            x_start = self.x
            groups = r.randint(2, 3)
            x = x_start
            for g in range(groups):
                n = r.randint(2, 4)
                spin_kind = "fwd" if fwd else ("back" if r.random() < 0.6 else "mix")
                fwd = not fwd
                x += r.uniform(55, 85) if g == 0 else r.uniform(60, 95)
                for i in range(n):
                    R = r.uniform(38, 55)
                    cx = x + R
                    cy = deck + R
                    if spin_kind == "fwd":
                        v = r.uniform(140, 220)
                    elif spin_kind == "back":
                        v = -r.uniform(70, 130)
                    else:
                        v = r.uniform(120, 180) if i % 2 == 0 else -r.uniform(60, 110)
                    pr = kin_circle(self.sim, (cx, cy), R, "sa_log", material="ground")
                    for sh in pr.body.shapes:
                        sh.friction, sh.elasticity = 0.95, 0.05
                    w = v / R
                    pr.body.angular_velocity = w
                    self.logs.append({"prop": pr, "cx": cx, "cy": cy, "R": R, "w": w,
                                      "ph": r.uniform(0, 6.28), "bob": r.uniform(2.5, 4.5)})
                    x = cx + R + (r.uniform(14, 26) if i < n - 1 else 0.0)
                if g < groups - 1 and r.random() < 0.45:
                    # a short static island to regroup on
                    x += r.uniform(60, 85)
                    iw = r.uniform(120, 170)
                    self.sim.static_segment((x, deck + 2), (x + iw, deck + 6), "ground")
                    self.sim.statics[-1]["type"] = "sa_island"
                    x += iw
            x += r.uniform(60, 85)
            self.add_water(x_start, x, water)
            self.span(x_start, water, x, water)
            self.low = max(self.low, water)
            self.x, self.y = x, deck + 10
            self.seg(r.uniform(220, 320), r.uniform(26, 44))
            if rv < rivers - 1:
                self.seg(r.uniform(100, 160), r.uniform(10, 20))
        self.seg(160, 20)
        self.finish(700)
        self.sim.kill_y = self.low + 320
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._water_tick)

    def _step(self, dt: float) -> None:
        self.st += dt
        t = self.st
        for lg in self.logs:
            y = lg["cy"] + lg["bob"] * math.sin(t * 2.2 + lg["ph"])
            b = lg["prop"].body
            b.velocity = (0.0, (y - b.position.y) / dt)
            b.angular_velocity = lg["w"] * self.sim.hazard_mult ** 0.5


# ================================================================================================ 5. lily pads
@register(
    "lily_pads", SIDE, "Lily Pad Pond", "sinking lily pads and a hungry tongue-lashing frog",
    ("Do not linger on the lily pads. The frog is watching.", "Ribbit means GO. Ribbit means GO NOW!"),
    ("reach_finish", "last_one_standing"),
    hazards=(), twists=("heavy_gravity", "giant_ball", "speed_boost_zones"),
)
class LilyPads(_SideA):
    chase_scale = 0.9
    rules = {"first_blood_s": 4.2}
    SINK_DEPTH, SINK_S, UNDER_S, RISE_S = 84.0, 0.8, 2.5, 0.6

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.pads: list[dict] = []
        self.frogs: list[dict] = []

    def build(self):
        r = self.sim.rng
        self.start()
        self.seg(r.uniform(160, 220), 26)
        ponds = self.p.setdefault("lily_ponds", r.randint(3, 4))
        for pd in range(ponds):
            deck = self.y
            water = deck + 10
            x_start = self.x
            x = x_start
            n = r.randint(5, 7)
            frog_at = set(r.sample(range(2, n), k=1 if n < 7 else 2))
            for i in range(n):
                x += r.uniform(55, 95)
                w = r.uniform(120, 170) if i not in frog_at else r.uniform(170, 200)
                top = deck + r.uniform(-4, 4)
                pr = kin_box(self.sim, (x + w / 2, top + 10), w, 20, "sa_pad", material="ground", radius=3)
                pad = {"prop": pr, "x0": x, "x1": x + w, "top": top, "cx": x + w / 2, "state": 0, "t0": 0.0,
                       "delay": r.uniform(0.8, 1.0), "off": 0.0, "frog": i in frog_at, "notch": r.uniform(-0.8, 0.8)}
                self.pads.append(pad)
                if i in frog_at:
                    self.frogs.append({"pad": pad, "x": x + w * 0.62, "period": r.uniform(1.5, 2.2),
                                       "ph": r.uniform(0, 1.0), "dir": -1.0, "fired": -1, "tx": 0.0, "ty": 0.0})
                x += w
            x += r.uniform(60, 90)
            self.add_water(x_start, x, water)
            self.span(x_start, water, x, water)
            self.low = max(self.low, water)
            self.x, self.y = x, deck + 4
            self.seg(r.uniform(220, 320), r.uniform(26, 44))
            if pd < ponds - 1:
                self.seg(r.uniform(90, 140), r.uniform(10, 20))
        self.seg(160, 20)
        self.finish(700)
        self.sim.kill_y = self.low + 320
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._frame)

    def _step(self, dt: float) -> None:
        self.st += dt
        for p in self.pads:
            drive_kin(p["prop"], p["cx"], p["top"] + 10 + p["off"], dt)

    def _frame(self, t: float) -> None:
        sim = self.sim
        alive = sim.alive()
        hm = max(1.0, sim.hazard_mult) ** 0.5
        for p in self.pads:
            age = t - p["t0"]
            if p["state"] == 0:
                p["off"] = 0.0
                if not p["frog"] and t > 0 and riders(sim, p["x0"], p["x1"], p["top"], tol=16):
                    p["state"], p["t0"] = 1, t
            elif p["state"] == 1:                          # loaded: trembling, about to go
                p["off"] = 2.0 * math.sin(t * 40.0)
                if age >= p["delay"] / hm:
                    p["state"], p["t0"] = 2, t
            elif p["state"] == 2:                          # sinking
                p["off"] = self.SINK_DEPTH * min(1.0, age / self.SINK_S)
                if age >= self.SINK_S + self.UNDER_S:
                    p["state"], p["t0"] = 3, t
            elif p["state"] == 3:                          # resurfacing
                p["off"] = self.SINK_DEPTH * max(0.0, 1.0 - age / self.RISE_S)
                if age >= self.RISE_S:
                    p["state"], p["t0"], p["off"] = 0, t, 0.0
        frogs_z = []
        for f in self.frogs:
            per = f["period"] / hm
            cyc = (t / per + f["ph"]) if t > 0.8 else 0.0
            k = int(cyc)
            u = cyc - k
            fx, fy = f["x"], f["pad"]["top"] - 26
            ext = 0.0
            if t > 0.8 and u < 0.3:
                ext = math.sin(u / 0.3 * math.pi)
                if f["fired"] != k:
                    f["fired"] = k
                    near = [c for c in alive if abs(c.pos[0] - fx) < 210 and abs(c.pos[1] - fy) < 110]
                    if near:
                        tgt = min(near, key=lambda c: abs(c.pos[0] - fx))
                        f["dir"] = 1.0 if tgt.pos[0] > fx else -1.0
                        f["tx"], f["ty"] = tgt.pos
                        for c in near:
                            if (c.pos[0] - fx) * f["dir"] >= -20:
                                zap(sim, c, f["dir"] * 330.0, -250.0, stun=0.55, name="frog_tongue")
                    else:
                        f["tx"], f["ty"] = fx + f["dir"] * 170, fy
            frogs_z.append((round(fx, 1), round(fy, 1), round(ext, 3), f["dir"], round(f["tx"], 1), round(f["ty"], 1)))
        sim.zones["sa_frogs"] = frogs_z
        sim.zones["sa_pads"] = [p["state"] for p in self.pads]
        self._water_tick(t)


# ================================================================================================ 6. raft rapids
@register(
    "raft_rapids", SIDE, "Raft Rapids", "drifting rafts that sink under heavy riders",
    ("Rafts hold six units of ball. Juggernaut is eight and a half.", "Wait for the raft. WAIT for the raft!"),
    ("reach_finish", "last_one_standing"),
    hazards=(), twists=("heavy_gravity", "giant_ball"),
)
class RaftRapids(_SideA):
    chase_scale = 0.55
    lag_scale = 1.7      # a gentler wall: stragglers get more room before LEFT BEHIND
    rules = {"first_blood_s": 4.2}
    CAPACITY, K_SINK, SUNK = 6.0, 4.0, 95.0

    def __init__(self, sim) -> None:
        super().__init__(sim)
        self.rafts: list[dict] = []
        self.ledges: list[tuple[float, float, dict]] = []      # (x_end, y, raft that docks there)
        self.falls: list[dict] = []

    def _lane(self, r, water_drop: float = 0.0) -> None:
        deck = self.y
        water = deck + 26
        x0 = self.x
        rw = r.uniform(150, 200)
        travel = r.uniform(120, 180)
        xa = x0 + 10 + rw / 2                    # docked left: 10 px from the ledge edge
        xb = xa + travel                         # docked right
        x1 = xb + rw / 2 + 10
        pr = kin_box(self.sim, (xa, deck + 11), rw, 22, "sa_raft", material="ground", radius=4)
        for sh in pr.body.shapes:
            sh.friction, sh.elasticity = 1.3, 0.0
        speed = r.uniform(210, 250)
        raft = {"prop": pr, "xa": xa, "xb": xb, "w": rw, "deck": deck, "y": deck, "dip": 0.0, "load": 0.0,
                "per": 4.2 * travel / speed + 0.6, "ph": r.uniform(0, 1.0), "sunk": False, "x": xa}
        self.rafts.append(raft)
        self.ledges.append((x0, deck, raft))
        self.add_water(x0, x1, water)
        self.span(x0, water, x1, water)
        self.low = max(self.low, water)
        self.x, self.y = x1, deck + r.uniform(-6, 6)

    def build(self):
        r = self.sim.rng
        self.soft_start()
        self.seg(r.uniform(520, 580), 30)
        lanes = self.p.setdefault("raft_lanes", r.randint(4, 5))
        for i in range(lanes):
            self._lane(r)
            if i == lanes - 2:
                # the waterfall drop: a short ledge then a steep cascade into the lower river
                self.seg(r.uniform(140, 180), 10)
                fx0, fy0 = self.x, self.y
                self.seg(160, r.uniform(150, 190))
                self.falls.append({"x0": fx0, "y0": fy0, "x1": self.x, "y1": self.y})
                self.sim.statics.append({"type": "sa_waterfall", "x0": fx0, "y0": fy0, "x1": self.x, "y1": self.y})
                self.seg(r.uniform(260, 320), 12)
            else:
                self.seg(r.uniform(300, 380), r.uniform(10, 26))
        self.seg(160, 20)
        self.finish(700)
        self.sim.kill_y = self.low + 320
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._frame)

    def _raft_x(self, rf: dict, t: float) -> float:
        u = (t / rf["per"] + rf["ph"]) % 1.0
        # ease with a dwell at both docks: 0..0.22 dock A, 0.22..0.5 travel, 0.5..0.72 dock B, 0.72..1 back
        if u < 0.22:
            k = 0.0
        elif u < 0.5:
            k = 0.5 - 0.5 * math.cos((u - 0.22) / 0.28 * math.pi)
        elif u < 0.72:
            k = 1.0
        else:
            k = 0.5 + 0.5 * math.cos((u - 0.72) / 0.28 * math.pi)
        return rf["xa"] + (rf["xb"] - rf["xa"]) * k

    def _step(self, dt: float) -> None:
        self.st += dt
        t = self.st
        for rf in self.rafts:
            x = self._raft_x(rf, t)
            target = self.SUNK if rf["sunk"] else min(self.SUNK, self.K_SINK * rf["load"])
            rate = 110.0 if target > rf["dip"] else 70.0
            rf["dip"] += max(-rate * dt, min(rate * dt, target - rf["dip"]))
            rf["x"] = x
            rf["y"] = rf["deck"] + rf["dip"]
            drive_kin(rf["prop"], x, rf["y"] + 11, dt, angle=0.03 * math.sin(t * 2.0 + rf["ph"] * 6.0) * (1 + rf["dip"] / 30))
            # the AI brake pulls riders toward zero WORLD velocity; add the raft's own velocity back so a waiting rider
            # is held relative to the deck (net brake force = -(v - v_raft) * m * k)
            vx = float(rf["prop"].body.velocity.x)
            if abs(vx) > 1.0:
                for c in rf.get("riders", ()):
                    if c.alive and c.stun <= 0 and self.brake(c):
                        m = float(c.body.mass)
                        c.body.apply_force_at_world_point((vx * m * 7.0 * min(1.0, c.traction), 0.0), c.body.position)

    def _on_raft(self, c: "Contestant") -> dict | None:
        x, y = c.pos
        for rf in self.rafts:
            if abs(x - rf["x"]) <= rf["w"] / 2 + 4 and rf["y"] - c.radius - 18 <= y <= rf["y"] + 8:
                return rf
        return None

    def _frame(self, t: float) -> None:
        alive = self.sim.alive()
        for rf in self.rafts:
            rs = [c for c in alive if abs(c.pos[0] - rf["x"]) <= rf["w"] / 2 + 4
                  and rf["y"] - c.radius - 18 <= c.pos[1] <= rf["y"] + 8]
            rf["load"] = sum(float(c.body.mass) for c in rs)
            rf["riders"] = rs
            if rf["load"] > self.CAPACITY and not rf["sunk"]:
                rf["sunk"] = True
                self.sim.event("arena_hit", [c.key for c in rs][:4], (rf["x"], rf["y"]), name="raft_sunk",
                               load=round(rf["load"], 1))
            elif rf["sunk"] and not rs and rf["dip"] >= self.SUNK - 1:
                rf["sunk"] = False
        self._water_tick(t)
        self.sim.zones["sa_rafts"] = [(round(rf["dip"], 1), int(rf["sunk"]), round(rf["load"], 1)) for rf in self.rafts]

    # ---- AI: wait for the raft, ride it, step off at the far dock
    def _impatient(self, c: "Contestant") -> bool:
        return c.extra is not None and (sum(map(ord, c.key)) % 3 == 0)

    def brake(self, c: "Contestant") -> bool:
        if self.sim.t < 0 or c.finished or self._impatient(c):
            return False
        rf = self._on_raft(c)
        if rf is not None:
            return rf["x"] < rf["xb"] - 18 or rf["sunk"]
        x = c.pos[0]
        for x_end, _, raft in self.ledges:
            if x_end - 300 <= x <= x_end + 2:
                if raft["x"] > raft["xa"] + 14 or raft["sunk"]:
                    return True
                # polite boarding: wait for the next trip if I would overload it (an empty raft takes anyone)
                return raft["load"] > 0 and raft["load"] + float(c.body.mass) > self.CAPACITY
        return False

    def jump_hint(self, c: "Contestant"):
        if self._impatient(c):
            return None
        if self._on_raft(c) is not None:
            return False
        x = c.pos[0]
        for x_end, _, _ in self.ledges:
            if x_end - 110 <= x <= x_end + 2:
                return False
        return None
