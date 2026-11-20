"""Render pipeline (§15, §4): draws ONLY from the chosen trace and pipes raw RGB24 frames into ffmpeg.

Output timeline: [flash-forward 1.0 s] -> cold open (pre-roll) -> gameplay -> 0.4x winner replay -> winner card ->
loop tail fading into the opening composition. Hitstop (2-3 frozen frames) is applied on major hero moments.
"""
from __future__ import annotations

import math
import os
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from src.characters import renderer  # noqa: E402
from src.characters.roster import EXPRESSIONS, HERO_BY_KEY, Extra  # noqa: E402
from src.config import FPS, H, LAYOUT, TIMELINE, VIDEO, W  # noqa: E402
from src.games.themes import THEME_BY_KEY, Theme  # noqa: E402
from src.physics import trace as T  # noqa: E402
from src.physics.camera import Cam, track  # noqa: E402
from src.rendering import effects, hud, scenery  # noqa: E402

BLACK = (17, 17, 17)
WHITE_ = (255, 255, 255)


@dataclass
class Shot:
    """One output frame: which trace frame (float for slow-mo) and what overlays are active."""
    tf: float
    segment: str                 # flash | cold | play | replay | card | tail
    seg_t: float
    zoom_mult: float = 1.0
    focus: str | None = None     # contestant key to centre on (replay / flash-forward)


@dataclass
class Episode:
    trace: T.Trace
    ep_label: str
    season_line: str = ""
    prompt: str = ""
    shots: list[Shot] = field(default_factory=list)
    flash_event: T.Event | None = None


def _lerp(a, b, k):
    return a + (b - a) * k


def plan_shots(ep: Episode) -> list[Shot]:
    tr = ep.trace
    pre = tr.meta.get("preroll_frames", 0)
    end_t = tr.meta.get("resolved_at") or (tr.n_frames - pre) / FPS
    end_f = min(tr.n_frames - 1, pre + int(round(end_t * FPS)))
    winner = tr.meta.get("winner")
    shots: list[Shot] = []
    if tr.meta["recipe"].get("flash_forward") and ep.flash_event is not None:
        f0 = pre + int(ep.flash_event.t * FPS) - int(0.5 * FPS)
        for i in range(int(TIMELINE.flash_forward_s * FPS)):
            shots.append(Shot(max(0, f0 + i), "flash", i / FPS, 1.35, ep.flash_event.actors[0]))
    for i in range(pre):
        shots.append(Shot(i, "cold", i / FPS))
    hitstops = {pre + int(e.t * FPS) for e in tr.events
                if (e.kind == "elimination" and e.data.get("hero")) or (e.kind == "impact" and e.data.get("hero_pair")
                                                                       and e.data.get("impulse", 0) > 1600)}
    for f in range(pre, end_f + 1):
        shots.append(Shot(f, "play", (f - pre) / FPS))
        if f in hitstops:
            shots += [Shot(f, "play", (f - pre) / FPS)] * 2
    # winner replay: 0.4x of the final 0.9 s of gameplay
    src0 = end_f - TIMELINE.replay_source_s * FPS
    n = int(TIMELINE.replay_s * FPS)
    for i in range(n):
        shots.append(Shot(src0 + (end_f - src0) * i / n, "replay", i / FPS, TIMELINE.replay_zoom, winner))
    for i in range(int(TIMELINE.winner_card_s * FPS)):
        shots.append(Shot(end_f, "card", i / FPS))
    for i in range(int(TIMELINE.loop_tail_s * FPS)):
        shots.append(Shot(0, "tail", i / FPS))
    return shots


