"""Visible hero powers (v5.1): every ball has ONE readable, cooldown-gated power that fires on screen with its own
popup ("TRICK SHOT!", "MAGNET!", ...), so viewers learn the cast by watching. Powers are modest nudges (impulses of
the same order as a normal AI shove) so no ball dominates; `tests/test_powers.py` keeps the win-share in check.

Deterministic: a dedicated RNG stream (never the Sim's main `rng`) decides the small random jitters, and every power
fires only from physical conditions (distance, speed, danger), so a (recipe, cast, seed) still replays identically.
Season 2+ rookies (see `src/characters/roster.py` ROOKIES) use the same power kinds.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.games.base import SIDE

JUMP_V = 440.0


@dataclass(frozen=True)
class Power:
    key: str            # power kind
    name: str           # shown on the roster card / commentary
    popup: str          # on-screen starburst word
    cooldown: float     # seconds between uses
    blurb: str          # one-line description for cards/commentary


POWERS: dict[str, Power] = {
    "bonk": Power("unmovable", "UNMOVABLE", "UNMOVABLE!", 6.0, "Rivals bounce off him like a wall"),
    "pip": Power("dodge", "DODGE HOP", "DODGE!", 5.0, "Hops clear of a big hit at the last second"),
    "boing": Power("super_bounce", "SUPER BOUNCE", "SUPER BOING!", 6.0, "One giant spring jump over trouble"),
    "sly": Power("trick_shot", "TRICK SHOT", "TRICK SHOT!", 7.0, "Lines up a rival and fires himself at them"),
    "grumble": Power("rage", "RAGE SHOVE", "RAGE!", 7.0, "Gets bumped, shoves back twice as hard"),
    "dash": Power("nitro", "NITRO", "NITRO!", 7.0, "A burst of pure speed on open track"),
    "magneto": Power("magnet", "MAGNET PULL", "MAGNET!", 8.0, "Yanks the nearest rival into range"),
    "floater": Power("updraft", "UPDRAFT", "UPDRAFT!", 6.0, "Catches a gust when about to fall"),
    "juggernaut": Power("stampede", "STAMPEDE", "STAMPEDE!", 8.0, "Charges through anything in front"),
    "glitch": Power("blink", "LAG BLINK", "ERROR!", 99.0, "Teleports a few pixels at random. Rude."),
    # ---- Season 2+ rookies
    "zap": Power("shockwave", "SHOCKWAVE", "ZAP!", 8.0, "An electric pulse that blasts everyone nearby"),
    "goo": Power("sticky", "STICKY SLIME", "SPLURT!", 8.0, "Slimes nearby rivals so they crawl"),
    "frosty": Power("freeze", "ICE SKATE", "FREEZE!", 7.0, "Turns the floor to ice under rivals"),
    "blaze": Power("nitro", "AFTERBURNER", "WHOOSH!", 6.5, "Rocket burst with a trail of fire"),
    "shadow": Power("dodge", "SHADOW STEP", "POOF!", 5.0, "Vanishes out of a collision"),
    "comet": Power("super_bounce", "METEOR DROP", "KABOOM!", 7.0, "Leaps high and slams down"),
}


def power_of(hero_key: str | None) -> Power | None:
    return POWERS.get(hero_key or "")


class PowerSystem:
    def __init__(self, sim) -> None:
        self.rng = random.Random((int(sim.seed) * 7919 + 1013) & 0xFFFFFFFF)
        self.ready_at: dict[str, float] = {}
        self.enabled = bool(sim.cfg.get("powers_enabled", True))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _rivals(sim, c, radius: float):
        x, y = c.pos
        out = []
        for o in sim.contestants:
            if o is c or not o.alive or o.finished:
                continue
            d = math.hypot(o.pos[0] - x, o.pos[1] - y) - o.radius - c.radius
            if d < radius:
                out.append((d, o))
        out.sort(key=lambda t: t[0])
        return out

    @staticmethod
    def _forward(sim, c) -> tuple[float, float]:
        if sim.mode == SIDE:
            dirx = sim.arena.drive_dir(c) if hasattr(sim.arena, "drive_dir") else (
                sim.goal.direction(c) if hasattr(sim.goal, "direction") else 1.0)
            return (1.0 if dirx >= 0 else -1.0), 0.0
        tx, ty = sim.goal.target(c)
        x, y = c.pos
        d = math.hypot(tx - x, ty - y) or 1.0
        return (tx - x) / d, (ty - y) / d

    @staticmethod
    def _imp(c, ix: float, iy: float) -> None:
        c.body.apply_impulse_at_world_point((ix, iy), c.body.position)

    def _fire(self, sim, c, p: Power, **data) -> None:
        self.ready_at[c.key] = sim.t + p.cooldown
        sim.trait(c, p.key, power=True, popup=p.popup, **data)

    # ------------------------------------------------------------------ main hook (once per frame per hero)
    def update(self, sim, c) -> None:
        if not self.enabled or c.hero is None or not c.alive or c.finished or sim.t < 1.0:
            return
        p = POWERS.get(c.hero.key)
        if p is None or p.key == "blink" or c.stun > 0:
            return
        if c.key not in self.ready_at:
            self.ready_at[c.key] = 1.0 + self.rng.random() * 2.0   # staggered first use
        if sim.t < self.ready_at[c.key]:
            return
        fn = getattr(self, f"_p_{p.key}", None)
        if fn is not None:
            fn(sim, c, p)

    # ------------------------------------------------------------------ power kinds
    def _p_unmovable(self, sim, c, p):
        near = [o for d, o in self._rivals(sim, c, 10.0)]
        if not near:
            return
        x, y = c.pos
        for o in near[:2]:
            dx, dy = o.pos[0] - x, o.pos[1] - y
            d = math.hypot(dx, dy) or 1.0
            k = 230.0 * o.body.mass
            self._imp(o, dx / d * k, dy / d * k - (40.0 * o.body.mass if sim.mode == SIDE else 0.0))
        c.body.velocity = (c.body.velocity.x * 0.9, c.body.velocity.y)
        self._fire(sim, c, p, victims=[o.key for o in near[:2]])

    def _p_dodge(self, sim, c, p):
        for d, o in self._rivals(sim, c, 70.0):
            rvx, rvy = o.body.velocity.x - c.body.velocity.x, o.body.velocity.y - c.body.velocity.y
            dx, dy = c.pos[0] - o.pos[0], c.pos[1] - o.pos[1]
            n = math.hypot(dx, dy) or 1.0
            closing = (rvx * dx + rvy * dy) / n
            if closing > 230.0 and o.body.mass >= c.body.mass:
                m = c.body.mass
                if sim.mode == SIDE:
                    if not c.grounded:
                        return
                    fx, _ = self._forward(sim, c)
                    self._imp(c, fx * 120.0 * m, -JUMP_V * 0.95 * m)
                else:
                    px, py = -dy / n, dx / n          # sidestep perpendicular to the incoming hit
                    s = 1.0 if self.rng.random() < 0.5 else -1.0
                    self._imp(c, px * s * 260.0 * m, py * s * 260.0 * m)
                self._fire(sim, c, p, dodged=o.key)
                return

    def _p_super_bounce(self, sim, c, p):
        m = c.body.mass
        if sim.mode == SIDE:
            if not c.grounded:
                return
            danger = sim.arena.danger(c, 110) if hasattr(sim.arena, "danger") else False
            crowd = len(self._rivals(sim, c, 40.0)) >= 2
            if danger or crowd:
                fx, _ = self._forward(sim, c)
                self._imp(c, fx * 160.0 * m, -JUMP_V * 1.45 * m)
                self._fire(sim, c, p)
        else:
            near = self._rivals(sim, c, 30.0)
            if near:
                x, y = c.pos
                for _, o in near[:3]:
                    dx, dy = o.pos[0] - x, o.pos[1] - y
                    d = math.hypot(dx, dy) or 1.0
                    self._imp(o, dx / d * 210.0 * o.body.mass, dy / d * 210.0 * o.body.mass)
                self._fire(sim, c, p)

    def _p_trick_shot(self, sim, c, p):
        fx, fy = self._forward(sim, c)
        best = None
        for d, o in self._rivals(sim, c, 170.0):
            if d < 12.0:
                continue
            dx, dy = o.pos[0] - c.pos[0], o.pos[1] - c.pos[1]
            n = math.hypot(dx, dy) or 1.0
            if sim.mode == SIDE and (dx * fx <= 0 or abs(dy) > 70):
                continue                                  # only rivals ahead, on roughly the same level
            score = (o.hero is not None) * 2 + (1 - d / 170.0)
            if best is None or score > best[0]:
                best = (score, o, dx / n, dy / n)
        if best is None:
            return
        _, o, ux, uy = best
        m = c.body.mass
        if sim.mode == SIDE:
            if not c.grounded:
                return
            self._imp(c, ux * 300.0 * m, min(-60.0, uy * 300.0) * m)
        else:
            self._imp(c, ux * 330.0 * m, uy * 330.0 * m)
        self._fire(sim, c, p, target=o.key)

    def _p_rage(self, sim, c, p):
        recent = [k for t, k in c.contacts if sim.t - t < 0.5]
        if not recent:
            return
        near = self._rivals(sim, c, 45.0)
        if not near:
            return
        _, o = near[0]
        dx, dy = o.pos[0] - c.pos[0], o.pos[1] - c.pos[1]
        d = math.hypot(dx, dy) or 1.0
        k = 300.0 * min(c.body.mass, 3.0 * o.body.mass)
        self._imp(o, dx / d * k, dy / d * k - (50.0 * o.body.mass if sim.mode == SIDE else 0.0))
        c.angry_until = sim.t + 1.2
        self._fire(sim, c, p, target=o.key)

    def _p_nitro(self, sim, c, p):
        fx, fy = self._forward(sim, c)
        m = c.body.mass
        if sim.mode == SIDE:
            if not c.grounded or (hasattr(sim.arena, "danger") and sim.arena.danger(c, 140)):
                return
            if c.body.velocity.x * fx > c.max_speed * 0.9:
                return
            self._imp(c, fx * 260.0 * m, -20.0 * m)
        else:
            edge = sim.arena.edge_vector(*c.pos)[0] if hasattr(sim.arena, "edge_vector") else 999.0
            if edge < 140:
                return
            self._imp(c, fx * 280.0 * m, fy * 280.0 * m)
        self._fire(sim, c, p)

    def _p_magnet(self, sim, c, p):
        near = [(d, o) for d, o in self._rivals(sim, c, 210.0) if d > 25.0]
        if not near:
            return
        _, o = near[0]
        dx, dy = c.pos[0] - o.pos[0], c.pos[1] - o.pos[1]
        d = math.hypot(dx, dy) or 1.0
        k = 190.0 * o.body.mass
        self._imp(o, dx / d * k, (dy / d * k) if sim.mode != SIDE else min(0.0, dy / d * k))
        self._fire(sim, c, p, target=o.key)

    def _p_updraft(self, sim, c, p):
        m = c.body.mass
        if sim.mode == SIDE:
            falling = not c.grounded and c.body.velocity.y > 120.0
            danger = hasattr(sim.arena, "danger") and sim.arena.danger(c, 90)
            if falling and (danger or c.pos[1] > sim.kill_y - 500):
                fx, _ = self._forward(sim, c)
                self._imp(c, fx * 90.0 * m, -(c.body.velocity.y * 0.85 + 220.0) * m)
                self._fire(sim, c, p)
        else:
            if not hasattr(sim.arena, "edge_vector"):
                return
            edge, ux, uy = sim.arena.edge_vector(*c.pos)
            if edge < 45.0:
                self._imp(c, -ux * 300.0 * m, -uy * 300.0 * m)
                self._fire(sim, c, p)

    def _p_stampede(self, sim, c, p):
        fx, fy = self._forward(sim, c)
        speed = math.hypot(c.body.velocity.x, c.body.velocity.y)
        if speed < c.max_speed * 0.45:
            return
        ahead = [o for d, o in self._rivals(sim, c, 70.0)
                 if (o.pos[0] - c.pos[0]) * fx + (o.pos[1] - c.pos[1]) * fy > 0]
        if not ahead:
            return
        m = c.body.mass
        self._imp(c, fx * 160.0 * m, fy * 160.0 * m)
        for o in ahead[:2]:
            self._imp(o, fx * 200.0 * o.body.mass, fy * 200.0 * o.body.mass - (40.0 * o.body.mass if sim.mode == SIDE else 0))
        self._fire(sim, c, p, victims=[o.key for o in ahead[:2]])

    def _p_shockwave(self, sim, c, p):
        near = self._rivals(sim, c, 110.0)
        if len(near) < 2:
            return
        x, y = c.pos
        for d, o in near[:4]:
            dx, dy = o.pos[0] - x, o.pos[1] - y
            n = math.hypot(dx, dy) or 1.0
            k = 220.0 * o.body.mass * (1.0 - min(1.0, d / 130.0) * 0.5)
            self._imp(o, dx / n * k, dy / n * k - (60.0 * o.body.mass if sim.mode == SIDE else 0))
        self._fire(sim, c, p, victims=[o.key for _, o in near[:4]])

    def _p_sticky(self, sim, c, p):
        near = self._rivals(sim, c, 90.0)
        if len(near) < 1:
            return
        for _, o in near[:3]:
            o.body.velocity = (o.body.velocity.x * 0.45, o.body.velocity.y * (0.45 if sim.mode != SIDE else 1.0))
        self._fire(sim, c, p, victims=[o.key for _, o in near[:3]])

    def _p_freeze(self, sim, c, p):
        near = self._rivals(sim, c, 100.0)
        if len(near) < 1:
            return
        for _, o in near[:3]:
            o.body.angular_velocity *= 0.2           # spinning wheels on ice: they lose their grip for a moment
            o.panic_until = max(o.panic_until, sim.t + 0.45)
        self._fire(sim, c, p, victims=[o.key for _, o in near[:3]])
