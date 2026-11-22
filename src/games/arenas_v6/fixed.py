"""v6 FIXED single-screen arenas (locked 9:16 camera, SIDE gravity, no chasing wall):

  needle_drop     Needle Drop     tiers of deflectors -> needle chamber with sliding safe pads that retract round by round
  plinko_cashout  Plinko Cashout  game-show peg board: gold bins (gated) win, spring bins relaunch, spike bins eliminate
  pinball_pit     Pinball Pit     neon pinball table: rhythm flippers, pop bumpers, spinners, drain, TILT!, jackpot lane
  wall_rush       Wall Rush       three one-way lanes; giant walls with one gap sweep in from the right

All randomness comes from `self.sim.rng` and is drawn inside build() (or deterministic per-frame decisions in hooks).
Per-frame render state lives in `self.sim.zones` under arena-prefixed keys (nd_, pc_, pp_, wr_); every list placed in
zones is a NEW object each frame (zones are shallow-copied per recorded frame).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pymunk

from src.games.arena_kit import SIDE, FixedScreen, kin_body, move_kin, park, register
from src.physics.engine import CT_BODY

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Prop

CT_LANE = 41          # Wall Rush one-way lane platforms (own collision type -> pre_solve pass-through)


class _Screen(FixedScreen):
    """Shared helpers for the four fixed screens."""

    def wseg(self, a, b, kind: str, material: str = "wall", radius: float = 10.0, **extra) -> pymunk.Segment:
        """Static segment drawn by our own STATIC renderer `kind` (never the generic castle track / grey bar)."""
        s = self.sim.static_segment(a, b, material, radius=radius)
        d = self.sim.statics[-1]
        d["type"] = kind
        d.update(extra)
        return s

    def wcirc(self, c, r: float, kind: str, material: str = "bumper", **extra) -> pymunk.Circle:
        s = self.sim.static_circle(c, r, material)
        d = self.sim.statics[-1]
        d["type"] = kind
        d.update(extra)
        return s

    @staticmethod
    def hero_bias(c: "Contestant") -> float:
        return 0.0 if c.is_hero else -5000.0      # crash dummies never take a tiebreak win

    @staticmethod
    def grid(n: int, rng, x0: float, x1: float, y0: float, dy: float = 76.0, step: float = 80.0) -> list:
        cols = max(1, int((x1 - x0) // step) + 1)
        sp = (x1 - x0) / max(1, cols - 1)
        pts = []
        for i in range(n):
            r_, k = divmod(i, cols)
            off = (sp / 2) if r_ % 2 else 0.0
            x = min(x1, x0 + k * sp + off) + rng.uniform(-6, 6)
            pts.append((x, y0 - r_ * dy + rng.uniform(-5, 5)))
        return pts


# ================================================================================================ 1. NEEDLE DROP
@register(
    "needle_drop", SIDE, "Needle Drop", "needle pit survival with vanishing safe pads",
    quips=("Floor is needles. Pads are lies. Good luck!", "Four pads, fourteen balls. Do the math, champs."),
    goals=("last_one_standing", "survive_timer", "hot_potato_bomb"),
    hazards=(), twists=("low_gravity", "heavy_gravity", "slippery_floor"),
)
class NeedleDrop(_Screen):
    """~5-tier screen: deflector tiers funnel the drop into a needle chamber (floor + lower side walls = needles).
    3-4 green safe pads slide left/right above the needles; each round one pad flashes red for 1 s and retracts."""
    WALL_L, WALL_R = 26.0, 1054.0
    CHAMBER_TOP = 1090.0
    NEEDLE_Y = 1470.0
    PAD_H = 26.0
    NET_Y = 1446.0
    LIP_H = 16.0
    GRIP = 2.6

    def build(self):
        r = self.sim.rng
        sim = self.sim
        self.setup_screen()
        L, R = self.WALL_L, self.WALL_R
        # upper plain walls, lower needle walls + needle floor
        self.wseg((L, -400), (L, self.CHAMBER_TOP), "nd_wall", radius=12)
        self.wseg((R, -400), (R, self.CHAMBER_TOP), "nd_wall", radius=12)
        self.wseg((L, self.CHAMBER_TOP), (L, self.NEEDLE_Y), "nd_needles", radius=10, side="L")
        self.wseg((R, self.CHAMBER_TOP), (R, self.NEEDLE_Y), "nd_needles", radius=10, side="R")
        self.wseg((L, self.NEEDLE_Y), (R, self.NEEDLE_Y), "nd_needles", radius=10, side="F")
        # 4 deflector tiers (the 5th tier is the chamber)
        self.tiers = [300.0, 500.0, 700.0, 900.0]
        flip = r.random() < 0.5
        for i, ty in enumerate(self.tiers):
            if i == len(self.tiers) - 1:
                # last tier: long inward funnels so nobody slides down the needle walls
                for sx, d in ((L + 8, 1), (R - 8, -1)):
                    self.wseg((sx, ty - 50), (sx + d * r.uniform(255, 290), ty + 80), "nd_deflector", material="wall",
                              radius=11)
                self.wcirc((540 + r.uniform(-40, 40), ty + 20), 17, "nd_peg")
                continue
            if (i % 2 == 0) != flip:
                # wall funnels angled inward + a centre peg pair
                a = r.uniform(170, 230)
                self.wseg((L + 8, ty - 60), (L + a, ty + 40), "nd_deflector", material="wall", radius=11)
                b = r.uniform(170, 230)
                self.wseg((R - 8, ty - 60), (R - b, ty + 40), "nd_deflector", material="wall", radius=11)
                cx = 540 + r.uniform(-60, 60)
                for dx in (-95, 95):
                    self.wcirc((cx + dx, ty + r.uniform(-10, 10)), r.uniform(15, 19), "nd_peg")
            else:
                # centre tent + side pegs
                cx = 540 + r.uniform(-110, 110)
                w = r.uniform(110, 145)
                self.wseg((cx - w, ty + 40), (cx, ty - 40), "nd_deflector", material="wall", radius=11)
                self.wseg((cx, ty - 40), (cx + w, ty + 40), "nd_deflector", material="wall", radius=11)
                for px in (r.uniform(150, 230), r.uniform(850, 930)):
                    self.wcirc((px, ty + r.uniform(-12, 12)), r.uniform(15, 19), "nd_peg")
        # safe pads (kinematic platforms)
        n_pads = 4
        self.pads: list[Prop] = []
        self.pad_cx, self.pad_y, self.pad_w, self.pad_amp, self.pad_om, self.pad_ph = [], [], [], [], [], []
        self.pad_state: list[int] = []            # 0 active, 1 flashing, 2 gone
        lanes = [218.0, 436.0, 644.0, 862.0]
        self.pad_shape: list[list[pymunk.Shape]] = []
        hi_first = r.random() < 0.5
        for i in range(n_pads):
            cx = lanes[i] + r.uniform(-12, 12)
            y = 1225.0 if ((i % 2 == 0) == hi_first) else 1345.0
            w = r.uniform(200, 212)
            b = kin_body(sim, (cx, y))
            shapes = self._pad_shapes(b, w)
            p = sim.add_prop(b, shapes, "nd_pad", material="ground")
            self.pads.append(p)
            self.pad_shape.append(shapes)
            self.pad_cx.append(cx)
            self.pad_y.append(y)
            self.pad_w.append(w)
            self.pad_amp.append(r.uniform(30, 42))
            self.pad_om.append(r.uniform(0.85, 1.35) * (1 if r.random() < 0.5 else -1))
            self.pad_ph.append(r.uniform(0, 2 * math.pi))
            self.pad_state.append(0)
            b.position = (self._pad_x(i, 0.0), y)     # start exactly on the t=0 pose (no first-step teleport kick)
        self.order = r.sample(range(n_pads), n_pads - 1)     # seeded retract order (the last pad never retracts)
        bomb = sim.recipe.goal == "hot_potato_bomb"        # the bomb already pops a ball every ~3.6 s
        self.first_round = r.uniform(6.6, 7.2) * (1.25 if bomb else 1.0)
        self.round_gap = r.uniform(5.3, 5.9) * (1.4 if bomb else 1.0)
        self.flame_y = -240.0                    # ceiling flames: lower one tier per round
        self.flame_target = -240.0
        self.next_flash = self.first_round - 1.0
        self.flash_i: int | None = None
        self.flash_end = 0.0
        self.rounds = 0
        self.clock = 0.0
        self.hop_cd: dict[str, float] = {}
        # safety net over the needles for the opening scramble; "NEEDLES ARMED!" retracts it
        self.net = self.wseg((L + 12, self.NET_Y), (R - 12, self.NET_Y), "nd_net", material="ground", radius=8)
        self.net_t = r.uniform(2.5, 3.0)
        self.net_on = True
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self._publish(0.0)

    def spawn_points(self, n, rng):
        return self.grid(n, rng, 120.0, 960.0, 190.0, dy=72.0, step=78.0)

    # -- pads
    def _pad_x(self, i: int, t: float) -> float:
        """t is unused: pad_ph is integrated per step so speed/amplitude changes never teleport the pad."""
        x = self.pad_cx[i] + self.pad_amp[i] * math.sin(self.pad_ph[i])
        m = 78.0 + self.pad_w[i] / 2          # riders never touch the side needles
        return max(self.WALL_L + m, min(self.WALL_R - m, x))

    def _pad_shapes(self, b: pymunk.Body, w: float) -> list:
        """Pad slab + two low guard lips (riders only leave when shoved or launched)."""
        h, lh, lw = self.PAD_H / 2, self.LIP_H, 12.0
        slab = pymunk.Poly.create_box(b, (w, self.PAD_H), radius=4)
        lips = [pymunk.Poly(b, [(sx, -h), (sx + d * lw, -h), (sx + d * lw, -h - lh), (sx, -h - lh)], radius=3)
                for sx, d in ((-w / 2, 1), (w / 2, -1))]
        return [slab] + lips

    def _resize(self, i: int, w: float) -> None:
        b = self.pads[i].body
        for old in self.pad_shape[i]:
            if old in self.sim.space.shapes:
                self.sim.space.remove(old)
        shapes = self._pad_shapes(b, w)
        for s in shapes:
            self.sim._material(s, "ground")
        self.sim.space.add(*shapes)
        self.pad_shape[i] = shapes
        self.pad_w[i] = w

    def active(self, include_flash: bool = False) -> list[int]:
        return [i for i, st in enumerate(self.pad_state) if st == 0 or (include_flash and st == 1)]

    def _step(self, dt: float) -> None:
        self.clock += dt
        t = self.clock
        for i, p in enumerate(self.pads):
            if self.pad_state[i] == 2:
                continue
            self.pad_ph[i] += self.pad_om[i] * dt
            x0 = float(p.body.position.x)
            x = self._pad_x(i, t)
            x = x0 + max(-420.0 * dt, min(420.0 * dt, x - x0))      # speed-limited: riders are carried, not kicked
            move_kin(p, x, self.pad_y[i], dt)
        L, R = self.WALL_L + 10, self.WALL_R - 10
        self.flame_y = min(self.flame_target, self.flame_y + 260.0 * dt) if self.flame_y < self.flame_target \
            else self.flame_target
        damp = math.exp(-self.GRIP * dt)
        damp_d = math.exp(-self.GRIP * 0.35 * dt)           # crash dummies have slippery soles
        for c in self.sim.alive():
            x, y = c.pos
            rr = c.radius
            on = self._on_pad(c)
            if on is not None:
                pv = float(self.pads[on].body.velocity.x)
                v = c.body.velocity
                k = damp if c.is_hero else damp_d
                c.body.velocity = (pv + (v.x - pv) * k, v.y)
            if y + rr >= self.NEEDLE_Y - 13 or (y > self.CHAMBER_TOP and (x - rr <= L + 3 or x + rr >= R - 3)):
                self.kill(c, "needles")
            elif y - rr * 0.5 < self.flame_y:
                self.kill(c, "flames")

    def _lower_flames(self) -> None:
        k = min(self.rounds, len(self.tiers))
        self.flame_target = self.tiers[k - 1] + 40.0 if k >= 1 else -240.0

    def _hop_to(self, c: "Contestant", tgt: int, vy: float, t: float) -> None:
        x, y = c.pos
        tx = float(self.pads[tgt].body.position.x)
        g = 980.0 * self.sim.gravity_scale
        land = self.pad_y[tgt] - self.PAD_H / 2 - c.radius
        h = y - land                                     # >0: target is higher
        disc = vy * vy - 2 * g * h
        tf = (-vy + math.sqrt(disc)) / g if disc > 0 else 0.6
        vx = max(-420.0, min(420.0, (tx - x) / max(0.25, tf)))
        m = c.body.mass
        v = c.body.velocity
        c.body.apply_impulse_at_world_point(((vx - v.x) * m, (vy - min(0.0, v.y)) * m), c.body.position)
        self.hop_cd[c.key] = t + 0.9
        c.squash = 1.0
        self.sim.event("arena_hit", [c.key], c.pos, name="pad_hop")

    def _frame(self, t: float) -> None:
        sim = self.sim
        sm = math.sqrt(sim.speed_mult)
        if self.net_on:
            if t >= self.net_t:
                self.net_on = False
                sim.remove_static(self.net)
                sim.event("escalation", [], None, mult=sim.speed_mult, banner="NEEDLES ARMED!")
            else:
                # stranded balls scramble up onto the nearest pad
                for c in sim.alive():
                    x, y = c.pos
                    if y + c.radius < self.NET_Y - 30 or self.hop_cd.get(c.key, -9) > t or c.stun > 0:
                        continue
                    tgt = self._target_pad(c)
                    if tgt is None:
                        continue
                    if abs(float(self.pads[tgt].body.position.x) - x) > 150 + self.pad_w[tgt] / 2:
                        continue
                    skill = (0.10 + 0.10 * c.behaviour.jumpiness) if c.is_hero else 0.05
                    if sim.rng.random() < skill:
                        up = self.NET_Y - self.pad_y[tgt]
                        self._hop_to(c, tgt, -math.sqrt(2 * 980 * sim.gravity_scale * (up + 70)), t)
        if self.flash_i is None and t >= self.next_flash:
            left = [i for i in self.order if self.pad_state[i] == 0]
            if left:
                self.flash_i = left[0]
                self.pad_state[self.flash_i] = 1
                self.flash_end = t + 1.0
            else:
                # final pad: it shrinks and speeds up every round
                self.rounds += 1
                last = self.active()
                for i in last:
                    self._resize(i, max(92.0, self.pad_w[i] * 0.86))
                    self.pad_om[i] *= 1.18
                    self.pad_amp[i] = min(150.0, self.pad_amp[i] + 25)
                self.next_flash = t + self.round_gap * 0.85 / sm
                self._lower_flames()
        if self.flash_i is not None and t >= self.flash_end:
            i = self.flash_i
            self.pad_state[i] = 2
            park(self.pads[i])
            self.flash_i = None
            self.rounds += 1
            for j in self.active():
                self._resize(j, max(110.0, self.pad_w[j] * 0.9))
                self.pad_om[j] *= 1.15
                self.pad_amp[j] = min(120.0, self.pad_amp[j] + 12)
            if len(self.active()) == 1:
                sim.event("escalation", [], None, mult=sim.speed_mult, banner="LAST PAD!")
            self._lower_flames()
            self.next_flash = t + self.round_gap / sm - 1.0
        # riders parked on a good pad are not "stuck": skip the engine's anti-stuck eject hop for them
        for c in sim.alive():
            on = self._on_pad(c)
            if on is not None and self.pad_state[on] == 0 and c.is_hero:
                c.last_unstick_t = t                 # (crash dummies keep their clumsy anti-stuck hops)
        # AI hop assistance: riders of a flashing pad (or anyone stranded) hop toward the nearest active pad
        if self.flash_i is not None:
            fi = self.flash_i
            fx = float(self.pads[fi].body.position.x)
            hw = self.pad_w[fi] / 2
            for c in sim.alive():
                x, y = c.pos
                if not (fx - hw - 6 <= x <= fx + hw + 6 and abs(y + c.radius - (self.pad_y[fi] - self.PAD_H / 2)) < 16):
                    continue
                if self.hop_cd.get(c.key, -9) > t or c.stun > 0 or t < c.panic_until:
                    continue
                tgt = self._target_pad(c, exclude=fi)
                if tgt is None:
                    continue
                tx = float(self.pads[tgt].body.position.x)
                d = 1.0 if tx > x else -1.0
                edge = fx + hw * d
                bh = c.behaviour
                skill = (0.55 + 0.35 * bh.jumpiness + 0.1 * bh.caution) if c.is_hero else 0.15
                near_edge = abs(edge - x) < 55 + 30 * bh.caution
                if near_edge and sim.rng.random() < skill * 0.5:
                    up = self.pad_y[tgt] < self.pad_y[fi] - 20
                    self._hop_to(c, tgt, -650.0 if up else -430.0, t)
        self._publish(t)

    def _publish(self, t: float) -> None:
        pads = []
        for i, p in enumerate(self.pads):
            st = self.pad_state[i]
            frac = 0.0
            if st == 1:
                frac = max(0.0, min(1.0, 1.0 - (self.flash_end - t)))
            pads.append((float(p.body.position.x), self.pad_y[i], round(self.pad_w[i], 1), st, round(frac, 3)))
        self.sim.zones["nd_pads"] = pads
        self.sim.zones["nd_round"] = self.rounds
        self.sim.zones["nd_net"] = self.net_on
        self.sim.zones["nd_flame"] = round(self.flame_y, 1)

    # -- AI hooks
    def _target_pad(self, c: "Contestant", exclude: int | None = None) -> int | None:
        x, y = c.pos
        best, bd = None, 1e9
        for i in self.active():
            if i == exclude:
                continue
            px = float(self.pads[i].body.position.x)
            d = abs(px - x) + 0.6 * abs(self.pad_y[i] - y)
            if d < bd:
                best, bd = i, d
        return best

    def _on_pad(self, c: "Contestant") -> int | None:
        x, y = c.pos
        for i, p in enumerate(self.pads):
            if self.pad_state[i] == 2:
                continue
            px = float(p.body.position.x)
            hw = self.pad_w[i] / 2
            if px - hw - 4 <= x <= px + hw + 4 and abs(y + c.radius - (self.pad_y[i] - self.PAD_H / 2)) < 18:
                return i
        return None

    def drive_dir(self, c: "Contestant") -> float:
        if c.pos[1] < self.CHAMBER_TOP - 40:
            return 0.0                                   # in the tiers: let gravity and the deflectors work
        on = self._on_pad(c)
        if on is not None and self.pad_state[on] == 0:
            px = float(self.pads[on].body.position.x)
            dx = px - c.pos[0]
            if abs(dx) < self.pad_w[on] * 0.28:
                return 0.0
            return 1.0 if dx > 0 else -1.0
        tgt = self._target_pad(c, exclude=on)
        if tgt is None:
            return 0.0
        dx = float(self.pads[tgt].body.position.x) - c.pos[0]
        return 1.0 if dx > 0 else -1.0

    def jump_hint(self, c: "Contestant"):
        on = self._on_pad(c)
        if on is not None and self.pad_state[on] == 0:
            return False                      # never hop off a good pad
        return None

    def progress(self, c: "Contestant") -> float:
        on = self._on_pad(c)
        base = 0.0
        if on is not None and self.pad_state[on] == 0:
            base = 2000.0 - abs(float(self.pads[on].body.position.x) - c.pos[0])
        else:
            base = -c.pos[1] * 0.1
        return base + self.hero_bias(c)


# ================================================================================================ 2. PLINKO CASHOUT
@register(
    "plinko_cashout", SIDE, "Plinko Cashout", "game show plinko board with gold bins",
    quips=("Gold bin pays out. Spike bin pays... differently.", "Come on down! Mind the spikes on the way."),
    goals=("reach_finish",),
    hazards=(), twists=("low_gravity", "heavy_gravity"),
)
class PlinkoCashout(_Screen):
    """Peg field under a drop chute; 7 bins: 2 GOLD (gated lids -> win), spring SAFE bins (relaunch to the top after
    ~1.3 s), SPIKE bins (eliminated). Pure physics (no_drive)."""
    no_drive = True
    WALL_L, WALL_R = 22.0, 1058.0
    BIN_TOP = 1236.0
    FLOOR_Y = 1478.0
    LID_Y = 1214.0

    def build(self):
        r = self.sim.rng
        sim = self.sim
        self.setup_screen()
        L, R = self.WALL_L, self.WALL_R
        self.wseg((L, -400), (L, self.FLOOR_Y), "pc_wall", radius=12)
        self.wseg((R, -400), (R, self.FLOOR_Y), "pc_wall", radius=12)
        # hopper + funnel chute
        self.wseg((300, -300), (300, 170), "pc_chute", radius=10)
        self.wseg((780, -300), (780, 170), "pc_chute", radius=10)
        self.wseg((300, 150), (462, 300), "pc_chute", radius=10)
        self.wseg((780, 150), (618, 300), "pc_chute", radius=10)
        # chute gate (kinematic slider under the neck)
        gb = kin_body(sim, (540, 318))
        gs = pymunk.Poly.create_box(gb, (196, 16), radius=3)
        self.gate_prop = sim.add_prop(gb, [gs], "pc_gate", material="wall")
        self.gate_x = 540.0
        # peg field
        rows = 9
        self.pegs = []
        for row in range(rows):
            y = 420 + row * 88
            off = 0 if row % 2 == 0 else 62
            x = 70 + off
            while x <= 1010:
                if not (row == 0 and 470 < x < 610):          # leave the chute mouth open
                    pr = r.uniform(11, 13)
                    self.wcirc((x + r.uniform(-5, 5), y + r.uniform(-4, 4)), pr, "pc_peg")
                x += 124
        # wall half-pegs (stop balls sliding down the walls)
        for row in range(0, rows, 2):
            y = 420 + row * 88 + 30
            self.wseg((L + 4, y - 34), (L + 46, y + 8), "pc_kicker", radius=8)
            self.wseg((R - 4, y - 34), (R - 46, y + 8), "pc_kicker", radius=8)
        # bins
        n = 7
        bw = (R - L) / n
        self.bins: list[tuple[float, float, str]] = []
        idx = list(range(n))
        mid = n // 2
        while True:
            gold = sorted(r.sample([i for i in range(1, n - 1) if i != mid], 2))
            if gold[1] - gold[0] >= 2:
                break
        rest = [i for i in idx if i not in gold and i != mid]
        spikes = {mid} | set(r.sample(rest, r.choice([1, 2, 2])))      # the busy centre bin is always spikes
        for i in range(n):
            x0, x1 = L + i * bw, L + (i + 1) * bw
            kind = "gold" if i in gold else ("spike" if i in spikes else "safe")
            self.bins.append((x0, x1, kind))
        for i in range(1, n):
            x = L + i * bw
            self.wseg((x, self.BIN_TOP), (x, self.FLOOR_Y), "pc_divider", radius=8)
            self.wcirc((x, self.BIN_TOP - 2), 12, "pc_cap", material="wall")
        for x0, x1, kind in self.bins:
            mat = "ground"
            self.wseg((x0, self.FLOOR_Y), (x1, self.FLOOR_Y), "pc_floor", material=mat, radius=10, bin=kind)
        self.sim.statics.append({"type": "pc_bins", "bins": [list(b) for b in self.bins], "top": self.BIN_TOP,
                                 "floor": self.FLOOR_Y})
        # gold lids: kinematic trapdoors hinged at the bin's left edge (closed = horizontal, open = swung up)
        self.lids: list[dict[str, Any]] = []
        t0 = r.uniform(15.0, 16.8)
        for k, gi in enumerate(gold):
            x0, x1, _ = self.bins[gi]
            hx = x0 + 9
            ln = (x1 - x0) - 18
            b = kin_body(sim, (hx, self.LID_Y))
            s = pymunk.Segment(b, (0, 0), (ln, 0), 8)
            prop = sim.add_prop(b, [s], "pc_lid", material="bouncy")
            sched = []
            t = t0 + (0.0 if k == 0 else r.uniform(1.4, 2.8))
            while t < 40:
                o = r.uniform(2.2, 3.2)
                sched.append((t, t + o))
                t += o + r.uniform(1.6, 2.4)
            self.lids.append({"prop": prop, "bin": gi, "sched": sched, "ang": 0.0, "len": ln})
        self.gate_open_until = -1.0
        self.gate_next = 0.0
        self.gate_ph = 0
        self.in_bin_since: dict[str, float] = {}
        self.clock = 0.0
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self._publish(0.0)

    def spawn_points(self, n, rng):
        pts = []
        rows = [(120.0, 340.0, 740.0), (48.0, 340.0, 740.0), (-24.0, 340.0, 740.0), (-96.0, 340.0, 740.0)]
        k = 0
        for y, x0, x1 in rows:
            for j in range(6):
                if k >= n:
                    break
                x = x0 + j * (x1 - x0) / 5 + (18 if (k // 6) % 2 else 0) + rng.uniform(-4, 4)
                pts.append((min(x1, x), y + rng.uniform(-4, 4)))
                k += 1
        return pts[:n]

    def _lid_open(self, lid, t: float) -> bool:
        return any(a <= t < b for a, b in lid["sched"])

    def _step(self, dt: float) -> None:
        self.clock += dt
        t = self.clock
        # chute gate: open 0.45 s / closed 0.55 s waves
        want = 760.0 if t < self.gate_open_until else 540.0
        self.gate_x += max(-1100 * dt, min(1100 * dt, want - self.gate_x))
        move_kin(self.gate_prop, self.gate_x, 318.0, dt)
        for lid in self.lids:
            target = -1.45 if self._lid_open(lid, t) else 0.0
            a = lid["ang"]
            a += max(-7.0 * dt, min(7.0 * dt, target - a))
            lid["ang"] = a
            x0 = self.bins[lid["bin"]][0] + 9
            move_kin(lid["prop"], x0, self.LID_Y, dt, angle=a)
        for c in self.sim.alive():
            x, y = c.pos
            if y + c.radius > self.FLOOR_Y - 46 and y > self.BIN_TOP:
                b = self._bin_of(x)
                if b is not None and self.bins[b][2] == "spike":
                    self.kill(c, "spikes")

    def _bin_of(self, x: float) -> int | None:
        for i, (x0, x1, _) in enumerate(self.bins):
            if x0 <= x < x1:
                return i
        return None

    def _frame(self, t: float) -> None:
        sim = self.sim
        if t >= self.gate_next:
            self.gate_open_until = t + 0.55
            self.gate_next = t + 1.15
        for c in sim.alive():
            x, y = c.pos
            b = self._bin_of(x)
            inside = b is not None and y > self.BIN_TOP + 40
            kind = self.bins[b][2] if b is not None else ""
            if inside and (kind == "safe" or (kind == "gold" and not c.is_hero)):
                since = self.in_bin_since.setdefault(c.key, t)
                if t - since >= 1.3:
                    m = c.body.mass
                    v = c.body.velocity
                    vy = -sim.rng.uniform(1220, 1400) * math.sqrt(sim.gravity_scale)
                    vx = sim.rng.uniform(-70, 70)
                    c.body.apply_impulse_at_world_point(((vx - v.x) * m, (vy - v.y) * m), c.body.position)
                    c.squash = 1.0
                    self.in_bin_since.pop(c.key, None)
                    sim.event("arena_hit", [c.key], c.pos, name="spring")
                    self.sim.zones["pc_spring"] = (b, round(t, 2))
            else:
                self.in_bin_since.pop(c.key, None)
        self._publish(t)

    def _publish(self, t: float) -> None:
        z = self.sim.zones
        z["pc_lids"] = [(lid["bin"], round(lid["ang"], 3), self._lid_open(lid, self.clock)) for lid in self.lids]
        nxt = min((a for lid in self.lids for a, _ in lid["sched"] if a > self.clock), default=99.0)
        z["pc_next_open"] = round(nxt - self.clock, 2)

    def at_finish(self, c: "Contestant") -> bool:
        if not c.is_hero:
            return False
        x, y = c.pos
        if y < self.BIN_TOP + 50:
            return False
        b = self._bin_of(x)
        return b is not None and self.bins[b][2] == "gold"

    def drive_dir(self, c: "Contestant") -> float:
        return 0.0

    def progress(self, c: "Contestant") -> float:
        x, y = c.pos
        best = 1e9
        for x0, x1, kind in self.bins:
            if kind == "gold":
                best = min(best, math.hypot((x0 + x1) / 2 - x, self.FLOOR_Y - y))
        return -best + self.hero_bias(c)


# ================================================================================================ 3. PINBALL PIT
@register(
    "pinball_pit", SIDE, "Pinball Pit", "neon pinball table with flippers and a jackpot lane",
    quips=("Flippers flip on their own. Nobody tilt the table. Oops.", "Hit the jackpot or hit the drain!"),
    goals=("reach_finish", "survive_timer"),
    hazards=(), twists=("low_gravity", "heavy_gravity"),
)
class PinballPit(_Screen):
    """Full-screen pinball table: rhythm flippers above a centre drain, slingshots, pop bumpers, spinners, a TILT!
    shake mid-race, a drain-saver post (pacing) and a jackpot lane at the top centre (reach_finish win)."""
    no_drive = True
    WALL_L, WALL_R = 24.0, 1056.0
    FLIP_L = (346.0, 1338.0)
    FLIP_R = (734.0, 1338.0)
    FLIP_LEN = 150.0
    REST, UP = 0.5, -0.46
    LANE = (478.0, 602.0)
    JACK_Y = 112.0

    def build(self):
        r = self.sim.rng
        sim = self.sim
        self.setup_screen()
        L, R = self.WALL_L, self.WALL_R
        self.goal_key = sim.recipe.goal
        # outer walls + top arch
        self.wseg((L, 300), (L, 1080), "pp_rail", radius=12)
        self.wseg((R, 300), (R, 1080), "pp_rail", radius=12)
        arch = [(L, 300), (60, 170), (150, 80), (290, 30), (440, 14), (640, 14), (790, 30), (930, 80), (1020, 170), (R, 300)]
        for a, b in zip(arch, arch[1:]):
            self.wseg(a, b, "pp_rail", radius=12)
        # inlane guides down to the flippers
        self.wseg((L, 1080), (self.FLIP_L[0] - 6, self.FLIP_L[1] - 4), "pp_rail", radius=12)
        self.wseg((R, 1080), (self.FLIP_R[0] + 6, self.FLIP_R[1] - 4), "pp_rail", radius=12)
        # slingshots (bouncy kickers above the inlanes)
        self.slings = [((150, 950), (268, 1105)), ((930, 950), (812, 1105))]
        for a, b in self.slings:
            self.wseg(a, b, "pp_sling", material="bouncy", radius=13)
        # jackpot lane + funnel mouth
        lx0, lx1 = self.LANE
        self.wseg((lx0, 40), (lx0, 205), "pp_lane", radius=9)
        self.wseg((lx1, 40), (lx1, 205), "pp_lane", radius=9)
        self.wseg((lx0, 205), (lx0 - 120, 330), "pp_lane", radius=9)
        self.wseg((lx1, 205), (lx1 + 120, 330), "pp_lane", radius=9)
        self.door = self.wseg((lx0 + 4, 200), (lx1 - 4, 200), "pp_door", radius=8)
        self.door_open = False
        self.door_t = r.uniform(14.5, 16.5) if self.goal_key == "reach_finish" else 1e9
        # pop bumpers
        self.bumpers = [((372, 575), 44.0), ((708, 575), 44.0), ((540, 745), 46.0), ((190, 530), 30.0), ((890, 530), 30.0)]
        jit = [(r.uniform(-18, 18), r.uniform(-18, 18)) for _ in self.bumpers]
        self.bumpers = [((x + dx, y + dy), rr) for ((x, y), rr), (dx, dy) in zip(self.bumpers, jit)]
        for i, (c, rr) in enumerate(self.bumpers):
            self.wcirc(c, rr, "pp_bumper", material="bumper", idx=i)
        self.bump_t = [-9.0] * len(self.bumpers)
        self.bump_cd: dict[tuple[str, int], float] = {}
        # spinners (kinematic rotating bars)
        self.spinners = []
        for (sx, sy), w in (((222, 880), r.uniform(2.2, 3.0)), ((858, 880), -r.uniform(2.2, 3.0))):
            b = kin_body(sim, (sx, sy))
            s = pymunk.Segment(b, (-72, 0), (72, 0), 9)
            ph = r.uniform(0, math.pi)
            b.angle = ph
            p = sim.add_prop(b, [s], "pp_spinner", material="wall")
            self.spinners.append((p, w, ph))
        # flippers
        self.flips = []
        for side, (px, py) in (("L", self.FLIP_L), ("R", self.FLIP_R)):
            b = kin_body(sim, (px, py))
            end = (self.FLIP_LEN, 0) if side == "L" else (-self.FLIP_LEN, 0)
            s = pymunk.Segment(b, (0, 0), end, 13)
            p = sim.add_prop(b, [s], "pp_flipper", material="wall")
            rest = self.REST if side == "L" else -self.REST
            b.angle = rest
            sched = []
            t = r.uniform(0.2, 0.9)
            while t < 40:
                sched.append(t)
                t += r.uniform(0.75, 1.45)
            self.flips.append({"prop": p, "side": side, "sched": sched, "k": 0, "rest": rest,
                               "up": self.UP if side == "L" else -self.UP, "ang": rest})
        # drain saver post (pacing): pops up while Lord Tuno's schedule says we're ahead on eliminations
        self.post = kin_body(sim, (540, 1600))
        ps = pymunk.Circle(self.post, 24)
        self.post_prop = sim.add_prop(self.post, [ps], "pp_post", material="bumper")
        self.post_up = False
        self.post_hold = 0.0
        self.tilt_t = r.uniform(9.5, 12.0)
        self.tilted = False
        self.clock = 0.0
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self._publish(0.0)

    def spawn_points(self, n, rng):
        pts = []
        for i in range(n):
            row, k = divmod(i, 7)
            x = 135 + k * 135 + (60 if row % 2 else 0) + rng.uniform(-6, 6)
            y = 410 + row * 72 + rng.uniform(-5, 5)
            pts.append((min(960.0, x), y))
        return pts

    def _flip_angle(self, f, t: float) -> float:
        sched = f["sched"]
        while f["k"] + 1 < len(sched) and t >= sched[f["k"] + 1]:
            f["k"] += 1
        s = t - sched[f["k"]]
        rest, up = f["rest"], f["up"]
        if s < 0:
            return rest
        if s < 0.07:
            return rest + (up - rest) * (s / 0.07)
        if s < 0.19:
            return up
        if s < 0.52:
            return up + (rest - up) * ((s - 0.19) / 0.33)
        return rest

    def _step(self, dt: float) -> None:
        self.clock += dt
        t = self.clock
        for f in self.flips:
            a = self._flip_angle(f, t)
            f["ang"] = a
            move_kin(f["prop"], f["prop"].body.position.x, f["prop"].body.position.y, dt, angle=a)
        for p, w, ph in self.spinners:
            move_kin(p, p.body.position.x, p.body.position.y, dt, angle=ph + w * t)
        py = 1418.0 if self.post_up else 1600.0
        cy = float(self.post.position.y)
        ny = cy + max(-900 * dt, min(900 * dt, py - cy))
        move_kin(self.post_prop, 540.0, ny, dt)
        sim = self.sim
        for c in sim.alive():
            x, y = c.pos
            if y > 1452 or y > 1520:
                self.kill(c, "drain")
                continue
            # pop bumpers: active kick
            for i, ((bx, by), br) in enumerate(self.bumpers):
                dx, dy = x - bx, y - by
                d = math.hypot(dx, dy)
                if d < br + c.radius + 5 and self.bump_cd.get((c.key, i), -9) <= t:
                    self.bump_cd[(c.key, i)] = t + 0.18
                    self.bump_t[i] = t
                    nx, ny_ = dx / (d or 1), dy / (d or 1)
                    v = c.body.velocity
                    vn = v.x * nx + v.y * ny_
                    kick = max(0.0, 620.0 - vn)
                    m = c.body.mass
                    c.body.apply_impulse_at_world_point((nx * kick * m, ny_ * kick * m), c.body.position)
                    c.hit_until = sim.t + 0.3
            # jackpot hole: dummies get spat back out (only heroes can cash the jackpot)
            if self.door_open and not c.is_hero and self.LANE[0] < x < self.LANE[1] and y < self.JACK_Y + 10:
                v = c.body.velocity
                m = c.body.mass
                c.body.apply_impulse_at_world_point((-v.x * m, (520 - v.y) * m), c.body.position)

    def _frame(self, t: float) -> None:
        sim = self.sim
        if not self.door_open and t >= self.door_t:
            self.door_open = True
            sim.remove_static(self.door)
            sim.event("escalation", [], None, mult=sim.speed_mult, banner="JACKPOT OPEN!")
        if not self.tilted and t >= self.tilt_t:
            self.tilted = True
            sim.event("escalation", [], None, mult=sim.speed_mult, banner="TILT!")
            side = 1.0 if sim.rng.random() < 0.5 else -1.0
            for c in sim.alive():
                m = c.body.mass
                ix = side * sim.rng.uniform(260, 520)
                iy = -sim.rng.uniform(380, 640)
                c.body.apply_impulse_at_world_point((ix * m, iy * m), c.body.position)
                c.stun = max(c.stun, 0.35)
            sim.zones["pp_tilt"] = (round(t, 2), side)
        # drain saver: up while fewer balls remain than the pacing schedule wants
        if t >= self.post_hold:
            want = t > 2.5 and sim.pressure < 0.92
            if want != self.post_up:
                self.post_up = want
                self.post_hold = t + 1.4
        self._publish(t)

    def _publish(self, t: float) -> None:
        z = self.sim.zones
        z["pp_bump"] = [round(self.clock - bt, 2) for bt in self.bump_t]
        z["pp_flip"] = [round(f["ang"], 3) for f in self.flips]
        z["pp_door"] = self.door_open
        z["pp_post"] = self.post_up

    def at_finish(self, c: "Contestant") -> bool:
        if not (self.door_open and c.is_hero):
            return False
        x, y = c.pos
        return self.LANE[0] < x < self.LANE[1] and y < self.JACK_Y

    def drive_dir(self, c: "Contestant") -> float:
        return 0.0

    def progress(self, c: "Contestant") -> float:
        x, y = c.pos
        return -math.hypot(x - 540.0, y - self.JACK_Y) * 0.2 - (y - 600) * 0.0 + self.hero_bias(c) + \
            (1e5 if c.finished else 0.0)


# ================================================================================================ 4. WALL RUSH
@register(
    "wall_rush", SIDE, "Wall Rush", "three-lane wall dodge with sliding gap walls",
    quips=("Find the hole in the wall. Or become part of it.", "Three lanes, one gap, zero mercy."),
    goals=("survive_timer", "last_one_standing"),
    hazards=(), twists=("heavy_gravity", "slippery_floor"),
)
class WallRush(_Screen):
    """Three one-way lane platforms; walls with one gap slide in from the right (1 s warning) and sweep left; a ball
    in a blocked lane is shoved off the left end into the shaft. The arena hops balls between lanes."""
    LANES = (560.0, 900.0, 1240.0)
    LANE_X0, LANE_X1 = 150.0, 1250.0
    GAP_H = 236.0
    WALL_W = 84.0
    START_X = 1310.0

    def build(self):
        r = self.sim.rng
        sim = self.sim
        self.setup_screen()
        self.lane_shapes = []
        for i, ly in enumerate(self.LANES):
            s = self.wseg((self.LANE_X0, ly), (self.LANE_X1, ly), "wr_lane", material="ground", radius=12, lane=i)
            s.collision_type = CT_LANE
            s.lane_idx = i  # type: ignore[attr-defined]
            self.lane_shapes.append(s)
        self.wseg((self.LANE_X1, 250), (self.LANE_X1, 1300), "wr_stop", radius=12)
        self.wseg((14, -400), (14, 1500), "wr_shaft", radius=12)
        sim.space.on_collision(CT_BODY, CT_LANE, pre_solve=self._pre)
        # three wall props (one per gap lane), parked until used
        self.walls: list[Prop] = []
        top, bot = 60.0, 1470.0
        for g, ly in enumerate(self.LANES):
            b = kin_body(sim, (9000.0, 9000.0))
            hw = self.WALL_W / 2
            up_y1 = ly - self.GAP_H
            lo_y0 = ly + 22
            shapes = [pymunk.Poly(b, [(-hw, top), (hw, top), (hw, up_y1), (-hw, up_y1)], radius=3),
                      pymunk.Poly(b, [(-hw, lo_y0), (hw, lo_y0), (hw, bot), (-hw, bot)], radius=3)]
            p = sim.add_prop(b, shapes, "wr_wall", material="wall")
            self.walls.append(p)
        self.active: dict[int, float] = {}         # gap lane -> wall x
        self.queue: list[dict[str, Any]] = []      # scheduled warnings
        self.warn: tuple[int, float] | None = None
        self.next_warn = 0.25
        self.last_gap = -1
        self.first = True
        self.dropping: dict[str, int] = {}         # key -> deepest lane index to ignore (exclusive target)
        self.plans: list[tuple[float, str, int, int]] = []   # (time, key, target lane, wall id)
        self.wall_id = 0
        self.target_x: dict[str, float] = {}
        self.clock = 0.0
        sim.hooks_step.append(self._step)
        sim.hooks_frame.append(self._frame)
        self._publish(0.0)

    def spawn_points(self, n, rng):
        pts = self.grid(n, rng, 300.0, 1000.0, 470.0, dy=74.0, step=80.0)
        return pts

    # -- one-way lanes
    def _pre(self, arb: pymunk.Arbiter, space, data) -> None:
        a, b = arb.shapes
        ball, lane = (a, b) if getattr(a, "contestant", None) is not None else (b, a)
        c = getattr(ball, "contestant", None)
        li = getattr(lane, "lane_idx", None)
        if c is None or li is None:
            arb.process_collision = True
            return
        ly = self.LANES[li] - 12
        y = float(c.body.position.y)
        vy = float(c.body.velocity.y)
        ok = y < ly - c.radius * 0.55 and vy > -40.0 and li >= self.dropping.get(c.key, -1)
        arb.process_collision = ok

    def lane_of(self, c: "Contestant") -> int | None:
        y = c.pos[1]
        for i, ly in enumerate(self.LANES):
            if ly - c.radius - 40 <= y <= ly - c.radius + 14 and c.pos[0] > self.LANE_X0 - 6:
                return i
        return None

    def _hop(self, c: "Contestant", cur: int, tgt: int) -> None:
        g = abs(self.sim.space.gravity.y) or 980.0
        m = c.body.mass
        v = c.body.velocity
        if tgt < cur:
            h = (self.LANES[cur] - self.LANES[tgt]) + 95
            vy = -math.sqrt(2 * g * h)
            c.body.apply_impulse_at_world_point((-v.x * 0.3 * m, (vy - v.y) * m), c.body.position)
            self.sim.event("arena_hit", [c.key], c.pos, name="lane_hop")
        elif tgt > cur:
            self.dropping[c.key] = tgt
            c.body.apply_impulse_at_world_point((0.0, 160 * m), c.body.position)
        c.squash = 1.0

    def _plan_for(self, wall_t: float, gap: int, wid: int, late: bool = False) -> None:
        sim = self.sim
        for c in sim.alive():
            cur = self.lane_of(c)
            if cur is None:
                continue
            if late and cur == gap:
                continue
            bh = c.behaviour
            if c.is_hero:
                p = min(0.95, 0.74 + 0.16 * bh.edge_awareness + 0.08 * bh.caution)
            else:
                p = 0.5
            if late:
                p *= 0.7
            if sim.rng.random() < p:
                tgt = gap
            else:
                tgt = sim.rng.choice([0, 1, 2]) if not late else cur
            delay = sim.rng.uniform(0.12, 0.65) + (0.0 if c.is_hero else 0.25)
            if tgt != cur:
                self.plans.append((wall_t + delay, c.key, tgt, wid))

    def _step(self, dt: float) -> None:
        self.clock += dt
        sim = self.sim
        speed = 390.0 * sim.speed_mult * (1.12 if sim.overtime else 1.0)
        for g in list(self.active):
            x = self.active[g] - speed * dt
            if x < -140:
                del self.active[g]
                park(self.walls[g])
                continue
            self.active[g] = x
            move_kin(self.walls[g], x, 0.0, dt)
        for c in sim.alive():
            x, y = c.pos
            if x < 128 or y > 1430:
                self.kill(c, "wall")

    def _frame(self, t: float) -> None:
        sim = self.sim
        # cleanup finished drops
        for k in list(self.dropping):
            c = sim.by_key[k]
            d = self.dropping[k]
            if not c.alive or c.pos[1] > self.LANES[d - 1] + 30 or c.pos[1] > self.LANES[d] - c.radius - 2:
                self.dropping.pop(k, None)
        if self.warn is None and t >= self.next_warn:
            choices = [g for g in range(3) if g != self.last_gap and g not in self.active]
            if self.first:
                choices = [g for g in choices if g != 0] or choices
                self.first = False
            if choices:
                gap = sim.rng.choice(choices)
                self.last_gap = gap
                self.warn = (gap, t + 1.0)
                self.wall_id += 1
                self._plan_for(t, gap, self.wall_id)
                gapk = 3.35 * (0.78 if sim.overtime else 1.0)
                self.next_warn = t + gapk / sim.speed_mult
        if self.warn is not None and t >= self.warn[1]:
            gap = self.warn[0]
            self.active[gap] = self.START_X
            move_kin(self.walls[gap], self.START_X, 0.0, 0.0)
            self.walls[gap].body.velocity = (0.0, 0.0)
            self._plan_for(t + 0.35, gap, self.wall_id, late=True)
            self.warn = None
        # execute lane plans
        due = [p for p in self.plans if p[0] <= t]
        if due:
            self.plans = [p for p in self.plans if p[0] > t]
            for _, key, tgt, _wid in due:
                c = sim.by_key[key]
                if not c.alive or c.stun > 0:
                    continue
                cur = self.lane_of(c)
                if cur is None or cur == tgt:
                    continue
                self._hop(c, cur, tgt)
        self._publish(t)

    def _publish(self, t: float) -> None:
        z = self.sim.zones
        z["wr_walls"] = [(g, round(x, 1)) for g, x in self.active.items()]
        z["wr_warn"] = (self.warn[0], round(self.warn[1] - t, 2)) if self.warn else None

    def drive_dir(self, c: "Contestant") -> float:
        tx = self.target_x.get(c.key)
        if tx is None:
            h = (sum(map(ord, c.key)) * 2654435761) % 1000 / 1000
            tx = self.target_x[c.key] = 430.0 + 420.0 * h
        dx = tx - c.pos[0]
        if abs(dx) < 40:
            return 0.0
        return 1.0 if dx > 0 else -1.0

    def jump_hint(self, c: "Contestant"):
        return False

    def progress(self, c: "Contestant") -> float:
        x, y = c.pos
        # safest = far from the shaft and the incoming wall
        return x * 0.1 - min((abs(wx - x) for _, wx in self.active.items()), default=0.0) * 0.0 + self.hero_bias(c)
