"""Physics engine (§10): pymunk world, contestants, force-based locomotion, stun, anti-stuck, eliminations, escalation,
and the per-frame trace. Arenas, goals, hazards and twists plug in through the small `Sim` API below.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pymunk

from src.characters.roster import EXPRESSIONS, Extra, Hero
from src.config import FPS, TIMELINE, settings
from src.games.base import SIDE, TOP, Recipe
from src.physics import trace as T

CT_BODY, CT_GROUND, CT_HAZARD, CT_BOUNCY, CT_ITEM = 1, 2, 3, 4, 5
EXPR = {e: i for i, e in enumerate(EXPRESSIONS)}
MATERIALS = {  # friction, elasticity
    "ground": (0.9, 0.1), "wall": (0.6, 0.2), "ice": (0.01, 0.05), "mud": (1.0, 0.0), "bouncy": (0.5, 1.25),
    "conveyor": (1.0, 0.05), "plank": (0.9, 0.1), "bumper": (0.3, 1.1), "prop": (0.7, 0.3),
}


@dataclass
class Contestant:
    key: str
    hero: Hero | None
    extra: Extra | None
    body: pymunk.Body
    shape: pymunk.Shape
    radius: float
    max_speed: float
    behaviour: Any
    alive: bool = True
    stun: float = 0.0
    last_stun_end: float = -9.0
    angry_until: float = -9.0
    happy_until: float = -9.0
    grounded: bool = False
    air_time: float = 0.0
    anchor_pos: tuple[float, float] = (0.0, 0.0)
    anchor_t: float = 0.0
    jump_cd: float = 0.0
    shove_cd: float = 0.0
    eliminated_at: float | None = None
    elim_pos: tuple[float, float] | None = None
    last_toucher: str | None = None
    last_touch_t: float = -9.0
    score: float = 0.0          # goal-specific points (items, zone time, KOs)
    finished: bool = False
    squash: float = 0.0
    fall_t: float = -1.0        # top-down visual fall timer
    trait_cd: float = 0.0
    contacts: list[tuple[float, str]] = field(default_factory=list)
    fan_favorite: bool = False
    drive: tuple[float, float] = (0.0, 0.0)   # force re-applied on every substep (pymunk resets forces per step)
    panic_until: float = -9.0   # extras freeze in cartoon panic at drops and hazards

    @property
    def is_hero(self) -> bool:
        return self.hero is not None

    @property
    def name(self) -> str:
        return self.hero.name if self.hero else f"Number {self.extra.number}"  # type: ignore[union-attr]

    @property
    def pos(self) -> tuple[float, float]:
        return float(self.body.position.x), float(self.body.position.y)


@dataclass
class Prop:
    body: pymunk.Body
    shapes: list[dict]          # render description in body-local coordinates
    style: str                  # render style key (hazard | platform | seesaw | disc | bumper | ...)
    alive: bool = True


class Sim:
    """One candidate simulation. Deterministic for a given (recipe, cast, seed)."""

    def __init__(self, recipe: Recipe, heroes: list[Hero], extras: list[Extra], seed: int,
                 fan_favorite: str | None = None) -> None:
        from src.games import arenas, goals, hazards, twists

        self.cfg = settings()["physics"]
        self.recipe = recipe
        self.mode = recipe.mode
        self.rng = random.Random(seed)
        self.seed = seed
        self.space = pymunk.Space()
        self.space.iterations = 15
        self.gravity_scale = 1.0
        self.friction_scale = 1.0
        self.reversed_until = -1.0
        self._apply_gravity()
        if self.mode == TOP:
            self.space.damping = self.cfg["topdown_damping"]
        self.t = 0.0                      # gameplay time
        self.dt = 1.0 / (FPS * self.cfg["substeps"])
        self.contestants: list[Contestant] = []
        self.by_key: dict[str, Contestant] = {}
        self.props: list[Prop] = []
        self.statics: list[dict] = []     # render description of static geometry
        self.zones: dict[str, Any] = {}   # per-frame dynamic zone state
        self.events: list[T.Event] = []
        self.hooks_step: list[Callable[[float], None]] = []
        self.hooks_frame: list[Callable[[float], None]] = []
        self.surface_mods: list[Callable[[Contestant], float]] = []   # movement multipliers (mud, boost...)
        self.winner: str | None = None
        self.resolved_at: float | None = None
        self.leader: str | None = None
        self.speed_mult = 1.0
        self.escalation_idx = 0
        self.kill_y = 1e9
        self.finish_x: float | None = None
        self.walkable: Callable[[float, float], bool] | None = None
        self.bounds = (-600.0, -1400.0, 6000.0, 700.0)   # x0, y0, x1, y1 for the camera
        self.view_w = 1080.0 / settings()["render"]["side_zoom"]   # world px across the screen in SIDE_VIEW
        self.chase_x = -500.0           # SIDE: the collapsing castle floor chasing from the left
        self.edge_k = 1.0               # TOP: escalation shrinks every arena's walkable edge (§4 "arena shrinks")
        self.pressure = 1.0             # Lord Tuno's pacing pressure: >1 when more contestants remain than the schedule
        self.cam_x = 0.0
        self.fan_favorite = fan_favorite
        self.arena = arenas.build(self)
        self._spawn(heroes, extras)
        self.goal = goals.make(self)
        self.hazards = [hazards.make(h, self) for h in recipe.hazards]
        self.twist = twists.make(recipe.twist, self) if recipe.twist else None
        self._collisions()
        self.trace = T.Trace(FPS, self.mode, [c.key for c in self.contestants])
        self.trace.meta.update(recipe=recipe.to_dict(), statics=self.statics,
                               props=[{"shapes": p.shapes, "style": p.style} for p in self.props],
                               bounds=self.bounds, finish_x=self.finish_x, kill_y=self.kill_y,
                               heroes=[c.key for c in self.contestants if c.is_hero],
                               extras={c.key: {"number": c.extra.number, "colour": c.extra.colour, "cult": c.extra.cult}
                                       for c in self.contestants if c.extra})

    # ------------------------------------------------------------------ world API (used by arenas/hazards)
    def _apply_gravity(self) -> None:
        g = self.cfg["gravity_side"] * self.gravity_scale if self.mode == SIDE else 0.0
        self.space.gravity = (0, g)

    def set_gravity_scale(self, k: float) -> None:
        self.gravity_scale = k
        self._apply_gravity()

    def static_segment(self, a, b, material: str = "ground", radius: float | None = None, **kw) -> pymunk.Segment:
        r = max(radius or self.cfg["segment_radius"], self.cfg["segment_radius"])
        s = pymunk.Segment(self.space.static_body, a, b, r)
        self._material(s, material, **kw)
        self.space.add(s)
        self.statics.append({"type": "seg", "a": tuple(a), "b": tuple(b), "r": r, "mat": material, "id": id(s)})
        return s

    def static_poly(self, verts, material: str = "ground", **kw) -> pymunk.Poly:
        s = pymunk.Poly(self.space.static_body, verts, radius=self.cfg["bevel_radius"])
        self._material(s, material, **kw)
        self.space.add(s)
        self.statics.append({"type": "poly", "verts": [tuple(v) for v in verts], "mat": material, "id": id(s)})
        return s

    def static_circle(self, c, r: float, material: str = "bumper") -> pymunk.Circle:
        s = pymunk.Circle(self.space.static_body, r, c)
        self._material(s, material)
        self.space.add(s)
        self.statics.append({"type": "circle", "c": tuple(c), "r": r, "mat": material, "id": id(s)})
        return s

    def remove_static(self, shape: pymunk.Shape) -> None:
        if shape in self.space.shapes:
            self.space.remove(shape)
        self.zones.setdefault("removed_statics", [])
        self.zones["removed_statics"] = self.zones["removed_statics"] + [id(shape)]

    def _material(self, s: pymunk.Shape, material: str, surface_velocity=None, hazard: bool = False) -> None:
        f, e = MATERIALS[material]
        s.friction, s.elasticity = f, e
        s.collision_type = CT_BOUNCY if material in ("bouncy", "bumper") else (CT_HAZARD if hazard else CT_GROUND)
        s.material = material  # type: ignore[attr-defined]
        if surface_velocity is not None:
            s.surface_velocity = surface_velocity

    def add_prop(self, body: pymunk.Body, shapes: list[pymunk.Shape], style: str, material: str = "prop",
                 hazard: bool = False) -> Prop:
        desc = []
        for s in shapes:
            self._material(s, material, hazard=hazard)
            if isinstance(s, pymunk.Circle):
                desc.append({"type": "circle", "c": tuple(s.offset), "r": s.radius})
            elif isinstance(s, pymunk.Segment):
                desc.append({"type": "seg", "a": tuple(s.a), "b": tuple(s.b), "r": s.radius})
            else:
                desc.append({"type": "poly", "verts": [tuple(v) for v in s.get_vertices()]})
        if body.body_type != pymunk.Body.STATIC:
            self.space.add(body)
        self.space.add(*shapes)
        p = Prop(body, desc, style)
        self.props.append(p)
        return p

    def remove_prop(self, p: Prop) -> None:
        if p.alive:
            for s in list(p.body.shapes):
                self.space.remove(s)
            if p.body in self.space.bodies:
                self.space.remove(p.body)
            p.alive = False

    def event(self, kind: str, actors: list[str], pos=None, **data) -> None:
        self.events.append(T.Event(round(self.t, 3), kind, actors, data, pos))

    def alive(self, heroes_only: bool = False) -> list[Contestant]:
        return [c for c in self.contestants if c.alive and (c.is_hero or not heroes_only)]

    # ------------------------------------------------------------------ contestants
    def _spawn(self, heroes: list[Hero], extras: list[Extra]) -> None:
        spawn = self.arena.spawn_points(len(heroes) + len(extras), self.rng)
        order = [("h", h) for h in heroes] + [("e", e) for e in extras]
        self.rng.shuffle(order)
        for (kind, who), p in zip(order, spawn):
            if kind == "h":
                c = self._make_hero(who, p)
            else:
                c = self._make_extra(who, p)
            self.contestants.append(c)
            self.by_key[c.key] = c
            if self.fan_favorite and c.key == self.fan_favorite:
                c.fan_favorite = True

    def _velocity_func(self, c_ref: list[Contestant]) -> Callable:
        clamp = self.cfg["velocity_clamp"]

        def f(body, gravity, damping, dt):
            c = c_ref[0]
            g = gravity
            if c.hero is not None and c.hero.gravity_mult != 1.0:
                g = (gravity[0] * c.hero.gravity_mult, gravity[1] * c.hero.gravity_mult)
            pymunk.Body.update_velocity(body, g, damping, dt)
            v = body.velocity
            sp = v.length
            if sp > clamp:
                body.velocity = v * (clamp / sp)
        return f

    def _make_body(self, mass: float, shape_fn, pos, angle_locked: bool):
        moment = pymunk.moment_for_circle(mass, 0, 20) * (40.0 if angle_locked else 1.0)
        body = pymunk.Body(mass, moment)
        body.position = pos
        shape = shape_fn(body)
        self.space.add(body, shape)
        return body, shape

    def _make_hero(self, h: Hero, pos) -> Contestant:
        w, hh = h.size

        def shape_fn(body):
            if h.shape in ("circle", "cloud"):
                return pymunk.Circle(body, w)
            if h.shape == "oval":   # approximate the oval with a beveled octagon
                pts = [(math.cos(a) * (w - 4), math.sin(a) * (hh - 4)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
                return pymunk.Poly(body, pts, radius=4)
            if h.shape == "square":
                return pymunk.Poly.create_box(body, (w - 16, hh - 16), radius=8)
            n = 6 if h.shape == "hexagon" else 8
            pts = [(math.cos(2 * math.pi * i / n + math.pi / n) * (w - 8), math.sin(2 * math.pi * i / n + math.pi / n) * (w - 8))
                   for i in range(n)]
            return pymunk.Poly(body, pts, radius=8)

        mass = h.mass if not h.mass_range else self.rng.uniform(*h.mass_range)
        body, shape = self._make_body(mass, shape_fn, pos, angle_locked=True)
        shape.friction, shape.elasticity = h.friction, h.elasticity
        shape.collision_type = CT_BODY
        c = Contestant(h.key, h, None, body, shape, h.radius, self.eff_speed(h.max_speed), h.behaviour, anchor_pos=pos)
        body.velocity_func = self._velocity_func([c])
        shape.contestant = c  # type: ignore[attr-defined]
        return c

    def _make_extra(self, e: Extra, pos) -> Contestant:
        body, shape = self._make_body(e.mass, lambda b: pymunk.Circle(b, e.radius), pos, angle_locked=True)
        shape.friction, shape.elasticity = e.friction, e.elasticity
        shape.collision_type = CT_BODY
        c = Contestant(e.key, None, e, body, shape, e.radius, self.eff_speed(e.max_speed), e.behaviour, anchor_pos=pos)
        body.velocity_func = self._velocity_func([c])
        shape.contestant = c  # type: ignore[attr-defined]
        return c

    def eff_speed(self, stat: float) -> float:
        c, k = self.cfg["speed_centre"], self.cfg["speed_spread"]
        return c + (stat - c) * k

    def eliminate(self, c: Contestant, cause: str, by: str | None = None) -> None:
        if not c.alive or self.winner:
            return
        c.alive = False
        c.eliminated_at = self.t
        c.elim_pos = c.pos
        if by is None and c.last_toucher and self.t - c.last_touch_t < 2.0:
            by = c.last_toucher
        if self.mode == TOP:
            c.fall_t = 0.0
        self.space.remove(c.body, c.shape)
        self.event("elimination", [c.key] + ([by] if by else []), c.pos, cause=cause, hero=c.is_hero,
                   by_hero=bool(by and self.by_key[by].is_hero))

    # ------------------------------------------------------------------ collisions
    def _collisions(self) -> None:
        def post_body_body(arb: pymunk.Arbiter, space, data):
            a, b = arb.shapes
            ca, cb = getattr(a, "contestant", None), getattr(b, "contestant", None)
            if not ca or not cb:
                return
            imp = arb.total_impulse.length
            for x, y in ((ca, cb), (cb, ca)):
                x.last_toucher, x.last_touch_t = y.key, self.t
                x.contacts.append((self.t, y.key))
            self._impact(ca, imp, cb)
            self._impact(cb, imp, ca)
            if (ca.is_hero or cb.is_hero) and imp > 300:
                self.event("impact", [ca.key, cb.key], ((ca.pos[0] + cb.pos[0]) / 2, (ca.pos[1] + cb.pos[1]) / 2),
                           impulse=round(imp), hero_pair=ca.is_hero and cb.is_hero)
                for x, y in ((ca, cb), (cb, ca)):
                    if x.is_hero and y.is_hero:
                        x.angry_until = self.t + 1.5

        def post_body_world(arb: pymunk.Arbiter, space, data):
            a, b = arb.shapes
            c = getattr(a, "contestant", None) or getattr(b, "contestant", None)
            if c:
                imp = arb.total_impulse.length
                self._impact(c, imp, None)
                if c.hero and c.hero.trait == "no_brakes" and imp > 260 * c.body.mass and abs(arb.normal.x) > 0.7:
                    self.trait(c, "wall_slam")

        def begin_bouncy(arb: pymunk.Arbiter, space, data):
            pass

        self.space.on_collision(CT_BODY, CT_BODY, post_solve=post_body_body)
        self.space.on_collision(CT_BODY, CT_GROUND, post_solve=post_body_world)
        self.space.on_collision(CT_BODY, CT_HAZARD, post_solve=post_body_world)
        self.space.on_collision(CT_BODY, CT_BOUNCY, post_solve=post_body_world)

    def _impact(self, c: Contestant, impulse: float, other: Contestant | None) -> None:
        per_mass = impulse / max(0.5, c.body.mass)
        if per_mass > 120:
            c.squash = max(c.squash, min(1.0, per_mass / 400))
        thr = self.cfg["stun_threshold"]
        if per_mass > thr and c.stun <= 0:
            mult = c.hero.stun_mult if c.hero else 1.0
            c.stun = self.cfg["stun_s"] * mult
        if c.hero and c.hero.trait == "glitch" and per_mass > thr * 0.8:
            c.trait_cd = 0.0  # strong impact triggers a glitch next frame

    def trait(self, c: Contestant, name: str, **data) -> None:
        last = [e for e in self.events if e.kind == "trait" and e.actors[0] == c.key and e.data.get("name") == name]
        if last and self.t - last[-1].t < 2.5:
            return
        self.event("trait", [c.key], c.pos, name=name, **data)

    # ------------------------------------------------------------------ main loop
    def run(self, max_gameplay: float | None = None) -> T.Trace:
        from src.physics import ai

        hard = max_gameplay or TIMELINE.hard_stop_s
        start = time.time()
        brain = ai.Brain(self)
        pre = int(round(TIMELINE.cold_open_s * FPS))       # cold open: contestants bouncing at the closed gate
        self.trace.meta["preroll_frames"] = pre
        for i in range(pre):
            self.t = (i - pre) / FPS
            if self.mode == SIDE:
                brain.think(self)
            else:
                for c in self.contestants:
                    if self.rng.random() < 0.08:
                        c.squash = 0.6
            for _ in range(self.cfg["substeps"]):
                self._apply_drives()
                self.space.step(self.dt)
            self._record()
        self.arena.open_gate()
        self.event("gate", [], None)
        frame = 0
        while True:
            self.t = frame / FPS
            self._escalate()
            brain.think(self)
            for h in self.hooks_frame:
                h(self.t)
            for _ in range(self.cfg["substeps"]):
                self._apply_drives()
                for h in self.hooks_step:
                    h(self.dt)
                self.space.step(self.dt)
            self._post_frame(1.0 / FPS)
            self.goal.update(self.t)
            self._record()
            frame += 1
            if self.winner and self.resolved_at is not None and self.t >= self.resolved_at + 0.5:
                break
            if self.t >= TIMELINE.forced_resolution_s and not self.winner:
                self.goal.force_resolve(self.t)
            if self.t >= hard and not self.winner:
                self.goal.force_resolve(self.t, hard=True)
            if self.t > hard + 1.0:
                break
        self.trace.events = self.events
        self.trace.meta.update(winner=self.winner, resolved_at=self.resolved_at, sim_s=round(time.time() - start, 2),
                               seed=self.seed, ranking=self.goal.ranking(),
                               props=[{"shapes": p.shapes, "style": p.style} for p in self.props])
        return self.trace

    def _apply_drives(self) -> None:
        for c in self.contestants:
            if c.alive and (c.drive[0] or c.drive[1]):
                c.body.apply_force_at_world_point(c.drive, c.body.position)

    def push(self, c: Contestant, fx: float, fy: float) -> None:
        """Add a continuous force for the current frame (applied on every substep)."""
        c.drive = (c.drive[0] + fx, c.drive[1] + fy)

    def _escalate(self) -> None:
        esc = TIMELINE.escalation
        while self.escalation_idx + 1 < len(esc) and self.t >= esc[self.escalation_idx + 1][0]:
            self.escalation_idx += 1
            _, mult, banner = esc[self.escalation_idx]
            self.speed_mult = mult
            self.event("escalation", [], None, mult=mult, banner=banner)

    def _post_frame(self, dt: float) -> None:
        tl = TIMELINE
        for c in self.contestants:
            if not c.alive:
                if c.fall_t >= 0:
                    c.fall_t += dt
                continue
            c.squash = max(0.0, c.squash - dt / (8 / FPS))
            if c.stun > 0:
                c.stun -= dt
                if c.stun <= 0:
                    c.last_stun_end = self.t
            x, y = c.pos
            # anti-stuck: living, unstunned body moving < 18 px over 1.5 s gets an unstick hop
            if self.t - c.anchor_t >= self.cfg["unstick_window_s"]:
                moved = math.hypot(x - c.anchor_pos[0], y - c.anchor_pos[1])
                if moved < self.cfg["unstick_min_px"] and c.stun <= 0 and not c.finished:
                    hop = (220 if self.mode == SIDE else 0)
                    fwd = 160 if self.mode == SIDE else 0
                    if self.mode == TOP:
                        a = self.rng.uniform(0, 2 * math.pi)
                        c.body.apply_impulse_at_local_point((math.cos(a) * 200 * c.body.mass, math.sin(a) * 200 * c.body.mass))
                    else:
                        c.body.apply_impulse_at_local_point((fwd * c.body.mass, -hop * c.body.mass))
                c.anchor_pos, c.anchor_t = (x, y), self.t
            # eliminations
            if self.mode == SIDE:
                if y > self.kill_y:
                    self.eliminate(c, "fell")
                elif self.finish_x is not None and (c.pos[0] < self.cam_x - self.view_w * self._behind_k()
                                                    or c.pos[0] < self.chase_x):
                    self.eliminate(c, "left_behind")
            elif self.walkable is not None and not self.walkable(x / self.edge_k, y / self.edge_k):
                self.eliminate(c, "fell")
            c.contacts = [k for k in c.contacts if self.t - k[0] < 1.5]
        self._pacing()
        if self.mode == SIDE and self.finish_x is not None and self.t > 3.0:
            # paced so the collapse reaches the finish around the forced-resolution time (faster when behind schedule)
            esc_units = 9 * 1.0 + 10 * 1.3 + 14 * 1.65
            k = min(self.cfg["pacing"]["chase_max"], max(self.cfg["pacing"]["chase_min"], self.pressure))
            self.chase_x += (self.finish_x / esc_units) * self.speed_mult * k * dt
            self.zones["chase_x"] = self.chase_x
        pc = self.cfg["pacing"]
        if self.mode != SIDE and self.t > pc["shrink_start_s"]:
            self.edge_k = max(pc["edge_k_min"], self.edge_k - pc["shrink_rate"] * self.speed_mult * self.pressure * dt)
            self.zones["edge_k"] = round(self.edge_k, 4)
        # leader + camera proxy for LEFT BEHIND (mirrors camera framing: leading 40% of surviving heroes)
        alive = self.alive()
        if alive:
            if self.mode == SIDE:
                xs = sorted((c.pos[0] for c in alive if c.is_hero), reverse=True) or sorted((c.pos[0] for c in alive), reverse=True)
                lead = xs[: max(1, math.ceil(len(xs) * 0.4))]
                target = sum(lead) / len(lead)
                self.cam_x += (target - self.cam_x) * min(1.0, dt * 2.5)   # eased, like the real camera
            ld = self.goal.leader() if hasattr(self, "goal") else None
            if ld and ld != self.leader:
                if self.leader is not None:
                    self.event("lead_change", [ld, self.leader], self.by_key[ld].pos)
                    self.by_key[ld].happy_until = self.t + 1.0
                self.leader = ld
        if self.reversed_until > self.t:
            self.zones["reversed"] = True
        else:
            self.zones.pop("reversed", None)

    def _behind_k(self) -> float:
        """LEFT BEHIND distance in view widths: 1.5 (spec), wider while the elimination schedule is ahead, as the
        camera pulls back to keep the pack in frame."""
        return 1.5 + 1.5 * max(0.0, 1.0 - self.pressure)

    def _pacing(self) -> None:
        """Schedule-driven pressure (like a battle-royale storm): the arena squeezes harder while more contestants remain
        than the elimination schedule expects, and eases off when ahead of it. It never picks who goes out."""
        pc = self.cfg["pacing"]
        target = max(0.03, 1.0 - (max(0.0, self.t) / pc["schedule_end_s"]) ** pc["schedule_power"])
        frac = len(self.alive()) / max(1, len(self.contestants))
        self.pressure = min(pc["pressure_max"], max(0.0, 1.0 + pc["pressure_gain"] * (frac - target)))

    def _expression(self, c: Contestant) -> str:
        if not c.alive:
            return "eliminated"
        if self.winner == c.key:
            return "celebrating"
        if c.stun > 0 or self.t - c.last_stun_end < 1.2:
            return "dizzy"
        if self.arena.danger(c, 90):
            return "scared"
        if self.t < c.panic_until:
            return "scared"
        if self.t < c.angry_until:
            return "angry"
        if self.t < c.happy_until:
            return "happy"
        return "neutral"

    def _record(self) -> None:
        n = len(self.contestants)
        rows = np.zeros((n, 6), np.float32)
        flags = np.zeros(n, np.uint8)
        expr = np.zeros(n, np.uint8)
        for i, c in enumerate(self.contestants):
            if c.alive:
                b = c.body
                rows[i] = (b.position.x, b.position.y, math.degrees(b.angle), b.velocity.x, b.velocity.y, c.squash)
                f = T.ALIVE
                if c.stun > 0:
                    f |= T.STUNNED
                if not c.grounded:
                    f |= T.AIRBORNE
            else:
                ex, ey = c.elim_pos or (0, 0)
                rows[i] = (ex, ey, 0, 0, 0, max(0.0, min(1.0, c.fall_t / 0.5)) if c.fall_t >= 0 else 0)
                f = T.FALLING if 0 <= c.fall_t < 0.5 else 0
            if self.winner == c.key:
                f |= T.WINNER | T.VICTORY
            if c.fan_favorite:
                f |= T.FAN_FAV
            if getattr(self.goal, "holder", None) == c.key:
                f |= T.HAS_BOMB
            flags[i] = f
            expr[i] = EXPR[self._expression(c)]
        props = np.array([(p.body.position.x, p.body.position.y, math.degrees(p.body.angle) if p.alive else -9999)
                          for p in self.props], np.float32).reshape(-1, 3)
        zone = {k: v for k, v in self.zones.items()}
        zone["speed_mult"] = self.speed_mult
        zone.update(self.goal.zone_state())
        for hz in self.hazards:
            zone.update(hz.zone_state())
        if self.twist:
            zone.update(self.twist.zone_state())
        self.trace.record(rows, flags, expr, props, zone)
