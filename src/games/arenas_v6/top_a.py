"""v6 TOP_DOWN arenas, group A: Color Floor, Tilt Table, Whirlpool Drain, Spotlight Panic.

Renderers live in src/rendering/arena_art/top_a.py (UNDER floors, OVER banners/beams). Per-frame state is published in
`sim.zones` under arena-specific keys (cf, tilt, drain_r, beams...). Zone values are always REPLACED (never mutated in
place) because the recorder shallow-copies the zones dict each frame.
"""
from __future__ import annotations

import math

from src.games.arena_kit import TOP, V6Top, kin_circle, register

TAU = 2.0 * math.pi


def _kall(sim) -> float:
    """Generic edge shrink x the shrinking_arena twist (the combined layout scale)."""
    tw = getattr(sim, "twist", None)
    return sim.edge_k * (getattr(tw, "k", 1.0) if tw is not None and tw.key == "shrinking_arena" else 1.0)


def _hash01(key: str, salt: int = 0) -> float:
    """Stable per-contestant pseudo-random value in [0, 1) (no RNG draw -> replay safe)."""
    return ((sum(map(ord, key)) * 2654435761 + salt * 40503) % 1000) / 1000.0


def _wrap(a: float) -> float:
    return (a + math.pi) % TAU - math.pi


def _calm(sim, c) -> None:
    """Champion's victory hold: brake and settle toward the hub so the winner never slides off afterwards."""
    x, y = c.pos
    m = c.body.mass
    c.body.velocity = c.body.velocity * 0.82
    c.body.apply_force_at_world_point((-x * 10.0 * m, -y * 10.0 * m), c.body.position)


# ============================================================================================== 1. COLOR FLOOR
COLOUR_NAMES = ("RED", "BLUE", "GREEN", "YELLOW", "PURPLE")


@register("color_floor", TOP, "Color Floor", "colour-call tile drop party game",
          quips=("Know your colours or know the floor!", "Blue means blue, Bonk. Not snack."),
          goals=("last_one_standing", "survive_timer", "push_others_out"),
          hazards=(), twists=("reversed_controls", "slippery_floor"))
