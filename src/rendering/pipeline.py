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
from typing import Any

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
REACTION_BEAT_S = 0.45       # v4.3 live beat after the decisive moment before replay/confetti/card


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
    outcome: Any = None
    league_ctx: dict[str, Any] = field(default_factory=dict)


def plan_shots(ep: Episode, teaser_f: int | None = None) -> list[Shot]:
    """v5.0: instant-action cold open (<= 1.2-1.5 s) -> gameplay -> immediate 1.5 s 0.3x slow-motion finish + confetti
    on the exact finish-line crossing frame (zero post-finish wall bouncing!) -> Winner Card (2.5-3.0 s)."""
    tr = ep.trace
    pre = tr.meta.get("preroll_frames", 0)
    end_t = tr.meta.get("resolved_at") or (tr.n_frames - pre) / FPS
    finish_won = bool(tr.meta.get("finish_won")) or any(e.kind == "finish" for e in tr.events)
    if finish_won:
        # P0.1: Cut to 0.3x slow-mo + confetti on the EXACT finish-line crossing frame (zero dead-air bouncing!)
        end_f = min(tr.n_frames - 1, pre + int(round(end_t * FPS)))
    else:
        end_f = min(tr.n_frames - 1, pre + int(round((end_t + 0.25) * FPS)))
    winner = tr.meta.get("winner")
    shots: list[Shot] = []
    for f in range(pre):
        shots.append(Shot(f, "cold", f / FPS))
    hitstops = {pre + int(e.t * FPS) for e in tr.events
                if (e.kind == "elimination" and e.data.get("hero")) or (e.kind == "impact" and e.data.get("hero_pair")
                                                                       and e.data.get("impulse", 0) > 1600)}
    for f in range(pre, end_f + 1):
        shots.append(Shot(f, "play", (f - pre) / FPS))
        if f in hitstops and f < end_f:
            shots += [Shot(f, "play", (f - pre) / FPS)] * 2
    n_rep = int(round(TIMELINE.replay_s * FPS))
    if finish_won:
        src0 = max(float(pre), end_f - TIMELINE.replay_source_s * 0.78 * FPS)
        src1 = min(float(tr.n_frames - 1), end_f + TIMELINE.replay_source_s * 0.22 * FPS)
    else:
        src0 = max(float(pre), end_f - TIMELINE.replay_source_s * FPS)
        src1 = float(end_f)
    for i in range(n_rep):
        shots.append(Shot(src0 + (src1 - src0) * i / max(1, n_rep), "replay", i / FPS, TIMELINE.replay_zoom, winner))
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
        if not self.ep.ep_label:
            from src.state import league
            lctx = self.ep.league_ctx or {}
            s_no = int(lctx.get("season_number") or getattr(self.ep.outcome, "season_number", 0) or 1)
            e_no = int(lctx.get("episode_number") or getattr(self.ep.outcome, "race_number", 0) or 1)
            arena_lbl = str(self.meta.get("recipe", {}).get("arena", "race")).replace("_", " ").upper()
            self.ep.ep_label = league.header_label(s_no, e_no, arena_lbl)
        self.theme: Theme = THEME_BY_KEY[self.meta["recipe"]["theme"]]
        self.finale: bool = bool(self.meta["recipe"].get("finale"))
        self.cams = track(self.tr)
        self.frame = pygame.Surface((W, H))
        self.sky_bg, self.far_spires, self.mid_arches = scenery.parallax_layers(self.theme, finale=self.finale)
        self.castle = scenery.castle_header(self.theme)
        self.heroes = [HERO_BY_KEY[k] for k in self.meta["heroes"]]
        self.extras = {
            k: Extra(v["number"], v["colour"], cult=v["cult"], golden=bool(v.get("golden", False)))
            for k, v in self.meta["extras"].items()
        }
        self.pre = self.meta.get("preroll_frames", 0)
        self.rng = random.Random(self.meta.get("seed", 0))
        self.escalations = [e for e in self.tr.events if e.kind in ("escalation", "twist", "stage_final", "reverse")]
        self.lever_times = sorted(
            e.t for e in self.escalations
            if e.kind in ("twist", "reverse")
            or any(k in str(e.data.get("banner", "")).upper() for k in ("SPEED UP", "SHRINKING", "REVERSED", "OVERTIME"))
        )
        self.elims = sorted((e for e in self.tr.events if e.kind == "elimination"), key=lambda e: e.t)
        self.glitches = sorted((e for e in self.tr.events if e.kind == "glitch"), key=lambda e: e.t)
        self.glitch_blinks = sorted((e for e in self.tr.events if e.kind == "glitch_blink"), key=lambda e: e.t)
        self.overtime_t = next((e.t for e in self.escalations if e.data.get("overtime")), 999.0)
        end_t = self.meta.get("resolved_at") or (self.tr.n_frames - self.pre) / FPS
        self.end_f = min(self.tr.n_frames - 1, self.pre + int(round(end_t * FPS)))
        self.end_t = end_t
        self.late_leads = [e.t for e in self.tr.events if e.kind == "lead_change" and e.t >= end_t - 3.0]
        self.is_photo_finish = self._detect_photo_finish()
        self._monotonic_alive = self._build_monotonic_alive()
        self._running_min_alive = len(self.tr.keys)
        self.banners = self._schedule_banners()
        self.face = self._face_angles()
        self.teaser_f = self._teaser_frame()
        self.disc_prop = next((i for i, p in enumerate(self.meta["props"]) if p["style"] == "disc_marks"), None)
        self.bridge_prop_indices = [i for i, p in enumerate(self.meta["props"]) if p["style"] == "bridge_tile"]
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
        self.speech: list = []                  # narration lines: borderless 2-4 word pop captions
        self.voice_rms: list[float] | None = None  # per-frame 33ms isolated voice RMS for MC Tuno lip-sync
        self.out_index: dict = {}               # output frame index -> output time (for captions)

    def _build_monotonic_alive(self) -> list[int]:
        """P0.5: Persistent `eliminated_ids: set[str]` per match. Once eliminated, a character NEVER returns;
        live count is strictly `total_racers - len(eliminated_ids)` (monotonically non-increasing)."""
        eliminated_ids: set[str] = set()
        total = len(self.tr.keys)
        counts: list[int] = []
        elim_by_t = [(e.t, e.actors[0]) for e in self.elims if e.actors]
        ei = 0
        for fi in range(self.tr.n_frames):
            play_t = (fi - self.pre) / FPS
            while ei < len(elim_by_t) and elim_by_t[ei][0] <= play_t + 1e-4:
                eliminated_ids.add(elim_by_t[ei][1])
                ei += 1
            flags = self.tr.flags[fi]
            for idx, k in enumerate(self.tr.keys):
                if not (flags[idx] & T.ALIVE):
                    eliminated_ids.add(k)
            counts.append(max(0, total - len(eliminated_ids)))
        return counts

    def _alive_at(self, fi: int, segment: str) -> int:
        c = self._monotonic_alive[min(max(0, fi), len(self._monotonic_alive) - 1)]
        if segment == "cold":
            self._running_min_alive = len(self.tr.keys)
            return len(self.tr.keys)
        if segment == "play":
            self._running_min_alive = min(self._running_min_alive, c)
            return self._running_min_alive
        # During slow-mo replay / card, never tick upward above the lowest count already reached!
        return self._running_min_alive

    def _detect_photo_finish(self) -> bool:
        fx = self.meta.get("finish_x")
        rows, flags = self.tr.frames[self.end_f], self.tr.flags[self.end_f]
        alive_h = [i for i in range(len(self.tr.keys)) if (flags[i] & T.ALIVE) and self.tr.keys[i] in HERO_BY_KEY]
        if fx is not None and len(alive_h) >= 2:
            xs = sorted((float(rows[i, 0]) for i in alive_h), reverse=True)
            if xs[0] - xs[1] <= 75.0:
                return True
        if any(t >= self.end_t - 1.2 for t in self.late_leads):
            return True
        return False

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
        """v4.2 theme-matched TOP_DOWN depths under the floating platform (no generic starfield)."""
        st = getattr(self.theme, "block_style", "royal")
        pal = {
            "royal": ((26, 92, 120), (8, 30, 52), (120, 200, 230)),       # castle moat water
            "frost": ((150, 205, 235), (30, 60, 110), (240, 252, 255)),   # icy crevasse
            "obsidian": ((70, 20, 14), (14, 6, 8), (255, 110, 30)),       # cracked glowing basalt magma
            "neon": ((30, 10, 70), (6, 2, 18), (0, 230, 255)),            # cyber grid abyss
            "moss": ((30, 58, 82), (8, 16, 30), (150, 200, 240)),         # swirling storm waters
            "gothic": ((48, 60, 46), (12, 10, 22), (150, 255, 130)),      # misty swamp
            "sandstone": ((196, 120, 60), (70, 30, 16), (255, 210, 140)), # desert canyon
            "wafer": ((250, 170, 210), (170, 80, 140), (255, 245, 250)),  # frosting pool
        }
        inner, outer, acc = pal.get(st, pal["royal"])
        s = pygame.Surface((W, H))
        cx, cy = W / 2, 970
        maxr = math.hypot(W, H) * 0.62
        for r in range(int(maxr), 0, -6):
            pygame.draw.circle(s, scenery.mix(inner, outer, min(1.0, r / maxr)), (cx, cy), r)
        rng = random.Random(5 + len(st))
        if st in ("royal", "moss", "wafer"):
            # concentric water / frosting ripple rings + swirl arcs
            for k, r in enumerate(range(500, 1150, 70)):
                pygame.draw.circle(s, scenery.mix(inner, acc, 0.16 + 0.05 * (k % 2)), (cx, cy), r, 3)
            for _ in range(26):
                rr = rng.uniform(480, 1000)
                a0 = rng.uniform(0, 6.28)
                rect = pygame.Rect(int(cx - rr), int(cy - rr), int(rr * 2), int(rr * 2))
                pygame.draw.arc(s, scenery.mix(inner, acc, 0.35), rect, a0, a0 + rng.uniform(0.2, 0.6), 4)
            if st == "royal":   # castle courtyard flagstone rim at the frame edges
                for y in range(0, H, 64):
                    for x in (0, W - 70):
                        pygame.draw.rect(s, (118, 118, 132), (x + (y // 64 % 2) * 6, y, 64, 60), border_radius=6)
                        pygame.draw.rect(s, (70, 70, 84), (x + (y // 64 % 2) * 6, y, 64, 60), 3, border_radius=6)
        elif st == "obsidian":
            for _ in range(34):   # glowing lava cracks through dark basalt
                x, y = rng.uniform(0, W), rng.uniform(260, H)
                pts = [(x, y)]
                for _k in range(5):
                    x += rng.uniform(-60, 60)
                    y += rng.uniform(-50, 50)
                    pts.append((x, y))
                pygame.draw.lines(s, (255, 90, 20), False, pts, 6)
                pygame.draw.lines(s, (255, 210, 90), False, pts, 2)
        elif st == "frost":
            for _ in range(28):   # white ice fracture lines
                x, y = rng.uniform(0, W), rng.uniform(260, H)
                pygame.draw.line(s, acc, (x, y), (x + rng.uniform(-140, 140), y + rng.uniform(-140, 140)), 3)
        elif st == "neon":
            for gx in range(0, W, 60):
                pygame.draw.line(s, scenery.mix(inner, acc, 0.35), (gx, 260), (gx, H), 2)
            for gy in range(260, H, 60):
                pygame.draw.line(s, scenery.mix(inner, (255, 48, 192), 0.3), (0, gy), (W, gy), 2)
        elif st == "gothic":
            fog = pygame.Surface((W, H), pygame.SRCALPHA)
            for _ in range(22):
                pygame.draw.ellipse(fog, (170, 150, 200, 34), (rng.uniform(-200, W), rng.uniform(260, H), rng.uniform(260, 520), rng.uniform(70, 140)))
            s.blit(fog, (0, 0))
            for _ in range(40):
                pygame.draw.circle(s, acc, (int(rng.uniform(0, W)), int(rng.uniform(300, H))), rng.choice((2, 3)))
        elif st == "sandstone":
            for k, y in enumerate(range(300, H, 46)):   # layered canyon strata
                pygame.draw.line(s, scenery.mix(inner, outer, 0.25 + 0.1 * (k % 3)), (0, y), (W, y + rng.uniform(-20, 20)), 10)
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
                elif cause == "crushed":
                    word = "CRUNCH!"
                elif cause != "left_behind":
                    word = "YEET!"
                prio = 3
            elif e.kind == "impact" and e.data.get("hero_pair") and e.data.get("impulse", 0) > 900:
                word, prio = ("BONK!" if seed % 2 else "OOF!"), 1
            elif e.kind == "crush_hit" and e.data.get("hero"):
                word, prio = "SQUASHED!", 3
            elif e.kind == "glitch_blink" and e.data.get("moved"):
                word, prio = ("LAG!" if e.data.get("back") else "ZAP!"), 2
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
            if s["type"] in ("disc", "octagon_pool"):
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
        """Draws background vertical castle pillars / iron chains, then seamless stitched masonry/beam slabs."""
        chains = self._build_track_chains(removed)
        z = cam.zoom
        self._lowest_slab_y = 0.0
        placed: list[float] = []
        for pts, mats, _ in chains:
            x0, x1 = min(pts[0][0], pts[-1][0]), max(pts[0][0], pts[-1][0])
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
                if short or has_lower or self.meta.get("vertical_tower"):
                    has_upper = any(
                        other_pts is not pts and (uy := self._chain_y_at(other_pts, wx)) is not None and wy - 360 < uy < wy - 30
                        for other_pts, _, _ in chains
                    )
                    if not has_upper:
                        scenery.draw_support_pillar(self.frame, sx, sy + 6 * z, max(LAYOUT["viewport"][0], sy - 200 * z),
                                                    z, self.theme, chain=True)
                else:
                    scenery.draw_support_pillar(self.frame, sx, sy + 56 * z, H, z, self.theme, chain=False)

        for pts, mats, belts in chains:
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
            scenery.draw_track_chain(self.frame, sub_pts, sub_mats, sub_belts, z, self.theme, t_anim, finale=self.finale)

    def _draw_drop_gate(self, cam: Cam, wx: float, wy: float, play_t: float) -> None:
        """Compact mechanical castle portcullis gate that retracts smoothly upward at t = 0..0.38 s."""
        sx, sy = cam.to_screen(wx, wy)
        if sx < -120 or sx > W + 120:
            return
        z = cam.zoom
        lw = max(2, int(4 * z))
        lift = 0.0 if play_t <= 0.0 else min(1.0, play_t / 0.38)
        lift_eased = 1.0 - (1.0 - lift) ** 2
        gate_h = 138 * z
        housing_h = 46 * z
        top_y = sy - gate_h - housing_h
        bar_bottom = sy - lift_eased * (gate_h - 14 * z)
        bar_top = top_y + 12 * z
        if bar_bottom > bar_top + 6:
            gw = max(12, int(24 * z))
            grate = pygame.Rect(int(sx - gw / 2), int(bar_top), gw, int(bar_bottom - bar_top))
            pygame.draw.rect(self.frame, BLACK, grate.inflate(6, 4), border_radius=4)
            pygame.draw.rect(self.frame, (78, 84, 102), grate, border_radius=3)
            shoe_h = min(grate.height, max(8, int(18 * z)))
            pygame.draw.rect(self.frame, (255, 204, 36), (grate.left + 2, grate.bottom - shoe_h, grate.width - 4, shoe_h))
            pygame.draw.line(self.frame, BLACK, (grate.centerx, grate.top), (grate.centerx, grate.bottom), max(2, lw - 1))
        hw = max(26, int(52 * z))
        house = pygame.Rect(int(sx - hw / 2), int(top_y), int(hw), int(housing_h))
        _, rock, dark, _light = scenery.rock_colours(self.theme)
        pygame.draw.rect(self.frame, BLACK, house.inflate(lw * 2, lw * 2), border_radius=8)
        pygame.draw.rect(self.frame, rock, house, border_radius=6)
        pygame.draw.rect(self.frame, dark, (house.left, house.bottom - int(housing_h * 0.34), house.width, int(housing_h * 0.34)),
                         border_radius=4)
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
            fr.blit(self._void, (0, 0))
        else:
            for surf, factor in ((self.sky_bg, 0.04), (self.far_spires, 0.11), (self.mid_arches, 0.24)):
                par = (-cam.x * factor) % W
                fr.blit(surf, (par - W, 0))
                fr.blit(surf, (par, 0))
            # S5 Monsoon Storm: subtle 0.12s distant lightning flash + forked sky bolt every ~5.8s
            if getattr(th, "particles", "") == "monsoon":
                cyc = (play_t + 2.1) % 5.8
                if 0.0 <= cyc <= 0.12 and play_t > 0.3:
                    al = int(78 * (1.0 - cyc / 0.12))
                    flash_s = pygame.Surface((W, H), pygame.SRCALPHA)
                    flash_s.fill((215, 238, 255, al))
                    bx = int((int(play_t // 5.8) * 317 + 260) % (W - 220) + 110)
                    bolt = [(bx, 255), (bx - 28, 430), (bx + 18, 455), (bx - 36, 670), (bx + 8, 695), (bx - 22, 880)]
                    pygame.draw.lines(flash_s, (235, 248, 255, min(255, al * 3)), False, bolt, 5)
                    fr.blit(flash_s, (0, 0))

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
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), s["r"] * z * k, z, th, spin_deg=spin,
                                               finale=self.finale)
            elif s["type"] == "octagon_pool":
                k = self._k(zone)
                push_p = min(1.0, max(0.0, (play_t - 16.0) / 10.0))
                pr_px = (76.0 + 54.0 * push_p) * z * k
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), s["r"] * z * k, z, th,
                                               shape="octagon_pool", pocket_r=pr_px, finale=self.finale)
            elif s["type"] == "ring":
                r = zone.get("ring_r", s["r"]) * self._k(zone)
                scenery.draw_floating_platform(fr, cam.to_screen(*s["c"]), r * z, z, th, finale=self.finale)
                pygame.draw.circle(fr, th.accent, cam.to_screen(*s["c"]), r * z, max(3, int(6 * z)))
            elif s["type"] == "square":
                k = self._k(zone)
                scenery.draw_floating_platform(fr, cam.to_screen(0, 0), 0, z, th, "square", s["half"] * k * z,
                                               finale=self.finale)
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
                if max(a[0], b[0]) < -70 or min(a[0], b[0]) > W + 70:
                    continue
                if self.tr.mode == "SIDE_VIEW" and s["mat"] == "wall":
                    if self.meta.get("vertical_tower") and abs(s["b"][1] - s["a"][1]) > 1400:
                        # CollapseTower outer masonry containment wall
                        _, rock, dark, light = scenery.rock_colours(th)
                        ww = max(24, int(44 * z))
                        top_sy = int(max(LAYOUT["viewport"][0] - 10, min(a[1], b[1])))
                        bot_sy = int(min(H + 10, max(a[1], b[1])))
                        if bot_sy > top_sy:
                            rect_w = pygame.Rect(int(a[0] - ww / 2), top_sy, ww, bot_sy - top_sy)
                            pygame.draw.rect(fr, rock, rect_w)
                            pygame.draw.rect(fr, dark, (rect_w.right - ww // 3, rect_w.top, ww // 3, rect_w.height))
                            for yy in range(top_sy, bot_sy, max(20, int(48 * z))):
                                pygame.draw.line(fr, dark, (rect_w.left + 2, yy), (rect_w.right - 2, yy), 2)
                            pygame.draw.rect(fr, BLACK, rect_w, max(2, int(4 * z)))
                            pygame.draw.line(fr, light, (rect_w.left + 4, rect_w.top), (rect_w.left + 4, rect_w.bottom), 2)
                        continue
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
        for sb in self.meta["statics"]:
            if sb["type"] == "ceiling_beam":
                self._draw_ceiling_beam(cam, sb)
            elif sb["type"] == "ceiling_girder":
                self._draw_ceiling_girder(cam, sb)

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
        """v4.3 pass-through checkered FINISH ARCH (two checkered posts + curved FINISH banner, golden on the Grand
        Final) + a red victory tape that snaps into two flapping halves the moment the winner crosses."""
        z = cam.zoom
        top_y = y - 230
        a, b = cam.to_screen(x, top_y), cam.to_screen(x, y)
        sq = max(8.0, 20 * z)
        gold = self.finale
        span = 120 * z
        for px in (a[0] - span, a[0] + span):                       # two checkered posts straddling the line
            for i in range(int((b[1] - a[1]) / sq) + 1):
                for j in range(2):
                    col = BLACK if (i + j) % 2 else ((255, 214, 40) if gold else WHITE_)
                    pygame.draw.rect(self.frame, col, (px + j * sq - sq, a[1] + i * sq, sq + 1, sq + 1))
            pygame.draw.rect(self.frame, BLACK, (px - sq - 2, a[1] - 2, 2 * sq + 4, b[1] - a[1] + 4), 3)
        # curved banner across the top of the arch
        arc = [(a[0] - span - sq, a[1] + 4)]
        for k in range(13):
            u = k / 12
            arc.append((a[0] - span - sq + (2 * span + 2 * sq) * u, a[1] - 46 * z * math.sin(math.pi * u) - 12 * z))
        arc.append((a[0] + span + sq, a[1] + 4))
        inner = [(px_, py_ + 40 * z) for px_, py_ in reversed(arc[1:-1])]
        band = arc[1:-1] + inner
        pygame.draw.polygon(self.frame, BLACK, [(px_ + 3, py_ + 5) for px_, py_ in band])
        pygame.draw.polygon(self.frame, (226, 160, 18) if gold else (232, 40, 60), band)
        pygame.draw.polygon(self.frame, BLACK, band, max(3, int(4 * z)))
        lbl = hud.outlined("FINISH", max(14, int(30 * z)), fill=(255, 250, 214) if gold else WHITE_, width=3)
        self.frame.blit(lbl, lbl.get_rect(center=(a[0], a[1] - 38 * z)))
        if gold:
            hud._crown_badge(self.frame, a[0], a[1] - 84 * z, max(18, 40 * z))
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
        if age < 1.0:          # the winner has visibly crossed the arch -> genuine race finish celebration
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
            # v3.4: sleek flattened glossy dark-brown puddle with small bubbles (zero puffy cloud lobes)
            ph1 = wx * 0.037 + wy * 0.021
            ph2 = wy * 0.043 - wx * 0.019
            puddle = []
            inner_pool = []
            for k in range(56):
                a = 2 * math.pi * k / 56
                und = 0.92 + 0.055 * math.sin(2 * a + ph1) + 0.035 * math.cos(3 * a + ph2)
                px = cx + math.cos(a) * r * und
                py = cy + math.sin(a) * r * 0.84 * und
                puddle.append((px, py))
                inner_pool.append((cx + (px - cx) * 0.72, cy + (py - cy) * 0.72))
            pygame.draw.polygon(fr, (38, 20, 9), [(px, py + 2) for px, py in puddle])
            pygame.draw.polygon(fr, (78, 45, 20), puddle)
            pygame.draw.polygon(fr, (58, 32, 13), inner_pool)
            pygame.draw.polygon(fr, (36, 18, 8), puddle, max(2, lw - 1))
            # Sleek wet glossy specular sheen arcs
            sheen = [
                (cx + math.cos(a) * r * 0.64, cy + math.sin(a) * r * 0.52)
                for a in (-2.45 + 0.16 * u for u in range(9))
            ]
            pygame.draw.lines(fr, (255, 240, 218, 95), False, sheen, max(2, int(4 * z)))
            pygame.draw.ellipse(fr, (255, 242, 224, 65), (cx + r * 0.14, cy + r * 0.18, r * 0.24, r * 0.10))
            # Small rising/popping mud bubbles
            for j in range(3):
                ang = j * 2.15 + ph1 + t * 0.45
                bx = cx + math.cos(ang) * r * 0.36
                by = cy + math.sin(ang * 1.15) * r * 0.28
                br = max(2, int(r * 0.085 * (0.80 + 0.30 * math.sin(t * 4.8 + j * 1.9))))
                pygame.draw.circle(fr, (36, 18, 8), (bx, by), br + 1)
                pygame.draw.circle(fr, (108, 66, 32), (bx, by), br)
                pygame.draw.circle(fr, (240, 215, 185), (bx - br * 0.3, by - br * 0.3), max(1, int(br * 0.28)))
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
            self._apply_platform_mask(fr, ox_, oy_, cam, zone)
        self.frame.blit(fr, (ox_, oy_))

    def _apply_platform_mask(self, surf: pygame.Surface, ox: float, oy: float, cam: Cam, zone: dict) -> None:
        """P0.3: Clips any TOP_DOWN floor hazard/patch surface strictly inside the active shrinking platform mask."""
        z = cam.zoom
        dsx, dsy = cam.to_screen(0, 0)
        cx_l, cy_l = dsx - ox, dsy - oy
        mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        k = self._k(zone)
        drawn = False
        for s in self.meta["statics"]:
            st = s["type"]
            if st in ("disc", "ring"):
                rad = (zone.get("ring_r", s["r"]) if st == "ring" else s["r"]) * k * z - 3.0
                if rad > 2.0:
                    pygame.draw.circle(mask, (255, 255, 255, 255), (cx_l, cy_l), rad)
                drawn = True
                break
            if st == "octagon_pool":
                rad = s["r"] * k * z - 3.0
                if rad > 4.0:
                    pts = scenery._octagon_pts(cx_l, cy_l, rad)
                    pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
                drawn = True
                break
            if st == "square":
                h_px = s["half"] * k * z - 3.0
                if h_px > 4.0:
                    pygame.draw.rect(mask, (255, 255, 255, 255),
                                     pygame.Rect(int(cx_l - h_px), int(cy_l - h_px), int(2 * h_px), int(2 * h_px)),
                                     border_radius=14)
                drawn = True
                break
        if drawn:
            surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    def _zones(self, cam: Cam, zone: dict, t: float) -> None:
        fr, z = self.frame, cam.zoom
        for key in ("ice_zones", "mud_zones", "boost_zones", "grip_zones"):
            for zz in zone.get(key, []):
                draw_key = "mud_zones" if key == "grip_zones" else key
                if zz[0] == "rect":
                    self._draw_side_surface_mod(cam, draw_key, float(zz[1]), float(zz[2]), t)
                else:
                    self._draw_top_surface_mod(cam, draw_key, float(zz[1][0]), float(zz[1][1]), float(zz[2]), zone, t)
        if "lava_y" in zone:
            y = cam.to_screen(0, zone["lava_y"])[1]
            if y < H:
                c_out = getattr(self.theme, "wall_outer", (195, 42, 16))
                c_mid = getattr(self.theme, "wall_mid", (255, 96, 20))
                c_core = getattr(self.theme, "wall_core", (255, 232, 118))
                pygame.draw.rect(fr, c_out, (0, y + 10, W, H - y))
                wave_pts = [(wx, y + 7 * math.sin(t * 4.2 + wx * 0.018)) for wx in range(0, W + 24, 24)]
                pygame.draw.polygon(fr, c_mid, wave_pts + [(W, H), (0, H)])
                for i in range(12):
                    bx = (i * 97 + t * 44) % W
                    pygame.draw.circle(fr, c_core, (bx, y + 14 + 6 * math.sin(t * 5 + i)), 12)
                pygame.draw.lines(fr, c_core, False, wave_pts, 5)
        if zone.get("zone"):
            zx, zy, r = zone["zone"]
            c = cam.to_screen(zx, zy)
            rz = max(12.0, r * z)
            zf = pygame.Surface((int(rz * 2 + 24), int(rz * 2 + 24)), pygame.SRCALPHA)
            zc = zf.get_width() // 2
            pygame.draw.circle(zf, (255, 214, 0, 46), (zc, zc), int(rz))
            if self.tr.mode == "TOP_DOWN":
                self._apply_platform_mask(zf, c[0] - zc, c[1] - zc, cam, zone)
            self.frame.blit(zf, (int(c[0] - zc), int(c[1] - zc)))
            pygame.draw.circle(fr, BLACK, c, rz + 3, max(4, int(10 * z)))
            pygame.draw.circle(fr, (255, 214, 0), c, rz, max(3, int(6 * z)))
            pygame.draw.circle(fr, (255, 240, 128), c, rz * (0.68 + 0.08 * math.sin(t * 6)), max(2, int(3 * z)))
            scores = zone.get("scores") or {}
            need = float(zone.get("zone_need") or 5.5)
            best_s = max((float(v) for v in scores.values()), default=0.0)
            if best_s > 0.05 and need > 0:
                frac = min(1.0, best_s / need)
                arc_r = pygame.Rect(int(c[0] - rz - 8), int(c[1] - rz - 8), int((rz + 8) * 2), int((rz + 8) * 2))
                pygame.draw.arc(fr, (80, 250, 140), arc_r, math.pi / 2 - frac * 2 * math.pi, math.pi / 2, max(5, int(8 * z)))
        for x0_c, x1_c in zone.get("cracking", []):
            mx = (float(x0_c) + float(x1_c)) * 0.5
            g_c = self._ground_seg_at(mx)
            if g_c is not None:
                a_c = cam.to_screen(float(x0_c), self.ground_y(float(x0_c)))
                b_c = cam.to_screen(float(x1_c), self.ground_y(float(x1_c)))
                jit = math.sin(t * 70.0 + mx) * 3.0 * z
                pygame.draw.line(fr, (238, 62, 48), (a_c[0], a_c[1] + jit), (b_c[0], b_c[1] - jit), max(5, int(12 * z)))
                cm = ((a_c[0] + b_c[0]) * 0.5, (a_c[1] + b_c[1]) * 0.5)
                pygame.draw.lines(fr, (255, 236, 96), False,
                                  [(cm[0] - 16 * z, cm[1] - 7 * z), (cm[0] + 4 * z, cm[1]), (cm[0] - 6 * z, cm[1] + 8 * z)],
                                  max(2, int(3.5 * z)))
        for it in zone.get("items", []):
            c = cam.to_screen(*it)
            bob = math.sin(t * 6 + it[0]) * 5
            pts = [(c[0] - 14, c[1] + 8 + bob), (c[0] - 14, c[1] - 6 + bob), (c[0] - 7, c[1] + bob), (c[0], c[1] - 12 + bob),
                   (c[0] + 7, c[1] + bob), (c[0] + 14, c[1] - 6 + bob), (c[0] + 14, c[1] + 8 + bob)]
            pygame.draw.polygon(fr, (255, 205, 40), pts)
            pygame.draw.polygon(fr, BLACK, pts, 3)
        for p in zone.get("pads", []):
            if self.tr.mode == "TOP_DOWN":
                k_p = self._k(zone)
                if math.hypot(p[0], p[1]) > self._platform_r(zone) - 24:
                    continue
                c = cam.to_screen(p[0] * k_p, p[1] * k_p)
            else:
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
            plat_r = self._platform_r(zone)
            if math.hypot(cx, cy) - r > plat_r - 4:
                continue
            c = cam.to_screen(cx, cy)
            rz_ = max(4, int(r * z))
            ts = pygame.Surface((rz_ * 2 + 24, rz_ * 2 + 24), pygame.SRCALPHA)
            tc = rz_ + 12
            col = (255, 80, 80) if st == 1 else WHITE_
            jx = int(math.sin(t * 60) * 3) if st == 1 else 0
            pygame.draw.circle(ts, (14, 12, 26, 175 if st == 1 else 95), (tc + jx, tc), rz_)
            pygame.draw.circle(ts, col, (tc + jx, tc), rz_, 5)
            self._apply_platform_mask(ts, c[0] - tc, c[1] - tc, cam, zone)
            self.frame.blit(ts, (int(c[0] - tc), int(c[1] - tc)))

    def _draw_seesaw(self, cam: Cam, x: float, y: float, ang: float, verts: list) -> None:
        """Chunky wood-and-iron seesaw plank with bolted end-caps and a riveted cast-iron center gear hub."""
        z = cam.zoom
        lw = max(3, int(4.5 * z))
        ca, sa = math.cos(ang), math.sin(ang)
        cx_s, cy_s = cam.to_screen(x, y)
        brk = [(cx_s - 20 * z, cy_s + 36 * z), (cx_s, cy_s), (cx_s + 20 * z, cy_s + 36 * z)]
        pygame.draw.polygon(self.frame, (64, 68, 84), brk)
        pygame.draw.polygon(self.frame, BLACK, brk, lw)

        pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in verts]
        pygame.draw.polygon(self.frame, (176, 122, 68), pts)
        xs_loc = [v[0] for v in verts]
        ys_loc = [v[1] for v in verts]
        hw, hh = max(xs_loc), max(ys_loc)
        for gy_k in (-0.35, 0.25):
            g0 = cam.to_screen(x + (-hw * 0.82) * ca - (hh * gy_k) * sa, y + (-hw * 0.82) * sa + (hh * gy_k) * ca)
            g1 = cam.to_screen(x + (hw * 0.82) * ca - (hh * gy_k) * sa, y + (hw * 0.82) * sa + (hh * gy_k) * ca)
            pygame.draw.line(self.frame, (132, 86, 44), g0, g1, max(2, int(2.5 * z)))
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
        b_states = self.tr.zones[fi].get("bridge_states", [])
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
                    rr = sh["r"] * cam.zoom
                    if st["style"] == "piston_bumper":
                        # SumoPoolPit oscillating concentric spring-ring bumper
                        pygame.draw.circle(self.frame, BLACK, c, rr + 4)
                        pygame.draw.circle(self.frame, (255, 196, 36), c, rr)
                        pygame.draw.circle(self.frame, (238, 48, 82), c, rr * 0.72)
                        pygame.draw.circle(self.frame, WHITE_, c, rr * 0.42)
                        pygame.draw.circle(self.frame, BLACK, c, rr * 0.72, max(2, int(2.5 * cam.zoom)))
                        continue
                    if st["style"] in ("giant_ball", "boulder"):
                        self._draw_boulder(c, rr, ang)
                        continue
                    col = {"boulder": (130, 110, 100), "cannonball": (40, 40, 50)}.get(st["style"], th.hazard)
                    pygame.draw.circle(self.frame, BLACK, c, rr + 4)
                    pygame.draw.circle(self.frame, col, c, rr)
                    pygame.draw.circle(self.frame, WHITE_, (c[0] - rr * 0.35, c[1] - rr * 0.35), rr * 0.2)
                elif sh["type"] == "seg":
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in (sh["a"], sh["b"])]
                    if st["style"] == "disc_marks":
                        continue
                    wd = max(4, int(sh["r"] * 2 * cam.zoom))
                    pygame.draw.line(self.frame, BLACK, pts[0], pts[1], wd + 8)
                    if st["style"] == "hammer":
                        pygame.draw.line(self.frame, (150, 95, 45), pts[0], pts[1], wd + 2)
                        for kk in (0.2, 0.5, 0.8):
                            bx = pts[0][0] + (pts[1][0] - pts[0][0]) * kk
                            by = pts[0][1] + (pts[1][1] - pts[0][1]) * kk
                            pygame.draw.circle(self.frame, (190, 195, 205), (bx, by), wd * 0.9 + 2)
                    elif st["style"] == "crusher":
                        # Heavy hydraulic steel piston shaft
                        pygame.draw.line(self.frame, (98, 106, 124), pts[0], pts[1], wd + 2)
                        pygame.draw.line(self.frame, (210, 218, 232), pts[0], pts[1], max(2, wd // 3))
                    elif st["style"] == "pool_rail":
                        # High-elasticity bouncy pool table bumper cushion rail
                        pygame.draw.line(self.frame, (255, 82, 168), pts[0], pts[1], wd + 2)
                        pygame.draw.line(self.frame, (255, 224, 92), pts[0], pts[1], max(2, wd // 3))
                        for end_p in pts:
                            pygame.draw.circle(self.frame, BLACK, end_p, wd * 0.65 + 3)
                            pygame.draw.circle(self.frame, (255, 214, 42), end_p, wd * 0.65)
                    elif st["style"] == "maze_wall":
                        _, rock, _dark, light = scenery.rock_colours(th)
                        pygame.draw.line(self.frame, rock, pts[0], pts[1], wd + 2)
                        pygame.draw.line(self.frame, light, pts[0], pts[1], max(2, wd // 3))
                        for end_p in pts:
                            pygame.draw.circle(self.frame, BLACK, end_p, wd * 0.58 + 3)
                            pygame.draw.circle(self.frame, rock, end_p, wd * 0.58)
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
                elif st["style"] == "bridge_tile":
                    pts = [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in sh["verts"]]
                    b_ord = self.bridge_prop_indices.index(i) if i in self.bridge_prop_indices else -1
                    b_st = b_states[b_ord] if (0 <= b_ord < len(b_states)) else 0
                    base_c = (232, 86, 54) if b_st == 1 else ((192, 136, 74) if b_st == 0 else (142, 96, 52))
                    pygame.draw.polygon(self.frame, base_c, pts)
                    if len(pts) >= 4:
                        pygame.draw.line(self.frame, scenery.mix(base_c, WHITE_, 0.35), pts[0], pts[1], max(2, int(4 * cam.zoom)))
                        if b_st >= 1:
                            # Warning crack zigzag when tile is shaking/dropping!
                            mx = sum(p[0] for p in pts) / 4.0
                            my = sum(p[1] for p in pts) / 4.0
                            pygame.draw.lines(self.frame, (255, 232, 92), False,
                                              [(mx - 14 * cam.zoom, my - 8 * cam.zoom), (mx + 4 * cam.zoom, my),
                                               (mx - 6 * cam.zoom, my + 8 * cam.zoom)], max(2, int(3 * cam.zoom)))
                    pygame.draw.polygon(self.frame, BLACK, pts, max(3, int(4 * cam.zoom)))
                elif st["style"] == "crusher":
                    def to_s(px_, py_):
                        return cam.to_screen(x + px_ * ca - py_ * sa, y + px_ * sa + py_ * ca)
                    pts = [to_s(px, py) for px, py in sh["verts"]]
                    warn_xs = self.tr.zones[fi].get("crusher_warn", [])
                    warning = any(abs(x - float(wx)) < 60.0 for wx in warn_xs)
                    flash = warning and fi % 4 < 2
                    pygame.draw.polygon(self.frame, (255, 226, 60) if flash else (72, 78, 96), pts)
                    if len(pts) >= 4:
                        # slope-parallel yellow/black hazard band + iron spikes along the head's own bottom edge
                        lxs = [p[0] for p in sh["verts"]]
                        lys = [p[1] for p in sh["verts"]]
                        hw_, hh_ = (max(lxs) - min(lxs)) / 2, (max(lys) - min(lys)) / 2
                        band_l = [(-hw_ + 4, hh_ * 0.05), (hw_ - 4, hh_ * 0.05), (hw_ - 4, hh_ * 0.62), (-hw_ + 4, hh_ * 0.62)]
                        pygame.draw.polygon(self.frame, (250, 204, 21) if not flash else (232, 40, 60),
                                            [to_s(*p) for p in band_l])
                        nst = max(3, int(2 * hw_ / 22))
                        for k in range(nst):
                            u = -hw_ + 8 + (2 * hw_ - 16) * k / max(1, nst - 1)
                            pygame.draw.line(self.frame, BLACK, to_s(u - 5, hh_ * 0.62), to_s(u + 5, hh_ * 0.05),
                                             max(3, int(5 * cam.zoom)))
                        nsp = max(3, int(2 * hw_ / 24))
                        for k in range(nsp):
                            u = -hw_ + 12 + (2 * hw_ - 24) * k / max(1, nsp - 1)
                            tri = [to_s(u - 7, hh_), to_s(u + 7, hh_), to_s(u, hh_ + 14)]
                            pygame.draw.polygon(self.frame, (176, 184, 202), tri)
                            pygame.draw.polygon(self.frame, BLACK, tri, max(2, int(3 * cam.zoom)))
                        if warning:
                            ex, ey = to_s(0, -hh_ - 34)
                            bang = hud.outlined("!", max(18, int(40 * cam.zoom)), fill=(255, 226, 60), width=4)
                            self.frame.blit(bang, bang.get_rect(center=(ex, ey)))
                    pygame.draw.polygon(self.frame, BLACK, pts, max(3, int(5 * cam.zoom)))
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

    # ------------------------------------------------------------------ v4.2 live starting-gate spotlight + VS clash
    def _draw_spotlights(self, cam: Cam, fi: int, seg_t: float) -> None:
        spots = (self.ep.league_ctx or {}).get("spotlights") or []
        if not spots or seg_t > 1.45:
            return
        fade = min(1.0, seg_t / 0.18) * (1.0 if seg_t < 1.2 else max(0.0, (1.45 - seg_t) / 0.25))
        styles = {"leader": (255, 214, 40), "rival": (255, 96, 48), "wildcard": (0, 229, 255)}
        placed: list[pygame.Rect] = []
        for k, sp in enumerate(spots[:3]):
            try:
                i = self.tr.index(sp["key"])
            except ValueError:
                continue
            x, y = float(self.tr.frames[fi][i][0]), float(self.tr.frames[fi][i][1])
            sx, sy = cam.to_screen(x, y)
            col = styles.get(sp.get("kind", "leader"), (255, 214, 40))
            rad = (HERO_BY_KEY[sp["key"]].radius if sp["key"] in HERO_BY_KEY else 24) * cam.zoom
            ring_r = rad + 10 + 4 * math.sin(seg_t * 9 + k)
            glow = pygame.Surface((int(ring_r * 4), int(ring_r * 4)), pygame.SRCALPHA)
            gc = glow.get_width() // 2
            pygame.draw.circle(glow, (*col, int(70 * fade)), (gc, gc), int(ring_r * 1.5))
            self.frame.blit(glow, (sx - gc, sy - gc))
            pygame.draw.circle(self.frame, BLACK, (int(sx), int(sy)), int(ring_r + 3), 7)
            pygame.draw.circle(self.frame, col, (int(sx), int(sy)), int(ring_r), 4)
            # angled floating pointer tag (staggered so tags never stack)
            ang = (-0.95, -2.2, -0.45)[k % 3]
            dist = 120 + 26 * k
            tx, ty = sx + math.cos(ang) * dist, sy + math.sin(ang) * dist
            tx = max(150.0, min(W - 150.0, tx))
            ty = max(LAYOUT["viewport"][0] + 40.0, ty)
            txt = hud.outlined(sp.get("label", ""), 30, fill=WHITE_, width=4)
            box = pygame.Rect(0, 0, txt.get_width() + 56, txt.get_height() + 10)
            box.center = (int(tx), int(ty))
            # de-overlap against tags already placed this frame (bunched gate): hop up, else down
            top_lim = LAYOUT["viewport"][0] + 40 - box.height // 2
            for _ in range(6):
                hit = next((p for p in placed if box.inflate(8, 8).colliderect(p)), None)
                if hit is None:
                    break
                up = hit.top - 6 - box.height
                box.top = up if up >= top_lim else hit.bottom + 6
            placed.append(box.copy())
            tx, ty = float(box.centerx), float(box.centery)
            pygame.draw.line(self.frame, BLACK, (sx, sy - ring_r), (tx, ty), 7)
            pygame.draw.line(self.frame, col, (sx, sy - ring_r), (tx, ty), 3)
            plate = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(plate, (18, 16, 36, int(235 * fade)), plate.get_rect(), border_radius=14)
            pygame.draw.rect(plate, (*col, int(255 * fade)), plate.get_rect(), 4, border_radius=14)
            plate = pygame.transform.rotozoom(plate, 0, 0.92 + 0.08 * min(1.0, seg_t / 0.2))
            self.frame.blit(plate, plate.get_rect(center=box.center))
            icx, icy = box.left + 26, box.centery
            if sp.get("kind") == "leader":
                hud._crown_badge(self.frame, icx, icy + 2, 30)
            elif sp.get("kind") == "rival":
                hud._draw_flame_icon(self.frame, icx, icy, 12)
            else:
                bolt = [(icx + 3, icy - 14), (icx - 9, icy + 2), (icx - 1, icy + 2), (icx - 5, icy + 14), (icx + 9, icy - 3), (icx + 1, icy - 3)]
                pygame.draw.polygon(self.frame, (250, 204, 21), bolt)
                pygame.draw.polygon(self.frame, BLACK, bolt, 2)
            self.frame.blit(txt, txt.get_rect(midleft=(box.left + 44, box.centery)))
            hud.TEXT_BOXES.append(box)

    def _draw_vs_clash(self, seg_t: float) -> None:
        """Grand Final: snappy 1.6 s 3-way VS clash banner over the trembling live starting gate."""
        fins = (self.ep.league_ctx or {}).get("finalists") or [h.key for h in self.heroes[:3]]
        if seg_t > 1.6:
            return
        k_in = min(1.0, seg_t / 0.22)
        k_out = 1.0 if seg_t < 1.35 else max(0.0, (1.6 - seg_t) / 0.25)
        band = pygame.Rect(0, 560, W, 420)
        plate = pygame.Surface(band.size, pygame.SRCALPHA)
        plate.fill((24, 10, 30, int(205 * k_out)))
        pygame.draw.rect(plate, (255, 212, 44, int(255 * k_out)), (0, 0, W, 8))
        pygame.draw.rect(plate, (255, 212, 44, int(255 * k_out)), (0, band.height - 8, W, 8))
        self.frame.blit(plate, band.topleft)
        title = hud.fit_width(hud.outlined("GRAND FINAL", 70, fill=(255, 226, 60), width=7), 860)
        self.frame.blit(title, title.get_rect(center=(W / 2, band.top + 58)))
        n = max(1, len(fins[:3]))
        for idx, hk in enumerate(fins[:3]):
            slide = (1.0 - k_in) * (-520 if idx == 0 else (520 if idx == n - 1 else 0))
            cx = W * (idx + 0.5) / n + slide
            cy = band.top + 230 + 6 * math.sin(seg_t * 14 + idx)
            if hk in HERO_BY_KEY:
                h = HERO_BY_KEY[hk]
                balls.draw_ball(self.frame, h, None, (cx, cy), 0.0, 0.0, (0, 0), 0.0, "angry", "none", seg_t, 2.0 / max(0.6, h.radius / 25))
                nm = hud.fit_width(hud.outlined(h.name.upper(), 40, fill=WHITE_, width=5), 300)
                self.frame.blit(nm, nm.get_rect(center=(cx, band.top + 352)))
            if idx < n - 1:
                vs = pygame.transform.rotozoom(hud.outlined("VS", 64, fill=(255, 82, 72), width=7), -8, 1.0 + 0.15 * abs(math.sin(seg_t * 10)))
                self.frame.blit(vs, vs.get_rect(center=(W * (idx + 1) / n, band.top + 230)))

    def _draw_boulder(self, c, rr: float, ang: float) -> None:
        """Massive textured rock boulder for the GIANT BALL twist."""
        rng = random.Random(int(rr * 10))
        pts = []
        for k in range(14):
            a = ang + 2 * math.pi * k / 14
            rk = rr * (0.92 + 0.08 * rng.random())
            pts.append((c[0] + math.cos(a) * rk, c[1] + math.sin(a) * rk))
        pygame.draw.polygon(self.frame, BLACK, [(x + 3, y + 5) for x, y in pts])
        pygame.draw.polygon(self.frame, (122, 104, 92), pts)
        pygame.draw.circle(self.frame, (96, 80, 72), (int(c[0] + rr * 0.22), int(c[1] + rr * 0.26)), int(rr * 0.62))
        pygame.draw.circle(self.frame, (152, 134, 120), (int(c[0] - rr * 0.3), int(c[1] - rr * 0.32)), int(rr * 0.3))
        for k in range(4):
            a = ang + k * 1.7
            p0 = (c[0] + math.cos(a) * rr * 0.15, c[1] + math.sin(a) * rr * 0.15)
            p1 = (c[0] + math.cos(a + 0.3) * rr * 0.55, c[1] + math.sin(a + 0.3) * rr * 0.55)
            p2 = (c[0] + math.cos(a - 0.1) * rr * 0.8, c[1] + math.sin(a - 0.1) * rr * 0.8)
            pygame.draw.lines(self.frame, (58, 46, 40), False, [p0, p1, p2], 4)
        pygame.draw.polygon(self.frame, BLACK, pts, 5)

    def _draw_ceiling_beam(self, cam: Cam, sb: dict) -> None:
        a = cam.to_screen(sb["x0"], sb["y"])
        b = cam.to_screen(sb["x1"], sb["y"])
        if b[0] < -60 or a[0] > W + 60:
            return
        z = cam.zoom
        _, rock, dark, light = scenery.rock_colours(self.theme)
        hgt = max(18, int(46 * z))
        beam = pygame.Rect(int(a[0]), int(a[1] - hgt / 2), int(b[0] - a[0]), hgt)
        # anchor pillars rising off the top of the frame
        for px in (beam.left + int(14 * z), beam.right - int(30 * z)):
            col_r = pygame.Rect(px, LAYOUT["viewport"][0] - 20, max(10, int(18 * z)), beam.top - LAYOUT["viewport"][0] + 22)
            if col_r.height > 0:
                pygame.draw.rect(self.frame, dark, col_r)
                pygame.draw.rect(self.frame, BLACK, col_r, 3)
        pygame.draw.rect(self.frame, rock, beam)
        pygame.draw.rect(self.frame, dark, (beam.left, beam.bottom - hgt // 3, beam.width, hgt // 3))
        pygame.draw.line(self.frame, light, (beam.left + 3, beam.top + 4), (beam.right - 3, beam.top + 4), 3)
        for rx in range(beam.left + 12, beam.right - 6, max(16, int(30 * z))):
            pygame.draw.circle(self.frame, (205, 212, 226), (rx, beam.centery), max(2, int(3 * z)))
        pygame.draw.rect(self.frame, BLACK, beam, 4)

    def _draw_ceiling_girder(self, cam: Cam, sb: dict) -> None:
        """v4.3 Crusher Gauntlet: ONE continuous riveted iron truss girder spanning the whole gauntlet, carried by
        stone castle pillars standing on the track, with every piston bolted into it."""
        pts = [cam.to_screen(float(x), float(y)) for x, y in sb["pts"]]
        if not pts or pts[-1][0] < -80 or pts[0][0] > W + 80:
            return
        z = cam.zoom
        _, rock, dark, light = scenery.rock_colours(self.theme)
        hgt = max(22.0, 54.0 * z)
        # stone support pillars (girder -> track top)
        for px, py_top, py_floor in sb.get("pillars", []):
            a = cam.to_screen(float(px), float(py_top))
            b = cam.to_screen(float(px), float(py_floor))
            if a[0] < -60 or a[0] > W + 60:
                continue
            pw = max(14, int(34 * z))
            col = pygame.Rect(int(a[0] - pw / 2), int(a[1]), pw, int(max(4, b[1] - a[1] - 2)))
            pygame.draw.rect(self.frame, dark, col)
            pygame.draw.rect(self.frame, rock, col.inflate(-int(10 * z), 0))
            for yy in range(col.top + int(26 * z), col.bottom, max(14, int(30 * z))):
                pygame.draw.line(self.frame, dark, (col.left + 2, yy), (col.right - 2, yy), max(2, int(2 * z)))
            pygame.draw.rect(self.frame, BLACK, col, 3)
            cap = pygame.Rect(col.left - int(6 * z), col.bottom - int(10 * z), col.width + int(12 * z), int(12 * z))
            pygame.draw.rect(self.frame, dark, cap)
            pygame.draw.rect(self.frame, BLACK, cap, 2)
        iron, iron_hi, iron_dk = (92, 98, 116), (176, 184, 202), (52, 56, 70)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if max(x0, x1) < -60 or min(x0, x1) > W + 60:
                continue
            top0, top1 = y0 - hgt / 2, y1 - hgt / 2
            bot0, bot1 = y0 + hgt / 2, y1 + hgt / 2
            body = [(x0, top0), (x1, top1), (x1, bot1), (x0, bot0)]
            pygame.draw.polygon(self.frame, iron_dk, [(x + 4, y + 6) for x, y in body])
            pygame.draw.polygon(self.frame, iron, body)
            # lattice truss diagonals
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L / max(26.0, 60.0 * z)))
            for k in range(n):
                u0, u1 = k / n, (k + 1) / n
                ax, ay = x0 + (x1 - x0) * u0, y0 + (y1 - y0) * u0
                bx, by = x0 + (x1 - x0) * u1, y0 + (y1 - y0) * u1
                if k % 2 == 0:
                    pygame.draw.line(self.frame, iron_dk, (ax, ay - hgt * 0.32), (bx, by + hgt * 0.32), max(3, int(5 * z)))
                else:
                    pygame.draw.line(self.frame, iron_dk, (ax, ay + hgt * 0.32), (bx, by - hgt * 0.32), max(3, int(5 * z)))
            pygame.draw.line(self.frame, iron_hi, (x0, top0 + 4), (x1, top1 + 4), max(2, int(4 * z)))
            pygame.draw.line(self.frame, iron_dk, (x0, bot0 - 5), (x1, bot1 - 5), max(2, int(5 * z)))
            for k in range(n + 1):                       # rivets on both chords
                u = k / n
                rx, ry = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
                for oy in (-hgt * 0.36, hgt * 0.36):
                    pygame.draw.circle(self.frame, iron_hi, (rx, ry + oy), max(2, int(3.5 * z)))
            pygame.draw.polygon(self.frame, BLACK, body, max(3, int(4 * z)))
        # piston mount collars bolted into the girder + hydraulic sleeves the telescoping shafts slide into
        for mx, my in sb.get("mounts", []):
            c = cam.to_screen(float(mx), float(my))
            if -60 < c[0] < W + 60:
                sl_bot = cam.to_screen(float(mx), float(my) + 175.0)
                sw = max(14, int(40 * z))
                sleeve = pygame.Rect(int(c[0] - sw / 2), int(c[1]), sw, int(max(4, sl_bot[1] - c[1])))
                pygame.draw.rect(self.frame, iron_dk, sleeve)
                pygame.draw.rect(self.frame, iron, sleeve.inflate(-int(12 * z), 0))
                pygame.draw.line(self.frame, iron_hi, (sleeve.left + int(8 * z), sleeve.top), (sleeve.left + int(8 * z), sleeve.bottom), max(2, int(3 * z)))
                pygame.draw.rect(self.frame, BLACK, sleeve, 3)
                ring = pygame.Rect(sleeve.left - int(5 * z), sleeve.bottom - int(10 * z), sleeve.width + int(10 * z), int(12 * z))
                pygame.draw.rect(self.frame, (250, 204, 21), ring)
                pygame.draw.rect(self.frame, BLACK, ring, 2)
                r_ = pygame.Rect(0, 0, int(64 * z), int(hgt + 14 * z))
                r_.center = (int(c[0]), int(c[1]))
                pygame.draw.rect(self.frame, iron_dk, r_, border_radius=int(6 * z))
                pygame.draw.rect(self.frame, (250, 204, 21), r_.inflate(-int(16 * z), -int(hgt * 0.55)))
                pygame.draw.rect(self.frame, BLACK, r_, 3, border_radius=int(6 * z))


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
        """v4.0 Procedural Atmospheric Weather across all 8 Seasonal Themes."""
        kind = self.theme.particles
        rng = random.Random(3)
        palette = {
            "motes": (255, 246, 195),
            "snow": (244, 250, 255),
            "embers": (255, 146, 48),
            "cyber_glitch": (0, 242, 255),
            "monsoon": (168, 206, 245),
            "haunted_mist": (152, 255, 128),
            "sand_wind": (246, 212, 138),
            "sprinkles": (255, 112, 192),
            "stars": (255, 255, 220),
            "bubbles": (200, 240, 255),
            "rain": (170, 190, 230),
            "sand": (240, 210, 150),
            "fireflies": (255, 240, 120),
            "wisps": (190, 255, 160),
            "sparks": (255, 210, 90),
            "clouds": (255, 255, 255),
            "pollen": (255, 236, 150),
        }
        col = palette.get(kind, (255, 244, 190))

        if kind == "haunted_mist" and self.tr.mode != "TOP_DOWN":
            # S6 Haunted Castle: Drifting translucent purple-green mist ribbons + glowing fireflies
            mist = pygame.Surface((W, 240), pygame.SRCALPHA)
            for k in range(5):
                mx = ((k * 260 - t * (34 + k * 9) - cam.x * 0.18) % (W + 340)) - 340
                my = 30 + (k % 3) * 52
                pygame.draw.ellipse(mist, (124, 96, 178, 38), (int(mx), int(my), 360, 74))
            self.frame.blit(mist, (0, 1310))

        sprinkle_cols = ((255, 88, 168), (88, 220, 255), (255, 224, 68), (148, 245, 128))
        for i in range(36):
            x0, y0 = rng.uniform(0, W), rng.uniform(300, 1600)
            sp = rng.uniform(28, 86)
            if kind in ("monsoon", "rain"):
                y = (y0 + t * sp * 7.2) % 1300 + 290
                x = (x0 - t * sp * 2.1 - cam.x * 0.3) % W
                pygame.draw.line(self.frame, col, (x, y), (x - 10, y + 28), 2)
            elif kind == "snow":
                y = (y0 + t * sp * 1.65) % 1300 + 290
                x = (x0 + math.sin(t * 2.1 + i) * 26 - cam.x * 0.3) % W
                pygame.draw.circle(self.frame, col, (int(x), int(y)), 3 if i % 3 else 4)
            elif kind == "sand_wind":
                x = (x0 + t * sp * 6.5 - cam.x * 0.35) % (W + 120) - 60
                y = (y0 + math.sin(t * 3.0 + i) * 14) % 1260 + 310
                pygame.draw.line(self.frame, col, (x, y), (x + 48 + (i % 3) * 18, y + 3), 2)
            elif kind == "cyber_glitch":
                if i < 14:
                    gx = (x0 + math.sin(t * 8.0 + i) * 40 - cam.x * 0.25) % W
                    gy = (y0 - t * sp * 1.4) % 1260 + 310
                    gc = (0, 242, 255) if i % 2 == 0 else (255, 48, 192)
                    if int(t * 12 + i * 3) % 5 == 0:
                        pygame.draw.rect(self.frame, gc, (int(gx), int(gy), 28 + (i % 4) * 12, 4))
                    else:
                        pygame.draw.rect(self.frame, gc, (int(gx), int(gy), 5, 5))
            elif kind == "sprinkles":
                y = (y0 + t * sp * 1.9) % 1300 + 290
                x = (x0 + math.sin(t * 2.4 + i) * 18 - cam.x * 0.3) % W
                sc = sprinkle_cols[i % len(sprinkle_cols)]
                ang_s = t * 3.5 + i
                pygame.draw.line(
                    self.frame,
                    sc,
                    (x - math.cos(ang_s) * 6, y - math.sin(ang_s) * 6),
                    (x + math.cos(ang_s) * 6, y + math.sin(ang_s) * 6),
                    4,
                )
            else:
                y = (y0 - t * sp) % 1270 + 320
                x = (x0 + math.sin(t * 2.2 + i) * 22 - cam.x * 0.3) % W
                r_p = 4 if (kind == "haunted_mist" and int(t * 4 + i) % 2 == 0) else 3
                pygame.draw.circle(self.frame, col, (int(x), int(y)), r_p)

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
            z_cur = self.tr.zones[min(fi, len(self.tr.zones) - 1)]
            if alive and self.meta["recipe"].get("goal") == "collect_items":
                cnt = int((z_cur.get("scores") or {}).get(k, 0))
                if cnt > 0:
                    br = balls.body_radius(hero, extra) * z
                    bx_i, by_i = sx + br * 0.72, sy - br * 0.72
                    pygame.draw.circle(self.frame, BLACK, (int(bx_i), int(by_i)), 16)
                    pygame.draw.circle(self.frame, (255, 210, 36), (int(bx_i), int(by_i)), 13)
                    ct = hud.outlined(f"{cnt}", 20, fill=WHITE_, width=3)
                    self.frame.blit(ct, ct.get_rect(center=(int(bx_i), int(by_i))))
            if f & T.HAS_BOMB:
                rad_b = balls.body_radius(hero, extra) * z
                pygame.draw.circle(self.frame, (255, 52, 52), (int(sx), int(sy)),
                                   int(rad_b + 8 + 4 * abs(math.sin(t_anim * 12))), 4)
                self._bomb(sx, sy - rad_b - 12, t_anim, z_cur.get("bomb_timer"))
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
        # P2.3 Nameplate Anti-Overlap: detect dense pile-up (inter-character distance < 140px) -> restrict to top 3
        dense_pileup = False
        if len(pts) >= 4:
            close_pairs = sum(
                1 for a_i in range(len(pts)) for b_i in range(a_i + 1, len(pts))
                if math.hypot(pts[a_i][0] - pts[b_i][0], pts[a_i][1] - pts[b_i][1]) < 140.0
            )
            dense_pileup = close_pairs >= 3
        ordered_pills = sorted(pills, key=lambda item: ranks.get(item[0].key, 99))
        if dense_pileup:
            ordered_pills = ordered_pills[:3]
        boxes = []
        for h, x, y, fan in ordered_pills:
            rk = ranks.get(h.key, 99)
            if not (window or alive_n <= 3 or h.key in recent or rk <= 3):
                continue
            sx, sy = screen[h.key]
            if not dense_pileup and sum(1 for px, py in pts if math.hypot(px - sx, py - sy) < 115) >= 4 and rk > 3:
                continue
            s = renderer.name_pill(h, crown=fan, size=22)
            boxes.append([s, float(x - s.get_width() / 2), float(y - s.get_height()), rk])
        y_min = float(LAYOUT["viewport"][0] + 12)
        y_max = float(LAYOUT["captions"]["y"][0] - 44)
        for _ in range(8):
            for a in range(len(boxes)):
                boxes[a][1] = max(24.0, min(boxes[a][1], float(W - boxes[a][0].get_width() - 24)))
                boxes[a][2] = max(y_min, min(boxes[a][2], y_max))
            moved = False
            for a in range(len(boxes)):
                for b in range(a + 1, len(boxes)):
                    ra = pygame.Rect(int(boxes[a][1]), int(boxes[a][2]), boxes[a][0].get_width(), boxes[a][0].get_height()).inflate(8, 6)
                    rb = pygame.Rect(int(boxes[b][1]), int(boxes[b][2]), boxes[b][0].get_width(), boxes[b][0].get_height()).inflate(8, 6)
                    if ra.colliderect(rb):
                        dy = (ra.bottom - rb.top) / 2.0 + 2.0 if ra.centery <= rb.centery else -((rb.bottom - ra.top) / 2.0 + 2.0)
                        boxes[a][2] -= dy
                        boxes[b][2] += dy
                        moved = True
            if not moved:
                break
        drawn_rects: list[pygame.Rect] = []
        for s, x, y, _rk in boxes:
            x = max(24.0, min(x, float(W - s.get_width() - 24)))
            y = max(y_min, min(y, y_max))
            cand = pygame.Rect(int(x), int(y), s.get_width(), s.get_height())
            if any(cand.inflate(4, 2).colliderect(prev) for prev in drawn_rects):
                continue
            self.frame.blit(s, cand.topleft)
            drawn_rects.append(cand)

    def _bomb(self, x, y, t, timer: float | None = None):
        pulse = 2 if (timer is not None and timer < 1.5 and int(t * 14) % 2 == 0) else 0
        pygame.draw.circle(self.frame, WHITE_ if pulse else BLACK, (int(x), int(y - 16)), 20 + pulse)
        pygame.draw.circle(self.frame, (44, 46, 62), (int(x), int(y - 16)), 17 + pulse)
        pygame.draw.circle(self.frame, (120, 128, 152), (int(x - 5), int(y - 22)), 5)
        pygame.draw.line(self.frame, (175, 132, 86), (x + 8, y - 30), (x + 18, y - 44), 4)
        pygame.draw.circle(self.frame, (255, 224, 48) if int(t * 12) % 2 else (255, 72, 36), (int(x + 19), int(y - 46)), 8)
        if timer is not None:
            col_t = (255, 76, 76) if timer < 1.8 else (255, 228, 72)
            ft = hud.outlined(f"{timer:.1f}s", 22, fill=col_t, width=3)
            self.frame.blit(ft, ft.get_rect(center=(int(x), int(y - 62))))

    def draw_juice(self, cam: Cam, play_t: float, t_anim: float, popups: bool = False) -> None:
        """World-space elimination ghosts, sparks, dust & corner clunks.
        P0.4: Comic callouts (`BETRAYAL!`, `BONK!`, `YEET!`, `OOF!`) now render in `draw_popups()` ABOVE the HUD layer."""
        for e in self.tr.events:
            age = play_t - e.t
            if age < 0 or age > 0.95 or e.pos is None:
                continue
            sx, sy = cam.to_screen(*e.pos)
            visible = cam.on_screen(e.pos[0], e.pos[1], pad=10)
            seed = int(e.t * 1000) % 997
            if e.kind == "elimination":
                cause = e.data.get("cause", "")
                if cause == "left_behind":
                    continue   # rendered in foreground right over the Killer Fire Wall!
                if cause == "bomb" and visible:
                    effects.draw_incineration(self.frame, (sx, sy), age, seed)
                    effects.draw_sparks(self.frame, (sx, sy), age, seed)
                elif cause in ("fell", "lava", "crushed") and self.tr.mode == "SIDE_VIEW" and 0 <= sx <= W:
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
        if popups:
            self.draw_popups(cam, play_t)

    def draw_popups(self, cam: Cam, play_t: float) -> None:
        """P0.4: High-Z comic starburst pass rendered strictly ABOVE the HUD layer & clamped clear of HUD bounds."""
        for t0, word, pos, seed in self.popups:
            age = play_t - t0
            if 0 <= age < effects.POPUP_S and cam.on_screen(pos[0], pos[1], pad=10):
                sx, sy = cam.to_screen(*pos)
                effects.draw_popup(self.frame, word, (sx, sy - 70), age, seed)

    def _draw_killer_fire(self, cam: Cam, fi: int, play_t: float, t_anim: float) -> None:
        """v4.0 Foreground Themed Killer Wall & Ceiling Purge Wave (SIDE_VIEW):
        - Skinned per SeasonTheme (Royal Fire, Frostfire, Molten Magma, Cyber Plasma, Monsoon Lightning,
          Toxic Ghostfire, Solar Flare, Hot-Pink Berry Syrup).
        - Richly textured [0 .. base_x] interior: scrolling storm bands, billowing smoke arcs, diagonal heat/plasma
          streaks, and drifting bright embers (NEVER a flat solid block!).
        - Also renders CollapseTower's descending `tower_fire_y` ceiling purge wave."""
        zone = self.tr.zones[fi]
        fr = self.frame
        th = self.theme
        top = LAYOUT["viewport"][0]
        h_span = H - top
        c_out = getattr(th, "wall_outer", (185, 28, 28))
        c_mid = getattr(th, "wall_mid", (249, 115, 22))
        c_core = getattr(th, "wall_core", (254, 240, 138))
        c_back = getattr(th, "wall_back", (128, 18, 18))
        c_glow = getattr(th, "wall_glow", (11, 5, 1))

        base_x = cam.to_screen(zone["chase_x"], 0)[0] if "chase_x" in zone else -999.0

        # A) CollapseTower descending ceiling purge wave (`tower_fire_y`)
        if "tower_fire_y" in zone:
            purge_sy = cam.to_screen(0, zone["tower_fire_y"])[1]
            if purge_sy > top - 24:
                xs = list(range(-16, W + 28, 16))
                p1, p2, p3 = [], [], []
                for x in xs:
                    u1 = x + t_anim * 155.0
                    dy1 = 30.0 + 18.0 * math.sin(u1 * 0.025) + 10.0 * math.sin(u1 * 0.064 + 1.2)
                    p1.append((float(x), purge_sy + dy1))
                    u2 = x + t_anim * 235.0
                    dy2 = 12.0 + 14.0 * math.sin(u2 * 0.032 + 0.9) + 8.0 * math.sin(u2 * 0.078 + 2.1)
                    p2.append((float(x), purge_sy + dy2))
                    u3 = x + t_anim * 315.0
                    dy3 = -6.0 + 11.0 * math.sin(u3 * 0.041 + 2.0) + 6.0 * math.sin(u3 * 0.095 + 0.5)
                    p3.append((float(x), purge_sy + dy3))
                pygame.draw.polygon(fr, c_out, [(-20.0, float(top - 10)), (float(W + 20), float(top - 10))] + p1[::-1])
                pygame.draw.polygon(fr, c_mid, [(-20.0, float(top - 10)), (float(W + 20), float(top - 10))] + p2[::-1])
                pygame.draw.polygon(fr, c_core, [(-20.0, float(top - 10)), (float(W + 20), float(top - 10))] + p3[::-1])
                if purge_sy - top > 32:
                    back_band = [(px, py - 34.0 - 10.0 * math.sin((px + t_anim * 220.0) * 0.03)) for px, py in p3]
                    pygame.draw.polygon(fr, c_back, [(-20.0, float(top - 10)), (float(W + 20), float(top - 10))] + back_band[::-1])
                    for k in range(12):
                        sx_k = (k * 103.0 + t_anim * 95.0) % W
                        sy_k = top + ((k * 47.0 + t_anim * 110.0) % max(16.0, purge_sy - top))
                        pygame.draw.arc(fr, scenery.mix(c_back, BLACK, 0.45), (int(sx_k - 32), int(sy_k - 14), 64, 28), 0.2, 2.9, 4)
                        pygame.draw.circle(fr, c_core, (int((sx_k + 45) % W), int(sy_k)), 3)

        # B) Side-view advancing Killer Wall (`chase_x`) + Richly Textured [0 .. base_x] Interior
        if base_x > -110:
            pts1: list[tuple[float, float]] = []
            pts2: list[tuple[float, float]] = []
            pts3: list[tuple[float, float]] = []
            ys = list(range(top - 16, H + 28, 12))
            for y in ys:
                u1 = y + t_anim * 140.0
                dx1 = 42.0 + 26.0 * math.sin(u1 * 0.026) + 15.0 * math.sin(u1 * 0.061 + 1.1) + 9.0 * math.sin(u1 * 0.128 - t_anim * 3.8)
                cy1 = y - 11.0 * max(0.0, math.sin(u1 * 0.026 + 0.65))
                pts1.append((base_x + dx1, cy1))

                u2 = y + t_anim * 220.0
                dx2 = 16.0 + 22.0 * math.sin(u2 * 0.031 + 0.9) + 12.0 * math.sin(u2 * 0.074 + 2.2) + 7.5 * math.sin(u2 * 0.149 - t_anim * 5.2)
                cy2 = y - 9.0 * max(0.0, math.sin(u2 * 0.031 + 1.55))
                pts2.append((base_x + dx2, cy2))

                u3 = y + t_anim * 310.0
                dx3 = -10.0 + 18.0 * math.sin(u3 * 0.038 + 2.0) + 10.0 * math.sin(u3 * 0.089 + 0.4) + 6.0 * math.sin(u3 * 0.176 - t_anim * 7.0)
                cy3 = y - 7.0 * max(0.0, math.sin(u3 * 0.038 + 2.65))
                pts3.append((base_x + dx3, cy3))

            max_x = max(p[0] for p in pts1)
            glow_w = min(W, max(16, int(max_x + 92)))
            if glow_w > 16:
                glow = pygame.Surface((glow_w, h_span))
                for step in range(17, 0, -1):
                    off = step * 5.0
                    poly_g = [(0.0, 0.0)] + [(max(0.0, px + off), py - top) for px, py in pts1] + [(0.0, float(h_span))]
                    pygame.draw.polygon(glow, c_glow, poly_g)
                fr.blit(glow, (0, top), special_flags=pygame.BLEND_RGB_ADD)

                smoke = pygame.Surface((min(W, glow_w + 40), h_span), pygame.SRCALPHA)
                for i in range(14):
                    sy_loc = (i * 137.0 - t_anim * (175.0 + (i % 3) * 28.0)) % (h_span + 60) - 30
                    u_s = (sy_loc + top) + t_anim * 140.0
                    edge_x = base_x + 44.0 + 22.0 * math.sin(u_s * 0.026) + 14.0 * math.sin(t_anim * 2.4 + i)
                    if 0 <= edge_x < smoke.get_width() - 20:
                        sr = 18 + (i % 4) * 5
                        pygame.draw.circle(smoke, (26, 20, 28, 72), (int(edge_x + 12), int(sy_loc)), sr)
                fr.blit(smoke, (0, top))

            if getattr(th, "wall_style", "") == "neon" and base_x > 0:
                # Solid dark pulsing cyber-grid void behind the plasma edge (castle never peeks through)
                vw = int(min(W, base_x + 30))
                pygame.draw.rect(fr, (12, 6, 30), (0, top, vw, h_span))
                pulse_c = scenery.mix((40, 18, 90), (0, 200, 255), 0.35 + 0.25 * math.sin(t_anim * 6.0))
                for gx in range(int((t_anim * 40) % 44) - 44, vw, 44):
                    pygame.draw.line(fr, pulse_c, (gx, top), (gx, H), 2)
                for gy in range(top + int((t_anim * 90) % 44), H, 44):
                    pygame.draw.line(fr, pulse_c, (0, gy), (vw, gy), 2)
            # 3-Layer Leading Edge Ribbons
            pygame.draw.polygon(fr, c_out, [(-20.0, float(top - 20))] + pts1 + [(-20.0, float(H + 20))])
            pygame.draw.polygon(fr, c_mid, [(-20.0, float(top - 20))] + pts2 + [(-20.0, float(H + 20))])
            pygame.draw.polygon(fr, c_core, [(-20.0, float(top - 20))] + pts3 + [(-20.0, float(H + 20))])

            # Richly Textured Interior [0 .. base_x] (scrolling storm waves + billowing dark smoke arcs + diagonal heat streaks + embers)
            if base_x > 26:
                back_mid = [(px - 36.0 - 14.0 * math.sin((py + t_anim * 250.0) * 0.034), py) for px, py in pts3]
                pygame.draw.polygon(fr, scenery.mix(c_mid, c_out, 0.45), [(-20.0, float(top - 20))] + back_mid + [(-20.0, float(H + 20))])
                if base_x > 72:
                    back_dp = [(px - 80.0 - 18.0 * math.sin((py + t_anim * 185.0) * 0.028 + 1.3), py) for px, py in pts3]
                    pygame.draw.polygon(fr, c_back, [(-20.0, float(top - 20))] + back_dp + [(-20.0, float(H + 20))])

                int_w = max(12, int(min(W, base_x - 14)))
                smoke_col_dark = scenery.mix(c_back, BLACK, 0.52)
                streak_col = scenery.mix(c_mid, c_core, 0.48)
                # Diagonal heat/plasma streaks sweeping upward-right inside [0 .. base_x]
                for i in range(14):
                    sx0 = ((i * 73.0 + t_anim * 135.0) % (int_w + 80)) - 60
                    sy0 = top + ((i * 129.0 - t_anim * (230.0 + (i % 4) * 35.0)) % h_span)
                    sx1 = min(float(int_w), sx0 + 46.0 + (i % 3) * 18.0)
                    sy1 = sy0 - 54.0
                    if sx1 > 2 and sx0 < int_w:
                        pygame.draw.line(fr, streak_col, (max(0.0, sx0), sy0), (sx1, sy1), 4 if i % 2 == 0 else 3)

                # Billowing dark smoke arcs swirling upward inside [0 .. base_x]
                for i in range(18):
                    bx_s = ((i * 61.0 - t_anim * 48.0 + 18.0 * math.sin(t_anim * 2.6 + i)) % max(24.0, float(int_w)))
                    by_s = top + ((i * 97.0 - t_anim * (165.0 + (i % 5) * 24.0)) % h_span)
                    rw = 34 + (i % 4) * 12
                    rh = 24 + (i % 3) * 8
                    if bx_s + rw * 0.5 < int_w + 8:
                        pygame.draw.arc(fr, smoke_col_dark, (int(bx_s - rw / 2), int(by_s - rh / 2), rw, rh),
                                        0.3 + (i % 3) * 0.4, 2.8 + (i % 2) * 0.5, 5)

                # Drifting incandescent interior embers inside [0 .. base_x]
                for i in range(20):
                    ex_in = ((i * 53.0 + t_anim * 92.0 + 14.0 * math.cos(t_anim * 4.2 + i)) % max(16.0, float(int_w)))
                    ey_in = top + ((i * 107.0 - t_anim * (260.0 + (i % 4) * 32.0)) % h_span)
                    er_in = 2 + (i % 3)
                    pygame.draw.circle(fr, c_mid, (int(ex_in), int(ey_in)), er_in + 2)
                    pygame.draw.circle(fr, c_core, (int(ex_in), int(ey_in)), er_in)

            # Rising bright ember sparks ahead of the leading edge
            for i in range(22):
                spd_y = 250.0 + (i % 5) * 38.0
                ey = top + ((i * 113.0 - t_anim * spd_y) % h_span)
                life = ((i * 0.31 + t_anim * 1.4) % 1.0)
                ex = base_x + 24.0 + life * 68.0 + 16.0 * math.sin(t_anim * 5.5 + i * 1.7)
                if -10 <= ex <= W:
                    er = max(2, int((4.5 - 2.5 * life)))
                    pygame.draw.circle(fr, c_mid, (int(ex), int(ey)), er + 2)
                    pygame.draw.circle(fr, c_core, (int(ex), int(ey)), er)

        # C) Foreground Incineration Burn VFX (exact frame of flame/purge contact -> flare + char + ghost)
        for e in self.tr.events:
            if e.kind != "elimination" or e.data.get("cause") != "left_behind" or e.pos is None:
                continue
            age = play_t - e.t
            if age < 0.0 or age > 1.05:
                continue
            sx, sy = cam.to_screen(*e.pos)
            if "chase_x" in zone:
                sx = max(float(max(28.0, base_x + 18.0)), sx)
            if -40 <= sx <= W + 40 and top <= sy <= H:
                seed = int(e.t * 1000) % 997
                effects.draw_incineration(fr, (sx, sy), age, seed)
                if age >= 0.16:
                    col = renderer.hex_rgb(HERO_BY_KEY[e.actors[0]].colour) if e.actors[0] in HERO_BY_KEY else (230, 220, 200)
                    effects.draw_ghost(fr, (sx, sy - 10), age - 0.16, col)

    # ------------------------------------------------------------------ frame & Commentator Host state
    def _ranks(self, fi: int) -> dict[str, int]:
        rows, flags = self.tr.frames[fi], self.tr.flags[fi]
        scores = self.tr.zones[min(fi, len(self.tr.zones) - 1)].get("scores") or {}
        alive_heroes = [i for i in range(len(self.tr.keys)) if (flags[i] & T.ALIVE) and self.tr.keys[i] in HERO_BY_KEY]

        def tie(i: int) -> float:
            if self.tr.mode == "TOP_DOWN":
                return float(rows[i, 0] ** 2 + rows[i, 1] ** 2)
            if self.meta.get("vertical_tower"):
                return float(-rows[i, 1])
            return float(-rows[i, 0])

        alive_heroes.sort(key=lambda i: (bool(flags[i] & T.HAS_BOMB), -float(scores.get(self.tr.keys[i], 0.0)), tie(i)))
        w = self.meta.get("winner")
        if w and w in HERO_BY_KEY and flags[self.tr.index(w)] & T.WINNER:
            alive_heroes.sort(key=lambda i: self.tr.keys[i] != w)
        return {self.tr.keys[i]: r + 1 for r, i in enumerate(alive_heroes)}

    def tuno_state(self, play_t: float, segment: str) -> tuple[str, str]:
        """P2.4 Event-Driven King Animations in the castle window:
        - `LEVER_PULL`: 0.5 s before (through +0.35 s after) REVERSED CONTROLS!, SPEED UP!, SHRINKING ARENA!, or twists.
        - `LAUGHING_TEARS`: multi-eliminations (>= 3 eliminations within 1.0 s).
        - `SHOCKED_JAWDROP`: BETRAYAL! events or photo finishes."""
        if segment == "cold":
            return "HYPED_TALKING", ""
        if segment == "card":
            return "TROPHY_CHEER", ""
        if segment == "replay":
            return ("SHOCKED_JAWDROP" if self.is_photo_finish else "TROPHY_CHEER"), ""
        # 1. lever_pull: 0.5 s before REVERSED CONTROLS!, SPEED UP!, SHRINKING ARENA! (holds briefly through pull)
        if any(-0.50 <= play_t - lt <= 0.35 for lt in self.lever_times):
            return "LEVER_PULL", ""
        # 2. laughing: >= 3 eliminations within 1.0 s
        recent = [e for e in self.elims if 0.0 <= play_t - e.t < 1.15]
        for e in recent:
            if sum(1 for o in self.elims if e.t - 1.0 <= o.t <= e.t) >= 3:
                return "LAUGHING_TEARS", ""
        # 3. shocked: BETRAYAL! events or photo finishes
        if any(e.data.get("hero") and e.data.get("by_hero") for e in recent):
            return "SHOCKED_JAWDROP", ""
        if self.is_photo_finish and play_t >= self.end_t - 1.2:
            return "SHOCKED_JAWDROP", ""
        if recent and not recent[-1].data.get("by_hero") and recent[-1].data.get("cause") in ("fell", "lava"):
            return "FACEPALM", ""
        if play_t >= self.overtime_t:
            return "SWEATING_INTENSE", ""
        return "HYPED_TALKING", ""

    def _active_twist_badge(self, fi: int, play_t: float) -> tuple[str, str, tuple[int, int, int]] | None:
        zone = self.tr.zones[fi]
        tw = self.meta["recipe"].get("twist")
        if tw and zone.get("twist_on"):
            mapping = {
                "heavy_gravity": ("down", "HEAVY GRAV", (255, 118, 42)),
                "low_gravity": ("up", "LOW GRAV", (0, 229, 255)),
                "slippery_floor": ("ice", "SLIPPERY ICE", (125, 232, 255)),
                "speed_boost_zones": ("bolt", "2X BOOST", (250, 204, 21)),
                "shrinking_arena": ("orb", "SHRINKING", (255, 82, 120)),
                "giant_ball": ("orb", "GIANT BALL", (255, 77, 166)),
                "reversed_controls": ("orb", "REVERSED", (192, 112, 255)),
                "random_teleport_pads": ("orb", "TELEPORT", (148, 92, 255)),
            }
            if tw in mapping:
                return mapping[tw]
        if play_t >= self.overtime_t or TIMELINE.speed_at(play_t) >= 1.6:
            return ("bolt", "2X OVERTIME", (255, 72, 88))
        if TIMELINE.speed_at(play_t) > 1.05:
            return ("bolt", "1.3X SPEED", (250, 204, 21))
        return None

    def _draw_cold_hook_banner(self, seg_t: float) -> None:
        """P1.1: Crisp <= 1.5s instant-action viewer hook overlay ('PICK YOUR FIGHTER!' or 'WHO SURVIVES?')."""
        goal = str(self.meta.get("recipe", {}).get("goal") or "reach_finish")
        text = "WHO SURVIVES?" if (self.tr.mode == "TOP_DOWN" or goal in ("last_one_standing", "survive_timer", "hot_potato_bomb")) else "PICK YOUR FIGHTER!"
        k_in = min(1.0, seg_t / 0.14)
        k_out = 1.0 if seg_t < TIMELINE.cold_open_s - 0.22 else max(0.0, (TIMELINE.cold_open_s - seg_t) / 0.22)
        alpha = int(255 * min(k_in, k_out))
        if alpha <= 12:
            return
        scale = 1.22 - 0.22 * k_in
        base = hud.fit_width(hud.outlined(text, 74, fill=(255, 224, 48), width=7), 860)
        s = hud.fit_width(pygame.transform.rotozoom(base, -2, scale), 920)
        if alpha < 255:
            s = s.copy()
            s.set_alpha(alpha)
        hud.blit_text(self.frame, s, center=(W // 2, 418))

    def _resolve_cam(self, shot: Shot, fi: int, tf: float) -> Cam:
        cam = self.cams[fi]
        cap = self.cams[min(self.pre, len(self.cams) - 1)].zoom * 2.6
        if self.tr.mode == "TOP_DOWN":
            z_top = min(cam.zoom * (1.08 if shot.segment == "replay" else shot.zoom_mult), cap)
            return Cam(cam.x, cam.y, z_top, cam.shake)
        if shot.zoom_mult != 1.0 and shot.focus:
            i = self.tr.index(shot.focus)
            rows, _, _ = self.tr.sample(tf / FPS)
            return Cam(float(rows[i, 0]), float(rows[i, 1]), min(cam.zoom * shot.zoom_mult, cap))
        if shot.zoom_mult != 1.0:
            return Cam(cam.x, cam.y, min(cam.zoom * shot.zoom_mult, cap), cam.shake)
        return cam

    def render_world_crop(self, shot: Shot, index: int, out_w: int = 1120, out_h: int = 840) -> pygame.Surface:
        """Part 5: Renders a clean HUD-free 4:3 (1120x840) widescreen action crop centered on the camera's focal band
        so characters and physics fill 58% of the 1920x1080 Tuno Report screen with zero aspect distortion."""
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self._resolve_cam(shot, fi, tf)
        t_anim = index / FPS
        play_t = (fi - self.pre) / FPS
        eff_play_t = play_t if shot.segment not in ("cold", "replay", "chaos_slomo") else (tf - self.pre) / FPS
        ranks = self._ranks(fi)
        slow = shot.segment in ("cold", "replay", "chaos_slomo") or abs(tf - round(tf)) > 1e-3
        active_seg = shot.segment in ("play", "replay", "chaos_slomo")

        self.frame.set_clip(None)
        self.draw_world(cam, fi, t_anim, 0.0 if shot.segment == "cold" else play_t)
        self.frame.set_clip(pygame.Rect(0, 0, W, H))
        self.draw_contestants(cam, tf if slow else fi, t_anim, ranks=ranks, show_tags=active_seg)
        if shot.segment == "replay":
            effects.draw_confetti(self.frame, shot.seg_t, 5, pygame.Rect(0, 420, W, 1080))
        if shot.segment in ("play", "replay", "chaos_slomo", "cold"):
            self.draw_juice(cam, eff_play_t, t_anim, popups=False)
        if active_seg:
            self._draw_glitch_blinks(cam, fi, eff_play_t)
        if self.tr.mode == "SIDE_VIEW":
            self._abyss(cam, fi, t_anim)
            if shot.segment != "card":
                self._draw_killer_fire(cam, fi, eff_play_t, t_anim)
        if active_seg:
            self.draw_popups(cam, eff_play_t)
        self.frame.set_clip(None)

        # Exact 4:3 crop (1080x810) centered at the camera's SCREEN_CY (950) -> scaled cleanly to out_w x out_h (1120x840)
        crop_h = int(round(W * out_h / max(1, out_w)))
        cy_screen = int(round(sum(LAYOUT["action_bias"]) / 2))
        y0 = max(0, min(H - crop_h, cy_screen - crop_h // 2))
        sub = self.frame.subsurface(pygame.Rect(0, y0, W, crop_h))
        out = pygame.transform.smoothscale(sub, (out_w, out_h)) if (W, crop_h) != (out_w, out_h) else sub.copy()
        if shot.segment in ("replay", "chaos_slomo"):
            lbl_s = "INSTANT REPLAY" if shot.segment == "replay" else "CHAOS CAM • 0.4X"
            bg_c = (190, 30, 60) if shot.segment == "replay" else (217, 119, 6)
            txt = hud.outlined(lbl_s, 28, fill=(255, 236, 120), width=4)
            box = pygame.Rect(0, 0, txt.get_width() + 62, 46)
            box.topright = (out_w - 22, 20)
            pygame.draw.rect(out, BLACK, box.move(0, 3), border_radius=23)
            pygame.draw.rect(out, bg_c, box, border_radius=23)
            pygame.draw.rect(out, BLACK, box, 3, border_radius=23)
            if int(t_anim * 4) % 2 == 0:
                pygame.draw.circle(out, WHITE_, (box.left + 22, box.centery), 8)
            out.blit(txt, txt.get_rect(midleft=(box.left + 40, box.centery)))
        return out

    def render_shot(self, shot: Shot, index: int) -> pygame.Surface:
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self._resolve_cam(shot, fi, tf)
        t_anim = index / FPS
        play_t = (fi - self.pre) / FPS
        eff_play_t = play_t if shot.segment not in ("cold", "replay") else (tf - self.pre) / FPS
        hud_fi = self.end_f if shot.segment == "card" else fi
        ranks = self._ranks(hud_fi)
        slow = shot.segment in ("cold", "replay")
        self.frame.set_clip(None)
        self.draw_world(cam, fi, t_anim, 0.0 if shot.segment == "cold" else play_t)
        self.frame.set_clip(self.world_rect)
        self.draw_contestants(cam, tf if slow else fi, t_anim, ranks=ranks,
                              show_tags=shot.segment in ("play", "replay"))
        # P0.1: Trigger confetti particle burst immediately throughout the 1.5s 0.3x slow-motion finish sequence!
        if shot.segment == "replay":
            effects.draw_confetti(self.frame, shot.seg_t, 5, self.world_rect)
        if shot.segment == "cold" and not self.finale:
            self._draw_spotlights(cam, fi, shot.seg_t)
        if shot.segment in ("play", "replay", "cold"):
            self.draw_juice(cam, eff_play_t, t_anim, popups=False)
        if shot.segment in ("play", "replay"):
            self._draw_glitch_blinks(cam, fi, eff_play_t)
        if self.tr.mode == "SIDE_VIEW":
            self._abyss(cam, fi, t_anim)
            if shot.segment != "card":
                self._draw_killer_fire(cam, fi, eff_play_t, t_anim)
            if shot.segment in ("play", "replay"):
                self._edge_rival_pills(cam, fi, ranks, t_anim)
        if shot.segment == "replay":
            self._replay_badge(t_anim)
        self.frame.set_clip(None)
        rms = self.voice_rms[index] if (self.voice_rms is not None and index < len(self.voice_rms)) else None
        self._overlays(shot, play_t, t_anim, hud_fi, ranks, index / FPS, voice_rms=rms)
        # P0.4: Comic callouts render on a strictly higher z-layer ABOVE the HUD (and never over Winner Card)
        if shot.segment in ("play", "replay"):
            self.draw_popups(cam, eff_play_t)
        self._draw_brand_overlay(shot)
        return self.frame

    def _draw_glitch_blinks(self, cam: Cam, fi: int, play_t: float) -> None:
        """v4.3.1 HIGH-VISIBILITY Glitch Micro Lag-Blink (mobile-first): 3 bold cyan/magenta wireframe ghosts bridging
        old -> new position (alpha 0.90 -> 0.0 over 0.38 s, black-backed for contrast), a crisp 0.18 s horizontal RGB
        slice flash over Glitch's body, and neon pixel sparks."""
        GHOST_S, TEAR_S = 0.38, 0.18
        for e in self.glitch_blinks:
            age = play_t - e.t
            if age < 0.0 or age > GHOST_S:
                continue
            src, dst = e.data.get("src") or e.pos, e.data.get("dst") or e.pos
            if src is None or dst is None:
                continue
            k = e.actors[0] if e.actors else "glitch"
            rad = (HERO_BY_KEY[k].radius if k in HERO_BY_KEY else 24.0) * cam.zoom
            fade = max(0.0, 1.0 - age / GHOST_S)
            a = int(255 * 0.90 * fade)
            lw = max(3, int(5 * cam.zoom))
            layer = pygame.Surface((W, H), pygame.SRCALPHA)
            if e.data.get("moved"):
                for gi, u in enumerate((0.0, 0.34, 0.67)):
                    gx, gy = cam.to_screen(src[0] + (dst[0] - src[0]) * u, src[1] + (dst[1] - src[1]) * u)
                    col = (0, 255, 255) if gi % 2 == 0 else (255, 0, 220)
                    off = (gi - 1) * 5
                    pygame.draw.circle(layer, (10, 10, 20, int(a * 0.8)), (gx + off, gy), rad + 2, lw + 4)   # contrast
                    pygame.draw.circle(layer, (*col, int(a * 0.22)), (gx + off, gy), rad)                    # glow fill
                    pygame.draw.circle(layer, (*col, a), (gx + off, gy), rad, lw)
                    step = max(4, int(rad / 3.2))
                    for yy in range(int(gy - rad) + step // 2, int(gy + rad), step):        # pixel scan-lines
                        hw_ = math.sqrt(max(0.0, rad * rad - (yy - gy) ** 2))
                        pygame.draw.line(layer, (*col, int(a * 0.7)), (gx - hw_ + off, yy), (gx + hw_ + off, yy), 2)
                # streak connecting the ghosts
                s0, s1 = cam.to_screen(*src), cam.to_screen(*dst)
                pygame.draw.line(layer, (255, 255, 255, int(a * 0.6)), s0, s1, max(2, int(3 * cam.zoom)))
            cx, cy = cam.to_screen(*dst)
            rng = random.Random(int(e.t * 1000))
            for _ in range(14):                                                    # neon pixel sparks
                ang = rng.uniform(0, 2 * math.pi)
                d = rad * (1.0 + 1.8 * age / GHOST_S) * rng.uniform(0.8, 1.3)
                sz = max(4, int(8 * cam.zoom))
                col = (0, 255, 255) if rng.random() < 0.5 else (255, 0, 220)
                pygame.draw.rect(layer, (*col, int(255 * fade)), (cx + math.cos(ang) * d, cy + math.sin(ang) * d, sz, sz))
            self.frame.blit(layer, (0, 0))
            if age <= TEAR_S:                                                      # crisp horizontal RGB slice flash
                kf = 1.0 - age / TEAR_S
                box = pygame.Rect(int(cx - rad * 1.8), int(cy - rad * 1.3), int(rad * 3.6), int(rad * 2.6))
                box = box.clip(self.frame.get_rect())
                if box.width > 4 and box.height > 4:
                    snap = self.frame.subsurface(box).copy()
                    sl_h = max(4, box.height // 8)
                    for si, yy in enumerate(range(0, box.height, sl_h)):
                        shift = int(rng.uniform(-1, 1) * rad * 0.8 * kf)
                        h_ = min(sl_h, box.height - yy)
                        strip = snap.subsurface(pygame.Rect(0, yy, box.width, h_)).copy()
                        tint = (0, 255, 255) if si % 2 == 0 else (255, 0, 220)
                        self.frame.blit(strip, (box.left + shift, box.top + yy))
                        band = pygame.Surface((box.width, h_), pygame.SRCALPHA)
                        band.fill((*tint, int(110 * kf)))
                        self.frame.blit(band, (box.left + shift, box.top + yy))
                        pygame.draw.line(self.frame, tint, (box.left + shift, box.top + yy),
                                         (box.left + shift + box.width, box.top + yy), 2)

    def _edge_rival_pills(self, cam: Cam, fi: int, ranks: dict[str, int], t: float) -> None:
        """v4.3: when the final 2-3 are spread out, a compact `◀ [icon] #2` pill rides the screen edge showing the
        off-screen chaser's live position (the camera stays big on the lead cluster instead of zooming out)."""
        flags = self.tr.flags[fi]
        alive = [h.key for h in self.heroes if flags[self.tr.index(h.key)] & T.ALIVE]
        if not (2 <= len(alive) <= 3):
            return
        vy0, vy1 = LAYOUT["viewport"]
        for k in alive:
            x, y = float(self.tr.frames[fi][self.tr.index(k)][0]), float(self.tr.frames[fi][self.tr.index(k)][1])
            sx, sy = cam.to_screen(x, y)
            if 0 <= sx <= W:
                continue
            left = sx < 0
            py = max(vy0 + 170, min(vy1 - 120, sy))
            pill = pygame.Rect(0, 0, 170, 62)
            if left:
                pill.midleft = (12, int(py))
            else:
                pill.midright = (W - 12, int(py))
            bob = 3 * math.sin(t * 7)
            pill.move_ip(int(bob if left else -bob), 0)
            pygame.draw.rect(self.frame, BLACK, pill.move(0, 4), border_radius=31)
            pygame.draw.rect(self.frame, (24, 20, 46), pill, border_radius=31)
            pygame.draw.rect(self.frame, (255, 96, 48), pill, 4, border_radius=31)
            ax = pill.left + 22 if left else pill.right - 22
            d = -1 if left else 1
            tri = [(ax + d * 12, pill.centery), (ax - d * 8, pill.centery - 14), (ax - d * 8, pill.centery + 14)]
            pygame.draw.polygon(self.frame, (255, 96, 48), tri)
            pygame.draw.polygon(self.frame, BLACK, tri, 2)
            icx = pill.left + 70 if left else pill.right - 112
            hud._mini_hero_ball(self.frame, k, icx, pill.centery, 20, None)
            rk = hud.outlined(f"#{ranks.get(k, 2)}", 30, fill=WHITE_, width=4)
            self.frame.blit(rk, rk.get_rect(midleft=(icx + 28, pill.centery)))
            hud.TEXT_BOXES.append(pill)

    def _replay_badge(self, t: float) -> None:
        txt = hud.outlined("INSTANT REPLAY", 30, fill=(255, 236, 120), width=4)
        box = pygame.Rect(0, 0, txt.get_width() + 70, 52)
        box.midtop = (W // 2, LAYOUT["viewport"][0] + 150)
        pygame.draw.rect(self.frame, BLACK, box.move(0, 4), border_radius=26)
        pygame.draw.rect(self.frame, (190, 30, 60), box, border_radius=26)
        pygame.draw.rect(self.frame, BLACK, box, 3, border_radius=26)
        if int(t * 4) % 2 == 0:
            pygame.draw.circle(self.frame, WHITE_, (box.left + 26, box.centery), 9)
        self.frame.blit(txt, txt.get_rect(midleft=(box.left + 46, box.centery)))

    def _abyss(self, cam: Cam, fi: int, t: float) -> None:
        """Recessed pit trench in front of background pillars & below all track slabs (SIDE_VIEW only)."""
        fr = self.frame
        bstyle = getattr(self.theme, "block_style", "royal")
        ky = self.tr.zones[fi].get("lava_y", self.meta.get("kill_y", 500.0))
        y0 = int(cam.to_screen(0, ky)[1])
        if H >= 1500:
            y0 = max(1540, int(self._lowest_slab_y + 28), min(1760, y0))
            y0 = min(1760, y0)
        else:
            y0 = max(H - 220, int(self._lowest_slab_y + 24), min(H - 86, y0))
            y0 = min(H - 86, y0)

        pygame.draw.rect(fr, BLACK, (0, y0 - 8, W, H - y0 + 8))
        pygame.draw.rect(fr, (54, 52, 74), (0, y0 - 6, W, 12))
        pygame.draw.rect(fr, (18, 16, 30), (0, y0 + 6, W, H - y0 - 6))

        if bstyle in ("obsidian", "sandstone", "neon", "gothic", "wafer"):
            c_out = getattr(self.theme, "wall_outer", (195, 48, 12))
            c_mid = getattr(self.theme, "wall_mid", (255, 112, 22))
            c_core = getattr(self.theme, "wall_core", (255, 224, 92))
            pygame.draw.rect(fr, c_out, (0, y0 + 18, W, H - y0 - 18))
            pts = [(x, y0 + 18 + 10 * math.sin(t * 3.2 + x * 0.02)) for x in range(0, W + 20, 20)]
            pygame.draw.polygon(fr, c_mid, pts + [(W, H), (0, H)])
            pygame.draw.lines(fr, c_core, False, pts, 5)
            for i in range(9):
                bx = (i * 131 + t * 32) % W
                by = y0 + 56 + 24 * math.sin(t * 2.4 + i)
                pygame.draw.circle(fr, c_core, (bx, by), 9 + 3 * math.sin(t * 6 + i))
        else:
            spike_hi = (198, 240, 255) if bstyle == "frost" else (148, 156, 174)
            spike_sh = (96, 148, 198) if bstyle == "frost" else (98, 106, 124)
            for x in range(-8, W + 48, 52):
                btip = (x + 52, y0 + 16)
                pygame.draw.polygon(fr, (42, 46, 64), [(x + 26, y0 + 78), btip, (x + 78, y0 + 78)])
            for x in range(-20, W + 48, 52):
                tip = (x + 26, y0 + 4)
                pygame.draw.polygon(fr, BLACK, [(x - 3, y0 + 78), tip, (x + 55, y0 + 78)])
                pygame.draw.polygon(fr, spike_hi, [(x + 3, y0 + 74), (tip[0], tip[1] + 8), (x + 49, y0 + 74)])
                pygame.draw.polygon(fr, spike_sh, [(tip[0], tip[1] + 8), (x + 49, y0 + 74), (tip[0], y0 + 74)])
                pygame.draw.line(fr, (232, 244, 255), (tip[0] - 2, tip[1] + 12), (x + 11, y0 + 68), 3)
            pygame.draw.rect(fr, (26, 26, 40), (0, y0 + 74, W, H - y0 - 74))

    def _talking(self, out_t: float) -> bool | None:
        if not self.speech:
            return None
        for ln in self.speech:
            if ln["t0"] <= out_t <= ln["t1"]:
                words = ln.get("words") or []
                if not words:
                    return True
                return any(w0 - 0.03 <= out_t <= w1 + 0.03 for w0, w1, _ in words)
        return False

    def _draw_goal_hud(self, fi: int, t_anim: float) -> None:
        """Compact broadcast objective badge at top-center of viewport so all 7 gameplays read instantly."""
        goal = str(self.meta.get("recipe", {}).get("goal") or "reach_finish")
        zone = self.tr.zones[min(fi, len(self.tr.zones) - 1)]
        scores = zone.get("scores") or {}
        top_hero, top_val = None, 0.0
        for k, v in scores.items():
            if k in HERO_BY_KEY and float(v) > top_val:
                top_hero, top_val = k, float(v)

        accent = (255, 214, 48)
        label = "RACE TO FINISH"
        if goal == "reach_finish":
            label, accent = "RACE TO FINISH", (255, 214, 48)
        elif goal == "last_one_standing":
            label, accent = "LAST BALL STANDING", (255, 168, 42)
        elif goal == "survive_timer":
            rem = float(zone.get("timer", 0.0))
            label = f"SURVIVE: {rem:04.1f}S"
            accent = (255, 78, 88) if rem < 4.5 else (96, 232, 255)
        elif goal == "collect_items":
            rem = float(zone.get("goal_timer", 0.0))
            label = f"CROWN RUSH {rem:04.1f}S" + (f"  x{int(top_val)}" if top_hero else "")
            accent = (255, 214, 42)
        elif goal == "hold_a_zone":
            need = float(zone.get("zone_need") or 5.5)
            label = f"KING OF THE HILL  {top_val:.1f}/{need:.1f}S" if top_hero else "KING OF THE HILL"
            accent = (92, 248, 148)
        elif goal == "push_others_out":
            label = f"KO BRAWL  {int(top_val)} KOS" if top_hero else "KO BRAWL"
            accent = (255, 96, 56)
        elif goal == "hot_potato_bomb":
            rem = float(zone.get("bomb_timer", 0.0))
            label = f"HOT POTATO  {rem:.1f}S"
            accent = (255, 68, 68) if rem < 1.8 else (255, 148, 48)

        txt = hud.outlined(label, 24, fill=WHITE_, width=3)
        extra_icon = 36 if top_hero and goal in ("collect_items", "hold_a_zone", "push_others_out") else 0
        w = min(560, txt.get_width() + 62 + extra_icon)
        h = 42
        box = pygame.Rect(0, 0, w, h)
        box.midtop = (W // 2, 314)
        plate = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(plate, (18, 18, 36, 224), (0, 0, w, h), border_radius=21)
        pygame.draw.rect(plate, (*accent, 245), (0, 0, w, h), 3, border_radius=21)
        self.frame.blit(plate, box.topleft)

        icx, icy = box.left + 24, box.centery
        if goal == "reach_finish":
            for r_i in range(2):
                for c_i in range(2):
                    col_f = BLACK if (r_i + c_i) % 2 else WHITE_
                    pygame.draw.rect(self.frame, col_f, (icx - 10 + c_i * 10, icy - 10 + r_i * 10, 10, 10))
            pygame.draw.rect(self.frame, accent, (icx - 10, icy - 10, 20, 20), 2)
        elif goal in ("last_one_standing", "collect_items"):
            hud._crown_badge(self.frame, icx, icy + 2, 24)
        elif goal == "survive_timer":
            hud._draw_hourglass_icon(self.frame, icx, icy, 11)
        elif goal == "hold_a_zone":
            pygame.draw.circle(self.frame, accent, (icx, icy), 11, 3)
            pygame.draw.circle(self.frame, (255, 214, 48), (icx, icy), 5)
        elif goal == "push_others_out":
            hud._draw_flame_icon(self.frame, icx, icy, 11)
        elif goal == "hot_potato_bomb":
            pygame.draw.circle(self.frame, BLACK, (icx, icy + 2), 10)
            pygame.draw.circle(self.frame, (255, 214, 48) if int(t_anim * 12) % 2 else (255, 68, 48), (icx + 7, icy - 8), 4)

        tx_left = box.left + 44
        if extra_icon and top_hero:
            hud._mini_hero_ball(self.frame, top_hero, tx_left + 12, icy, 13, None)
            tx_left += 32
        fit = hud.fit_width(txt, box.right - tx_left - 14)
        self.frame.blit(fit, fit.get_rect(midleft=(tx_left, icy + 1)))
        hud.TEXT_BOXES.append(box)

    def _draw_brand_overlay(self, shot: Shot) -> None:
        """v4.5 Unclipped Top-Most Branding Layer (rendered LAST after `set_clip(None)` and all HUD/card layers):
        1. MC Tuno Broadcast Booth Network Plate (`#0F172A`, `2px` `#FACC15` border at `y=238`, `22px` bold white `TOONTOONCASTLE`).
        2. Visible Anti-Scraper Watermark (`@ToonToonCastle` centered at `(540, 282)`, `30px` bold, `62%` opacity `alpha=160` + `4px` black outline).
        3. Winner Card Header Brand Bar (`TOONTOONCASTLE` `34px` `#FACC15`-on-`#0F172A` header pill atop the IPL Winner Card)."""
        self.frame.set_clip(None)
        fr = self.frame
        navy = (15, 23, 42)        # #0F172A
        gold = (250, 204, 21)      # #FACC15

        # 1. MC Tuno Broadcast Booth Network Plate (Always On, High Contrast)
        booth_lbl = getattr(self, "_booth_brand_surf", None)
        if booth_lbl is None:
            raw_b = hud.outlined("TOONTOONCASTLE", 22, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
            booth_lbl = hud.fit_width(raw_b, 212)
            self._booth_brand_surf = booth_lbl
        plate_w = max(216, min(236, booth_lbl.get_width() + 24))
        plate_rect = pygame.Rect(0, 0, plate_w, 32)
        plate_rect.center = (scenery.CAM_RECT.centerx, 238)
        pygame.draw.rect(fr, (0, 0, 0), plate_rect.inflate(4, 4), border_radius=13)
        pygame.draw.rect(fr, navy, plate_rect, border_radius=12)
        pygame.draw.rect(fr, gold, plate_rect, 2, border_radius=12)
        fr.blit(booth_lbl, booth_lbl.get_rect(center=(plate_rect.centerx, plate_rect.centery + 1)))
        hud.TEXT_BOXES.append(plate_rect)

        # 2. Visible Anti-Scraper Watermark (`@ToonToonCastle`, 30px bold, 62% opacity / alpha=160, 4px black outline)
        wm = getattr(self, "_wm_surf", None)
        if wm is None:
            wm = hud.outlined("@ToonToonCastle", 30, fill=(255, 255, 255), outline=(0, 0, 0), width=4, face="Fredoka.ttf").copy()
            wm.fill((255, 255, 255, 160), special_flags=pygame.BLEND_RGBA_MULT)
            self._wm_surf = wm
        fr.blit(wm, wm.get_rect(center=(540, 282)))

        # 3. Winner Card Header Brand Bar (`TOONTOONCASTLE` 34px gold-on-dark badge atop the IPL Winner Card)
        if shot.segment == "card":
            card_lbl = getattr(self, "_card_brand_surf", None)
            if card_lbl is None:
                card_lbl = hud.outlined("TOONTOONCASTLE", 34, fill=gold, outline=(0, 0, 0), width=4)
                self._card_brand_surf = card_lbl
            bar_w = card_lbl.get_width() + 48
            bar_rect = pygame.Rect(0, 0, bar_w, 48)
            bar_rect.center = (540, 336)
            pygame.draw.rect(fr, (0, 0, 0), bar_rect.move(0, 4), border_radius=24)
            pygame.draw.rect(fr, navy, bar_rect, border_radius=24)
            pygame.draw.rect(fr, gold, bar_rect, 3, border_radius=24)
            fr.blit(card_lbl, card_lbl.get_rect(center=(bar_rect.centerx, bar_rect.centery + 1)))
            hud.TEXT_BOXES.append(bar_rect)

    def _overlays(self, shot: Shot, play_t: float, t_anim: float, fi: int, ranks: dict[str, int],
                  out_t: float = 0.0, voice_rms: float | None = None) -> None:
        fr = self.frame
        flags = self.tr.flags[fi]
        alive = self._alive_at(fi, shot.segment)
        total = len(self.tr.keys)
        status = {}
        for h in self.heroes:
            f = flags[self.tr.index(h.key)]
            status[h.key] = "crown" if f & T.WINNER else ("alive" if f & T.ALIVE else "out")

        elim_ages = [play_t - e.t for e in self.elims if 0.0 <= play_t - e.t <= 0.38] if shot.segment in ("play", "replay") else []
        pulse = max(((1.0 - a / 0.38) ** 1.5 for a in elim_ages), default=0.0)

        live_heroes_n = sum(1 for h in self.heroes if status.get(h.key) != "out")
        hero_ko_ages = [play_t - e.t for e in self.elims if e.data.get("hero") and 0.0 <= play_t - e.t <= 0.24]
        eff_slots = min(5.0, float(live_heroes_n) + sum(1.0 - a / 0.24 for a in hero_ko_ages))

        reigning = getattr(self.ep.outcome, "reigning_champion", None) if self.ep.outcome else None
        t_st, _ = self.tuno_state(play_t, shot.segment)
        twist_badge = self._active_twist_badge(fi, play_t) if shot.segment == "play" else None

        if shot.segment != "card":
            scenery.draw_panel(fr, alive, total, self.heroes, status, ranks, hud.TEXT_BOXES,
                               pulse=pulse, t=t_anim, eff_slots=eff_slots, reigning_champion=reigning)
        if shot.segment in ("cold", "play") and not (shot.segment == "cold" and self.finale):
            self._draw_goal_hud(fi, t_anim)
        if shot.segment == "cold":
            if self.finale:
                self._draw_vs_clash(shot.seg_t)
            else:
                self._draw_cold_hook_banner(shot.seg_t)

        scenery.draw_header(fr, self.castle, self.ep.ep_label, t_st, t_anim, hud.TEXT_BOXES,
                            talking=self._talking(out_t), voice_rms=voice_rms, twist_badge=twist_badge)

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
            f_teaser: bool | None = None
            if self.ep.outcome is None and self.ep.league_ctx:
                scfg = settings().get("season") or {}
                r_no = int(self.ep.league_ctx.get("race_number") or self.ep.league_ctx.get("episode_number") or 0)
                if scfg.get("finale_cross_promo_enabled", True) and r_no:
                    f_teaser = r_no in set(scfg.get("finale_cross_promo_races") or [28, 29, 30])
            hud.draw_winner_card(
                fr,
                hero,
                name,
                col,
                self.ep.season_line or "+10 PTS",
                self.ep.prompt or "Drop your pick below!",
                shot.seg_t,
                bot=self.extras.get(w) if w else None,
                outcome=self.ep.outcome,
                finale_teaser=f_teaser,
            )
        elif self.speech:
            from src.rendering import captions
            captions.draw_caption(fr, self.speech, out_t, hud.TEXT_BOXES)


def encode(ep: Episode, out: Path, audio: Path | None = None, stills: int = 0, sound: bool = True,
           brand_stills: bool = False) -> dict:
    r = Renderer(ep)
    ep.shots = plan_shots(ep, r.teaser_f)
    out.parent.mkdir(parents=True, exist_ok=True)
    snd_info: dict = {}
    if sound and audio is None:
        # M5/v3.4: MC Tuno narration (isolated voice stem -> 33ms RMS lip-sync) + ducked SFX + funk BGM (-18/-24 dB)
        from src.audio.mix import build_soundtrack
        snd = build_soundtrack(r, ep, out.with_suffix(".wav"))
        audio = snd["wav"]
        r.speech = snd["speech"]
        r.voice_rms = snd["frame_rms"]
        snd_info = {k: v for k, v in snd.items() if k not in ("speech", "wav", "frame_rms", "voice_wav")}
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
    pcts = (0.02, 0.16, 0.42, 0.68, 0.84, 1.0)[:stills]
    still_at = {min(n - 1, int((n - 1) * k)) for k in pcts} if stills else set()
    gp_brand_idx = min(n - 1, int(round(5.0 * FPS))) if brand_stills else -1
    win_brand_idx = (
        next((idx for idx in range(n - 1, -1, -1) if ep.shots[idx].segment == "card" and ep.shots[idx].seg_t >= 0.6), n - 1)
        if brand_stills else -1
    )
    for i, shot in enumerate(ep.shots):
        frame = r.render_shot(shot, i)
        proc.stdin.write(pygame.image.tobytes(frame, "RGB"))
        if i in still_at:
            small = pygame.transform.smoothscale(frame, (W // 2, H // 2))
            pygame.image.save(small, str(out.with_name(f"{out.stem}_f{i:04d}.png")))
        if i == gp_brand_idx:
            pygame.image.save(frame, str(out.parent / "verify_gameplay_brand.png"))
        if i == win_brand_idx:
            pygame.image.save(frame, str(out.parent / "verify_winner_brand.png"))
        if i % 15 == 0:
            boxes.append([tuple(b) for b in hud.TEXT_BOXES])
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    zooms = [float(c.zoom) for c in r.cams] if r.cams else [1.0]
    return {
        "frames": len(ep.shots),
        "duration": len(ep.shots) / FPS,
        "text_boxes": boxes,
        "sound": snd_info,
        "cam_zoom_min": round(min(zooms), 4),
        "cam_zoom_max": round(max(zooms), 4),
        "cam_rescues": int(getattr(track, "rescues", 0)),
    }
