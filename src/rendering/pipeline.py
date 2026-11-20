"""Render pipeline (§15, §4, v3.2): draws ONLY from the chosen trace and pipes raw RGB24 frames into ffmpeg.

Output timeline: cold-open teaser (0.8 s) -> gameplay -> 0.3x winner replay (1.5 s) -> game-show winner card (2.0 s).
Zero trailing cold-open flash frames.
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
from src.config import FPS, H, LAYOUT, TIMELINE, VIDEO, W, settings  # noqa: E402
from src.games.themes import THEME_BY_KEY, Theme  # noqa: E402
from src.physics import trace as T  # noqa: E402
from src.physics.camera import Cam, track  # noqa: E402
from src.rendering import balls, effects, hud, scenery  # noqa: E402

BLACK = (17, 17, 17)
WHITE_ = (255, 255, 255)
BANNER_S = 1.0
TRACK_MATS = ("ground", "ice", "mud", "bouncy", "conveyor", "plank")


@dataclass
class Shot:
    """One output frame: which trace frame (float for slow-mo) and what overlays are active."""
    tf: float
    segment: str                 # cold | play | replay | card
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


def plan_shots(ep: Episode, teaser_f: int | None = None) -> list[Shot]:
    """0.8 s cold-open teaser -> gameplay from gate retraction -> 0.3x winner replay -> 2.0 s game-show winner card.
    v3.2: Zero trailing loop-tail cold-open flash frames; video ends cleanly on the Winner Card."""
    tr = ep.trace
    pre = tr.meta.get("preroll_frames", 0)
    end_t = tr.meta.get("resolved_at") or (tr.n_frames - pre) / FPS
    end_f = min(tr.n_frames - 1, pre + int(round(end_t * FPS)))
    winner = tr.meta.get("winner")
    shots: list[Shot] = []
    n_cold = int(round(TIMELINE.cold_open_s * FPS))
    tz_mult = 1.0 if tr.mode == "TOP_DOWN" else 1.08
    if teaser_f is not None:
        src = 0.3 * FPS
        f0 = teaser_f - src * 0.55
        for i in range(n_cold):
            shots.append(Shot(max(pre, min(end_f, f0 + src * i / n_cold)), "cold", i / FPS, tz_mult, None))
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
    n_rep = int(round(TIMELINE.replay_s * FPS))
    for i in range(n_rep):
        shots.append(Shot(src0 + (end_f - src0) * i / max(1, n_rep), "replay", i / FPS, TIMELINE.replay_zoom, winner))
    n_card = int(round(TIMELINE.winner_card_s * FPS))
    for i in range(n_card):
        shots.append(Shot(end_f, "card", i / FPS))
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
        self.sky_bg, self.far_spires, self.mid_arches = scenery.parallax_layers(self.theme)
        self.castle = scenery.castle_header(self.theme)
        self.heroes = [HERO_BY_KEY[k] for k in self.meta["heroes"]]
        self.extras = {k: Extra(v["number"], v["colour"], cult=v["cult"]) for k, v in self.meta["extras"].items()}
        self.pre = self.meta.get("preroll_frames", 0)
        self.rng = random.Random(self.meta.get("seed", 0))
        self.escalations = [e for e in self.tr.events if e.kind in ("escalation", "twist", "stage_final", "reverse")]
        self.elims = sorted((e for e in self.tr.events if e.kind == "elimination"), key=lambda e: e.t)
        self.glitches = sorted((e for e in self.tr.events if e.kind == "glitch"), key=lambda e: e.t)
        self.overtime_t = next((e.t for e in self.escalations if e.data.get("overtime")), 999.0)
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
        self.world_rect = pygame.Rect(0, LAYOUT["viewport"][0], W, H - LAYOUT["viewport"][0])
        self.splat_wins: dict[str, list[float]] = {}
        for e in self.tr.events:
            if e.kind == "impact" and e.data.get("impulse", 0) > 450:
                for a in e.actors:
                    self.splat_wins.setdefault(a, []).append(e.t)
            elif e.kind == "elimination" and e.data.get("by_hero") and len(e.actors) > 1:
                self.splat_wins.setdefault(e.actors[0], []).append(e.t)
        self._lowest_slab_y = 0.0
        self._void = self._build_void() if self.tr.mode == "TOP_DOWN" else None
        self.finish_t = next((e.t for e in self.tr.events if e.kind in ("finish", "win")), None) \
            if self.meta.get("finish_x") is not None else None
        self.popups = self._schedule_popups()
        self.speech: list = []          # narration lines (set by the audio module): captions + MC Tuno lip-sync
        self.out_index: dict = {}       # output frame index -> output time (for captions)

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
        """v3.3 cold open: the frame where the most balls (>= 5 preferred) are packed together inside the middle 60% of
        the screen, ideally right on a big hero collision."""
        hits = {}
        for e in self.tr.events:
            if e.kind == "impact" and e.data.get("impulse", 0) > 500:
                f = self.pre + int(e.t * FPS)
                hits[f] = max(hits.get(f, 0), e.data.get("impulse", 0))
        best, bs = None, -1.0
        lo = self.pre + int(1.0 * FPS)
        hi = min(self.end_f - int(1.0 * FPS), len(self.cams) - 1)
        x_lo, x_hi = W * 0.2, W * 0.8
        vy0, vy1 = LAYOUT["viewport"]
        y_lo, y_hi = vy0 + (vy1 - vy0) * 0.2, vy1 - (vy1 - vy0) * 0.2
        for f in range(lo, max(lo + 1, hi), 2):
            cam = self.cams[f]
            pts = []
            for i in range(len(self.tr.keys)):
                if self.tr.flags[f][i] & T.ALIVE:
                    sx, sy = cam.to_screen(float(self.tr.frames[f][i][0]), float(self.tr.frames[f][i][1]))
                    if x_lo <= sx <= x_hi and y_lo <= sy <= y_hi:
                        pts.append((sx, sy))
            if not pts:
                continue
            dense = max(sum(1 for q in pts if math.hypot(q[0] - p[0], q[1] - p[1]) < 240) for p in pts)
            near_hit = max((hits.get(g, 0) for g in range(f - 4, f + 5)), default=0)
            sc = dense * 1000 + min(near_hit, 3000) * 0.2
            if sc > bs:
                best, bs = f, sc
        return best

    def _build_void(self) -> pygame.Surface:
        """v3.3 TOP_DOWN background: a deep abyss/moat void (radial gradient, faint ripple rings, drifting motes)."""
        s = pygame.Surface((W, H))
        cx, cy = W / 2, 970
        inner, outer = scenery.mix(self.theme.sky_top, (20, 18, 46), 0.75), (8, 8, 20)
        maxr = math.hypot(W, H) * 0.62
        for r in range(int(maxr), 0, -6):
            pygame.draw.circle(s, scenery.mix(inner, outer, min(1.0, r / maxr)), (cx, cy), r)
        for k, r in enumerate(range(520, 1100, 110)):
            pygame.draw.circle(s, scenery.mix(inner, (90, 110, 170), 0.10 + 0.04 * (k % 2)), (cx, cy), r, 2)
        rng = random.Random(5)
        for _ in range(70):
            x, y = rng.uniform(0, W), rng.uniform(260, H)
            pygame.draw.circle(s, scenery.mix(inner, (200, 220, 255), rng.uniform(0.15, 0.4)), (x, y), rng.choice((1, 2, 2, 3)))
        return s

    def _schedule_popups(self) -> list[tuple[float, str, tuple[float, float], int]]:
        """v3.3: comic starbursts ONLY for collisions visible on camera, max one every 0.65 s (no stacking).
        Returns (gameplay_t, word, world_pos, seed)."""
        cands = []
        for e in self.tr.events:
            if e.pos is None or e.t < 0.2:
                continue
            seed = int(e.t * 1000) % 997
            word = None
            pos = e.pos
            if e.kind == "elimination" and e.data.get("hero"):
                cause = e.data.get("cause", "")
                if e.data.get("by_hero"):
                    word = "BETRAYAL!"
                elif cause == "lava":
                    word = "SPLAT!"
                elif cause != "left_behind":
                    word = "YEET!"
                prio = 3
            elif e.kind == "impact" and e.data.get("hero_pair") and e.data.get("impulse", 0) > 900:
                word, prio = ("BONK!" if seed % 2 else "OOF!"), 1
            elif e.kind == "trait":
                word, prio = effects.CONTEXT_POPUPS.get(e.actors[0], "BOING!"), 2
            if word:
                cands.append((e.t, -prio, word, pos, seed))
        out: list[tuple[float, str, tuple[float, float], int]] = []
        last_t = -9.0
        for t, _, word, pos, seed in sorted(cands):
            f = min(len(self.cams) - 1, self.pre + int(t * FPS))
            if not self.cams[f].on_screen(pos[0], pos[1], pad=30):
                continue                                   # off-camera collision: drop silently
            if t - last_t < 0.65:
                continue
            out.append((t, word, pos, seed))
            last_t = t
        return out

    # ------------------------------------------------------------------ world drawing
    def _k(self, zone: dict) -> float:
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

    def _build_track_chains(self, removed: set) -> list[tuple[list[tuple[float, float]], list[str], list[float]]]:
        """Stitches consecutive SIDE_VIEW ground segments sharing endpoints into seamless track chains."""
        segs = [
            s for s in self.meta["statics"]
            if s["type"] == "seg" and s["mat"] in TRACK_MATS and s.get("id") not in removed
        ]
        chains: list[tuple[list[tuple[float, float]], list[str], list[float]]] = []
        for s in segs:
            a, b = (float(s["a"][0]), float(s["a"][1])), (float(s["b"][0]), float(s["b"][1]))
            if abs(b[0] - a[0]) < 1.0 and abs(b[1] - a[1]) < 1.0:
                continue
            mat = s["mat"]
            belt = float(s.get("belt", 0.0))
            if chains and math.hypot(chains[-1][0][-1][0] - a[0], chains[-1][0][-1][1] - a[1]) < 3.0:
                chains[-1][0].append(b)
                chains[-1][1].append(mat)
                chains[-1][2].append(belt)
            else:
                chains.append(([a, b], [mat], [belt]))
        return chains

    @staticmethod
    def _chain_y_at(pts: list[tuple[float, float]], wx: float) -> float | None:
        for i in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            if min(ax, bx) <= wx <= max(ax, bx) and abs(bx - ax) > 1e-3:
                return ay + (by - ay) * (wx - ax) / (bx - ax)
        return None

    def _draw_side_tracks(self, cam: Cam, removed: set, t_anim: float) -> None:
        """v3.2: Draws background vertical castle pillars / iron chains, then seamless stitched masonry/beam slabs."""
        chains = self._build_track_chains(removed)
        z = cam.zoom
        self._lowest_slab_y = 0.0
        # 1. Background supports (behind all track slabs). v3.3: sparse — pillars only under long slabs, >= 620 px apart;
        #    short step ledges hang from thin chains instead, so the lower half of the frame stays clean and open.
        placed: list[float] = []
        for pts, mats, _ in chains:
            x0, x1 = pts[0][0], pts[-1][0]
            span = x1 - x0
            if span < 90:
                continue
            short = span < 380
            if span < 700:
                support_xs = [(x0 + x1) * 0.5]
            else:
                step = 760.0
                first = math.ceil((x0 + 160.0) / step) * step
                support_xs = []
                wx = first
                while wx <= x1 - 160.0:
                    support_xs.append(wx)
                    wx += step
                if not support_xs:
                    support_xs = [(x0 + x1) * 0.5]
            for wx in support_xs:
                if any(abs(wx - px) < 620 for px in placed):
                    continue
                sx_test, _ = cam.to_screen(wx, 0)
                if sx_test < -90 or sx_test > W + 90:
                    continue
                wy = self._chain_y_at(pts, wx)
                if wy is None:
                    continue
                has_lower = any(
                    other_pts is not pts and (ly := self._chain_y_at(other_pts, wx)) is not None and wy + 45 < ly < wy + 720
                    for other_pts, _, _ in chains
                )
                sx, sy = cam.to_screen(wx, wy)
                placed.append(wx)
                if short or has_lower:
                    has_upper = any(
                        other_pts is not pts and (uy := self._chain_y_at(other_pts, wx)) is not None and wy - 360 < uy < wy - 30
                        for other_pts, _, _ in chains
                    )
                    if not has_upper:
                        scenery.draw_support_pillar(self.frame, sx, sy + 6 * z, max(LAYOUT["viewport"][0], sy - 200 * z),
                                                    z, self.theme, chain=True)
                else:
                    scenery.draw_support_pillar(self.frame, sx, sy + 56 * z, H, z, self.theme, chain=False)

        # 2. Stitched beveled architectural slabs
        for pts, mats, belts in chains:
            # Slice visible sub-range with 1-segment margin for clean off-screen joins
            vis_i = [
                i for i in range(len(pts) - 1)
                if max(cam.to_screen(*pts[i])[0], cam.to_screen(*pts[i + 1])[0]) > -120
                and min(cam.to_screen(*pts[i])[0], cam.to_screen(*pts[i + 1])[0]) < W + 120
            ]
            if not vis_i:
                continue
            i0, i1 = max(0, min(vis_i) - 1), min(len(pts) - 1, max(vis_i) + 2)
            sub_pts = [cam.to_screen(*p) for p in pts[i0: i1 + 1]]
            sub_mats = mats[i0:i1]
            sub_belts = belts[i0:i1]
            for _, py in sub_pts:
                self._lowest_slab_y = max(self._lowest_slab_y, py + 72 * z)
            scenery.draw_track_chain(self.frame, sub_pts, sub_mats, sub_belts, z, self.theme, t_anim)

    def _draw_drop_gate(self, cam: Cam, wx: float, wy: float, play_t: float) -> None:
        """v3.2: Compact mechanical castle portcullis gate that retracts smoothly upward at t = 0..0.38 s."""
        sx, sy = cam.to_screen(wx, wy)
        if sx < -120 or sx > W + 120:
            return
        z = cam.zoom
        lw = max(2, int(4 * z))
        lift = 0.0 if play_t <= 0.0 else min(1.0, play_t / 0.38)
        # Ease-out smooth mechanical lift
        lift_eased = 1.0 - (1.0 - lift) ** 2
        gate_h = 138 * z
        housing_h = 46 * z
        top_y = sy - gate_h - housing_h
        # Iron portcullis grate sliding upward into the stone gatehouse
        bar_bottom = sy - lift_eased * (gate_h - 14 * z)
        bar_top = top_y + 12 * z
        if bar_bottom > bar_top + 6:
            gw = max(12, int(24 * z))
            grate = pygame.Rect(int(sx - gw / 2), int(bar_top), gw, int(bar_bottom - bar_top))
            pygame.draw.rect(self.frame, BLACK, grate.inflate(6, 4), border_radius=4)
            pygame.draw.rect(self.frame, (78, 84, 102), grate, border_radius=3)
            # Warning gold/black stripes near bottom shoe of portcullis
            shoe_h = min(grate.height, max(8, int(18 * z)))
            pygame.draw.rect(self.frame, (255, 204, 36), (grate.left + 2, grate.bottom - shoe_h, grate.width - 4, shoe_h))
            pygame.draw.line(self.frame, BLACK, (grate.centerx, grate.top), (grate.centerx, grate.bottom), max(2, lw - 1))
        # Compact stone-and-iron overhead gatehouse arch + rotating brass gear
        hw = max(26, int(52 * z))
        house = pygame.Rect(int(sx - hw / 2), int(top_y), int(hw), int(housing_h))
        _, rock, dark, light = scenery.rock_colours(self.theme)
        pygame.draw.rect(self.frame, BLACK, house.inflate(lw * 2, lw * 2), border_radius=8)
        pygame.draw.rect(self.frame, rock, house, border_radius=6)
        pygame.draw.rect(self.frame, dark, (house.left, house.bottom - int(housing_h * 0.34), house.width, int(housing_h * 0.34)),
                         border_radius=4)
        # Mechanical gear wheel on gatehouse face
        gr = max(7, int(13 * z))
        gcx, gcy = house.centerx, house.centery
        ang0 = lift_eased * math.pi * 1.8
        for k in range(8):
            a = ang0 + k * math.pi / 4
            tx, ty = gcx + math.cos(a) * (gr + 4 * z), gcy + math.sin(a) * (gr + 4 * z)
            pygame.draw.line(self.frame, BLACK, (gcx, gcy), (tx, ty), max(3, int(6 * z)))
            pygame.draw.line(self.frame, (240, 192, 48), (gcx, gcy), (tx, ty), max(2, int(4 * z)))
        pygame.draw.circle(self.frame, BLACK, (gcx, gcy), gr + 2)
        pygame.draw.circle(self.frame, (240, 192, 48), (gcx, gcy), gr)
        pygame.draw.circle(self.frame, BLACK, (gcx, gcy), max(2, int(gr * 0.38)))

    def draw_world(self, cam: Cam, fi: int, t_anim: float, play_t: float) -> None:
        fr = self.frame
        th = self.theme
        zone = self.tr.zones[fi]
        removed = set(zone.get("removed_statics", []))

        if self.tr.mode == "TOP_DOWN":
            fr.blit(self._void, (0, 0))                 # v3.3: clean top-down abyss under the spinning disc
        else:
            # v3.2: 3-Layer Parallax Background
            for surf, factor in ((self.sky_bg, 0.04), (self.far_spires, 0.11), (self.mid_arches, 0.24)):
                par = (-cam.x * factor) % W
                fr.blit(surf, (par - W, 0))
                fr.blit(surf, (par, 0))

        fr.set_clip(self.world_rect)
        self._particles(cam, t_anim)
        z = cam.zoom
        if self.tr.mode == "TOP_DOWN":
            self._falling_bumpers(cam, fi, z)
            self.draw_contestants(cam, fi, t_anim, falling_only=True)
        # TOP_DOWN platforms
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
                    side = [(px, py + 18 * z) for px, py in pts]
                    pygame.draw.polygon(fr, BLACK, side)
                    pygame.draw.polygon(fr, scenery.mix(col, BLACK, 0.3), [(px, py - 3) for px, py in side])
                    pygame.draw.polygon(fr, col, pts)
                    pygame.draw.polygon(fr, BLACK, pts, 4)

        # SIDE_VIEW stitched architectural platforms & pillars
        if self.tr.mode == "SIDE_VIEW":
            self._draw_side_tracks(cam, removed, t_anim)

        # Remaining statics (walls, bumpers, finish flag, mechanical drop-gate)
        for s in self.meta["statics"]:
            if "id" in s and s["id"] in removed:
                continue
            if s["type"] == "seg":
                if s["mat"] in TRACK_MATS or s["mat"] == "gate":
                    continue
                a, b = cam.to_screen(*s["a"]), cam.to_screen(*s["b"])
                if max(a[0], b[0]) < -50 or min(a[0], b[0]) > W + 50:
                    continue
                if self.tr.mode == "SIDE_VIEW" and s["mat"] == "wall":
                    # v3.3: compact 130 px castle stone bumper instead of a sky-tall grey pole
                    wx = s["a"][0]
                    g = self._ground_seg_at(wx + 30) or self._ground_seg_at(wx - 30)
                    gy = g[0] if g is not None else max(s["a"][1], s["b"][1])
                    self._stone_bumper(cam, wx, gy)
                    continue
                col = scenery.rock_colours(th)[1] if s["mat"] == "wall" else th.terrain_outline
                w = max(6, int(s["r"] * 2 * z))
                pygame.draw.line(fr, BLACK, a, b, w + 8)
                pygame.draw.line(fr, col, a, b, w)
            elif s["type"] == "drop_gate":
                self._draw_drop_gate(cam, s["x"], s["y"], play_t)
            elif s["type"] == "poly":
                pts = self._poly_screen(cam, s["verts"])
                stone = scenery.rock_colours(th)[1]
                pygame.draw.polygon(fr, stone, pts)
                if len(pts) > 3:
                    pygame.draw.line(fr, scenery.mix(stone, WHITE_, 0.3), pts[2], pts[3], max(2, int(6 * z)))
                pygame.draw.polygon(fr, BLACK, pts, 5)
            elif s["type"] == "circle":
                c = cam.to_screen(*s["c"])
                rr = s["r"] * z
                pygame.draw.circle(fr, BLACK, c, rr + 4)
                pygame.draw.circle(fr, (235, 50, 75), c, rr)
                pygame.draw.circle(fr, WHITE_, c, rr * 0.62)
                pygame.draw.circle(fr, (255, 210, 40), c, rr * 0.34)
            elif s["type"] == "finish":
                self._finish(cam, s["x"], s["y"], t_anim, play_t)
            elif s["type"] in ("post", "pivot"):
                c = cam.to_screen(*s["c"])
                pygame.draw.circle(fr, BLACK, c, 13 * z)
                pygame.draw.circle(fr, (140, 148, 165), c, 9 * z)
        self._zones(cam, zone, t_anim)
        self._props(cam, fi)

    def _stone_bumper(self, cam: Cam, wx: float, gy: float) -> None:
        """Compact castle tower bumper (130 px tall) with crenellations and a dark arched door."""
        z = cam.zoom
        sx, sy = cam.to_screen(wx, gy)
        w, h = 70 * z, 130 * z
        _, rock, dark, light = scenery.rock_colours(self.theme)
        body = pygame.Rect(int(sx - w / 2), int(sy - h), int(w), int(h))
        pygame.draw.rect(self.frame, BLACK, body.inflate(8, 8), border_radius=6)
        pygame.draw.rect(self.frame, rock, body, border_radius=4)
        pygame.draw.rect(self.frame, dark, (body.right - int(w * 0.3), body.top, int(w * 0.3), body.height))
        for k in range(3):
            cr = pygame.Rect(int(body.left + k * w / 2.5), int(body.top - 16 * z), int(w / 4), int(18 * z))
            pygame.draw.rect(self.frame, BLACK, cr.inflate(6, 6))
            pygame.draw.rect(self.frame, rock, cr)
        for yy in range(int(body.top + 26 * z), body.bottom, max(10, int(26 * z))):
            pygame.draw.line(self.frame, dark, (body.left + 3, yy), (body.right - 3, yy), max(2, int(2 * z)))
        door = pygame.Rect(int(sx - w * 0.2), int(sy - h * 0.45), int(w * 0.4), int(h * 0.45))
        pygame.draw.rect(self.frame, (30, 26, 40), door, border_top_left_radius=int(w * 0.2), border_top_right_radius=int(w * 0.2))
        pygame.draw.line(self.frame, light, (body.left + 4, body.top + 2), (body.left + 4, body.bottom - 2), max(2, int(3 * z)))

    def _finish(self, cam: Cam, x: float, y: float, t: float, play_t: float = 0.0) -> None:
        """v3.3 pass-through finish gate: short checkered pylon + a red victory tape that snaps into two flapping halves
        with a confetti burst the moment the winner crosses (zero physical collision)."""
        z = cam.zoom
        top_y = y - 230
        a, b = cam.to_screen(x, top_y), cam.to_screen(x, y)
        sq = max(8.0, 20 * z)
        # checkered pylon set just behind the line
        px = a[0] + sq * 1.4
        for i in range(int((b[1] - a[1]) / sq) + 1):
            for j in range(2):
                col = BLACK if (i + j) % 2 else WHITE_
                pygame.draw.rect(self.frame, col, (px + j * sq - sq, a[1] + i * sq, sq + 1, sq + 1))
        pygame.draw.rect(self.frame, BLACK, (px - sq - 2, a[1] - 2, 2 * sq + 4, b[1] - a[1] + 4), 3)
        pygame.draw.circle(self.frame, BLACK, (px, a[1] - 10 * z), 12 * z)
        pygame.draw.circle(self.frame, (255, 208, 40), (px, a[1] - 10 * z), 9 * z)
        cross_t = self.finish_t
        lw = max(4, int(7 * z))
        if cross_t is None or play_t < cross_t:
            for k in range(int((b[1] - a[1]) / (14 * z)) + 1):          # taut red/white tape across the line
                y0 = a[1] + k * 14 * z
                pygame.draw.line(self.frame, (232, 40, 60) if k % 2 == 0 else WHITE_, (a[0], y0),
                                 (a[0], min(b[1], y0 + 14 * z)), lw)
            return
        age = play_t - cross_t
        if age > 1.6:
            return
        mid = (a[1] + b[1]) / 2
        for side in (-1, 1):                                              # two halves whip away and flutter down
            ang = side * (0.4 + age * 3.2)
            L = (b[1] - a[1]) / 2 * max(0.2, 1.0 - age * 0.4)
            ox = a[0] + age * 140 * z
            oy = mid + side * (b[1] - a[1]) / 4 + age * age * 240 * z
            pts = []
            for u in range(7):
                d = L * u / 6
                pts.append((ox + math.sin(ang) * d + math.sin(t * 22 + u) * 5 * z, oy + side * math.cos(ang) * d * 0.5))
            pygame.draw.lines(self.frame, (232, 40, 60), False, pts, lw)
        if age < 1.0:
            effects.draw_confetti(self.frame, age, 41, pygame.Rect(int(a[0] - 220 * z), int(a[1] - 160 * z),
                                                                     int(440 * z), int((b[1] - a[1]) + 160 * z)), n=40)

    # ------------------------------------------------------------------ diegetic surface modifiers (NO debug boxes!)
    def _ground_seg_at(self, x: float) -> tuple[float, float, float] | None:
        """Returns (y, ux, uy) on the active SIDE_VIEW track at world x, or None over a pit."""
        for s in self.meta["statics"]:
            if s["type"] == "seg" and s["mat"] in TRACK_MATS:
                (ax, ay), (bx, by) = s["a"], s["b"]
                if min(ax, bx) <= x <= max(ax, bx) and abs(bx - ax) > 1.0:
                    y = ay + (by - ay) * (x - ax) / (bx - ax)
                    L = math.hypot(bx - ax, by - ay)
                    return y, (bx - ax) / L, (by - ay) / L
        return None

    def ground_y(self, x: float) -> float:
        res = self._ground_seg_at(x)
        return res[0] if res is not None else 0.0

    def _draw_side_surface_mod(self, cam: Cam, key: str, x0: float, x1: float, t: float) -> None:
        """v3.2: Embeds boost chevrons (>>>), cracked glossy ice, or bubbling mud flush into sloped platforms."""
        fr, z = self.frame, cam.zoom
        if cam.to_screen(x1, 0)[0] < -60 or cam.to_screen(x0, 0)[0] > W + 60:
            return
        # Sample contiguous track runs across [x0, x1] (automatically skips pit gaps!)
        step_w = 24.0
        runs: list[list[tuple[float, float, float, float]]] = []
        wx = x0
        while wx <= x1:
            g = self._ground_seg_at(wx)
            if g is not None:
                sx, sy = cam.to_screen(wx, g[0])
                if not runs or (runs[-1] and abs(sy - runs[-1][-1][1]) > 22 * z):
                    runs.append([])
                runs[-1].append((sx, sy, g[1], g[2]))
            elif runs and runs[-1]:
                runs.append([])
            wx += step_w
        runs = [r for r in runs if len(r) >= 2]
        cap_w = max(8, int(18 * z))
        for run in runs:
            pts = [(p[0], p[1]) for p in run]
            if key == "boost_zones":
                # Sleek dark-slate flush booster pad + glowing animated >>> chevron arrows along the slope
                pygame.draw.lines(fr, BLACK, False, pts, cap_w + 8)
                pygame.draw.lines(fr, (32, 36, 58), False, pts, cap_w)
                # Animated scrolling chevrons (>>>)
                total_px = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
                sp_c = max(18.0, 32.0 * z)
                phase_px = (t * 170 * z) % sp_c
                n_chev = int(total_px / sp_c)
                for c_idx in range(n_chev):
                    target_d = c_idx * sp_c + phase_px
                    acc = 0.0
                    for i in range(len(pts) - 1):
                        seg_d = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                        if acc + seg_d >= target_d and seg_d > 1e-3:
                            u = (target_d - acc) / seg_d
                            cx_c = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u
                            cy_c = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u
                            ux, uy = run[i][2], run[i][3]
                            nx, ny = -uy, ux
                            d_len, h_len = 9 * z, 7 * z
                            chev = [
                                (cx_c - ux * d_len + nx * h_len, cy_c - uy * d_len + ny * h_len),
                                (cx_c + ux * d_len * 0.55, cy_c + uy * d_len * 0.55),
                                (cx_c - ux * d_len - nx * h_len, cy_c - uy * d_len - ny * h_len),
                            ]
                            glow_col = (0, 245, 255) if c_idx % 2 == 0 else (255, 224, 48)
                            pygame.draw.lines(fr, BLACK, False, chev, max(4, int(6 * z)))
                            pygame.draw.lines(fr, glow_col, False, chev, max(2, int(3.5 * z)))
                            break
                        acc += seg_d
            elif key == "ice_zones":
                pygame.draw.lines(fr, (20, 75, 120), False, pts, cap_w + 6)
                pygame.draw.lines(fr, (195, 244, 255), False, pts, cap_w)
                pygame.draw.lines(fr, WHITE_, False, [(x, y - cap_w * 0.22) for x, y in pts], max(2, cap_w // 4))
                for idx in range(0, len(pts), 2):
                    sx, sy = pts[idx]
                    if (idx + int(t * 5)) % 3 == 0:
                        sr = max(4, int(7 * z))
                        pygame.draw.line(fr, WHITE_, (sx - sr, sy - cap_w * 0.6), (sx + sr, sy - cap_w * 0.6), 2)
                        pygame.draw.line(fr, WHITE_, (sx, sy - cap_w * 0.6 - sr), (sx, sy - cap_w * 0.6 + sr), 2)
            elif key == "mud_zones":
                pygame.draw.lines(fr, (58, 34, 16), False, pts, cap_w + 8)
                pygame.draw.lines(fr, (118, 76, 38), False, pts, cap_w + 2)
                for idx, (sx, sy) in enumerate(pts):
                    br = max(3, int((4 + 2.5 * abs(math.sin(t * 4.5 + idx))) * z))
                    pygame.draw.circle(fr, (158, 108, 62), (sx, sy - cap_w * 0.25), br)
                    pygame.draw.circle(fr, (58, 34, 16), (sx, sy - cap_w * 0.25), br, 1)

    def _draw_top_surface_mod(self, cam: Cam, key: str, wx: float, wy: float, wr: float, zone: dict, t: float) -> None:
        """v3.3: comic surface textures on the Rotating Disc at FIXED world spots (0.45R-0.75R), clipped to the shrinking
        disc so they peel off the rim (cracked glossy ice, glossy scalloped mud puddle, flush chevron boost pad)."""
        z = cam.zoom
        clip_r = None
        if self.tr.mode == "TOP_DOWN":
            plat_r = self._platform_r(zone)
            if math.hypot(wx, wy) - wr > plat_r - 4 or wr < 6:
                return
            clip_r = plat_r * z
        scx, scy = cam.to_screen(wx, wy)
        r = max(12, int(wr * z))
        pad = 24
        fr = pygame.Surface((2 * r + 2 * pad, 2 * r + 2 * pad), pygame.SRCALPHA)
        cx = cy = r + pad
        lw = max(2, int(3.5 * z))

        if key == "ice_zones":
            # Crisp faceted/scalloped glossy ice patch + fracture lines + white sparkles
            pts = [
                (cx + math.cos(2 * math.pi * i / 14) * r * (1.0 if i % 2 == 0 else 0.91),
                 cy + math.sin(2 * math.pi * i / 14) * r * (1.0 if i % 2 == 0 else 0.91))
                for i in range(14)
            ]
            pygame.draw.polygon(fr, (24, 92, 145), [(px, py + 2) for px, py in pts])
            pygame.draw.polygon(fr, (192, 242, 255), pts)
            # Glossy white diagonal sheen stripes
            pygame.draw.line(fr, WHITE_, (cx - r * 0.52, cy - r * 0.18), (cx - r * 0.12, cy - r * 0.58), max(3, int(6 * z)))
            pygame.draw.line(fr, WHITE_, (cx - r * 0.35, cy + r * 0.35), (cx + r * 0.38, cy - r * 0.38), max(2, int(4 * z)))
            # Crisp ice crack lines
            crack = [(cx - r * 0.45, cy + r * 0.12), (cx - r * 0.08, cy + r * 0.02),
                     (cx + r * 0.18, cy + r * 0.28), (cx + r * 0.52, cy + r * 0.18)]
            pygame.draw.lines(fr, (75, 165, 215), False, crack, max(2, int(2.5 * z)))
            pygame.draw.line(fr, (75, 165, 215), (cx - r * 0.08, cy + r * 0.02), (cx + r * 0.15, cy - r * 0.35), 2)
            pygame.draw.polygon(fr, (24, 92, 145), pts, lw)
            # Twinkling white 4-point ice sparkles
            for idx, (ox, oy) in enumerate(((-0.38, -0.32), (0.36, -0.24), (0.05, 0.42))):
                if int(t * 5 + idx) % 3 != 0:
                    sx, sy = cx + ox * r, cy + oy * r
                    sr = max(4, int(7 * z))
                    pygame.draw.line(fr, WHITE_, (sx - sr, sy), (sx + sr, sy), 2)
                    pygame.draw.line(fr, WHITE_, (sx, sy - sr), (sx, sy + sr), 2)
        elif key == "mud_zones":
            # v3.3: flat glossy dark-brown scalloped puddle (no stray highlight line)
            lobes = [
                (cx + math.cos(a) * r * (0.86 + 0.14 * math.sin(i * 2.3 + wx * 0.05)),
                 cy + math.sin(a) * r * (0.86 + 0.14 * math.cos(i * 1.9 + wy * 0.05)))
                for i, a in enumerate(2 * math.pi * k / 10 for k in range(10))
            ]
            lobe_r = max(6, int(r * 0.34))
            for lx, ly in lobes:
                pygame.draw.circle(fr, (40, 22, 10), (lx, ly), lobe_r + lw)
            pygame.draw.circle(fr, (40, 22, 10), (cx, cy), int(r * 0.80) + lw)
            for lx, ly in lobes:
                pygame.draw.circle(fr, (88, 52, 24), (lx, ly), lobe_r)
            pygame.draw.circle(fr, (88, 52, 24), (cx, cy), int(r * 0.80))
            pygame.draw.ellipse(fr, (255, 236, 210, 70), (cx - r * 0.55, cy - r * 0.52, r * 0.62, r * 0.26))
            pygame.draw.ellipse(fr, (255, 236, 210, 45), (cx + r * 0.12, cy + r * 0.18, r * 0.30, r * 0.12))
            for j in range(3):
                ang = j * 2.1 + t * 0.7
                bx, by = cx + math.cos(ang) * r * 0.42, cy + math.sin(ang * 1.2) * r * 0.38
                br = max(3, int(r * 0.11 * (0.85 + 0.35 * math.sin(t * 5 + j * 1.7))))
                pygame.draw.circle(fr, (40, 22, 10), (bx, by), br + 2)
                pygame.draw.circle(fr, (118, 76, 40), (bx, by), br)
                pygame.draw.circle(fr, (230, 200, 160), (bx - br * 0.3, by - br * 0.3), max(1, int(br * 0.28)))
        elif key == "boost_zones":
            pygame.draw.circle(fr, BLACK, (cx, cy), r + lw)
            pygame.draw.circle(fr, (32, 36, 58), (cx, cy), r)
            pygame.draw.circle(fr, (0, 229, 255), (cx, cy), r - 3, max(2, int(3 * z)))
            shift = ((t * 4.0) % 1.0) * r * 0.25
            for j in (-1, 0, 1):
                ox = cx + j * r * 0.36 + shift - r * 0.12
                chev = [(ox - r * 0.14, cy - r * 0.34), (ox + r * 0.12, cy), (ox - r * 0.14, cy + r * 0.34)]
                col_c = (0, 245, 255) if (j + int(t * 6)) % 2 == 0 else (255, 220, 40)
                pygame.draw.lines(fr, BLACK, False, chev, max(4, int(6 * z)))
                pygame.draw.lines(fr, col_c, False, chev, max(2, int(3.5 * z)))
        ox_, oy_ = scx - cx, scy - cy
        if clip_r is not None:
            dsx, dsy = cam.to_screen(0, 0)
            mask = pygame.Surface(fr.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (dsx - ox_, dsy - oy_), max(1, clip_r - 3))
            fr.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        self.frame.blit(fr, (ox_, oy_))

    def _zones(self, cam: Cam, zone: dict, t: float) -> None:
        fr, z = self.frame, cam.zoom
        for key in ("ice_zones", "mud_zones", "boost_zones"):
            for zz in zone.get(key, []):
                if zz[0] == "rect":
                    self._draw_side_surface_mod(cam, key, float(zz[1]), float(zz[2]), t)
                else:
                    self._draw_top_surface_mod(cam, key, float(zz[1][0]), float(zz[1][1]), float(zz[2]), zone, t)
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
            if x > -80:
                top = LAYOUT["viewport"][0]
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
                pygame.draw.line(fr, WHITE_, (x, y), (x + 90, y), 4)
        for tl in zone.get("tiles_top", []):
            (cx, cy), r, st = tl
            if st == 2:
                continue
            k = self._k(zone)
            cx, cy, r = cx * k, cy * k, r * k
            c = cam.to_screen(cx, cy)
            col = (255, 80, 80) if st == 1 else WHITE_
            pygame.draw.circle(self.frame, col, (c[0] + (math.sin(t * 60) * 3 if st == 1 else 0), c[1]), r * z, 5)

    def _draw_seesaw(self, cam: Cam, x: float, y: float, ang: float, verts: list) -> None:
        """v3.2: Chunky wood-and-iron seesaw plank with bolted end-caps and a riveted cast-iron center gear hub."""
        z = cam.zoom
        lw = max(3, int(4.5 * z))
        ca, sa = math.cos(ang), math.sin(ang)
        cx_s, cy_s = cam.to_screen(x, y)
        # Iron fulcrum A-bracket anchored underneath center hub
        brk = [(cx_s - 20 * z, cy_s + 36 * z), (cx_s, cy_s), (cx_s + 20 * z, cy_s + 36 * z)]
        pygame.draw.polygon(self.frame, (64, 68, 84), brk)
        pygame.draw.polygon(self.frame, BLACK, brk, lw)

        # Chunky timber plank + shaded lower bevel
        pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in verts]
        pygame.draw.polygon(self.frame, (176, 122, 68), pts)
        # Wood grain lines along the plank
        xs_loc = [v[0] for v in verts]
        ys_loc = [v[1] for v in verts]
        hw, hh = max(xs_loc), max(ys_loc)
        for gy_k in (-0.35, 0.25):
            g0 = cam.to_screen(x + (-hw * 0.82) * ca - (hh * gy_k) * sa, y + (-hw * 0.82) * sa + (hh * gy_k) * ca)
            g1 = cam.to_screen(x + (hw * 0.82) * ca - (hh * gy_k) * sa, y + (hw * 0.82) * sa + (hh * gy_k) * ca)
            pygame.draw.line(self.frame, (132, 86, 44), g0, g1, max(2, int(2.5 * z)))
        # Bolted dark-iron end-caps on left and right tips
        cap_len = min(36.0, hw * 0.18)
        for sgn in (-1, 1):
            x_in, x_out = sgn * (hw - cap_len), sgn * hw
            cap_local = [(x_in, -hh), (x_out, -hh), (x_out, hh), (x_in, hh)]
            cap_pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in cap_local]
            pygame.draw.polygon(self.frame, (72, 78, 96), cap_pts)
            pygame.draw.polygon(self.frame, BLACK, cap_pts, max(2, lw - 1))
            rv = cam.to_screen(x + (sgn * (hw - cap_len * 0.5)) * ca, y + (sgn * (hw - cap_len * 0.5)) * sa)
            pygame.draw.circle(self.frame, (215, 222, 235), rv, max(2, int(3.5 * z)))
        pygame.draw.polygon(self.frame, BLACK, pts, lw)

        # Riveted center gear hub
        gr = max(12, int(22 * z))
        for k in range(10):
            ga = ang + k * math.pi / 5
            tx, ty = cx_s + math.cos(ga) * (gr + 6 * z), cy_s + math.sin(ga) * (gr + 6 * z)
            pygame.draw.line(self.frame, BLACK, (cx_s, cy_s), (tx, ty), max(4, int(8 * z)))
            pygame.draw.line(self.frame, (112, 118, 136), (cx_s, cy_s), (tx, ty), max(2, int(5 * z)))
        pygame.draw.circle(self.frame, BLACK, (cx_s, cy_s), gr + 3)
        pygame.draw.circle(self.frame, (86, 92, 110), (cx_s, cy_s), gr)
        for k in range(4):
            ra = ang + k * math.pi / 2 + math.pi / 4
            pygame.draw.circle(self.frame, (215, 222, 235),
                               (cx_s + math.cos(ra) * gr * 0.62, cy_s + math.sin(ra) * gr * 0.62), max(2, int(2.8 * z)))
        pygame.draw.circle(self.frame, BLACK, (cx_s, cy_s), max(4, int(gr * 0.38)) + 2)
        pygame.draw.circle(self.frame, (245, 198, 46), (cx_s, cy_s), max(3, int(gr * 0.36)))

    def _props(self, cam: Cam, fi: int) -> None:
        props = self.tr.props[fi]
        styles = self.meta["props"]
        th = self.theme
        for i, row in enumerate(props):
            if i >= len(styles) or row[2] <= -9000:
                continue
            x, y, ang = float(row[0]), float(row[1]), math.radians(float(row[2]))
            if not cam.visible(x, y, 420):
                continue
            st = styles[i]
            ca, sa = math.cos(ang), math.sin(ang)
            for sh in st["shapes"]:
                if sh["type"] == "circle" and st["style"] == "disc_marks":
                    falls = self.tr.zones[fi].get("bumper_falls", [])
                    b_idx = sum(1 for prev in st["shapes"][:st["shapes"].index(sh)] if prev.get("bumper"))
                    if b_idx < len(falls) and falls[b_idx] >= 0:
                        continue
                    ox, oy = sh["c"]
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
                    pygame.draw.circle(self.frame, WHITE_, (c[0] - sh["r"] * 0.35 * cam.zoom, c[1] - sh["r"] * 0.35 * cam.zoom),
                                       sh["r"] * 0.2 * cam.zoom)
                elif sh["type"] == "seg":
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in (sh["a"], sh["b"])]
                    if st["style"] == "disc_marks":
                        continue                 # v3.3: no thin spoke lines (read as stray artifacts over patches)
                    wd = int(sh["r"] * 2 * cam.zoom)
                    pygame.draw.line(self.frame, BLACK, pts[0], pts[1], wd + 8)
                    if st["style"] == "hammer":
                        pygame.draw.line(self.frame, (150, 95, 45), pts[0], pts[1], wd + 2)
                        for kk in (0.2, 0.5, 0.8):
                            bx = pts[0][0] + (pts[1][0] - pts[0][0]) * kk
                            by = pts[0][1] + (pts[1][1] - pts[0][1]) * kk
                            pygame.draw.circle(self.frame, (190, 195, 205), (bx, by), wd * 0.9 + 2)
                    else:
                        pygame.draw.line(self.frame, (245, 245, 245), pts[0], pts[1], wd)
                        nseg = 8
                        for kk in range(0, nseg, 2):
                            a0, a1 = kk / nseg, (kk + 1) / nseg
                            p0 = (pts[0][0] + (pts[1][0] - pts[0][0]) * a0, pts[0][1] + (pts[1][1] - pts[0][1]) * a0)
                            p1 = (pts[0][0] + (pts[1][0] - pts[0][0]) * a1, pts[0][1] + (pts[1][1] - pts[0][1]) * a1)
                            pygame.draw.line(self.frame, th.hazard, p0, p1, wd)
                elif st["style"] == "seesaw":
                    self._draw_seesaw(cam, x, y, ang, sh["verts"])
                else:
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in sh["verts"]]
                    if st["style"] == "hammer":
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
                    col = {"tile": th.terrain, "wall_block": th.castle}.get(st["style"], th.hazard)
                    pygame.draw.polygon(self.frame, col, pts)
                    pygame.draw.polygon(self.frame, BLACK, pts, 4)

    def _falling_bumpers(self, cam: Cam, fi: int, z: float) -> None:
        if self.disc_prop is None:
            return
        falls = self.tr.zones[fi].get("bumper_falls", [])
        if not falls:
            return
        row = self.tr.props[fi][self.disc_prop]
        x, y, ang = float(row[0]), float(row[1]), math.radians(float(row[2]))
        ca, sa = math.cos(ang), math.sin(ang)
        st = self.meta["props"][self.disc_prop]
        bshapes = [sh for sh in st["shapes"] if sh.get("bumper")]
        for sh, age in zip(bshapes, falls):
            if age < 0 or age > 0.55:
                continue
            ox, oy = sh["c"]
            wx, wy = x + ox * ca - oy * sa, y + ox * sa + oy * ca
            d = math.hypot(wx, wy) or 1.0
            sx, sy = cam.to_screen(wx + wx / d * 180 * age, wy + wy / d * 180 * age + 420 * age * age)
            rr = sh["r"] * z * max(0.15, 1.0 - 1.4 * age)
            pygame.draw.circle(self.frame, BLACK, (sx, sy), rr + 3)
            pygame.draw.circle(self.frame, (230, 40, 60), (sx, sy), rr)

    def _particles(self, cam: Cam, t: float) -> None:
        kind = self.theme.particles
        rng = random.Random(3)
        col = {"snow": (255, 255, 255), "embers": (255, 150, 60), "stars": (255, 255, 220), "bubbles": (200, 240, 255),
               "rain": (170, 190, 230), "sand": (240, 210, 150), "fireflies": (255, 240, 120), "sprinkles": (255, 120, 200),
               "wisps": (190, 255, 160), "sparks": (255, 210, 90), "clouds": (255, 255, 255), "pollen": (255, 236, 150)}[kind]
        for i in range(32):
            x0, y0 = rng.uniform(0, W), rng.uniform(330, 1600)
            sp = rng.uniform(20, 80)
            if kind in ("snow", "rain", "sprinkles"):
                y = (y0 + t * sp * (6 if kind == "rain" else 1.5)) % 1270 + 330
                x = (x0 - cam.x * 0.3) % W
            else:
                y = (y0 - t * sp) % 1270 + 330
                x = (x0 + math.sin(t + i) * 20 - cam.x * 0.3) % W
            if kind == "rain":
                pygame.draw.line(self.frame, col, (x, y), (x - 6, y + 22), 2)
            elif kind == "clouds":
                pygame.draw.ellipse(self.frame, col, (x, y, 60, 22))
            else:
                pygame.draw.circle(self.frame, col, (x, y), 3)

    # ------------------------------------------------------------------ contestants + elemental cues + juice
    def _glitch_state(self, fi: int) -> tuple[str, float]:
        t = (fi - self.pre) / FPS
        past = [e for e in self.glitches if e.t <= t]
        if not past:
            return "FEATHER", 99.0
        last = past[-1]
        return ("LEAD" if last.data.get("effect") == "lead" else "FEATHER"), (t - last.t)

    def _draw_elemental_cues(self, cam: Cam, fi: int, idx: int, hero, sx: float, sy: float, vx: float, vy: float,
                             ang: float, face: float, grounded: bool, t_anim: float) -> None:
        """v3.2: Distinct elemental trails & contact cues (Dash frost afterimages, Glitch 3-frame RGB split,
        Magneto electric grip sparks, Grumble slope grip ticks)."""
        z = cam.zoom
        spd = math.hypot(vx, vy)
        top = self.tr.mode == "TOP_DOWN"
        if hero.key == "dash" and spd > 195:
            # Crisp cyan frost/speed puck afterimage trail from recent trace frames + icy streak lines
            for step, al in ((3, 42), (2, 78), (1, 120)):
                pf = max(0, fi - step)
                px, py, pang = (float(v) for v in self.tr.frames[pf][idx][:3])
                psx, psy = cam.to_screen(px, py)
                balls.draw_ball(self.frame, hero, None, (psx, psy), pang, face, (0, 0), 0.0, "neutral", "none",
                                t_anim, z, scale=1.0 - 0.06 * step, alpha=al, tint=(0, 232, 255))
            ux, uy = -vx / max(1.0, spd), -vy / max(1.0, spd)
            nx, ny = -uy, ux
            for side in (-0.55, 0.55):
                x0 = sx + ux * 16 * z + nx * side * 18 * z
                y0 = sy + uy * 16 * z + ny * side * 18 * z
                pygame.draw.line(self.frame, (215, 252, 255), (x0, y0), (x0 + ux * 28 * z, y0 + uy * 28 * z), max(2, int(3 * z)))
        elif hero.key == "glitch":
            _, shift_age = self._glitch_state(fi)
            if 0.0 <= shift_age <= 3.5 / FPS:
                # Crisp 3-frame RGB chromatic ghosting split (Crimson left + Cyan right + scanline bar)
                jit = 11.0 * z
                balls.draw_ball(self.frame, hero, None, (sx - jit, sy - 3 * z), ang, face, (0, 0), 0.0, "dizzy", "none",
                                t_anim, z, alpha=165, tint=(255, 35, 65))
                balls.draw_ball(self.frame, hero, None, (sx + jit, sy + 3 * z), ang, face, (0, 0), 0.0, "dizzy", "none",
                                t_anim, z, alpha=165, tint=(0, 245, 255))
                pygame.draw.rect(self.frame, (0, 245, 255), (int(sx - 34 * z), int(sy - 4 * z), int(68 * z), max(2, int(4 * z))))
        elif hero.key == "magneto" and ((top and spd > 42) or (not top and grounded and spd > 75)):
            # Subtle cyan electric grip sparks under Magneto when resisting lateral/centrifugal push
            rr = hero.radius * z
            base_a = math.pi / 2 if not top else math.atan2(-vy, -vx)
            for k in (-1, 1):
                if int(t_anim * 18 + k) % 2 == 0:
                    a = base_a + k * 0.42
                    p0 = (sx + math.cos(a) * rr * 0.88, sy + math.sin(a) * rr * 0.88)
                    pm = (p0[0] + math.cos(a + 0.5) * 8 * z, p0[1] + math.sin(a + 0.5) * 8 * z)
                    p1 = (p0[0] + math.cos(a - 0.3) * 14 * z, p0[1] + math.sin(a - 0.3) * 14 * z)
                    pygame.draw.lines(self.frame, (90, 250, 255), False, [p0, pm, p1], max(2, int(2.5 * z)))
        elif hero.key == "grumble" and ((not top and grounded and spd > 70) or (top and spd > 65)):
            # Tiny dirt/rubber grip ticks under Grumble on slopes / spinning discs
            rr = hero.radius * z
            ux = -1.0 if vx >= 0 else 1.0
            for k in range(3):
                ph = ((t_anim * 14 + k * 0.37) % 1.0)
                gx = sx + ux * (6 + ph * 20) * z
                gy = (sy + rr * 0.92 - ph * 8 * z) if not top else (sy - vy / max(1.0, spd) * (10 + ph * 14) * z)
                col_g = (96, 68, 44) if k % 2 == 0 else (36, 98, 156)
                pygame.draw.circle(self.frame, col_g, (int(gx), int(gy)), max(2, int(3.2 * (1.0 - 0.5 * ph) * z)))

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
        g_phase, _ = self._glitch_state(fi)
        for i in order:
            k = keys[i]
            f = int(flags[i])
            x, y, ang, vx, vy, sq, w = (float(v) for v in rows[i][:7])
            alive = bool(f & T.ALIVE)
            falling = bool(f & T.FALLING)
            if falling_only != bool(falling and top):
                continue
            if not alive and not falling:
                continue
            if not cam.visible(x, y, 140):
                continue
            if falling and top:
                ft = sq * 0.45
                d = math.hypot(x, y) or 1.0
                x = x + (vx * 0.4 + x / d * 180) * ft
                y = y + (vy * 0.4 + y / d * 180) * ft + 700 * ft * ft
            sx, sy = cam.to_screen(x, y)
            hero = HERO_BY_KEY.get(k)
            extra = self.extras.get(k)
            ex = EXPRESSIONS[int(expr[i])]
            if alive and hero is not None and abs(w) > 9.0 and ex not in ("eliminated", "celebrating"):
                ex = "dizzy"
            scale, alpha = 1.0, 255
            if falling:
                scale = 1.0 - 0.85 * sq
                ang = ang + sq * 540
                alpha = int(255 * (1 - 0.4 * sq))
                if hero is None:
                    ex = "scared"
            if top and alive:
                scenery.shadow(self.frame, (sx, sy), balls.body_radius(hero, extra) * z)
            play_t = (fi - self.pre) / FPS
            heavy = any(0.0 <= play_t - ht <= 0.22 for ht in self.splat_wins.get(k, ()))
            grounded = not bool(f & T.AIRBORNE)
            over_drop = (not top) and (not grounded) and (vy > 420 or (hero is None and ex == "scared"))
            pose = balls.pose_for(falling, vy, over_drop, heavy, False)
            look = (max(-1.0, min(1.0, vx / 300)), max(-1.0, min(1.0, vy / 300)))
            face = float(self.face[min(fi, len(self.face) - 1)][i]) if alive else ang
            if alive and hero is not None:
                self._draw_elemental_cues(cam, fi, i, hero, sx, sy, vx, vy, ang, face, grounded, t_anim)
            balls.draw_ball(self.frame, hero, extra, (sx, sy), ang, face, (vx, vy), w, ex, pose, t_anim + i * 0.37, z,
                            squash=sq if alive else 0.0, scale=scale, alpha=alpha,
                            phase=g_phase if (hero and hero.key == "glitch") else "",
                            look=look)
            screen[k] = (sx, sy)
            if alive and hero is not None:
                pills.append((hero, sx, sy - hero.radius * z - 16, bool(f & T.FAN_FAV)))
            if f & T.HAS_BOMB:
                self._bomb(sx, sy - balls.body_radius(hero, extra) * z - 10, t_anim)
        if show_tags and not falling_only:
            self._pills(pills, ranks or {}, screen, fi)

    def _pills(self, pills, ranks: dict[str, int], screen: dict, fi: int) -> None:
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
            x = max(24, min(x, W - s.get_width() - 24))
            y = max(LAYOUT["viewport"][0] + 10, min(y, LAYOUT["captions"]["y"][0] - 40))
            self.frame.blit(s, (x, y))

    def _bomb(self, x, y, t):
        pygame.draw.circle(self.frame, BLACK, (x, y - 14), 16)
        pygame.draw.line(self.frame, (160, 120, 80), (x + 8, y - 26), (x + 16, y - 38), 4)
        pygame.draw.circle(self.frame, (255, 200, 40) if int(t * 10) % 2 else (255, 80, 40), (x + 17, y - 40), 6)

    def draw_juice(self, cam: Cam, play_t: float, t_anim: float, popups: bool = True) -> None:
        """v3.3: ghosts/sparks only for KOs that are actually on camera; comic starbursts only from the pre-scheduled,
        on-screen, non-stacking popup list (offset 70 px above the hit, clamped to x in [40, 1040])."""
        for e in self.tr.events:
            age = play_t - e.t
            if age < 0 or age > 0.9 or e.pos is None:
                continue
            sx, sy = cam.to_screen(*e.pos)
            visible = cam.on_screen(e.pos[0], e.pos[1], pad=10)
            seed = int(e.t * 1000) % 997
            if e.kind == "elimination":
                cause = e.data.get("cause", "")
                if cause in ("fell", "lava") and self.tr.mode == "SIDE_VIEW" and 0 <= sx <= W:
                    ky = self.meta.get("kill_y", e.pos[1])
                    iy = cam.to_screen(e.pos[0], ky)[1]
                    if iy < H - 20:
                        effects.draw_sparks(self.frame, (sx, max(iy, 320)), age, seed)
                elif cause == "fell" and self.tr.mode == "TOP_DOWN" and visible:
                    effects.draw_sparks(self.frame, (sx, sy), age, seed)
                if visible:
                    col = renderer.hex_rgb(HERO_BY_KEY[e.actors[0]].colour) if e.actors[0] in HERO_BY_KEY else (230, 220, 200)
                    effects.draw_ghost(self.frame, (sx, sy), age, col)
            elif e.kind == "impact" and age < effects.POPUP_S and e.data.get("impulse", 0) > 900 and visible:
                effects.draw_sparks(self.frame, (sx, sy), age, seed)
            elif e.kind == "heavy_land" and age < 0.28 and visible:
                effects.draw_corner_clunk(self.frame, (sx, sy), age, seed)
            elif e.kind == "glitch" and age < 0.32 and visible:
                effects.draw_pixel_sparks(self.frame, (sx, sy), age, seed, lead=(e.data.get("effect") == "lead"))
        if not popups:
            return
        for t0, word, pos, seed in self.popups:
            age = play_t - t0
            if 0 <= age < effects.POPUP_S and cam.on_screen(pos[0], pos[1], pad=10):
                sx, sy = cam.to_screen(*pos)
                effects.draw_popup(self.frame, word, (sx, sy - 70), age, seed)

    # ------------------------------------------------------------------ frame & Commentator Host state
    def _ranks(self, fi: int) -> dict[str, int]:
        rows, flags = self.tr.frames[fi], self.tr.flags[fi]
        alive_heroes = [i for i in range(len(self.tr.keys)) if (flags[i] & T.ALIVE) and self.tr.keys[i] in HERO_BY_KEY]
        if self.tr.mode == "TOP_DOWN":
            alive_heroes.sort(key=lambda i: rows[i, 0] ** 2 + rows[i, 1] ** 2)
        else:
            alive_heroes.sort(key=lambda i: -rows[i, 0])
        w = self.meta.get("winner")
        if w and w in HERO_BY_KEY and flags[self.tr.index(w)] & T.WINNER:
            alive_heroes.sort(key=lambda i: self.tr.keys[i] != w)
        return {self.tr.keys[i]: r + 1 for r, i in enumerate(alive_heroes)}

    def tuno_state(self, play_t: float, segment: str) -> tuple[str, str]:
        """v3.2/3.3: MC Tuno's 6 reaction poses + bottom-anchored micro-callout tags. The cold open is always HYPED."""
        if segment == "cold":
            return "HYPED_TALKING", "LET'S GO!"
        if segment in ("card", "replay"):
            return "TROPHY_CHEER", ("GG!" if segment == "replay" else "")
        recent = [e for e in self.elims if 0 <= play_t - e.t < 1.15]
        # 1. Multi-KO wipeout -> LAUGHING_TEARS
        for e in recent:
            if sum(1 for o in self.elims if e.t - 1.1 <= o.t <= e.t) >= 2:
                return "LAUGHING_TEARS", ("WIPEOUT!" if play_t - e.t < 0.85 else "")
        # 2. Betrayal / Hero-on-Hero KO -> SHOCKED_JAWDROP
        if any(e.data.get("hero") and e.data.get("by_hero") for e in recent):
            return "SHOCKED_JAWDROP", "NO WAY!"
        # 3. Dumb unforced fall / Dummy self-KO -> FACEPALM
        if recent and not recent[-1].data.get("by_hero") and recent[-1].data.get("cause") in ("fell", "lava"):
            tag = "OOF!" if recent[-1].data.get("hero") else "RIP!"
            return "FACEPALM", (tag if play_t - recent[-1].t < 0.8 else "")
        # 4. Overtime Chaos / Final 3 clutch -> SWEATING_INTENSE
        if play_t >= self.overtime_t:
            tag = "WHOA!" if (len(self.late_leads) >= 1 and any(0 <= play_t - lt < 0.85 for lt in self.late_leads)) else ""
            if 0 <= play_t - self.overtime_t < 0.9:
                tag = "WHOA!"
            return "SWEATING_INTENSE", tag
        # 5. Twist / Speed-up escalation -> HYPED_TALKING with callout
        for e in self.escalations:
            if 0.0 <= play_t - e.t < 0.75:
                return "HYPED_TALKING", "LET'S GO!"
        return "HYPED_TALKING", ""

    def render_shot(self, shot: Shot, index: int) -> pygame.Surface:
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self.cams[fi]
        t_anim = index / FPS
        cap = self.cams[min(self.pre, len(self.cams) - 1)].zoom * 2.6
        if shot.zoom_mult != 1.0 and shot.focus:
            i = self.tr.index(shot.focus)
            rows, _, _ = self.tr.sample(tf / FPS)
            cam = Cam(float(rows[i, 0]), float(rows[i, 1]), min(cam.zoom * shot.zoom_mult, cap))
        elif shot.zoom_mult != 1.0:
            cam = Cam(cam.x, cam.y, min(cam.zoom * shot.zoom_mult, cap), cam.shake)
        play_t = (fi - self.pre) / FPS
        hud_fi = {"replay": self.end_f, "card": self.end_f}.get(shot.segment, fi)
        ranks = self._ranks(hud_fi)
        slow = shot.segment in ("cold", "replay")
        self.frame.set_clip(None)
        self.draw_world(cam, fi, t_anim, 0.0 if shot.segment == "cold" else play_t)
        self.frame.set_clip(self.world_rect)
        self.draw_contestants(cam, tf if slow else fi, t_anim, ranks=ranks,
                              show_tags=shot.segment in ("play", "replay"))
        if shot.segment == "replay":
            effects.draw_confetti(self.frame, shot.seg_t, 5, self.world_rect)
        if shot.segment in ("play", "replay", "cold"):
            self.draw_juice(cam, play_t if not slow else (tf - self.pre) / FPS, t_anim, popups=shot.segment != "cold")
        if self.tr.mode == "SIDE_VIEW":
            self._abyss(cam, fi, t_anim)
        self.frame.set_clip(None)
        self._overlays(shot, play_t, t_anim, hud_fi, ranks, index / FPS)
        return self.frame

    def _abyss(self, cam: Cam, fi: int, t: float) -> None:
        """v3.2: Recessed dark pit trench in front of background pillars & below all track slabs (SIDE_VIEW only)."""
        fr, key = self.frame, self.theme.key
        ky = self.tr.zones[fi].get("lava_y", self.meta.get("kill_y", 500.0))
        y0 = int(cam.to_screen(0, ky)[1])
        # Keep pit trench recessed cleanly below active platforms so zero slab undersides clip behind spikes
        y0 = max(1540, int(self._lowest_slab_y + 28), min(1760, y0))
        y0 = min(1760, y0)

        # Recessed dark stone pit lip + deep abyss trench backdrop
        pygame.draw.rect(fr, BLACK, (0, y0 - 8, W, H - y0 + 8))
        pygame.draw.rect(fr, (54, 52, 74), (0, y0 - 6, W, 12))
        pygame.draw.rect(fr, (18, 16, 30), (0, y0 + 6, W, H - y0 - 6))

        if key in ("volcano", "desert", "clockwork", "jungle"):
            pygame.draw.rect(fr, (195, 48, 12), (0, y0 + 18, W, H - y0 - 18))
            pts = [(x, y0 + 18 + 10 * math.sin(t * 3.2 + x * 0.02)) for x in range(0, W + 20, 20)]
            pygame.draw.polygon(fr, (255, 112, 22), pts + [(W, H), (0, H)])
            pygame.draw.lines(fr, (255, 224, 92), False, pts, 5)
            for i in range(9):
                bx = (i * 131 + t * 32) % W
                by = y0 + 56 + 24 * math.sin(t * 2.4 + i)
                pygame.draw.circle(fr, (255, 204, 64), (bx, by), 9 + 3 * math.sin(t * 6 + i))
        else:
            # Layered metallic castle spikes recessed inside the dark pit trench
            for x in range(-8, W + 48, 52):
                btip = (x + 52, y0 + 16)
                pygame.draw.polygon(fr, (42, 46, 64), [(x + 26, y0 + 78), btip, (x + 78, y0 + 78)])
            for x in range(-20, W + 48, 52):
                tip = (x + 26, y0 + 4)
                pygame.draw.polygon(fr, BLACK, [(x - 3, y0 + 78), tip, (x + 55, y0 + 78)])
                pygame.draw.polygon(fr, (148, 156, 174), [(x + 3, y0 + 74), (tip[0], tip[1] + 8), (x + 49, y0 + 74)])
                pygame.draw.polygon(fr, (98, 106, 124), [(tip[0], tip[1] + 8), (x + 49, y0 + 74), (tip[0], y0 + 74)])
                pygame.draw.line(fr, (224, 232, 246), (tip[0] - 2, tip[1] + 12), (x + 11, y0 + 68), 3)
            pygame.draw.rect(fr, (26, 26, 40), (0, y0 + 74, W, H - y0 - 74))

    def _talking(self, out_t: float) -> bool | None:
        """MC Tuno lip-sync: mouth flaps only while a narrated word is being spoken (None = no narration track)."""
        if not self.speech:
            return None
        for ln in self.speech:
            if ln["t0"] <= out_t <= ln["t1"]:
                words = ln.get("words") or []
                if not words:
                    return True
                return any(w0 - 0.03 <= out_t <= w1 + 0.03 for w0, w1, _ in words)
        return False

    def _overlays(self, shot: Shot, play_t: float, t_anim: float, fi: int, ranks: dict[str, int],
                  out_t: float = 0.0) -> None:
        fr = self.frame
        flags = self.tr.flags[fi]
        alive = int(sum(1 for f in flags if (f & T.ALIVE) or (self.tr.mode == "TOP_DOWN" and (f & T.FALLING))))
        total = len(self.tr.keys)
        status = {}
        for h in self.heroes:
            f = flags[self.tr.index(h.key)]
            status[h.key] = "crown" if f & T.WINNER else ("alive" if f & T.ALIVE else "out")
        recent = sum(1 for e in self.tr.events if e.kind == "elimination" and 0 <= play_t - e.t < 1.5)
        t_st, t_sp = self.tuno_state(play_t, shot.segment)
        if shot.segment == "cold":
            scenery.draw_pick_strip(fr, self.heroes, t_anim, hud.TEXT_BOXES)
            hud.blit_text(fr, hud.fit_width(hud.outlined("WHO SURVIVES?", 84, fill=(255, 214, 0), width=8), hud.MAX_BANNER_W),
                          center=(W / 2, 520))
        elif shot.segment != "card":
            scenery.draw_panel(fr, alive, total, self.heroes, status, ranks, hud.TEXT_BOXES,
                               pulse=1.0 if recent >= 3 else 0.0)
        # Draw header + Commentator Booth Cam AFTER panel so bottom-anchored speech tags are always crisp on top
        scenery.draw_header(fr, self.castle, self.ep.ep_label, t_st, t_anim, hud.TEXT_BOXES, speech=t_sp,
                            talking=self._talking(out_t))

        if shot.segment == "play":
            for start, txt in self.banners:
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
        if self.speech:
            from src.rendering import captions
            captions.draw_caption(fr, self.speech, out_t, hud.TEXT_BOXES)


