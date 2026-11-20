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
from src.rendering import balls, effects, hud, scenery  # noqa: E402

BLACK = (17, 17, 17)
WHITE_ = (255, 255, 255)
BANNER_S = 1.0


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


def plan_shots(ep: Episode, teaser_f: int | None = None) -> list[Shot]:
    """0.8 s cold-open teaser (slow-mo of the cleanest big collision) -> gameplay from the gate drop -> 0.3x winner
    replay -> 1.6 s winner card -> loop tail back into the teaser composition."""
    tr = ep.trace
    pre = tr.meta.get("preroll_frames", 0)
    end_t = tr.meta.get("resolved_at") or (tr.n_frames - pre) / FPS
    end_f = min(tr.n_frames - 1, pre + int(round(end_t * FPS)))
    winner = tr.meta.get("winner")
    shots: list[Shot] = []
    n_cold = int(round(TIMELINE.cold_open_s * FPS))
    if teaser_f is not None:
        src = 0.3 * FPS                                  # 0.3 s of real time stretched over the 0.8 s teaser
        f0 = teaser_f - src * 0.55
        for i in range(n_cold):
            shots.append(Shot(max(pre, min(end_f, f0 + src * i / n_cold)), "cold", i / FPS, 1.3, None))
    else:
        for i in range(n_cold):
            shots.append(Shot(pre, "cold", i / FPS))
    hitstops = {pre + int(e.t * FPS) for e in tr.events
                if (e.kind == "elimination" and e.data.get("hero")) or (e.kind == "impact" and e.data.get("hero_pair")
                                                                       and e.data.get("impulse", 0) > 1600)}
    for f in range(pre, end_f + 1):
        shots.append(Shot(f, "play", (f - pre) / FPS))
        if f in hitstops:
            shots += [Shot(f, "play", (f - pre) / FPS)] * 2
    src0 = end_f - TIMELINE.replay_source_s * FPS
    n = int(TIMELINE.replay_s * FPS)
    for i in range(n):
        shots.append(Shot(src0 + (end_f - src0) * i / n, "replay", i / FPS, TIMELINE.replay_zoom, winner))
    for i in range(int(TIMELINE.winner_card_s * FPS)):
        shots.append(Shot(end_f, "card", i / FPS))
    for i in range(int(TIMELINE.loop_tail_s * FPS)):
        shots.append(Shot(shots[0].tf, "tail", i / FPS, shots[0].zoom_mult, None))
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
        self.escalations = [e for e in self.tr.events if e.kind in ("escalation", "twist", "stage_final", "reverse")]
        self.elims = sorted((e for e in self.tr.events if e.kind == "elimination"), key=lambda e: e.t)
        end_t = self.meta.get("resolved_at") or (self.tr.n_frames - self.pre) / FPS
        self.end_f = min(self.tr.n_frames - 1, self.pre + int(round(end_t * FPS)))
        self.end_t = end_t
        self.late_leads = [e.t for e in self.tr.events if e.kind == "lead_change" and e.t >= end_t - 3.0]
        self.banners = self._schedule_banners()
        self.face = self._face_angles()
        self.teaser_f = self._teaser_frame()
        self.disc_prop = next((i for i, p in enumerate(self.meta["props"]) if p["style"] == "disc_marks"), None)
        self.tag_events = [(e.t, set(e.actors)) for e in self.tr.events
                           if e.kind == "lead_change" or (e.kind == "elimination" and e.data.get("by_hero"))]
        self.world_rect = pygame.Rect(0, scenery.PANEL.bottom, W, H - scenery.PANEL.bottom)

    # ------------------------------------------------------------------ precomputed presentation state
    def _schedule_banners(self) -> list[tuple[float, str]]:
        """Single-slot banner queue: one centre banner at a time, >= 0.8 s apart, stale ones dropped."""
        out: list[tuple[float, str]] = []
        free_at = -9.0
        for e in sorted(self.escalations, key=lambda e: e.t):
            txt = e.data.get("banner") or {"twist": e.data.get("twist", "").replace("_", " ").upper() + "!",
                                           "stage_final": "FINAL!", "reverse": "REVERSED!"}.get(e.kind, "")
            if not txt or (out and out[-1][1] == txt and e.t - out[-1][0] < 6.0):
                continue
            start = max(e.t, free_at)
            if start - e.t > 1.5:
                continue
            out.append((start, txt))
            free_at = start + BANNER_S + 0.8
        return out

    def _face_angles(self):
        """Spring-damped face tilt (+-35 deg, leans with motion, kicks on impacts); free spin above 9 rad/s."""
        import numpy as np
        n = len(self.tr.keys)
        out = np.zeros((self.tr.n_frames, n), np.float32)
        fa = np.zeros(n)
        fv = np.zeros(n)
        w, dt = 11.0, 1 / FPS
        for f in range(self.tr.n_frames):
            rows = self.tr.frames[f]
            target = np.clip(rows[:, 3] * 0.045 + rows[:, 5] * 25 * np.sign(rows[:, 3] + 1e-6), -35, 35)
            spin = np.abs(rows[:, 6]) > 9.0
            e = np.exp(-w * dt)
            d = fa - target
            tmp = (fv + w * d) * dt
            fa = target + (d + tmp) * e
            fv = (fv - w * tmp) * e
            fa = np.where(spin, rows[:, 2], fa)
            out[f] = fa
        return out

    def _teaser_frame(self) -> int | None:
        """Cleanest high-impact hero collision for the cold open (chase wall covering < 15% of the frame)."""
        best, bs = None, -1.0
        for e in self.tr.events:
            if e.kind != "impact" or not e.data.get("hero_pair") or e.t < 1.0 or e.t > self.end_t - 1.0:
                continue
            f = self.pre + int(e.t * FPS)
            cam = self.cams[min(f, len(self.cams) - 1)]
            chase = self.tr.zones[f].get("chase_x")
            if chase is not None and cam.to_screen(chase, 0)[0] > W * 0.15:
                continue
            sc = e.data.get("impulse", 0)
            if sc > bs:
                best, bs = f, sc
        if best is None:
            el = [e for e in self.elims if e.data.get("hero") and 1.0 <= e.t <= self.end_t - 1.0]
            if el:
                best = self.pre + int(el[0].t * FPS)
        return best

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
    def _k(self, zone: dict) -> float:
        """TOP_DOWN walkable scale = escalation edge creep x shrinking-arena twist (matches the physics exactly)."""
        return zone.get("edge_k", 1.0) * zone.get("shrink", 1.0)

    def _platform_r(self, zone: dict) -> float:
        for s in self.meta["statics"]:
            if s["type"] == "disc":
                return s["r"] * self._k(zone)
            if s["type"] == "ring":
                return zone.get("ring_r", s["r"]) * self._k(zone)
            if s["type"] == "square":
                return s["half"] * self._k(zone)
            if s["type"] == "hex_grid":
                return 430 * self._k(zone)
        return 1e9

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
        fr.set_clip(self.world_rect)               # world geometry/props never bleed into the castle/HUD band
        self._particles(cam, t_anim)
        z = cam.zoom
        if self.tr.mode == "TOP_DOWN":            # eliminated balls tumble down BEHIND the platform
            self.draw_contestants(cam, fi, t_anim, falling_only=True)
        # top-down platforms
        for s in self.meta["statics"]:
            if s["type"] == "disc":
                k = self._k(zone)
                spin = float(self.tr.props[fi][self.disc_prop][2]) if self.disc_prop is not None else 0.0
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), s["r"] * z * k, z, th, spin_deg=spin)
            elif s["type"] == "ring":
                r = zone.get("ring_r", s["r"]) * self._k(zone)
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), r * z, z, th)
                pygame.draw.circle(fr, th.accent, cam.to_screen(*s["c"]), r * z, max(3, int(6 * z)))
            elif s["type"] == "square":
                k = self._k(zone)
                scenery.draw_floating_platform(fr, cam.to_screen(0, 0), 0, z, th, "square", s["half"] * k * z)
            elif s["type"] == "hex_grid":
                states = zone.get("tiles", [0] * len(s["tiles"]))
                k = self._k(zone)
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
                    wx, wy = zz[1]
                    wr = zz[2]
                    if self.tr.mode == "TOP_DOWN":     # keep puddles/boost pads on the (shrinking) platform
                        k = self._k(zone)
                        wx, wy, wr = wx * k, wy * k, wr * k
                        room = self._platform_r(zone) - math.hypot(wx, wy)
                        wr = min(wr, room)
                        if wr < 12:
                            continue
                    c = cam.to_screen(wx, wy)
                    r = int(wr * z)
                    surf = pygame.Surface((2 * r + 8, 2 * r + 8), pygame.SRCALPHA)
                    o = r + 4
                    pygame.draw.circle(surf, col, (o, o), r)
                    edge = (255, 255, 255, 200) if key != "mud_zones" else (70, 45, 20, 230)
                    pygame.draw.circle(surf, edge, (o, o), r, 5)
                    if key == "mud_zones":           # bubbling mud puddle (not a hole)
                        for j in range(5):
                            a = j * 1.3 + t * 0.8
                            bx, by = o + math.cos(a) * r * 0.55, o + math.sin(a * 1.3) * r * 0.45
                            pygame.draw.circle(surf, (160, 115, 70, 230), (bx, by), max(3, r * 0.1 * (1 + 0.3 * math.sin(t * 4 + j))))
                    elif key == "boost_zones":
                        for j in (-1, 0, 1):
                            pygame.draw.lines(surf, (255, 140, 0, 255), False,
                                              [(o - r * 0.25, o + j * r * 0.35 - r * 0.15), (o + r * 0.1, o + j * r * 0.35),
                                               (o - r * 0.25, o + j * r * 0.35 + r * 0.15)], 5)
                    fr.blit(surf, (c[0] - o, c[1] - o))
        if "lava_y" in zone:
            y = cam.to_screen(0, zone["lava_y"])[1]
            if y < H:
                pygame.draw.rect(fr, (255, 90, 20), (0, y, W, H - y))
                for i in range(12):
                    bx = (i * 97 + t * 40) % W
                    pygame.draw.circle(fr, (255, 200, 60), (bx, y + 10 + 6 * math.sin(t * 5 + i)), 14)
                pygame.draw.line(fr, (255, 230, 120), (0, y), (W, y), 6)
        if "chase_x" in zone:                    # collapsing floor: a jagged animated wall of fire
            x = cam.to_screen(zone["chase_x"], 0)[0]
            if x > -80:
                top = scenery.PANEL.bottom
                pts = [(0, top)]
                for i in range(int((H - top) / 40) + 2):
                    yy = top + i * 40
                    jag = 34 + 22 * math.sin(t * 9 + i * 1.7) + (26 if i % 2 else 0)
                    pts.append((x + jag, yy))
                pts += [(0, H)]
                pygame.draw.polygon(fr, (120, 20, 10), pts)
                inner = [(px - 26 if px > 0 else 0, py) for px, py in pts]
                pygame.draw.polygon(fr, (240, 90, 20), inner)
                core = [(px - 52 if px > 0 else 0, py) for px, py in pts]
                pygame.draw.polygon(fr, (255, 200, 60), core)
                pygame.draw.lines(fr, BLACK, False, pts[1:-1], 5)
                for i in range(10):
                    ey = top + ((i * 157 + t * 260) % (H - top))
                    pygame.draw.circle(fr, (255, 220, 120), (x + 40 + 18 * math.sin(t * 5 + i), ey), 5)
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
            k = self._k(zone)                       # holes scale with the platform, exactly like the physics
            cx, cy, r = cx * k, cy * k, r * k
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
                if sh["type"] == "circle" and st["style"] == "disc_marks":   # pinball bumpers riding the disc
                    k = self._k(self.tr.zones[fi])
                    ox, oy = sh["c"][0] * k, sh["c"][1] * k
                    c = cam.to_screen(x + ox * ca - oy * sa, y + ox * sa + oy * ca)
                    rr = sh["r"] * cam.zoom
                    pygame.draw.circle(self.frame, BLACK, c, rr + 4)
                    pygame.draw.circle(self.frame, (230, 40, 60), c, rr)
                    pygame.draw.circle(self.frame, WHITE_, c, rr * 0.62)
                    pygame.draw.circle(self.frame, (230, 40, 60), c, rr * 0.36)
                    continue
                if sh["type"] == "circle":
                    ox, oy = sh["c"]
                    c = cam.to_screen(x + ox * ca - oy * sa, y + ox * sa + oy * ca)
                    col = {"boulder": (130, 110, 100), "cannonball": (40, 40, 50), "giant_ball": (255, 77, 166)}.get(st["style"], th.hazard)
                    pygame.draw.circle(self.frame, BLACK, c, sh["r"] * cam.zoom + 4)
                    pygame.draw.circle(self.frame, col, c, sh["r"] * cam.zoom)
                    pygame.draw.circle(self.frame, (255, 255, 255), (c[0] - sh["r"] * 0.35 * cam.zoom, c[1] - sh["r"] * 0.35 * cam.zoom), sh["r"] * 0.2 * cam.zoom)
                elif sh["type"] == "seg":
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in (sh["a"], sh["b"])]
                    if st["style"] == "disc_marks":     # spokes shrink with the platform
                        k = self._k(self.tr.zones[fi])
                        pts = [cam.to_screen(x + (px * ca - py * sa) * k, y + (px * sa + py * ca) * k)
                               for px, py in (sh["a"], sh["b"])]
                        pygame.draw.line(self.frame, scenery.mix(th.terrain, BLACK, 0.25), pts[0], pts[1], 4)
                        continue
                    wd = int(sh["r"] * 2 * cam.zoom)
                    pygame.draw.line(self.frame, BLACK, pts[0], pts[1], wd + 8)
                    if st["style"] == "hammer":                  # wooden shaft with steel bands
                        pygame.draw.line(self.frame, (150, 95, 45), pts[0], pts[1], wd + 2)
                        for kk in (0.2, 0.5, 0.8):
                            bx = pts[0][0] + (pts[1][0] - pts[0][0]) * kk
                            by = pts[0][1] + (pts[1][1] - pts[0][1]) * kk
                            pygame.draw.circle(self.frame, (190, 195, 205), (bx, by), wd * 0.9 + 2)
                    else:                                        # striped hazard bar
                        pygame.draw.line(self.frame, (245, 245, 245), pts[0], pts[1], wd)
                        nseg = 8
                        for kk in range(0, nseg, 2):
                            a0, a1 = kk / nseg, (kk + 1) / nseg
                            p0 = (pts[0][0] + (pts[1][0] - pts[0][0]) * a0, pts[0][1] + (pts[1][1] - pts[0][1]) * a0)
                            p1 = (pts[0][0] + (pts[1][0] - pts[0][0]) * a1, pts[0][1] + (pts[1][1] - pts[0][1]) * a1)
                            pygame.draw.line(self.frame, th.hazard, p0, p1, wd)
                else:
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in sh["verts"]]
                    if st["style"] == "hammer":                  # iron spiked mace head
                        mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
                        rr = 34 * cam.zoom
                        spikes = []
                        for kk in range(16):
                            a = ang + kk * math.pi / 8
                            spikes.append((mx + math.cos(a) * rr * (1.45 if kk % 2 == 0 else 0.95),
                                           my + math.sin(a) * rr * (1.45 if kk % 2 == 0 else 0.95)))
                        pygame.draw.polygon(self.frame, BLACK, spikes)
                        pygame.draw.polygon(self.frame, (150, 155, 165), [(mx + (sx - mx) * 0.86, my + (sy - my) * 0.86) for sx, sy in spikes])
                        pygame.draw.circle(self.frame, BLACK, (mx, my), rr + 3)
                        pygame.draw.circle(self.frame, (90, 95, 108), (mx, my), rr)
                        pygame.draw.circle(self.frame, (200, 205, 215), (mx - rr * 0.35, my - rr * 0.35), rr * 0.25)
                        continue
                    col = {"seesaw": (170, 120, 70), "tile": th.terrain, "wall_block": th.castle}.get(st["style"], th.hazard)
                    pygame.draw.polygon(self.frame, col, pts)
                    if st["style"] == "seesaw":
                        for kk in range(1, 6):
                            a = kk / 6
                            p0 = (pts[0][0] + (pts[1][0] - pts[0][0]) * a, pts[0][1] + (pts[1][1] - pts[0][1]) * a)
                            p1 = (pts[3][0] + (pts[2][0] - pts[3][0]) * a, pts[3][1] + (pts[2][1] - pts[3][1]) * a)
                            pygame.draw.line(self.frame, (110, 70, 35), p0, p1, 3)
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
    def draw_contestants(self, cam: Cam, tf: float, t_anim: float, focus_winner: bool = False,
                         ranks: dict[str, int] | None = None, falling_only: bool = False,
                         show_tags: bool = True) -> None:
        if abs(tf - round(tf)) > 1e-6:
            rows, flags, expr = self.tr.sample(tf / FPS)
            fi = int(tf)
        else:
            fi = int(round(tf))
            rows, flags, expr = self.tr.frames[fi], self.tr.flags[fi], self.tr.expr[fi]
        keys = self.tr.keys
        z = cam.zoom
        top = self.tr.mode == "TOP_DOWN"
        order = sorted(range(len(keys)), key=lambda i: (keys[i] in HERO_BY_KEY, flags[i] & T.WINNER))
        pills = []
        screen = {}
        for i in order:
            k = keys[i]
            f = int(flags[i])
            x, y, ang, vx, vy, sq, w = (float(v) for v in rows[i][:7])
            alive = f & T.ALIVE
            falling = f & T.FALLING
            if falling_only != bool(falling and top):
                continue
            if not alive and not falling:
                continue
            if not cam.visible(x, y, 140):
                continue
            sx, sy = cam.to_screen(x, y)
            hero = HERO_BY_KEY.get(k)
            extra = self.extras.get(k)
            ex = EXPRESSIONS[int(expr[i])]
            if alive and abs(w) > 9.0 and ex not in ("eliminated", "celebrating"):
                ex = "dizzy"
            scale, alpha = 1.0, 255
            if falling:                       # TOP_DOWN fall: shrink 1.0 -> 0.12 and spin down behind the platform
                scale = 1.0 - 0.88 * sq
                ang = ang + sq * 540
                alpha = int(255 * (1 - 0.4 * sq))
            if top and alive:
                scenery.shadow(self.frame, (sx, sy), balls.body_radius(hero, extra) * z)
            pose = balls.pose_for(bool(alive), not (f & T.AIRBORNE), (vx, vy), w, sq if alive else 0.0,
                                  bool(f & T.VICTORY), bool(hero and hero.key in ("grumble", "magneto")), top)
            if falling:
                pose = "flail"
            spd = math.hypot(vx, vy)
            look = (max(-1.0, min(1.0, vx / 300)), max(-1.0, min(1.0, vy / 300)))
            face = float(self.face[min(fi, len(self.face) - 1)][i]) if alive else ang
            if hero and hero.key == "dash" and spd > 400 and alive:        # ice-puck skid trail
                for j in (3, 2, 1):
                    pygame.draw.circle(self.frame, (200, 250, 255), (sx - vx * 0.012 * j * z, sy - vy * 0.012 * j * z),
                                       max(2, 6 * z / j))
            balls.draw_ball(self.frame, hero, extra, (sx, sy), ang, face, (vx, vy), w, ex, pose, t_anim + i * 0.37, z,
                            squash=sq if alive else 0.0, scale=scale, alpha=alpha,
                            phase="LEAD" if (hero and hero.key == "glitch" and self._glitch_lead(fi)) else "",
                            look=look)
            screen[k] = (sx, sy)
            if alive and hero is not None:
                pills.append((hero, sx, sy - hero.radius * z - 16, bool(f & T.FAN_FAV)))
            if f & T.HAS_BOMB:
                self._bomb(sx, sy - balls.body_radius(hero, extra) * z - 10, t_anim)
        if show_tags and not falling_only:
            self._pills(pills, ranks or {}, screen, fi)

    def _glitch_lead(self, fi: int) -> bool:
        t = (fi - self.pre) / FPS
        last = [e for e in self.tr.events if e.kind == "glitch" and e.t <= t]
        return bool(last and last[-1].data.get("effect") == "lead")

    def _pills(self, pills, ranks: dict[str, int], screen: dict, fi: int) -> None:
        """Smart name tags: only at 1.0-2.5 s, for 1.2 s around a lead change / betrayal, and in the final 3; hidden
        whenever 3+ balls cluster within 115 px so faces stay readable."""
        play_t = (fi - self.pre) / FPS
        alive_n = int(sum(1 for f in self.tr.flags[fi] if f & T.ALIVE))
        recent = set()
        for t, actors in self.tag_events:
            if 0 <= play_t - t < 1.2:
                recent |= actors
        window = 1.0 <= play_t <= 2.5
        pts = list(screen.values())
        boxes = []
        for h, x, y, fan in pills:
            if not (window or alive_n <= 3 or h.key in recent):
                continue
            sx, sy = screen[h.key]
            if sum(1 for px, py in pts if math.hypot(px - sx, py - sy) < 115) >= 3:
                continue
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
            y = max(scenery.PANEL.bottom + 6, min(y, LAYOUT["captions"]["y"][0] - 40))
            self.frame.blit(s, (x, y))

    def _bomb(self, x, y, t):
        pygame.draw.circle(self.frame, BLACK, (x, y - 14), 16)
        pygame.draw.line(self.frame, (160, 120, 80), (x + 8, y - 26), (x + 16, y - 38), 4)
        pygame.draw.circle(self.frame, (255, 200, 40) if int(t * 10) % 2 else (255, 80, 40), (x + 17, y - 40), 6)

    def draw_juice(self, cam: Cam, play_t: float, t_anim: float) -> None:
        """Popups, ghosts, sparks and dust from trace events near play_t."""
        for e in self.tr.events:
            age = play_t - e.t
            if age < 0 or age > 0.9 or e.pos is None:
                continue
            sx, sy = cam.to_screen(*e.pos)
            seed = int(e.t * 1000) % 997
            if e.kind == "elimination":
                gy = min(max(sy, scenery.PANEL.bottom + 80), LAYOUT["captions"]["y"][0] - 40)
                gx = min(max(sx, 60), W - 60)
                col = renderer.hex_rgb(HERO_BY_KEY[e.actors[0]].colour) if e.actors[0] in HERO_BY_KEY else (230, 220, 200)
                effects.draw_ghost(self.frame, (gx, gy), age, col)
                if e.data.get("hero") and age < effects.POPUP_S:
                    word = "BETRAYAL!" if e.data.get("by_hero") else ("SPLAT!" if e.data.get("cause") == "lava" else "YEET!")
                    effects.draw_popup(self.frame, word, (gx, max(gy - 120, scenery.PANEL.bottom + 90)), age, seed)
            elif e.kind == "impact" and age < effects.POPUP_S and e.data.get("impulse", 0) > 900:
                effects.draw_sparks(self.frame, (sx, sy), age, seed)
                if e.data.get("hero_pair"):
                    effects.draw_popup(self.frame, "BONK!" if seed % 2 else "OOF!", self._pop_xy(sx, sy - 90), age, seed)
            elif e.kind == "trait" and age < effects.POPUP_S:
                word = effects.CONTEXT_POPUPS.get(e.actors[0], "BOING!")
                effects.draw_popup(self.frame, word, self._pop_xy(sx, sy - 110), age, seed)

    @staticmethod
    def _pop_xy(x: float, y: float) -> tuple[float, float]:
        # above the HUD bar's bottom edge and clear of the caption band / platform UI below
        return min(max(x, 150), W - 150), min(max(y, scenery.PANEL.bottom + 90), LAYOUT["captions"]["y"][0] - 70)

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
        """Lord Tuno reacts to the real trace: lever just BEFORE every twist/escalation banner, belly laugh on
        multi-eliminations (3+ within 1 s), shock on betrayals and photo finishes."""
        if segment in ("card", "replay"):
            return "crowning"
        for e in self.escalations:
            if -0.6 <= play_t - e.t < 0.5:
                return "lever"
        recent = [e for e in self.elims if 0 <= play_t - e.t < 1.2]
        if any(e.data.get("hero") and e.data.get("by_hero") for e in recent):
            return "shocked"
        for e in recent:
            if sum(1 for o in self.elims if e.t - 1.0 <= o.t <= e.t) >= 3:
                return "laughing"
        if len(self.late_leads) >= 2 and self.end_t - 2.5 <= play_t <= self.end_t:
            return "shocked"
        if recent and play_t - recent[-1].t < 0.7:
            return "shocked" if recent[-1].data.get("hero") else "laughing"
        return "idle"

    def render_shot(self, shot: Shot, index: int) -> pygame.Surface:
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self.cams[fi]
        t_anim = index / FPS
        cap = self.cams[min(self.pre, len(self.cams) - 1)].zoom * 2.6     # keep sprites crisp
        if shot.zoom_mult != 1.0 and shot.focus:
            i = self.tr.index(shot.focus)
            rows, _, _ = self.tr.sample(tf / FPS)
            cam = Cam(float(rows[i, 0]), float(rows[i, 1]), min(cam.zoom * shot.zoom_mult, cap))
        elif shot.zoom_mult != 1.0:
            cam = Cam(cam.x, cam.y, min(cam.zoom * shot.zoom_mult, cap), cam.shake)
        play_t = (fi - self.pre) / FPS
        # HUD never runs backwards: replay/card show the final state
        hud_fi = {"replay": self.end_f, "card": self.end_f}.get(shot.segment, fi)
        ranks = self._ranks(hud_fi)
        slow = shot.segment in ("cold", "tail", "replay")
        self.frame.set_clip(None)
        self.draw_world(cam, fi, t_anim)
        self.frame.set_clip(self.world_rect)             # nothing in the world may bleed into the castle/HUD band
        self.draw_contestants(cam, tf if slow else fi, t_anim, ranks=ranks,
                              show_tags=shot.segment in ("play", "replay"))
        if shot.segment == "replay":
            effects.draw_confetti(self.frame, shot.seg_t, 5, self.world_rect)
        if shot.segment in ("play", "replay", "cold"):
            self.draw_juice(cam, play_t if not slow else (tf - self.pre) / FPS, t_anim)
        self._abyss(t_anim)
        self.frame.set_clip(None)
        self._overlays(shot, play_t, t_anim, hud_fi, ranks)
        return self.frame

    def _abyss(self, t: float) -> None:
        """Themed lethal abyss along the bottom edge (lava / iron spikes / storm clouds); keeps y 1440-1620 clear."""
        fr, key = self.frame, self.theme.key
        y0 = 1640
        if key in ("volcano", "desert", "clockwork", "jungle"):
            pygame.draw.rect(fr, (200, 50, 10), (0, y0, W, H - y0))
            pts = [(x, y0 + 12 * math.sin(t * 3 + x * 0.02)) for x in range(0, W + 20, 20)]
            pygame.draw.polygon(fr, (255, 110, 20), pts + [(W, H), (0, H)])
            pygame.draw.lines(fr, (255, 220, 90), False, pts, 6)
            for i in range(9):
                bx = (i * 131 + t * 30) % W
                by = y0 + 50 + 30 * math.sin(t * 2 + i)
                pygame.draw.circle(fr, (255, 200, 60), (bx, by), 10 + 4 * math.sin(t * 6 + i))
        elif key in ("haunted", "ice", "meadow", "candy"):
            pygame.draw.rect(fr, (40, 40, 52), (0, y0 + 50, W, H - y0))
            for x in range(-20, W + 40, 56):
                tip = (x + 28, y0 - 6)
                pygame.draw.polygon(fr, BLACK, [(x - 4, y0 + 56), tip, (x + 60, y0 + 56)])
                pygame.draw.polygon(fr, (150, 155, 170), [(x + 4, y0 + 52), (tip[0], tip[1] + 10), (x + 52, y0 + 52)])
                pygame.draw.line(fr, (220, 225, 235), (tip[0] - 3, tip[1] + 16), (x + 14, y0 + 48), 3)
        else:
            pygame.draw.rect(fr, (50, 44, 80), (0, y0 + 30, W, H - y0))
            for i in range(10):
                cx = (i * 120 + t * 60 * (1 if i % 2 else -1)) % (W + 200) - 100
                pygame.draw.circle(fr, (80, 72, 120), (cx, y0 + 40 + (i % 3) * 25), 70)
                pygame.draw.circle(fr, (110, 100, 160), (cx + 20, y0 + 30 + (i % 3) * 25), 46)
            if int(t * 3) % 4 == 0:
                bx = (int(t * 3) * 271) % W
                pygame.draw.lines(fr, (255, 240, 120), False, [(bx, y0 + 20), (bx + 20, y0 + 60), (bx - 5, y0 + 80),
                                                               (bx + 25, y0 + 130)], 5)

    def _overlays(self, shot: Shot, play_t: float, t_anim: float, fi: int, ranks: dict[str, int]) -> None:
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
        if shot.segment in ("cold", "tail"):             # pick-your-fighter strip replaces the bar, off the action
            scenery.draw_pick_strip(fr, self.heroes, t_anim, hud.TEXT_BOXES)
            hud.blit_text(fr, hud.outlined("WHO SURVIVES?", 84, fill=(255, 214, 0), width=8), center=(W / 2, 520))
        elif shot.segment != "card":
            scenery.draw_panel(fr, alive, total, self.heroes, status, ranks, hud.TEXT_BOXES,
                               pulse=1.0 if recent >= 3 else 0.0)
        if shot.segment == "play":
            for start, txt in self.banners:              # single slot: at most one centre banner at a time
                if 0 <= play_t - start < BANNER_S:
                    hud.draw_banner(fr, txt, (play_t - start) * 1.2 / BANNER_S)
                    break
        if shot.segment == "card":
            w = self.meta.get("winner")
            hero = HERO_BY_KEY.get(w) if w else None
            name = hero.name if hero else (f"Number {self.extras[w].number}" if w in self.extras else "Nobody")
            col = renderer.hex_rgb(hero.colour) if hero else (200, 180, 140)
            hud.draw_winner_card(fr, hero, name, col, self.ep.season_line or "+10 SEASON POINTS",
                                 self.ep.prompt or "Who wins tomorrow?", shot.seg_t, bot=self.extras.get(w) if w else None)
        if shot.segment == "tail":
            k = shot.seg_t / TIMELINE.loop_tail_s
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(60 * (1 - k))))
            fr.blit(veil, (0, 0))


def encode(ep: Episode, out: Path, audio: Path | None = None, stills: int = 0) -> dict:
    r = Renderer(ep)
    ep.shots = plan_shots(ep, r.teaser_f)
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
