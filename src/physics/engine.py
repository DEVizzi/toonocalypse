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
    pos_hist: list[tuple[float, float, float]] = field(default_factory=list)
    last_unstick_t: float = -9.0
    jump_cd: float = 0.0
    shove_cd: float = 0.0
    eliminated_at: float | None = None
    elim_pos: tuple[float, float] | None = None
    elim_vel: tuple[float, float] = (0.0, 0.0)
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
    drive_torque: float = 0.0   # SIDE rolling torque re-applied every substep
    traction: float = 1.0       # 0..1.3 from surface friction: scales grip-limited propulsion
    prop_mult: float = 1.0      # crash dummies push at 0.72x; Juggernaut at 0.65x
    phase: str = ""             # Glitch: FEATHER | LEAD
    phase_t: float = 0.0
    last_land_t: float = -9.0
    hit_until: float = -9.0     # v3.2: 0.4 s HIT window (X_X + tongue on Dummies)
    bounce_cd: float = -9.0     # v3.2: cooldown for Boing / Floater lift impulses

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
        self.view_w = 1080.0            # LEFT BEHIND unit: one viewport width at the reference zoom 1.0 (pacing-tuned)
        self.chase_x = -500.0           # SIDE: the collapsing castle floor chasing from the left
        self.edge_k = 1.0               # TOP: escalation shrinks every arena's walkable edge (§4 "arena shrinks")
        self.pressure = 1.0             # Lord Tuno's pacing pressure: >1 when more contestants remain than the schedule
        self.hazard_mult = 1.0          # hazards escalate harder than racers (speed_mult ** hazard_escalation_exp)
        self.overtime = False           # OVERTIME CHAOS: <= 3 survivors or the overtime escalation time
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
        clamp, wmax = self.cfg["velocity_clamp"], self.cfg["angular_clamp"]
        drag = self.cfg["floater_air_drag"]
        flat_damp = self.cfg.get("juggernaut_flat_damping", 5.2)

        def f(body, gravity, damping, dt):
            c = c_ref[0]
            g = gravity
            if c.hero is not None and c.hero.gravity_mult != 1.0:
                g = (gravity[0] * c.hero.gravity_mult, gravity[1] * c.hero.gravity_mult)
            pymunk.Body.update_velocity(body, g, damping, dt)
            if c.hero is not None and c.hero.trait == "glide" and not c.grounded and self.mode == SIDE:
                # v3.2: low horizontal drag so Floater sails far, soft vertical drag for slow floaty arcs
                vx = body.velocity.x * max(0.0, 1.0 - drag * 0.35 * dt)
                vy = body.velocity.y * max(0.0, 1.0 - drag * dt)
                body.velocity = pymunk.Vec2d(vx, vy)
            elif c.hero is not None and c.hero.trait == "bowling" and c.grounded and self.mode == SIDE:
                gn = getattr(c, "ground_n", pymunk.Vec2d(0, 1))
                if abs(float(gn.x)) < 0.17:
                    # v3.2: heavy square corners resist rolling on flat ground; downhill gravity unlocks full speed
                    body.angular_velocity *= max(0.0, 1.0 - flat_damp * dt)
                    body.velocity = pymunk.Vec2d(body.velocity.x * max(0.0, 1.0 - 1.3 * dt), body.velocity.y)
            v = body.velocity
            sp = v.length
            if sp > clamp:
                body.velocity = v * (clamp / sp)
            if abs(body.angular_velocity) > wmax:
                body.angular_velocity = math.copysign(wmax, body.angular_velocity)
        return f

    def _hero_shape(self, h: Hero, body: pymunk.Body) -> pymunk.Shape:
        w, hh = h.size
        if h.shape in ("circle", "cloud"):
            return pymunk.Circle(body, w)
        if h.shape == "oval":       # rounded puck: beveled 10-gon ellipse
            pts = [(math.cos(a) * (w - 5), math.sin(a) * (hh - 5)) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
            return pymunk.Poly(body, pts, radius=5)
        if h.shape == "square":     # heavy bevel so the cube tumbles and rolls
            return pymunk.Poly.create_box(body, (2 * (w - 10), 2 * (hh - 10)), radius=10)
        n = 6 if h.shape == "hexagon" else 8
        return pymunk.Poly(body, [(math.cos(2 * math.pi * i / n) * (w - 5), math.sin(2 * math.pi * i / n) * (w - 5))
                                  for i in range(n)], radius=5)

    def _moment(self, shape: pymunk.Shape, mass: float) -> float:
        """True moment of inertia for the actual shape (never infinite: everything rolls and tumbles)."""
        if isinstance(shape, pymunk.Circle):
            return pymunk.moment_for_circle(mass, 0, shape.radius)
        return pymunk.moment_for_poly(mass, shape.get_vertices(), radius=shape.radius)

    def _make_contestant(self, key: str, hero: Hero | None, extra: Extra | None, pos) -> Contestant:
        body = pymunk.Body(1.0, 1.0)
        body.position = pos
        if hero is not None:
            shape = self._hero_shape(hero, body)
            mass = hero.mass
            fr, el, radius, vmax, bh = hero.friction, hero.elasticity, hero.radius, hero.max_speed, hero.behaviour
        else:
            assert extra is not None
            shape = pymunk.Circle(body, extra.radius)
            mass = extra.mass
            fr, el, radius, vmax, bh = extra.friction, extra.elasticity, extra.radius, extra.max_speed, extra.behaviour
        body.mass, body.moment = mass, self._moment(shape, mass)
        shape.friction, shape.elasticity = fr, el
        shape.collision_type = CT_BODY
        self.space.add(body, shape)
        c = Contestant(key, hero, extra, body, shape, radius, self.eff_speed(vmax), bh, anchor_pos=pos)
        if hero is not None and hero.trait == "bowling":
            c.prop_mult = self.cfg.get("juggernaut_propulsion", 0.65)
        elif hero is not None:
            c.prop_mult = 1.0
        else:
            c.prop_mult = self.cfg["dummy_propulsion"]
        body.velocity_func = self._velocity_func([c])
        shape.contestant = c  # type: ignore[attr-defined]
        if hero is not None and hero.trait == "glitch":
            self._glitch_phase(c, "LEAD" if self.rng.random() < 0.5 else "FEATHER", event=False)
            c.phase_t = -1.1        # first visible RGB phase shift triggers around t = 0.9 s
        return c

    def _make_hero(self, h: Hero, pos) -> Contestant:
        return self._make_contestant(h.key, h, None, pos)

    def _make_extra(self, e: Extra, pos) -> Contestant:
        return self._make_contestant(e.key, None, e, pos)

    def _glitch_phase(self, c: Contestant, phase: str, event: bool = True) -> None:
        """Glitch phase-shift: FEATHER (tiny mass, hyper-bounce) <-> LEAD (heavy, dead thud) + erratic micro-impulse."""
        lo, hi = c.hero.mass_range or (0.55, 4.4)  # type: ignore[union-attr]
        mass, el = (lo, 0.98) if phase == "FEATHER" else (hi, 0.25)
        c.body.mass, c.body.moment = mass, self._moment(c.shape, mass)
        c.shape.elasticity = el
        c.phase, c.phase_t = phase, self.t
        if event:
            a = self.rng.uniform(0, 2 * math.pi)
            c.body.apply_impulse_at_world_point((math.cos(a) * 105 * mass, math.sin(a) * 105 * mass), c.body.position)
            self.event("glitch", [c.key], c.pos, effect=phase.lower())

    def eff_speed(self, stat: float) -> float:
        c, k = self.cfg["speed_centre"], self.cfg["speed_spread"]
        return c + (stat - c) * k

    def eliminate(self, c: Contestant, cause: str, by: str | None = None) -> None:
        if not c.alive or self.winner:
            return
        c.alive = False
        c.eliminated_at = self.t
        c.elim_pos = c.pos
        c.elim_vel = (float(c.body.velocity.x), float(c.body.velocity.y))
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
                if self.mode == SIDE and x.hero and x.hero.trait == "glide" and imp / x.body.mass > 85 and self.t >= x.bounce_cd:
                    x.bounce_cd = self.t + 0.32
                    x.body.apply_impulse_at_world_point((45 * x.body.mass, -170 * x.body.mass), x.body.position)
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
                if (c.hero and c.hero.trait == "bowling" and imp / c.body.mass > 62 and self.mode == SIDE
                        and self.t - c.last_land_t > 0.25):
                    c.last_land_t = self.t
                    self.event("heavy_land", [c.key], (c.pos[0], c.pos[1] + c.radius * 0.82),
                               shake=bool(imp / c.body.mass > 165))
                if (c.hero and c.hero.trait == "glide" and self.mode == SIDE and imp / c.body.mass > 70
                        and self.t >= c.bounce_cd):
                    c.bounce_cd = self.t + 0.30
                    c.body.apply_impulse_at_world_point((55 * c.body.mass, -185 * c.body.mass), c.body.position)
                if c.hero and c.hero.trait == "no_brakes" and imp > 260 * c.body.mass and abs(arb.normal.x) > 0.7:
                    self.trait(c, "wall_slam")

        def boing(arb: pymunk.Arbiter, space, data):
            # v3.2: Boing perpetual bouncer — minimum lively vertical rebound on grounded hits so he never sits flat
            for s in arb.shapes:
                c = getattr(s, "contestant", None)
                if not (c and c.hero and c.hero.trait == "auto_hop"):
                    continue
                n = arb.normal if s is arb.shapes[0] else -arb.normal
                v = c.body.velocity
                if self.mode == SIDE and n.y > 0.30 and self.t >= c.bounce_cd:
                    c.bounce_cd = self.t + 0.16
                    target_vy = min(-355.0, -abs(v.y) * 1.08)
                    if v.y > target_vy:
                        c.body.apply_impulse_at_world_point((36 * c.body.mass, (target_vy - v.y) * c.body.mass),
                                                            c.body.position)
                    c.squash = 1.0
                elif arb.is_first_contact and (v.length > 140 or self.mode != SIDE):
                    sp = max(250.0 if self.mode != SIDE else 180.0, min(1100.0, v.length * 1.08))
                    boost = max(60.0, sp - v.length)
                    c.body.apply_impulse_at_world_point((-n.x * boost * c.body.mass * 0.55, -n.y * boost * c.body.mass * 0.55),
                                                        c.body.position)
                    c.squash = 1.0

        for ct in (CT_BODY, CT_GROUND, CT_HAZARD, CT_BOUNCY):
            self.space.on_collision(CT_BODY, ct, post_solve=boing)
        self.space.on_collision(CT_BODY, CT_BODY, post_solve=post_body_body)
        self.space.on_collision(CT_BODY, CT_GROUND, post_solve=post_body_world)
        self.space.on_collision(CT_BODY, CT_HAZARD, post_solve=post_body_world)
        self.space.on_collision(CT_BODY, CT_BOUNCY, post_solve=post_body_world)

    def _impact(self, c: Contestant, impulse: float, other: Contestant | None) -> None:
        per_mass = impulse / max(0.3, c.body.mass)
        if per_mass > 105:
            c.hit_until = self.t + 0.40
        if per_mass > 120:
            c.squash = max(c.squash, min(1.0, per_mass / 400))
        thr = self.cfg["stun_threshold"]
        if per_mass > thr and c.stun <= 0:
            # knocked: propulsion cut for 0.35-0.75 s scaled by the hit, pure ballistics/spin take over
            lo, hi = self.cfg["stun_range"]
            mult = c.hero.stun_mult if c.hero else 1.0
            c.stun = (lo + (hi - lo) * min(1.0, (per_mass - thr) / (2.5 * thr))) * max(0.4, mult)
        if c.hero and c.hero.trait == "glitch" and per_mass > thr * 0.8 and self.t - c.phase_t > 0.4:
            self._glitch_phase(c, "FEATHER" if c.phase == "LEAD" else "LEAD")

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
            if not c.alive:
                continue
            if c.drive[0] or c.drive[1]:
                c.body.apply_force_at_world_point(c.drive, c.body.position)
            if c.drive_torque:
                c.body.torque += c.drive_torque

    def push(self, c: Contestant, fx: float, fy: float) -> None:
        """Add a continuous force for the current frame (applied on every substep)."""
        c.drive = (c.drive[0] + fx, c.drive[1] + fy)

    def _escalate(self) -> None:
        q = self.cfg.get("top_quake")
        if self.mode == TOP and q and not getattr(self, "_quaked", False) and self.t >= q["t"]:
            # Lord Tuno's opening lever: the floor bucks outward so the first wipeouts happen within seconds
            self._quaked = True
            self.event("escalation", [], None, mult=self.speed_mult, banner="TUNO QUAKE!")
            cx, cy = self.arena.center
            for c in self.alive():
                dx, dy = c.pos[0] - cx, c.pos[1] - cy
                d = math.hypot(dx, dy) or 1.0
                c.body.apply_impulse_at_world_point((dx / d * q["dv"] * c.body.mass, dy / d * q["dv"] * c.body.mass),
                                                    c.body.position)
                c.stun = max(c.stun, q["stun_s"] * (c.hero.stun_mult if c.hero else 1.0))
        esc = TIMELINE.escalation
        while self.escalation_idx + 1 < len(esc) and self.t >= esc[self.escalation_idx + 1][0]:
            self.escalation_idx += 1
            _, mult, banner = esc[self.escalation_idx]
            self.speed_mult = mult
            self.hazard_mult = mult ** self.cfg["hazard_escalation_exp"]
            if self.escalation_idx == len(esc) - 1:
                self._start_overtime(banner)
            else:
                self.event("escalation", [], None, mult=mult, banner=banner)
        if not self.overtime and self.t > 3.0 and len(self.alive()) <= self.cfg["overtime"]["survivors"]:
            self.escalation_idx = len(esc) - 1
            _, mult, banner = esc[-1]
            self.speed_mult = mult
            self._start_overtime(banner)

    def _start_overtime(self, banner: str) -> None:
        """OVERTIME CHAOS: hazards at double speed, the floor collapses behind the last place / the arena shrinks hard."""
        if self.overtime:
            return
        self.overtime = True
        self.hazard_mult = self.cfg["overtime"]["hazard_mult"]
        self.event("escalation", [], None, mult=self.speed_mult, banner=banner or "OVERTIME CHAOS!", overtime=True)

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
            if c.hero is not None and c.hero.trait == "glitch" and self.t - c.phase_t >= self.cfg["glitch_period_s"]:
                self._glitch_phase(c, "FEATHER" if c.phase == "LEAD" else "LEAD")
            if (self.mode == SIDE and c.hero is not None and c.hero.trait == "auto_hop" and c.grounded
                    and c.body.velocity.y > -120 and self.t >= c.bounce_cd and not c.finished):
                # v3.2: Boing never sits passively in flat clumps — perpetual rubber superball hop
                c.bounce_cd = self.t + 0.18
                c.squash = 1.0
                c.body.apply_impulse_at_world_point((44 * c.body.mass, -355 * c.body.mass), c.body.position)
            c.traction = min(1.3, max(0.03, c.shape.friction / 0.8))
            # anti-stuck: rolling 1.5 s displacement < 45 px -> crisp upward-and-forward eject impulse
            win = self.cfg["unstick_window_s"]
            c.pos_hist.append((self.t, x, y))
            while len(c.pos_hist) > 1 and self.t - c.pos_hist[0][0] > win:
                c.pos_hist.pop(0)
            if self.t >= win and self.t - c.pos_hist[0][0] >= win * 0.9 and self.t - c.last_unstick_t >= win:
                moved = math.hypot(x - c.pos_hist[0][1], y - c.pos_hist[0][2])
                if moved < self.cfg["unstick_min_px"] and c.stun <= 0 and not c.finished:
                    if self.mode == TOP:
                        a = self.rng.uniform(0, 2 * math.pi)
                        c.body.apply_impulse_at_world_point((math.cos(a) * 240 * c.body.mass, math.sin(a) * 240 * c.body.mass),
                                                            c.body.position)
                    else:
                        c.body.apply_impulse_at_world_point((260 * c.body.mass, -320 * c.body.mass), c.body.position)
                    c.last_unstick_t = self.t
            # eliminations
            if self.mode == SIDE:
                floor = self.arena.floor_y(x) if hasattr(self.arena, "floor_y") else None
                if y > self.kill_y or (floor is not None and y > floor + self.cfg["fall_kill_depth"]):
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
            esc_units = sum(TIMELINE.speed_at(3.0 + i * 0.1) * 0.1 for i in range(int((self.cfg["pacing"]["chase_finish_s"] - 3.0) * 10)))
            k = min(self.cfg["pacing"]["chase_max"], max(self.cfg["pacing"]["chase_min"], self.pressure))
            self.chase_x += (self.finish_x / esc_units) * self.speed_mult * k * dt
            if self.overtime:       # the floor collapses right behind the last-place survivor
                alive_x = [c.pos[0] for c in self.alive()]
                if alive_x:
                    target = min(alive_x) - 120
                    self.chase_x = max(self.chase_x, self.chase_x + (target - self.chase_x) * min(1.0, dt * 1.6))
            self.zones["chase_x"] = self.chase_x
        pc = self.cfg["pacing"]
        if self.mode != SIDE and self.t > pc["shrink_start_s"]:
            rate = pc["shrink_rate"] * self.speed_mult * max(self.pressure, 0.6 if self.overtime else 0.0)
            if self.overtime:
                rate *= self.cfg["overtime"]["shrink_mult"]
            self.edge_k = max(pc["edge_k_min"], self.edge_k - rate * dt)
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
        return self.cfg["pacing"]["left_behind_views"] + 1.5 * max(0.0, 1.0 - self.pressure)

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
        if c.extra is not None:
            # v3.2 Crash Dummies: FALLING (O_O scream) > HIT for 0.4 s (X_X + tongue) > NORMAL (googly + "o")
            if (self.mode == SIDE and not c.grounded and c.body.velocity.y > 380) or (
                self.mode == TOP and self.arena.edge_distance(*c.pos) < 42
            ):
                return "scared"
            if self.t < c.hit_until:
                return "dizzy"
            if self.mode == SIDE and not c.grounded and self.arena.danger(c, 85):
                return "scared"
            return "neutral"
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
        rows = np.zeros((n, 7), np.float32)
        flags = np.zeros(n, np.uint8)
        expr = np.zeros(n, np.uint8)
        for i, c in enumerate(self.contestants):
            if c.alive:
                b = c.body
                rows[i] = (b.position.x, b.position.y, math.degrees(b.angle), b.velocity.x, b.velocity.y, c.squash,
                           b.angular_velocity)
                f = T.ALIVE
                if c.stun > 0:
                    f |= T.STUNNED
                if not c.grounded:
                    f |= T.AIRBORNE
            else:
                ex, ey = c.elim_pos or (0, 0)
                fall = self.cfg["top_fall_s"]
                rows[i] = (ex, ey, math.degrees(c.body.angle), c.elim_vel[0], c.elim_vel[1],
                           max(0.0, min(1.0, c.fall_t / fall)) if c.fall_t >= 0 else 0, 0)
                f = T.FALLING if 0 <= c.fall_t < fall else 0
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