class ColorFloor(V6Top):
    """Square grid of bright tiles. Every round a colour is CALLED; after a countdown every other tile drops away for
    ~1.5 s and comes back re-shuffled. Later rounds: fewer safe tiles, shorter countdowns, outer tiles that never return."""
    no_shrink = True                         # the floor itself is the squeeze (outer tiles stop coming back)
    no_quake = True                          # the first colour drop (~3 s) is the opener; the quake wiped the board

    DROP_S = 1.5
    GAP_S = 0.5
    DUMMY_DELAY = 1.9        # dummies notice the call 0.45 .. 0.45 + this many seconds late
    CROWD_PX = 110.0         # a tile already claimed by someone counts as this much farther away
    LATE_T = 13.0            # rounds called after this offer (survivors - 1) safe tiles at most

    def build(self):
        r = self.sim.rng
        self.n = int(self.p.setdefault("cf_grid", 7))
        self.S = float(self.p.setdefault("cf_tile", r.choice([110, 112, 114])))
        self.n_cols = int(self.p.setdefault("cf_colours", r.choice([4, 5, 5])))
        self.half = self.n * self.S / 2.0
        self.spawn_r = self.half * 0.55
        n = self.n
        self.present = [True] * (n * n)
        self.cols = [r.randrange(self.n_cols) for _ in range(n * n)]
        # ---- round schedule (all drawn now -> deterministic)
        self.rounds: list[dict] = []
        t, k = 0.45, 0
        while t < 45.0:
            cd = 2.8 if k == 0 else max(1.5, 2.45 - 0.15 * k)
            self.rounds.append({"call": t, "drop": t + cd, "back": t + cd + self.DROP_S,
                                "col": r.randrange(self.n_cols), "safe": self._safe_count(k)})
            t += cd + self.DROP_S + self.GAP_S
            k += 1
        self.ri = 0
        self.phase = 0                       # 0 idle, 1 countdown, 2 dropped
        self.phase_t = 0.0
        self._recolour(self.rounds[0])
        self.claims: dict[str, int] = {}
        self.sim.walkable = self._walkable
        self.sim.statics.append({"type": "cf_grid", "n": n, "S": self.S, "half": self.half, "ncol": self.n_cols})
        self.sim.hooks_frame.append(self._tick)
        self._publish(0.0)
        self.frame_top(self.half)

    SAFE_SEQ = (12, 10, 8, 7, 6, 5, 4, 3)

    def _safe_count(self, k: int) -> int:
        seq = self.SAFE_SEQ
        return seq[min(k, len(seq) - 1)]

    # ---- geometry
    def _idx(self, x: float, y: float) -> int:
        ix = int((x + self.half) // self.S)
        iy = int((y + self.half) // self.S)
        if 0 <= ix < self.n and 0 <= iy < self.n:
            return iy * self.n + ix
        return -1

    def _centre(self, i: int) -> tuple[float, float]:
        iy, ix = divmod(i, self.n)
        return (-self.half + (ix + 0.5) * self.S, -self.half + (iy + 0.5) * self.S)

    def _walkable(self, x: float, y: float) -> bool:
        i = self._idx(x, y)
        if i < 0 or not self.present[i]:
            return False
        if self.phase == 2:
            return self.cols[i] == self.rounds[self.ri]["col"]
        return True

    def _ring(self, i: int) -> int:
        iy, ix = divmod(i, self.n)
        c = (self.n - 1) / 2.0
        return int(max(abs(ix - c), abs(iy - c)))

    # ---- colouring
    def _recolour(self, rnd: dict) -> None:
        """Re-shuffle all present tiles, then force exactly rnd['safe'] tiles of the called colour (spread out)."""
        r = self.sim.rng
        live = [i for i in range(self.n * self.n) if self.present[i]]
        call = rnd["col"]
        others = [c for c in range(self.n_cols) if c != call]
        for i in live:
            self.cols[i] = r.choice(others)
        want = min(len(live), max(3, rnd["safe"]))
        if rnd["call"] >= self.LATE_T:
            # late rounds: one safe tile fewer than survivors -> somebody has to share (and shove)
            want = min(len(live), rnd["safe"], max(1, len(self.sim.alive()) - 1))
        order = list(live)
        r.shuffle(order)
        picked: list[int] = []
        for i in order:                      # first pass: keep safe tiles apart (no two touching edge-to-edge)
            if len(picked) >= want:
                break
            iy, ix = divmod(i, self.n)
            if any(abs(iy - j // self.n) + abs(ix - j % self.n) == 1 for j in picked):
                continue
            picked.append(i)
        for i in order:
            if len(picked) >= want:
                break
            if i not in picked:
                picked.append(i)
        for i in picked:
            self.cols[i] = call
        self.cols_t = tuple(self.cols[i] if self.present[i] else -1 for i in range(self.n * self.n))

    def _publish(self, t: float) -> None:
        rnd = self.rounds[self.ri]
        if self.phase == 1:
            left, tot = rnd["drop"] - t, rnd["drop"] - rnd["call"]
        elif self.phase == 2:
            left, tot = rnd["back"] - t, self.DROP_S
        else:
            left, tot = 0.0, 1.0
        self.sim.zones["cf"] = (self.cols_t, self.phase, rnd["col"], round(max(0.0, left), 3), round(tot, 3),
                                round(t - self.phase_t, 3), self.ri)
        self.sim.zones["color_call"] = COLOUR_NAMES[rnd["col"]] if self.phase in (1, 2) else None

    def _tick(self, t: float) -> None:
        rnd = self.rounds[self.ri]
        if self.phase == 0 and t >= rnd["call"]:
            self.phase, self.phase_t = 1, t
            self.claims = {}
            self.sim.event("escalation", [], None, mult=self.sim.speed_mult, banner=COLOUR_NAMES[rnd["col"]] + "!",
                           color_call=COLOUR_NAMES[rnd["col"]], round=self.ri + 1)
        elif self.phase == 1 and t >= rnd["drop"]:
            self.phase, self.phase_t = 2, t
            self.sim.event("arena_hit", [], None, name="tiles_drop", colour=COLOUR_NAMES[rnd["col"]])
        elif self.phase == 2 and t >= rnd["back"]:
            # outer tiles that dropped may never come back (the floor shrinks round by round)
            k = self.ri
            if k >= 1:
                rings = [self._ring(i) for i in range(self.n * self.n) if self.present[i]]
                outer = max(rings) if rings else 0
                p_keep_gone = min(0.85, 0.22 + 0.16 * (k - 1))
                if outer >= 1:
                    for i in range(self.n * self.n):
                        if (self.present[i] and self._ring(i) == outer and self.cols[i] != rnd["col"]
                                and self.sim.rng.random() < p_keep_gone):
                            self.present[i] = False
            self.ri = min(self.ri + 1, len(self.rounds) - 1)
            self.phase, self.phase_t = 0, t
            self.claims = {}
            self._recolour(self.rounds[self.ri])
        self._publish(t)

    # ---- AI
    def brake(self, c) -> bool:
        """Settled on my safe tile: stop propelling and plant (others can still shove me off)."""
        if self.phase == 0:
            return False
        mine = self.claims.get(c.key)
        if mine is None:
            return False
        cx, cy = self._centre(mine)
        x, y = c.pos
        return abs(x - cx) < self.S * 0.2 and abs(y - cy) < self.S * 0.2

    def safe_target(self, c):
        if self.phase == 0:
            return None
        rnd = self.rounds[self.ri]
        # dummies (and slow heroes) react late
        if c.extra is not None:
            delay = 0.45 + self.DUMMY_DELAY * _hash01(c.key, self.ri)
        else:
            delay = 0.05 + 0.35 * (1.0 - c.behaviour.edge_awareness)
        if self.phase == 1 and self.sim.t - rnd["call"] < delay:
            return None
        call = rnd["col"]
        x, y = c.pos
        mine = self.claims.get(c.key)
        if mine is not None and self.present[mine] and self.cols[mine] == call:
            return self._centre(mine)
        # commit to one called tile for this round; claims by others spread the crowd over the safe tiles
        counts: dict[int, int] = {}
        for k, i in self.claims.items():
            if k != c.key:
                counts[i] = counts.get(i, 0) + 1
        best, bs = None, 1e9
        for i in range(self.n * self.n):
            if not self.present[i] or self.cols[i] != call:
                continue
            cx, cy = self._centre(i)
            sc = math.hypot(cx - x, cy - y) + self.CROWD_PX * counts.get(i, 0)
            if sc < bs:
                best, bs = i, sc
        if best is None:
            return None
        self.claims[c.key] = best
        return self._centre(best)

    def progress(self, c) -> float:
        return -math.hypot(*c.pos)


# ============================================================================================== 2. TILT TABLE
@register("tilt_table", TOP, "Tilt Table", "mass-balanced tilting plate",
          quips=("Everybody lean left! No wait, the OTHER left!", "Juggernaut sat down. The table noticed."),
          goals=("last_one_standing", "survive_timer", "collect_items", "push_others_out"),
          hazards=("wind_gusts", "slippery_ice"), twists=("reversed_controls", "slippery_floor", "shrinking_arena"))
class TiltTable(V6Top):
    """Round plate on a central pivot. The mass-weighted centre of the living balls tilts it (spring-smoothed);
    the tilt accelerates every ball toward the low side, so crowds tip the table and slide off together."""

    DRAG = 1.6               # plate surface drag (1/s): terminal slide speed = tilt acc / DRAG
    no_quake = True          # the generic quake flung most balls off the plate; the table LURCH replaces it
    LURCH_T = 1.0
    LURCH_V = 9.0            # tilt velocity kick (tilt units / s)

    def build(self):
        r = self.sim.rng
        self.R = float(self.p.setdefault("radius", round(r.uniform(405, 435))))
        self.gain = float(self.p.setdefault("tilt_gain", round(r.uniform(2.3, 2.7), 2)))
        self.acc = float(self.p.setdefault("tilt_acc", round(r.uniform(560, 620))))
        self.wob = float(self.p.setdefault("tilt_wobble", round(r.uniform(0.0, TAU), 2)))
        self.lurch_a = float(self.p.setdefault("tilt_lurch", round(r.uniform(0.0, TAU), 2)))
        self.spawn_r = self.R * 0.55
        self.sim.walkable = lambda x, y: x * x + y * y < self.R * self.R
        self.tilt = [0.0, 0.0]
        self.tv = [0.0, 0.0]
        self._sub = 0
        lu, t = [], self.LURCH_T
        while t < 40.0:
            lu.append(round(t, 2))
            t += r.uniform(3.6, 4.4)
        self.lurches = self.p.setdefault("tilt_lurches", lu)
        self._li = 0
        self.sim.statics.append({"type": "tilt_plate", "c": (0.0, 0.0), "r": self.R})
        self.sim.zones["tilt"] = (0.0, 0.0)
        self.sim.hooks_step.append(self._step)
        self.frame_top(self.R)

    def _step(self, dt: float) -> None:
        sim = self.sim
        alive = sim.alive()
        if not alive:
            return
        t = sim.t
        k_all = _kall(sim)
        rk = max(40.0, self.R * k_all)
        mt = sx = sy = 0.0
        for c in alive:
            m = float(c.body.mass)
            x, y = c.pos
            mt += m
            sx += m * x
            sy += m * y
        cx, cy = sx / mt, sy / mt
        # target tilt: COM offset (normalised by the live radius) x gain + a slow wobble that breaks symmetry
        wob = 0.14 + 0.30 * min(1.0, max(0.0, t) / 14.0)
        g = self.gain * (1.0 + 0.4 * min(1.0, max(0.0, t) / 18.0))
        tx = cx / rk * g + wob * math.cos(0.8 * t + self.wob)
        ty = cy / rk * g + wob * math.sin(1.1 * t + self.wob)
        n = math.hypot(tx, ty)
        if n > 1.0:
            tx, ty = tx / n, ty / n
        if self._li < len(self.lurches) and t >= self.lurches[self._li]:
            # the pivot slips: a hard kick of tilt velocity. First one toward the dummies (first wipeouts),
            # later ones toward the crowd's centre of mass (the heaviest side tips harder)
            if self._li == 0:
                dum = [c for c in alive if c.extra is not None] or alive
                ddx = sum(c.pos[0] for c in dum) / len(dum)
                ddy = sum(c.pos[1] for c in dum) / len(dum)
                a = math.atan2(ddy, ddx) if math.hypot(ddx, ddy) > 20 else self.lurch_a
                v = self.LURCH_V * 1.2
            else:
                a = math.atan2(cy, cx) if math.hypot(cx, cy) > 15 else self.lurch_a + self._li * 2.1
                v = self.LURCH_V * min(1.2, max(0.45, 0.35 + 0.45 * sim.pressure))
            self._li += 1
            self.tv = [math.cos(a) * v, math.sin(a) * v]
            sim.event("escalation", [], None, mult=sim.speed_mult, banner="TABLE LURCH!")
        kk, dd = 16.0, 6.5
        for i, tgt in ((0, tx), (1, ty)):
            self.tv[i] += ((tgt - self.tilt[i]) * kk - self.tv[i] * dd) * dt
            self.tilt[i] += self.tv[i] * dt
        n = math.hypot(*self.tilt)
        if n > 1.0:
            self.tilt = [self.tilt[0] / n, self.tilt[1] / n]
        self._sub += 1
        if self._sub % 6 == 0:
            sim.zones["tilt"] = (round(self.tilt[0], 3), round(self.tilt[1], 3))
        if t < 0.4:
            return
        if len(alive) <= 1:
            for c in alive:
                _calm(sim, c)
            return
        # Lord Tuno's pacing pressure loosens the pivot when the field is ahead of schedule, firms it when behind
        late = min(1.5, max(0.6, 0.55 + 0.45 * sim.pressure))
        a = self.acc * late * min(1.5, sim.speed_mult) * min(1.0, (t - 0.4) / 1.2)
        ax, ay = self.tilt[0] * a, self.tilt[1] * a
        drag = self.DRAG * min(1.0, max(0.3, (t - 1.0) / 3.0))
        for c in alive:
            m = c.body.mass
            mult = 1.25 if (c.hero is not None and c.hero.trait == "bowling") else 1.0    # cast iron slides
            v = c.body.velocity
            k = drag * min(1.0, c.traction)
            c.body.apply_force_at_world_point(((ax * mult - v.x * k) * m, (ay * mult - v.y * k) * m),
                                              c.body.position)

    def safe_target(self, c):
        tx, ty = self.tilt
        m = math.hypot(tx, ty)
        if m < 0.35:
            return None
        if c.extra is not None and _hash01(c.key, 3) < 0.55:
            return None                       # half the dummies never learn to walk uphill
        ux, uy = tx / m, ty / m
        x, y = c.pos
        rk = self.R * _kall(self.sim)
        along = x * ux + y * uy
        if along < 0.30 * rk:
            return None
        # climb back toward the high side, keeping the sideways offset (spreads the crowd -> the table re-balances)
        px, py = x - along * ux, y - along * uy
        return (px * 0.6 - ux * 0.25 * rk, py * 0.6 - uy * 0.25 * rk)


# ============================================================================================== 3. WHIRLPOOL DRAIN
@register("whirlpool_drain", TOP, "Whirlpool Drain", "spiral whirlpool with a growing drain",
          quips=("Hold onto the rail, it's bath time!", "Someone pulled the plug. It was me."),
          goals=("last_one_standing", "push_others_out", "collect_items", "survive_timer"),
          hazards=(), twists=("reversed_controls", "giant_ball"))
class WhirlpoolDrain(V6Top):
    """Round pool with a bouncy guard rail (no edge falls). A spiral current drags everything inward + around toward
    a centre drain whose radius grows over the race; periodic FLUSH surges pull hard. Falling in the drain = out."""
    no_shrink = True                          # the growing drain is the squeeze
    no_quake = True                           # an outward floor buck makes no sense in water; FLUSH! replaces it

    RD0, RD1 = 52.0, 150.0

    def build(self):
        r = self.sim.rng
        self.R = float(self.p.setdefault("radius", round(r.uniform(420, 440))))
        self.spin = float(self.p.setdefault("swirl_dir", r.choice([-1, 1])))
        self.k_in = float(self.p.setdefault("pull", round(r.uniform(330, 370))))
        self.k_t = float(self.p.setdefault("swirl", round(r.uniform(260, 320))))
        self.spawn_r = self.R * 0.62
        self.rd = self.RD0
        # FLUSH surges: first one early (first blood), then every ~5-6 s
        fl, t = [], 2.0
        while t < 40:
            fl.append(round(t, 2))
            t += r.uniform(3.8, 4.6)
        self.flushes = self.p.setdefault("flushes", fl)
        self._flush_i = 0
        self.flush_until = -1.0
        # bouncy guard rail (static segments; drawn by our renderer since 'bouncy' segs are skipped in TOP)
        nseg = 36
        rr = self.R + 10.0
        for i in range(nseg):
            a0, a1 = TAU * i / nseg, TAU * (i + 1) / nseg
            self.sim.static_segment((math.cos(a0) * rr, math.sin(a0) * rr), (math.cos(a1) * rr, math.sin(a1) * rr),
                                    "bouncy", radius=10)
        lim2 = (self.R + 70.0) ** 2
        self.sim.walkable = lambda x, y: self.rd * self.rd < x * x + y * y < lim2
        self.sim.statics.append({"type": "whirl_pool", "c": (0.0, 0.0), "r": self.R, "dir": self.spin})
        self.sim.zones["drain_r"] = self.rd
        self.sim.zones["flush"] = 0.0
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._tick)
        self.frame_top(self.R)

    def drain_r(self, t: float) -> float:
        u = min(1.0, max(0.0, (t - 2.0) / 19.0))
        return self.RD0 + (self.RD1 - self.RD0) * u ** 0.85

    def _tick(self, t: float) -> None:
        self.rd = self.drain_r(t)
        if self._flush_i < len(self.flushes) and t >= self.flushes[self._flush_i]:
            self._flush_i += 1
            self.flush_until = t + 1.25
            self.sim.event("escalation", [], None, mult=self.sim.speed_mult, banner="FLUSH!")
        self.sim.zones["drain_r"] = round(self.rd, 2)
        self.sim.zones["flush"] = round(max(0.0, self.flush_until - t), 3)

    def _step(self, dt: float) -> None:
        sim = self.sim
        t = sim.t
        if t < 0.0:
            return
        alive = sim.alive()
        if len(alive) <= 1:
            for c in alive:
                c.body.velocity = c.body.velocity * 0.85
            return
        prog = min(1.0, max(0.0, t / 22.0))
        surge = 1.0
        if t < self.flush_until:
            surge = 1.6 if self._flush_i <= 1 else 1.0 + 1.1 * min(1.0, max(0.2, sim.pressure))
        warm = min(1.0, 0.6 + 0.4 * t / 6.0)                     # gentle opening: the plughole is still tiny
        # pacing pressure: the current eases off when the field is ahead of the elimination schedule
        pace = min(1.4, max(0.45, 0.4 + 0.6 * sim.pressure))
        base = sim.speed_mult * (1.0 + 0.55 * prog) * pace * warm
        rd = self.rd
        for c in alive:
            x, y = c.pos
            d = math.hypot(x, y)
            if d < 1.0:
                continue
            ux, uy = -x / d, -y / d                       # inward
            tx, ty = -uy * self.spin, ux * self.spin      # tangential
            near = (rd + 90.0) / max(d, rd)
            a_in = self.k_in * base * surge * (0.32 + near ** 1.6)
            a_t = self.k_t * base * (0.45 + near)
            m = c.body.mass * (1.35 if c.extra is not None else 1.0)   # hollow crash dummies float to the plug
            c.body.apply_force_at_world_point(((ux * a_in + tx * a_t) * m, (uy * a_in + ty * a_t) * m),
                                              c.body.position)

    def safe_target(self, c):
        x, y = c.pos
        d = math.hypot(x, y) or 1.0
        rd = self.rd
        if c.extra is not None:
            # dummies mostly enjoy the ride; the clever ones only paddle away at the very lip
            if _hash01(c.key, 5) < 0.6 or d > rd + 60.0:
                return None
        if d < rd + 120.0:
            out = d + 230.0
            return (x / d * out, y / d * out)
        g = self.sim.goal.target(c)
        gd = math.hypot(*g)
        lim = rd + 170.0
        if gd < lim:
            if gd < 1.0:
                return (x / d * lim, y / d * lim)
            return (g[0] / gd * lim, g[1] / gd * lim)
        return None

    def progress(self, c) -> float:
        # the farther from the plughole, the safer; crash dummies never take a tiebreak (they can't win the show)
        return math.hypot(*c.pos) - (1000.0 if c.extra is not None else 0.0)


# ============================================================================================== 4. SPOTLIGHT PANIC
@register("spotlight_panic", TOP, "Spotlight Panic", "rotating laser beams on a dim stage",
          quips=("Stay out of the light, it's very rude!", "Lasers on! Tan lines guaranteed."),
          goals=("last_one_standing", "survive_timer", "hold_a_zone"),
          hazards=(), twists=("reversed_controls", "slippery_floor", "shrinking_arena"))
class SpotlightPanic(V6Top):
    """Dim round stage with 2-3 rotating red laser wedges fired from a centre turret (+ a sweeping chord beam after
    SPEED UP in some seeds). Staying inside a beam for > ZAP_S is a ZAP elimination. Edge falls still exist."""

    TURRET_R = 30.0
    no_quake = True          # the generic outward quake emptied the frictionless stage; the beams power-on opens instead

    def build(self):
        r = self.sim.rng
        self.R = float(self.p.setdefault("radius", round(r.uniform(415, 440))))
        self.nb = int(self.p.setdefault("beams", r.choice([2, 3, 3])))
        self.hw = math.radians(float(self.p.setdefault("beam_deg", 20.0 if self.nb == 3 else 22.0)) / 2.0)
        self.omega = float(self.p.setdefault("beam_w", round(r.uniform(0.52, 0.62), 3))) * r.choice([-1, 1])
        self.ang = float(self.p.setdefault("beam_a0", round(r.uniform(0, TAU), 3)))
        self.chord = bool(self.p.setdefault("chord", r.random() < 0.6))
        self.chord_phi = float(self.p.setdefault("chord_phi", round(r.uniform(0, math.pi), 3)))
        self.zap_s = float(self.p.setdefault("zap_s", 0.5))
        self.on_t = 0.8
        self.spawn_r = self.R * 0.62
        self.sim.walkable = lambda x, y: x * x + y * y < self.R * self.R
        self.turret = kin_circle(self.sim, (0.0, 0.0), self.TURRET_R, "spot_turret", material="bumper")
        self.expo: dict[str, float] = {}
        self.zaps: list[tuple[float, float, float]] = []
        self.chord_off = None
        self.sim.statics.append({"type": "spot_stage", "c": (0.0, 0.0), "r": self.R, "nb": self.nb, "hw": self.hw})
        self.sim.hooks_step.append(self._step)
        self.sim.hooks_frame.append(self._tick)
        self._publish(-1.0)
        self.frame_top(self.R)

    # beam geometry ---------------------------------------------------------------------------------
    def beams(self) -> list[float]:
        return [self.ang + TAU * i / self.nb for i in range(self.nb)]

    def _w(self) -> float:
        return self.omega * min(1.45, self.sim.speed_mult)

    def _chord_state(self, t: float):
        """(phi, offset, half_width) of the sweeping chord beam, or None."""
        if not self.chord or t < 8.0:
            return None
        rk = self.R * _kall(self.sim)
        off = math.sin((t - 8.0) * 0.75) * rk * 0.78
        return (self.chord_phi + 0.12 * (t - 8.0), off, 22.0)

    def _in_beam(self, x: float, y: float, beams: list[float]) -> bool:
        d = math.hypot(x, y)
        if d < self.TURRET_R + 4:
            return False
        th = math.atan2(y, x)
        for b in beams:
            if abs(_wrap(th - b)) < self.hw:
                return True
        cs = self.chord_off
        if cs is not None:
            phi, off, hwid = cs
            if abs(x * math.cos(phi) + y * math.sin(phi) - off) < hwid:
                return True
        return False

    def _step(self, dt: float) -> None:
        self.ang = (self.ang + self._w() * dt) % TAU
        self.turret.body.angular_velocity = self._w()
        self.turret.body.angle = self.ang

    def _tick(self, t: float) -> None:
        sim = self.sim
        self.chord_off = self._chord_state(t)
        live = t >= self.on_t
        alive = sim.alive()
        hot = []
        if live and len(alive) > 1:
            beams = self.beams()
            for c in alive:
                x, y = c.pos
                if self._in_beam(x, y, beams):
                    e = self.expo.get(c.key, 0.0) + 1.0 / 30.0
                    self.expo[c.key] = e
                    # pacing: a little more forgiving while the field is ahead of the elimination schedule
                    zap_s = self.zap_s * (1.35 - 0.35 * min(1.0, sim.pressure))
                    if c.extra is not None:
                        zap_s = self.zap_s * 0.8                        # foil-wrapped dummies fry fast
                    hot.append((round(x, 1), round(y, 1), round(min(1.0, e / zap_s), 2)))
                    if e >= zap_s:
                        sim.event("arena_hit", [c.key], c.pos, name="zapped")
                        sim.eliminate(c, "zapped")
                        self.zaps.append((round(x, 1), round(y, 1), t))
                        self.expo[c.key] = 0.0
                else:
                    self.expo[c.key] = max(0.0, self.expo.get(c.key, 0.0) - 2.0 / 30.0)
        self.zaps = [z for z in self.zaps if t - z[2] < 0.7]
        self._publish(t, hot)

    def _publish(self, t: float, hot=None) -> None:
        z = self.sim.zones
        z["beams"] = tuple(round(b, 4) for b in self.beams())
        z["beam_on"] = 1.0 if t >= self.on_t else max(0.0, min(1.0, (t + 1.0) / (self.on_t + 1.0))) * 0.4
        z["beam_hw"] = round(self.hw, 4)
        cs = self.chord_off
        z["chord"] = None if cs is None else (round(cs[0], 4), round(cs[1], 1), cs[2])
        z["spot_hot"] = tuple(hot or ())
        z["spot_zaps"] = tuple((x, y, round(t - zt, 3)) for x, y, zt in self.zaps)

    # AI --------------------------------------------------------------------------------------------
    def safe_target(self, c):
        sim = self.sim
        if sim.t < self.on_t - 0.4:
            return None
        x, y = c.pos
        d = math.hypot(x, y)
        th = math.atan2(y, x)
        w = self._w()
        dirn = 1.0 if w >= 0 else -1.0
        aw = max(0.05, abs(w))
        # delta = how far the nearest APPROACHING beam still has to travel to my angle
        delta = min(((th - b) * dirn) % TAU for b in self.beams())
        gap = TAU / self.nb
        inside = delta < self.hw or delta > TAU - self.hw
        dumb = c.extra is not None
        skill = _hash01(c.key, 7)
        rk = self.R * _kall(sim)
        cs = self.chord_off
        if cs is not None:
            phi, off, hwid = cs
            s = x * math.cos(phi) + y * math.sin(phi) - off
            if abs(s) < hwid + 70 and (not dumb or skill > 0.5):
                sgn = 1.0 if s >= 0 else -1.0
                return (x + math.cos(phi) * sgn * 140.0, y + math.sin(phi) * sgn * 140.0)
        if inside:
            if dumb and skill < 0.7:
                return None
            if delta < self.hw:
                fwd, back = self.hw - delta + 0.22, delta + self.hw + 0.22
            else:
                fwd, back = TAU - delta + self.hw + 0.22, self.hw - (TAU - delta) + 0.22
            if dumb or fwd < back * 0.55:
                a = th + dirn * fwd
            else:
                a = th - dirn * back
            rr = min(max(d, 0.25 * rk), 0.7 * rk)
            return (math.cos(a) * rr, math.sin(a) * rr)
        if dumb:
            return None                       # dummies never see the beam coming
        tth = (delta - self.hw) / aw
        react = 1.0 + 0.6 * c.behaviour.edge_awareness
        if tth > react:
            return None
        # drift with the dark pocket: mid-gap, a little ahead, at a comfortable radius
        a = th + dirn * (gap / 2.0 - delta) + dirn * aw * 0.35
        rr = min(max(d, 0.28 * rk), 0.62 * rk)
        return (math.cos(a) * rr, math.sin(a) * rr)

    def progress(self, c) -> float:
        return -math.hypot(*c.pos) - (1000.0 if c.extra is not None else 0.0)