class Renderer:
    def __init__(self, ep: Episode) -> None:
        pygame.init()
        self.ep = ep
        self.tr = ep.trace
        self.meta = self.tr.meta
        self.theme: Theme = THEME_BY_KEY[self.meta["recipe"]["theme"]]
        self.cams = track(self.tr)
        self.frame = pygame.Surface((W, H))
        self.sky = scenery.sky(self.theme)
        self.castle = scenery.castle_header(self.theme)
        self.heroes = [HERO_BY_KEY[k] for k in self.meta["heroes"]]
        self.extras = {k: Extra(v["number"], v["colour"], cult=v["cult"]) for k, v in self.meta["extras"].items()}
        self.pre = self.meta.get("preroll_frames", 0)
        self.rng = random.Random(self.meta.get("seed", 0))
        self.removed: set = set()
        self.escalations = [e for e in self.tr.events if e.kind in ("escalation", "twist", "stage_final")]

    # ------------------------------------------------------------------ static layers
    def _sky(self) -> pygame.Surface:
        s = pygame.Surface((W, H))
        a, b = self.theme.sky_top, self.theme.sky_bottom
        for y in range(H):
            k = y / H
            pygame.draw.line(s, tuple(int(_lerp(a[i], b[i], k)) for i in range(3)), (0, y), (W, y))
        rng = random.Random(7)
        castle = self.theme.castle
        far = tuple(int(c * 0.85 + 30) for c in castle)
        for i in range(6):       # far castle silhouettes (parallax layer drawn once; offset per frame)
            x = rng.randint(-100, W)
            w, h = rng.randint(140, 260), rng.randint(300, 600)
            pygame.draw.rect(s, far, (x, 1500 - h, w, h + 200))
            for k in range(w // 40):
                pygame.draw.rect(s, far, (x + k * 40, 1500 - h - 30, 24, 30))
            pygame.draw.polygon(s, far, [(x + w / 2 - 50, 1500 - h - 30), (x + w / 2 + 50, 1500 - h - 30), (x + w / 2, 1500 - h - 140)])
        return s

    # ------------------------------------------------------------------ world drawing
    def _poly_screen(self, cam: Cam, pts):
        return [cam.to_screen(x, y) for x, y in pts]

    def draw_world(self, cam: Cam, fi: int, t_anim: float) -> None:
        fr = self.frame
        th = self.theme
        zone = self.tr.zones[fi]
        removed = set(zone.get("removed_statics", []))
        par = (-cam.x * 0.1) % W
        fr.blit(self.sky, (par - W, 0))
        fr.blit(self.sky, (par, 0))
        self._particles(cam, t_anim)
        z = cam.zoom
        # top-down platforms
        for s in self.meta["statics"]:
            if s["type"] == "disc":
                k = zone.get("edge_k", 1.0)
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), s["r"] * z * k, z, th)
            elif s["type"] == "ring":
                r = zone.get("ring_r", s["r"]) * zone.get("edge_k", 1.0)
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), r * z, z, th)
                pygame.draw.circle(fr, th.accent, cam.to_screen(*s["c"]), r * z, max(3, int(6 * z)))
            elif s["type"] == "square":
                k = zone.get("edge_k", 1.0)
                scenery.draw_floating_platform(fr, cam.to_screen(0, 0), 0, z, th, "square", s["half"] * k * z)
            elif s["type"] == "hex_grid":
                states = zone.get("tiles", [0] * len(s["tiles"]))
                k = zone.get("edge_k", 1.0)
                for (x, y), st in zip(s["tiles"], states):
                    if st == 2:
                        continue
                    pts = [cam.to_screen(x * k + math.cos(a) * (s["size"] - 3), y * k + math.sin(a) * (s["size"] - 3))
                           for a in [i * math.pi / 3 for i in range(6)]]
                    col = th.terrain if st == 0 else th.hazard
                    if st == 1:
                        jx = math.sin(t_anim * 60 + x) * 3
                        pts = [(px + jx, py) for px, py in pts]
                    side = [(px, py + 22 * z) for px, py in pts]
                    pygame.draw.polygon(fr, BLACK, side)
                    pygame.draw.polygon(fr, scenery.mix(col, BLACK, 0.3), [(px, py - 3) for px, py in side])
                    pygame.draw.polygon(fr, col, pts)
                    pygame.draw.polygon(fr, BLACK, pts, 4)
        # SIDE terrain fills + top edges
        for s in self.meta["statics"]:
            if s["id"] in removed if "id" in s else False:
                continue
            if s["type"] == "fill":
                xs = [p[0] for p in s["verts"]]
                if not (cam.visible(min(xs), s["verts"][0][1], 2000) or cam.visible(max(xs), s["verts"][1][1], 2000)):
                    continue
                if s["mat"] == "plank":
                    continue                     # bridges have no cliff body underneath
                scenery.draw_cliff(fr, self._poly_screen(cam, s["verts"]), z, th, s["mat"])
        for s in self.meta["statics"]:
            if "id" in s and s["id"] in removed:
                continue
            if s["type"] == "seg":
                a, b = cam.to_screen(*s["a"]), cam.to_screen(*s["b"])
                if max(a[0], b[0]) < -50 or min(a[0], b[0]) > W + 50:
                    continue
                if s["mat"] in ("ground", "ice", "mud", "bouncy", "conveyor", "plank"):
                    scenery.draw_cap(fr, a, b, z, th, s["mat"])
                else:
                    col = {"gate": (150, 92, 48), "wall": scenery.rock_colours(th)[1]}.get(s["mat"], th.terrain_outline)
                    w = max(6, int(s["r"] * 2 * z))
                    pygame.draw.line(fr, BLACK, a, b, w + 8)
                    pygame.draw.line(fr, col, a, b, w)
                if s.get("belt"):   # moving chevrons on conveyors
                    n = int(math.hypot(b[0] - a[0], b[1] - a[1]) / 40)
                    off = (t_anim * s["belt"] * 0.25) % 40
                    for i in range(n):
                        x = a[0] + (i * 40 + off) * (1 if b[0] > a[0] else -1)
                        d = 8 if s["belt"] > 0 else -8
                        pygame.draw.lines(fr, (255, 214, 0), False, [(x - d, a[1] - 6), (x, a[1]), (x - d, a[1] + 6)], 3)
            elif s["type"] == "poly":
                pts = self._poly_screen(cam, s["verts"])
                stone = scenery.rock_colours(th)[1]
                pygame.draw.polygon(fr, stone, pts)
                pygame.draw.line(fr, scenery.mix(stone, WHITE_, 0.3), pts[2], pts[3], max(2, int(6 * z))) if len(pts) > 3 else None
                pygame.draw.polygon(fr, BLACK, pts, 5)
            elif s["type"] == "circle":
                c = cam.to_screen(*s["c"])
                pygame.draw.circle(fr, BLACK, c, s["r"] * z + 4)
                pygame.draw.circle(fr, th.hazard, c, s["r"] * z)
                pygame.draw.circle(fr, (255, 255, 255), c, s["r"] * z * 0.45)
            elif s["type"] == "finish":
                self._finish(cam, s["x"], s["y"], t_anim)
            elif s["type"] in ("post", "pivot"):
                c = cam.to_screen(*s["c"])
                pygame.draw.circle(fr, BLACK, c, 12 * z)
        self._zones(cam, zone, t_anim)
        self._props(cam, fi)

    def _finish(self, cam: Cam, x: float, y: float, t: float) -> None:
        a, b = cam.to_screen(x, y - 420), cam.to_screen(x, y)
        sq = 22 * cam.zoom
        for i in range(int((b[1] - a[1]) / sq) + 1):
            for j in range(2):
                col = BLACK if (i + j) % 2 else (255, 255, 255)
                pygame.draw.rect(self.frame, col, (a[0] + j * sq - sq, a[1] + i * sq, sq, sq))

    def _zones(self, cam: Cam, zone: dict, t: float) -> None:
        fr, th, z = self.frame, self.theme, cam.zoom
        for key, col in (("ice_zones", (190, 235, 255, 150)), ("mud_zones", (110, 75, 40, 170)),
                         ("boost_zones", (255, 214, 0, 120))):
            for zz in zone.get(key, []):
                if zz[0] == "rect":
                    a = cam.to_screen(zz[1], self.ground_y(zz[1]) - 8)
                    b = cam.to_screen(zz[2], self.ground_y(zz[2]) + 16)
                    surf = pygame.Surface((max(1, b[0] - a[0]), max(1, b[1] - a[1] + 10)), pygame.SRCALPHA)
                    surf.fill(col)
                    fr.blit(surf, (a[0], a[1]))
                else:
                    c = cam.to_screen(*zz[1])
                    r = int(zz[2] * z)
                    surf = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
                    pygame.draw.circle(surf, col, (r, r), r)
                    fr.blit(surf, (c[0] - r, c[1] - r))
        if "lava_y" in zone:
            y = cam.to_screen(0, zone["lava_y"])[1]
            if y < H:
                pygame.draw.rect(fr, (255, 90, 20), (0, y, W, H - y))
                for i in range(12):
                    bx = (i * 97 + t * 40) % W
                    pygame.draw.circle(fr, (255, 200, 60), (bx, y + 10 + 6 * math.sin(t * 5 + i)), 14)
                pygame.draw.line(fr, (255, 230, 120), (0, y), (W, y), 6)
        if "chase_x" in zone:
            x = cam.to_screen(zone["chase_x"], 0)[0]
            if x > -60:
                surf = pygame.Surface((max(1, int(x) + 60), H), pygame.SRCALPHA)
                surf.fill((30, 10, 40, 170))
                fr.blit(surf, (0, 0))
                for i in range(14):
                    yy = (i * 140 + t * 300) % H
                    pygame.draw.line(fr, (180, 120, 255), (x, yy), (x + 30 * math.sin(t * 7 + i), yy + 60), 5)
        if zone.get("zone"):
            zx, zy, r = zone["zone"]
            c = cam.to_screen(zx, zy)
            pygame.draw.circle(fr, (255, 214, 0), c, r * z, 8)
            pygame.draw.circle(fr, (255, 214, 0), c, r * z * (0.7 + 0.1 * math.sin(t * 6)), 3)
        for it in zone.get("items", []):
            c = cam.to_screen(*it)
            bob = math.sin(t * 6 + it[0]) * 5
            pts = [(c[0] - 14, c[1] + 8 + bob), (c[0] - 14, c[1] - 6 + bob), (c[0] - 7, c[1] + bob), (c[0], c[1] - 12 + bob),
                   (c[0] + 7, c[1] + bob), (c[0] + 14, c[1] - 6 + bob), (c[0] + 14, c[1] + 8 + bob)]
            pygame.draw.polygon(fr, (255, 205, 40), pts)
            pygame.draw.polygon(fr, BLACK, pts, 3)
        for p in zone.get("pads", []):
            c = cam.to_screen(*p)
            pygame.draw.ellipse(fr, (160, 80, 255), (c[0] - 34 * z, c[1] - 10 * z, 68 * z, 20 * z))
            pygame.draw.ellipse(fr, BLACK, (c[0] - 34 * z, c[1] - 10 * z, 68 * z, 20 * z), 3)
        if zone.get("wind") is not None:
            for i in range(18):
                y = 400 + (i * 73) % 1200
                x = (i * 211 + t * 900 * (1 if (isinstance(zone["wind"], int) and zone["wind"] > 0) else -1)) % (W + 200) - 100
                pygame.draw.line(fr, (255, 255, 255), (x, y), (x + 90, y), 4)
        for tl in zone.get("tiles_top", []):
            (cx, cy), r, st = tl
            if st == 2:
                continue
            c = cam.to_screen(cx, cy)
            col = (255, 80, 80) if st == 1 else (255, 255, 255)
            pygame.draw.circle(self.frame, col, (c[0] + (math.sin(t * 60) * 3 if st == 1 else 0), c[1]), r * z, 5)

    def ground_y(self, x: float) -> float:
        for s in self.meta["statics"]:
            if s["type"] == "seg" and s["mat"] in ("ground", "ice", "mud", "conveyor", "bouncy", "plank"):
                (ax, ay), (bx, by) = s["a"], s["b"]
                if min(ax, bx) <= x <= max(ax, bx) and ax != bx:
                    return ay + (by - ay) * (x - ax) / (bx - ax)
        return 0.0

    def _props(self, cam: Cam, fi: int) -> None:
        props = self.tr.props[fi]
        styles = self.meta["props"]
        th = self.theme
        for i, row in enumerate(props):
            if i >= len(styles) or row[2] <= -9000:
                continue
            x, y, ang = float(row[0]), float(row[1]), math.radians(float(row[2]))
            if not cam.visible(x, y, 400):
                continue
            st = styles[i]
            ca, sa = math.cos(ang), math.sin(ang)
            for sh in st["shapes"]:
                if sh["type"] == "circle":
                    ox, oy = sh["c"]
                    c = cam.to_screen(x + ox * ca - oy * sa, y + ox * sa + oy * ca)
                    col = {"boulder": (130, 110, 100), "cannonball": (40, 40, 50), "giant_ball": (255, 77, 166)}.get(st["style"], th.hazard)
                    pygame.draw.circle(self.frame, BLACK, c, sh["r"] * cam.zoom + 4)
                    pygame.draw.circle(self.frame, col, c, sh["r"] * cam.zoom)
                    pygame.draw.circle(self.frame, (255, 255, 255), (c[0] - sh["r"] * 0.35 * cam.zoom, c[1] - sh["r"] * 0.35 * cam.zoom), sh["r"] * 0.2 * cam.zoom)
                elif sh["type"] == "seg":
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in (sh["a"], sh["b"])]
                    if st["style"] == "disc_marks":
                        pygame.draw.line(self.frame, th.terrain_outline, pts[0], pts[1], 4)
                        continue
                    pygame.draw.line(self.frame, BLACK, pts[0], pts[1], int(sh["r"] * 2 * cam.zoom) + 6)
                    pygame.draw.line(self.frame, th.hazard, pts[0], pts[1], int(sh["r"] * 2 * cam.zoom))
                else:
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in sh["verts"]]
                    col = {"seesaw": (170, 120, 70), "tile": th.terrain, "wall_block": th.castle}.get(st["style"], th.hazard)
                    pygame.draw.polygon(self.frame, col, pts)
                    pygame.draw.polygon(self.frame, BLACK, pts, 4)

    def _particles(self, cam: Cam, t: float) -> None:
        kind = self.theme.particles
        rng = random.Random(3)
        col = {"snow": (255, 255, 255), "embers": (255, 150, 60), "stars": (255, 255, 220), "bubbles": (200, 240, 255),
               "rain": (170, 190, 230), "sand": (240, 210, 150), "fireflies": (255, 240, 120), "sprinkles": (255, 120, 200),
               "wisps": (190, 255, 160), "sparks": (255, 210, 90), "clouds": (255, 255, 255), "pollen": (255, 236, 150)}[kind]
        for i in range(36):
            x0, y0 = rng.uniform(0, W), rng.uniform(330, 1650)
            sp = rng.uniform(20, 80)
            if kind in ("snow", "rain", "sprinkles"):
                y = (y0 + t * sp * (6 if kind == "rain" else 1.5)) % 1320 + 330
                x = (x0 - cam.x * 0.3) % W
            else:
                y = (y0 - t * sp) % 1320 + 330
                x = (x0 + math.sin(t + i) * 20 - cam.x * 0.3) % W
            if kind == "rain":
                pygame.draw.line(self.frame, col, (x, y), (x - 6, y + 22), 2)
            elif kind == "clouds":
                pygame.draw.ellipse(self.frame, col, (x, y, 60, 22))
            else:
                pygame.draw.circle(self.frame, col, (x, y), 3)

    # ------------------------------------------------------------------ contestants + juice
    def draw_contestants(self, cam: Cam, tf: float, t_anim: float, focus_winner: bool = False) -> None:
        if abs(tf - round(tf)) > 1e-6:
            rows, flags, expr = self.tr.sample(tf / FPS)
        else:
            fi = int(round(tf))
            rows, flags, expr = self.tr.frames[fi], self.tr.flags[fi], self.tr.expr[fi]
        keys = self.tr.keys
        z = cam.zoom
        order = sorted(range(len(keys)), key=lambda i: (keys[i] in HERO_BY_KEY, flags[i] & T.WINNER))
        pills = []
        for i in order:
            k = keys[i]
            f = int(flags[i])
            x, y, ang, vx, vy, sq = (float(v) for v in rows[i])
            alive = f & T.ALIVE
            falling = f & T.FALLING
            if not alive and not falling:
                continue
            if not cam.visible(x, y, 120):
                continue
            sx, sy = cam.to_screen(x, y)
            ex = EXPRESSIONS[int(expr[i])]
            if self.tr.mode == "TOP_DOWN" and alive:
                scenery.shadow(self.frame, (sx, sy), (HERO_BY_KEY[k].radius if k in HERO_BY_KEY else 24) * z)
            scale = z * (1 - sq if falling else 1)
            spin = (t_anim * 900) % 360 if falling else ang
            if k in HERO_BY_KEY:
                h = HERO_BY_KEY[k]
                limb = "victory" if f & T.VICTORY else ("stunned" if f & T.STUNNED else ("airborne" if f & T.AIRBORNE else
                                                                                       ("running" if abs(vx) + abs(vy) > 40 else "idle")))
                if self.tr.mode == "TOP_DOWN" and limb == "airborne":
                    limb = "running"
                display_angle = spin if (f & T.STUNNED or falling) else max(-12.0, min(12.0, vx * 0.02))
                if abs(vx) + abs(vy) > 520:   # motion trail
                    for k2 in (3, 2, 1):
                        ghost = (sx - vx * 0.012 * k2 * z, sy - vy * 0.012 * k2 * z)
                        s = renderer.body_surface(h, ex, 0)
                        s2 = pygame.transform.rotozoom(s, 0, scale * 0.95)
                        s2.set_alpha(50 * (4 - k2))
                        self.frame.blit(s2, s2.get_rect(center=ghost))
                renderer.draw_hero(self.frame, h, (sx, sy), display_angle, (vx, vy), ex, limb, t_anim + i, squash=sq if alive else 0,
                                   zoom=max(0.05, scale))
                if alive:
                    pills.append((h, sx, sy - h.radius * z - 18, bool(f & T.FAN_FAV)))
                if f & T.HAS_BOMB:
                    self._bomb(sx, sy - h.radius * z - 10, t_anim)
            else:
                e = self.extras[k]
                bl = "stunned" if f & T.STUNNED else ("airborne" if (f & T.AIRBORNE and self.tr.mode != "TOP_DOWN") else
                                                      ("running" if abs(vx) + abs(vy) > 40 else "idle"))
                if falling:
                    bl = "airborne"
                renderer.draw_extra(self.frame, e, (sx, sy), spin, ex, zoom=max(0.05, scale), limb_state=bl,
                                    t=t_anim + i * 0.37, vx=vx)
                if f & T.HAS_BOMB:
                    self._bomb(sx, sy - 22 * z, t_anim)
        self._pills(pills)

    def _bomb(self, x, y, t):
        pygame.draw.circle(self.frame, BLACK, (x, y - 14), 16)
        pygame.draw.line(self.frame, (160, 120, 80), (x + 8, y - 26), (x + 16, y - 38), 4)
        pygame.draw.circle(self.frame, (255, 200, 40) if int(t * 10) % 2 else (255, 80, 40), (x + 17, y - 40), 6)

    def _pills(self, pills) -> None:
        """Name pills 18 px above heads with a 3-iteration screen-space repulsion pass."""
        boxes = []
        for h, x, y, fan in pills:
            s = renderer.name_pill(h, crown=fan, size=22)
            boxes.append([s, x - s.get_width() / 2, y - s.get_height()])
        for _ in range(3):
            for a in range(len(boxes)):
                for b in range(a + 1, len(boxes)):
                    ra = pygame.Rect(boxes[a][1], boxes[a][2], boxes[a][0].get_width(), boxes[a][0].get_height())
                    rb = pygame.Rect(boxes[b][1], boxes[b][2], boxes[b][0].get_width(), boxes[b][0].get_height())
                    if ra.colliderect(rb):
                        dy = (ra.bottom - rb.top) / 2 + 1 if ra.centery <= rb.centery else -((rb.bottom - ra.top) / 2 + 1)
                        boxes[a][2] -= dy
                        boxes[b][2] += dy
        for s, x, y in boxes:
            y = max(LAYOUT["viewport"][0] + 4, min(y, LAYOUT["viewport"][1] - 40))
            self.frame.blit(s, (x, y))

    def draw_juice(self, cam: Cam, play_t: float, t_anim: float) -> None:
        """Popups, ghosts, sparks and dust from trace events near play_t."""
        for e in self.tr.events:
            age = play_t - e.t
            if age < 0 or age > 0.9 or e.pos is None:
                continue
            sx, sy = cam.to_screen(*e.pos)
            seed = int(e.t * 1000) % 997
            if e.kind == "elimination":
                gy = min(max(sy, LAYOUT["viewport"][0] + 80), LAYOUT["viewport"][1] - 60)
                gx = min(max(sx, 60), W - 60)
                col = renderer.hex_rgb(HERO_BY_KEY[e.actors[0]].colour) if e.actors[0] in HERO_BY_KEY else (230, 220, 200)
                effects.draw_ghost(self.frame, (gx, gy), age, col)
                if e.data.get("hero") and age < effects.POPUP_S:
                    word = "BETRAYAL!" if e.data.get("by_hero") else ("SPLAT!" if e.data.get("cause") == "lava" else "YEET!")
                    effects.draw_popup(self.frame, word, (gx, max(gy - 120, LAYOUT["viewport"][0] + 90)), age, seed)
            elif e.kind == "impact" and age < effects.POPUP_S and e.data.get("impulse", 0) > 900:
                effects.draw_sparks(self.frame, (sx, sy), age, seed)
                if e.data.get("hero_pair"):
                    effects.draw_popup(self.frame, "BONK!" if seed % 2 else "OOF!", (sx, sy - 90), age, seed)
            elif e.kind == "trait" and age < effects.POPUP_S:
                word = effects.CONTEXT_POPUPS.get(e.actors[0], "BOING!")
                effects.draw_popup(self.frame, word, (sx, sy - 110), age, seed)

    # ------------------------------------------------------------------ frame
    def _ranks(self, fi: int) -> dict[str, int]:
        """Live placement of every hero: survivors by course progress (SIDE) / closeness to the centre (TOP),
        then the eliminated in reverse order of elimination."""
        rows, flags = self.tr.frames[fi], self.tr.flags[fi]
        n = len(self.tr.keys)
        alive = [i for i in range(n) if flags[i] & T.ALIVE]
        if self.tr.mode == "TOP_DOWN":
            alive.sort(key=lambda i: rows[i, 0] ** 2 + rows[i, 1] ** 2)
        else:
            alive.sort(key=lambda i: -rows[i, 0])
        w = self.meta.get("winner")
        if w and flags[self.tr.index(w)] & T.WINNER:
            alive.sort(key=lambda i: self.tr.keys[i] != w)
        out_t = {}
        play_t = (fi - self.pre) / FPS
        for e in self.tr.events:
            if e.kind == "elimination" and e.t <= play_t:
                out_t[e.actors[0]] = e.t
        dead = sorted((i for i in range(n) if not flags[i] & T.ALIVE), key=lambda i: -out_t.get(self.tr.keys[i], 0))
        order = alive + dead
        return {self.tr.keys[i]: r + 1 for r, i in enumerate(order) if self.tr.keys[i] in HERO_BY_KEY}

    def tuno_state(self, play_t: float, segment: str) -> str:
        if segment in ("card", "replay"):
            return "crowning"
        for e in self.escalations:
            if 0 <= play_t - e.t < 1.0:
                return "lever"
        for e in self.tr.events:
            if e.kind == "elimination" and 0 <= play_t - e.t < 0.8:
                return "shocked" if e.data.get("hero") else "laughing"
        return "idle"

    def render_shot(self, shot: Shot, index: int) -> pygame.Surface:
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self.cams[fi]
        t_anim = index / FPS
        if shot.zoom_mult != 1.0 and shot.focus:
            i = self.tr.index(shot.focus)
            rows, _, _ = self.tr.sample(tf / FPS)
            cam = Cam(float(rows[i, 0]), float(rows[i, 1]), cam.zoom * shot.zoom_mult)
        if shot.segment == "tail":
            cam = self.cams[0]
            fi = 0
        play_t = (fi - self.pre) / FPS
        self.draw_world(cam, fi, t_anim)
        self.draw_contestants(cam, tf if shot.segment == "replay" else fi, t_anim)
        if shot.segment in ("play", "replay", "flash"):
            self.draw_juice(cam, play_t if shot.segment != "replay" else (tf - self.pre) / FPS, t_anim)
        if shot.segment == "replay":
            effects.draw_confetti(self.frame, shot.seg_t, 5, pygame.Rect(0, 330, W, 1320))
        self._overlays(shot, play_t, t_anim, fi)
        return self.frame

    def _overlays(self, shot: Shot, play_t: float, t_anim: float, fi: int) -> None:
        fr = self.frame
        flags = self.tr.flags[fi]
        alive = int(sum(1 for f in flags if f & T.ALIVE))
        total = len(self.tr.keys)
        status = {}
        for h in self.heroes:
            f = flags[self.tr.index(h.key)]
            status[h.key] = "crown" if f & T.WINNER else ("alive" if f & T.ALIVE else "out")
        recent = sum(1 for e in self.tr.events if e.kind == "elimination" and 0 <= play_t - e.t < 1.5)
        scenery.draw_header(fr, self.castle, self.ep.ep_label, self.tuno_state(play_t, shot.segment), t_anim,
                            hud.TEXT_BOXES)
        if shot.segment not in ("card",):
            scenery.draw_panel(fr, alive, total, self.heroes, status, self._ranks(fi), hud.TEXT_BOXES,
                               pulse=1.0 if recent >= 3 else 0.0)
        if shot.segment == "cold" or (shot.segment == "tail"):
            hud.draw_pick_your_fighter(fr, self.heroes, t_anim)
        if shot.segment == "play":
            for e in self.escalations:
                txt = e.data.get("banner") or ({"twist": e.data.get("twist", "").replace("_", " ").upper() + "!",
                                                "stage_final": "FINAL!"}.get(e.kind, ""))
                if txt:
                    hud.draw_banner(fr, txt, play_t - e.t)
        if shot.segment == "flash":
            hud.blit_text(fr, hud.outlined("COMING UP...", 60, fill=(255, 80, 80), width=6), center=(W / 2, 470))
        if shot.segment == "card":
            w = self.meta.get("winner")
            hero = HERO_BY_KEY.get(w) if w else None
            name = hero.name if hero else (f"Number {self.extras[w].number}" if w in self.extras else "Nobody")
            col = renderer.hex_rgb(hero.colour) if hero else (200, 180, 140)
            hud.draw_winner_card(fr, hero, name, col, self.ep.season_line or "+10 SEASON POINTS",
                                 self.ep.prompt or "Who wins tomorrow?", t_anim)
        if shot.segment == "tail":
            k = shot.seg_t / TIMELINE.loop_tail_s
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(60 * (1 - k))))
            fr.blit(veil, (0, 0))


def encode(ep: Episode, out: Path, audio: Path | None = None, stills: int = 0) -> dict:
    ep.shots = plan_shots(ep)
    r = Renderer(ep)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", VIDEO["preset"], "-crf", str(VIDEO["crf"]), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    boxes = []
    n = len(ep.shots)
    still_at = {int(n * k) for k in (0.01, 0.2, 0.45, 0.7, 0.86, 0.96)[:stills]} if stills else set()
    for i, shot in enumerate(ep.shots):
        frame = r.render_shot(shot, i)
        proc.stdin.write(pygame.image.tobytes(frame, "RGB"))
        if i in still_at:
            small = pygame.transform.smoothscale(frame, (W // 2, H // 2))
            pygame.image.save(small, str(out.with_name(f"{out.stem}_f{i:04d}.png")))
        if i % 15 == 0:
            boxes.append([tuple(b) for b in hud.TEXT_BOXES])
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return {"frames": len(ep.shots), "duration": len(ep.shots) / FPS, "text_boxes": boxes}
