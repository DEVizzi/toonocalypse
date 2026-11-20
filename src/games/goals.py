"""Goals (§11.2). Each goal decides the leader, the winner, a forced resolution (tie-break) and TOP_DOWN targets."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from src.config import TIMELINE
from src.games.base import SIDE

if TYPE_CHECKING:
    from src.physics.engine import Contestant, Sim


class Goal:
    key = ""

    def __init__(self, sim: "Sim") -> None:
        self.sim = sim
        self.qualified = False

    # ---- ranking helpers
    def tiebreak(self, c: "Contestant") -> float:
        """Higher is better: distance along the course (SIDE) or closeness to the centre (TOP)."""
        if self.sim.mode == SIDE:
            return c.pos[0]
        cx, cy = self.sim.arena.center
        return -math.hypot(c.pos[0] - cx, c.pos[1] - cy)

    def score(self, c: "Contestant") -> float:
        return self.tiebreak(c)

    def ranking(self) -> list[str]:
        alive = sorted(self.sim.alive(), key=self.score, reverse=True)
        dead = sorted((c for c in self.sim.contestants if not c.alive), key=lambda c: c.eliminated_at or 0, reverse=True)
        return [c.key for c in alive] + [c.key for c in dead]

    def leader(self) -> str | None:
        heroes = [c for c in self.sim.alive() if c.is_hero] or self.sim.alive()
        return max(heroes, key=self.score).key if heroes else None

    def declare(self, key: str, t: float, how: str) -> None:
        if self.sim.winner:
            return
        self.sim.winner = key
        self.sim.resolved_at = t
        self.sim.event("win", [key], self.sim.by_key[key].pos, how=how, podium=self.ranking()[:3])

    def force_resolve(self, t: float, hard: bool = False) -> None:
        alive = self.sim.alive()
        if alive:
            self.declare(max(alive, key=self.score).key, t, "tiebreak" if hard else "forced")

    def target(self, c: "Contestant") -> tuple[float, float]:
        """Personal anchor around the centre (so the crowd doesn't pile onto one spot); aggressive ones go central."""
        cx, cy = self.sim.arena.center
        h = (sum(map(ord, c.key)) * 2654435761) % 1000 / 1000
        a = h * 2 * math.pi + self.sim.t * (0.45 + 0.4 * h) * (1 if h > 0.5 else -1)   # keep the crowd moving
        base = getattr(self.sim.arena, "spawn_r", 250)
        # extras mill about near the rim (fodder); heroes fight for the middle
        rad = base * (0.95 if c.extra is not None else 0.5 * (1 - 0.6 * c.behaviour.aggression))
        return cx + math.cos(a) * rad, cy + math.sin(a) * rad

    def update(self, t: float) -> None:
        r = self.sim.recipe
        if r.two_stage and not self.qualified and t >= TIMELINE.two_stage_qualifier_s:
            self.qualified = True
            keep = set(self.ranking()[: TIMELINE.two_stage_survivors])
            for c in self.sim.alive():
                if c.key not in keep:
                    self.sim.eliminate(c, "qualifier")
            self.sim.event("stage_final", [], None, survivors=sorted(keep))
        self.check(t)
        alive = self.sim.alive()
        if len(alive) == 1 and not self.sim.winner:
            self.declare(alive[0].key, t, "last_standing")
        elif not alive and not self.sim.winner:
            last = max(self.sim.contestants, key=lambda c: c.eliminated_at or 0)
            self.declare(last.key, t, "last_eliminated")

    def check(self, t: float) -> None:
        pass

    def zone_state(self) -> dict[str, Any]:
        return {}


class ReachFinish(Goal):
    key = "reach_finish"

    def check(self, t: float) -> None:
        fx = self.sim.finish_x
        for c in self.sim.alive():
            if not c.finished and fx is not None and c.pos[0] >= fx:
                c.finished = True
                self.sim.event("finish", [c.key], c.pos)
                if not self.sim.winner:
                    self.declare(c.key, t, "finish")


class LastOneStanding(Goal):
    key = "last_one_standing"


class SurviveTimer(Goal):
    key = "survive_timer"

    def __init__(self, sim):
        super().__init__(sim)
        self.limit = sim.recipe.params.setdefault("timer", round(sim.rng.uniform(28, 33), 1))

    def check(self, t: float) -> None:
        if t >= self.limit:
            self.force_resolve(t)

    def zone_state(self):
        return {"timer": max(0.0, self.limit - self.sim.t)}


class CollectItems(Goal):
    key = "collect_items"

    def __init__(self, sim):
        super().__init__(sim)
        self.items: list[list[float]] = []
        self.limit = sim.recipe.params.setdefault("timer", round(sim.rng.uniform(28, 32), 1))
        self.next_spawn = 0.0

    def _spawn(self, near: tuple[float, float] | None = None) -> None:
        r = self.sim.rng
        if self.sim.mode == SIDE:
            base = max((c.pos[0] for c in self.sim.alive()), default=600.0)
            x = (near[0] if near else base + r.uniform(150, 700))
            y = self.sim.arena.ground_y_at(x) - r.uniform(40, 140)
        else:
            for _ in range(20):
                a, d = r.uniform(0, 2 * math.pi), r.uniform(0, 330)
                x, y = math.cos(a) * d, math.sin(a) * d
                if self.sim.walkable is None or self.sim.walkable(x, y):
                    break
            if near:
                x, y = near[0] + r.uniform(-40, 40), near[1] + r.uniform(-40, 40)
        self.items.append([x, y])

    def check(self, t: float) -> None:
        if t >= self.next_spawn and len(self.items) < 8:
            self._spawn()
            self.next_spawn = t + 1.1 / self.sim.speed_mult
        for c in self.sim.alive():
            x, y = c.pos
            for it in list(self.items):
                if math.hypot(it[0] - x, it[1] - y) < c.radius + 18:
                    self.items.remove(it)
                    c.score += 1
                    self.sim.event("collect", [c.key], c.pos, total=c.score)
        for c in self.sim.contestants:
            if not c.alive and c.score > 0 and c.elim_pos and not getattr(c, "_dropped", False):
                c._dropped = True  # type: ignore[attr-defined]
                drop = int(c.score // 2)
                c.score -= drop
                for _ in range(drop):
                    self._spawn(near=c.elim_pos)
        if t >= self.limit:
            self.force_resolve(t)

    def score(self, c):
        return c.score * 10000 + self.tiebreak(c)

    def target(self, c):
        if not self.items:
            return super().target(c)
        x, y = c.pos
        return min(((i[0], i[1]) for i in self.items), key=lambda p: math.hypot(p[0] - x, p[1] - y))

    def direction(self, c):
        return 1.0

    def zone_state(self):
        return {"items": [tuple(i) for i in self.items], "scores": {c.key: c.score for c in self.sim.contestants if c.score}}


class HoldAZone(Goal):
    key = "hold_a_zone"

    def __init__(self, sim):
        super().__init__(sim)
        self.r = 95.0
        self.phase = sim.rng.uniform(0, 6.28)
        self.need = 10.0

    def center(self) -> tuple[float, float]:
        t = self.sim.t
        return math.cos(t * 0.25 + self.phase) * 170, math.sin(t * 0.33 + self.phase) * 150

    def check(self, t: float) -> None:
        zx, zy = self.center()
        for c in self.sim.alive():
            if math.hypot(c.pos[0] - zx, c.pos[1] - zy) < self.r:
                c.score += 1 / 30
                if c.score >= self.need:
                    self.declare(c.key, t, "zone")
                    return

    def score(self, c):
        return c.score * 10000 + self.tiebreak(c)

    def target(self, c):
        return self.center()

    def zone_state(self):
        return {"zone": (*self.center(), self.r), "scores": {c.key: round(c.score, 2) for c in self.sim.contestants if c.score}}


class PushOthersOut(Goal):
    key = "push_others_out"

    def check(self, t: float) -> None:
        for e in self.sim.events:
            if e.kind == "elimination" and len(e.actors) > 1 and not e.data.get("_counted"):
                e.data["_counted"] = True
                self.sim.by_key[e.actors[1]].score += 1

    def score(self, c):
        return c.score * 10000 + self.tiebreak(c)

    def target(self, c):
        # chase the nearest rival toward the edge
        x, y = c.pos
        others = [o for o in self.sim.alive() if o is not c]
        if not others or c.behaviour.aggression < 0.3:
            return super().target(c)
        o = min(others, key=lambda o: math.hypot(o.pos[0] - x, o.pos[1] - y))
        return o.pos

    def zone_state(self):
        return {"scores": {c.key: c.score for c in self.sim.contestants if c.score}}


class HotPotatoBomb(Goal):
    key = "hot_potato_bomb"

    def __init__(self, sim):
        super().__init__(sim)
        self.holder: str | None = None
        self.next_pop = 8.0
        self.pass_cd = 0.0

    def _give(self, key: str | None) -> None:
        self.holder = key

    def check(self, t: float) -> None:
        alive = self.sim.alive()
        if self.holder is None or not self.sim.by_key[self.holder].alive:
            if alive:
                self._give(self.sim.rng.choice(alive).key)
        self.pass_cd -= 1 / 30
        h = self.sim.by_key.get(self.holder) if self.holder else None
        if h and self.pass_cd <= 0:
            for tt, k in reversed(h.contacts):
                if t - tt < 0.1 and self.sim.by_key[k].alive:
                    self._give(k)
                    self.pass_cd = 0.4
                    self.sim.event("bomb_pass", [k, h.key], self.sim.by_key[k].pos)
                    break
        if t >= self.next_pop and h:
            self.sim.event("bomb_pop", [h.key], h.pos)
            self.sim.eliminate(h, "bomb")
            self.holder = None
            self.next_pop = t + (6.0 if self.sim.speed_mult > 1.5 else 8.0)

    def score(self, c):
        if self.holder and self.holder in self.sim.by_key:
            hx, hy = self.sim.by_key[self.holder].pos
            return math.hypot(c.pos[0] - hx, c.pos[1] - hy) - (1e6 if c.key == self.holder else 0)
        return self.tiebreak(c)

    def target(self, c):
        x, y = c.pos
        if c.key == self.holder:
            others = [o for o in self.sim.alive() if o is not c]
            if others:
                return min(others, key=lambda o: math.hypot(o.pos[0] - x, o.pos[1] - y)).pos
        elif self.holder:
            hx, hy = self.sim.by_key[self.holder].pos
            return x + (x - hx), y + (y - hy)
        return super().target(c)

    def zone_state(self):
        return {"bomb": self.holder, "bomb_timer": max(0.0, self.next_pop - self.sim.t)}


GOAL_CLASSES = {g.key: g for g in (ReachFinish, LastOneStanding, SurviveTimer, CollectItems, HoldAZone, PushOthersOut,
                                    HotPotatoBomb)}


def make(sim: "Sim") -> Goal:
    return GOAL_CLASSES[sim.recipe.goal](sim)