def encode(ep: Episode, out: Path, audio: Path | None = None, stills: int = 0, sound: bool = True) -> dict:
    r = Renderer(ep)
    ep.shots = plan_shots(ep, r.teaser_f)
    out.parent.mkdir(parents=True, exist_ok=True)
    snd_info: dict = {}
    if sound and audio is None:
        # M5: comedy commentary (Gemini/templated -> edge-tts) + procedural SFX + chiptune, mixed to -14 LUFS
        from src.audio.mix import build_soundtrack
        snd = build_soundtrack(r, ep, out.with_suffix(".wav"))
        audio = snd["wav"]
        r.speech = snd["speech"]
        snd_info = {k: v for k, v in snd.items() if k not in ("speech", "wav")}
        snd_info["lines"] = [ln["text"] for ln in snd["speech"]]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-"]
    if audio:
        lufs = settings()["audio"]["loudness_lufs"]
        cmd += ["-i", str(audio), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k",
                "-ar", "44100", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", VIDEO["preset"], "-crf", str(VIDEO["crf"]), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    boxes = []
    n = len(ep.shots)
    # Include the exact final frame (n - 1) when stills >= 6 so we can visually verify zero cold-open flash at end!
    pcts = (0.02, 0.16, 0.42, 0.68, 0.84, 1.0)[:stills]
    still_at = {min(n - 1, int((n - 1) * k)) for k in pcts} if stills else set()
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
    return {"frames": len(ep.shots), "duration": len(ep.shots) / FPS, "text_boxes": boxes, "sound": snd_info}
