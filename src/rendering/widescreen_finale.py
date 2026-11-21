"""Part 6: 16:9-Native 'Season Finale' Mega-Event (`widescreen_finale`, 1920x1080 @ 30fps).

Full-bleed widescreen arena (NO sidebar) hosting an exclusive 3-round, 20-participant Championship:
  - Round 1 (20 Balls: 10 Heroes + 10 Golden Dummies): Royal Gauntlet -> Top 6 Heroes advance!
  - Round 2 (10 Balls: 6 Qualified Heroes + 4 Golden Dummies): Shrinking Crucible -> Top 3 Finalists advance!
  - Round 3 (9 Balls: 3 Finalists + 6 Golden Guards): Championship Bridge -> 1 Season Champion crowned!
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

from src.audio import music, sfx  # noqa: E402
from src.audio.sfx import SR  # noqa: E402
from src.characters.roster import HERO_BY_KEY, HEROES, Hero, make_extras  # noqa: E402
from src.characters.tuno import draw_tuno  # noqa: E402
from src.config import FPS  # noqa: E402
from src.games import recipe_generator  # noqa: E402
from src.games.base import WIDESCREEN, Recipe  # noqa: E402
from src.games.themes import THEME_BY_KEY, Theme, for_season  # noqa: E402
from src.physics import trace as T  # noqa: E402
from src.physics.camera import track  # noqa: E402
from src.physics.engine import Sim  # noqa: E402
from src.rendering import balls, effects, hud, pipeline, scenery  # noqa: E402

WIDE_W, WIDE_H = 1920, 1080
WIDE_CY = 556.0
NAVY = (15, 23, 42)
GOLD = (250, 204, 21)
WHITE = (255, 255, 255)
BLACK = (17, 17, 24)


@dataclass
class WideCam:
    """Isotropic 1:1 pixel camera projecting world coordinates across the full 1920x1080 widescreen arena."""
    x: float
    y: float
    zoom: float
    shake: tuple[float, float] = (0.0, 0.0)

    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (
            (wx - self.x) * self.zoom + WIDE_W / 2.0 + self.shake[0],
            (wy - self.y) * self.zoom + WIDE_CY + self.shake[1],
        )

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (
            (sx - WIDE_W / 2.0 - self.shake[0]) / self.zoom + self.x,
            (sy - WIDE_CY - self.shake[1]) / self.zoom + self.y,
        )

    def visible(self, wx: float, wy: float, margin: float = 280.0) -> bool:
        sx, sy = self.to_screen(wx, wy)
        return -margin < sx < WIDE_W + margin and -margin < sy < WIDE_H + margin

    def on_screen(self, wx: float, wy: float, pad: float = 0.0) -> bool:
        sx, sy = self.to_screen(wx, wy)
        return pad <= sx <= WIDE_W - pad and 96.0 + pad <= sy <= WIDE_H - 64.0 - pad


@dataclass
class RoundResult:
    round_no: int
    title: str
    recipe: Recipe
    trace: T.Trace
    heroes_in: list[str]
    qualified: list[str]
    eliminated: list[str]
    stage_winner: str


@dataclass
class FinaleTournament:
    season: int
    seed: int
    theme_key: str
    rounds: list[RoundResult]
    champion: str


def _build_wide_parallax(theme: Theme) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    """Builds 1920x1080 full-bleed widescreen sky + distant castle spires + mid arches."""
    sky, spires, arches = scenery.parallax_layers(theme, finale=True)
    # Crop the vertical scenic sky/castle region (y=220..1300 -> 1080px tall) and tile horizontally across 1920px
    def _tile_1920(src: pygame.Surface, y0: int = 240) -> pygame.Surface:
        sw, sh = src.get_size()
        ch = min(sh - y0, WIDE_H)
        band = src.subsurface(pygame.Rect(0, y0, sw, ch))
        if ch < WIDE_H:
            band = pygame.transform.smoothscale(band, (sw, WIDE_H))
        out = pygame.Surface((WIDE_W, WIDE_H), pygame.SRCALPHA if src.get_flags() & pygame.SRCALPHA else 0)
        x = 0
        while x < WIDE_W:
            out.blit(band, (x, 0))
            x += sw
        return out

    return _tile_1920(sky, 220), _tile_1920(spires, 260), _tile_1920(arches, 280)


def _build_wide_void(theme: Theme, seed: int) -> pygame.Surface:
    """Builds a full-bleed 1920x1080 castle moat/abyss backdrop for TOP_DOWN widescreen rounds."""
    s = pygame.Surface((WIDE_W, WIDE_H))
    cx, cy = WIDE_W // 2, int(WIDE_CY)
    inner, outer, acc = (28, 94, 124), (10, 28, 50), theme.accent
    s.fill(outer)
    maxr = math.hypot(WIDE_W, WIDE_H) * 0.56
    for i in range(28, 0, -1):
        u = i / 28.0
        pygame.draw.circle(s, scenery.mix(inner, outer, u ** 0.85), (cx, cy), int(maxr * u))
    rng = random.Random(seed ^ 0x55AA)
    for r in range(180, int(maxr), 84):
        pygame.draw.circle(s, scenery.mix(inner, acc, 0.25), (cx, cy), r, 2)
    # Left & right castle battlements framing the full 16:9 moat
    stone = scenery.mix(theme.castle, outer, 0.35)
    for y in range(0, WIDE_H, 68):
        for x in (0, WIDE_W - 64):
            blk = pygame.Rect(x, y, 64, 58)
            pygame.draw.rect(s, stone, blk, border_radius=6)
            pygame.draw.rect(s, BLACK, blk, 3, border_radius=6)
    for _ in range(36):
        pygame.draw.circle(s, acc, (int(rng.uniform(80, WIDE_W - 80)), int(rng.uniform(80, WIDE_H - 80))), 2)
    return s


class WidescreenStageRenderer(pipeline.Renderer):
    """Renders a simulation trace natively onto a full-bleed 1920x1080 canvas (zero sidebar)."""

    def __init__(self, ep: pipeline.Episode, round_title: str, qualified_target: int) -> None:
        super().__init__(ep)
        self.round_title = round_title
        self.qualified_target = qualified_target
        self.wide_frame = pygame.Surface((WIDE_W, WIDE_H))
        self.wide_sky, self.wide_spires, self.wide_arches = _build_wide_parallax(self.theme)
        self.wide_void = _build_wide_void(self.theme, int(self.meta.get("seed", 1)))
        raw_cams = track(self.tr, screen_w=float(WIDE_W), screen_cy=WIDE_CY)
        z_boost = 1.08 if self.tr.mode == "SIDE_VIEW" else 1.02
        self.wide_cams = [WideCam(c.x, c.y, c.zoom * z_boost, c.shake) for c in raw_cams]

    def _resolve_wide_cam(self, shot: pipeline.Shot, fi: int, tf: float) -> WideCam:
        cam = self.wide_cams[fi]
        cap = self.wide_cams[min(self.pre, len(self.wide_cams) - 1)].zoom * 2.4
        if shot.focus and shot.focus in self.tr.keys and self.tr.mode == "SIDE_VIEW":
            i = self.tr.index(shot.focus)
            rows, _, _ = self.tr.sample(tf / FPS)
            return WideCam(float(rows[i, 0]), float(rows[i, 1]), min(cam.zoom * shot.zoom_mult, cap))
        if shot.zoom_mult != 1.0:
            return WideCam(cam.x, cam.y, min(cam.zoom * shot.zoom_mult, cap), cam.shake)
        return cam

    def render_wide_shot(self, shot: pipeline.Shot, index: int, caption: str | None = None,
                         voice_rms: float = 0.0) -> pygame.Surface:
        hud.TEXT_BOXES.clear()
        tf = shot.tf
        fi = int(min(self.tr.n_frames - 1, max(0, round(tf))))
        cam = self._resolve_wide_cam(shot, fi, tf)
        t_anim = index / FPS
        play_t = (fi - self.pre) / FPS
        eff_play_t = play_t if shot.segment not in ("cold", "replay") else (tf - self.pre) / FPS
        ranks = self._ranks(fi)
        slow = shot.segment in ("cold", "replay") or abs(tf - round(tf)) > 1e-3

        # Temporarily bind pipeline globals (W, H) and surfaces to native 1920x1080
        orig = (pipeline.W, pipeline.H, self.frame, self.world_rect, self.sky_bg, self.far_spires, self.mid_arches, self._void)
        try:
            pipeline.W, pipeline.H = WIDE_W, WIDE_H
            self.frame = self.wide_frame
            self.world_rect = pygame.Rect(0, 0, WIDE_W, WIDE_H)
            self.sky_bg, self.far_spires, self.mid_arches = self.wide_sky, self.wide_spires, self.wide_arches
            self._void = self.wide_void

            self.frame.set_clip(None)
            self.draw_world(cam, fi, t_anim, 0.0 if shot.segment == "cold" else play_t)  # type: ignore[arg-type]
            self.frame.set_clip(self.world_rect)
            self.draw_contestants(cam, tf if slow else fi, t_anim, ranks=ranks, show_tags=shot.segment in ("play", "replay"))  # type: ignore[arg-type]
            if shot.segment == "replay":
                effects.draw_confetti(self.frame, shot.seg_t, 5, pygame.Rect(0, 80, WIDE_W, WIDE_H - 80), n=110)
            if shot.segment in ("play", "replay", "cold"):
                self.draw_juice(cam, eff_play_t, t_anim, popups=False)  # type: ignore[arg-type]
            if shot.segment in ("play", "replay"):
                self._draw_glitch_blinks(cam, fi, eff_play_t)  # type: ignore[arg-type]
            if self.tr.mode == "SIDE_VIEW":
                self._abyss(cam, fi, t_anim)  # type: ignore[arg-type]
                self._draw_killer_fire(cam, fi, eff_play_t, t_anim)  # type: ignore[arg-type]
            if shot.segment in ("play", "replay"):
                self.draw_popups(cam, eff_play_t)  # type: ignore[arg-type]
            self.frame.set_clip(None)
        finally:
            (pipeline.W, pipeline.H, self.frame, self.world_rect,
             self.sky_bg, self.far_spires, self.mid_arches, self._void) = orig

        self._draw_wide_hud(self.wide_frame, shot, fi, play_t, t_anim, ranks, caption, voice_rms)
        return self.wide_frame

    def _draw_wide_hud(self, fr: pygame.Surface, shot: pipeline.Shot, fi: int, play_t: float,
                       t_anim: float, ranks: dict[str, int], caption: str | None, voice_rms: float) -> None:
        # 1. Top-Left floating tournament header + live single-row Top-6 Hero bar (no sidebar!)
        alive_n = self._alive_at(fi, shot.segment)
        total_n = len(self.tr.keys)
        hdr = pygame.Rect(26, 18, 680, 62)
        bg = pygame.Surface(hdr.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (*NAVY, 224), bg.get_rect(), border_radius=20)
        fr.blit(bg, hdr.topleft)
        pygame.draw.rect(fr, GOLD, hdr, 3, border_radius=20)
        t_surf = hud.fit_width(hud.outlined(self.round_title, 28, fill=GOLD, width=3), 460)
        fr.blit(t_surf, t_surf.get_rect(midleft=(hdr.x + 20, hdr.centery + 1)))
        al_surf = hud.outlined(f"ALIVE {alive_n}/{total_n}", 26, fill=WHITE, width=3)
        fr.blit(al_surf, al_surf.get_rect(midright=(hdr.right - 20, hdr.centery + 1)))

        # Single-row Top-6 living heroes strip next to header (x = 720..1460)
        flags = self.tr.flags[fi]
        live_heroes = sorted(
            [h for h in self.heroes if flags[self.tr.index(h.key)] & T.ALIVE],
            key=lambda h: ranks.get(h.key, 99),
        )[:6]
        if live_heroes:
            strip_w = 24 + len(live_heroes) * 116
            strip = pygame.Rect(722, 18, strip_w, 62)
            sb = pygame.Surface(strip.size, pygame.SRCALPHA)
            pygame.draw.rect(sb, (*NAVY, 210), sb.get_rect(), border_radius=20)
            fr.blit(sb, strip.topleft)
            pygame.draw.rect(fr, (148, 163, 184), strip, 2, border_radius=20)
            for idx_h, h in enumerate(live_heroes):
                cx = strip.x + 42 + idx_h * 116
                balls.draw_ball(fr, h, None, (cx, strip.centery), 0.0, 0.0, (0, 0), 0.0, "happy", "none", 0.0, 0.56)
                rk = ranks.get(h.key, idx_h + 1)
                rk_col = GOLD if rk <= self.qualified_target else WHITE
                rk_s = hud.outlined(f"#{rk}", 22, fill=rk_col, width=3)
                fr.blit(rk_s, rk_s.get_rect(midleft=(cx + 24, strip.centery + 1)))

        # 2. Compact floating MC Tuno castle cam in Top-Right corner (220x168 — 97% of screen stays open arena!)
        cam_r = pygame.Rect(WIDE_W - 246, 18, 220, 168)
        cb = pygame.Surface(cam_r.size, pygame.SRCALPHA)
        pygame.draw.rect(cb, (28, 20, 56, 232), cb.get_rect(), border_radius=22)
        t_state, _ = self.tuno_state(max(0.0, play_t), shot.segment)
        draw_tuno(cb, cam_r.w * 0.54, cam_r.h - 4, t_state, t_anim, scale=0.98, voice_rms=voice_rms)
        fr.blit(cb, cam_r.topleft)
        pygame.draw.rect(fr, BLACK, cam_r.inflate(4, 4), 4, border_radius=24)
        pygame.draw.rect(fr, GOLD, cam_r, 3, border_radius=22)
        wm = hud.outlined("@ToonToonCastle", 20, fill=WHITE, width=2)
        fr.blit(wm, wm.get_rect(midbottom=(cam_r.centerx, cam_r.bottom - 4)))

        if shot.segment == "replay":
            rep = hud.outlined("CHAMPIONSHIP REPLAY • 0.3X", 30, fill=(255, 236, 120), width=4)
            rbox = pygame.Rect(0, 0, rep.get_width() + 56, 48)
            rbox.topleft = (28, 92)
            pygame.draw.rect(fr, BLACK, rbox.move(0, 3), border_radius=24)
            pygame.draw.rect(fr, (190, 30, 60), rbox, border_radius=24)
            pygame.draw.rect(fr, GOLD, rbox, 3, border_radius=24)
            fr.blit(rep, rep.get_rect(center=rbox.center))

        # 3. Clean widescreen lower-third subtitle when MC Tuno speaks
        if caption:
            cap_s = hud.fit_width(hud.outlined(caption.upper(), 34, fill=WHITE, width=4), 1380)
            cbox = pygame.Rect(0, 0, cap_s.get_width() + 56, 58)
            cbox.center = (WIDE_W // 2, WIDE_H - 64)
            cbg = pygame.Surface(cbox.size, pygame.SRCALPHA)
            pygame.draw.rect(cbg, (*BLACK, 212), cbg.get_rect(), border_radius=28)
            fr.blit(cbg, cbox.topleft)
            pygame.draw.rect(fr, GOLD, cbox, 3, border_radius=28)
            fr.blit(cap_s, cap_s.get_rect(center=cbox.center))


def _simulate_round_best(recipe: Recipe, heroes: list[Hero], dummies_n: int, seed: int) -> T.Trace:
    """Runs up to 4 real physics candidate seeds and picks an action-packed run where a Hero finishes on top."""
    candidates: list[tuple[tuple, T.Trace]] = []
    for k in range(4):
        s = seed * 100 + k
        extras = make_extras(dummies_n, random.Random(s), golden=True)
        tr = Sim(recipe, heroes, extras, s).run()
        win = str(tr.meta.get("winner") or "")
        res_t = float(tr.meta.get("resolved_at") or 0.0)
        elims = sum(1 for e in tr.events if e.kind == "elimination")
        key = (win in HERO_BY_KEY, 12.0 <= res_t <= 26.0, elims, -abs(res_t - 19.0))
        candidates.append((key, tr))
        if win in HERO_BY_KEY and 13.0 <= res_t <= 25.0 and elims >= 3:
            break
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def simulate_widescreen_finale(season: int, seed: int, season_theme: str | None = None) -> FinaleTournament:
    """Part 6: Simulates the complete 3-round, 20-participant 16:9 Season Finale tournament."""
    theme_key = season_theme or for_season(season).key
    round_recipes = recipe_generator.generate_widescreen_finale_rounds(season, seed, season_theme=theme_key)
    active_heroes: list[Hero] = list(HEROES)
    round_results: list[RoundResult] = []

    for idx, rec in enumerate(round_recipes):
        r_no = idx + 1
        dummies_n = int(rec.params.get("dummies_in", 6))
        adv_n = int(rec.params.get("heroes_advance", 1))
        title = str(rec.params.get("round_title") or f"ROUND {r_no}")
        tr = _simulate_round_best(rec, active_heroes, dummies_n, seed + r_no * 37)
        ranking = [str(k) for k in (tr.meta.get("ranking") or [])]
        in_keys = {h.key for h in active_heroes}
        hero_order = [k for k in ranking if k in in_keys]
        for h in active_heroes:
            if h.key not in hero_order:
                hero_order.append(h.key)
        qualified = hero_order[:adv_n]
        eliminated = hero_order[adv_n:]
        stage_winner = hero_order[0]
        round_results.append(
            RoundResult(
                round_no=r_no,
                title=title,
                recipe=rec,
                trace=tr,
                heroes_in=[h.key for h in active_heroes],
                qualified=qualified,
                eliminated=eliminated,
                stage_winner=stage_winner,
            )
        )
        active_heroes = [HERO_BY_KEY[k] for k in qualified]

    champion = round_results[-1].qualified[0]
    return FinaleTournament(season=season, seed=seed, theme_key=theme_key, rounds=round_results, champion=champion)


def _draw_bracket_card(fr: pygame.Surface, bg: pygame.Surface, rr: RoundResult, season: int, t: float) -> None:
    fr.blit(bg, (0, 0))
    ov = pygame.Surface((WIDE_W, WIDE_H), pygame.SRCALPHA)
    ov.fill((10, 15, 32, 185))
    fr.blit(ov, (0, 0))
    t1 = hud.outlined(f"SEASON {season} FINALE • ROUND {rr.round_no} COMPLETE!", 64, fill=GOLD, width=6)
    fr.blit(t1, t1.get_rect(center=(WIDE_W // 2, 108)))
    sub = hud.outlined(
        f"TOP {len(rr.qualified)} ADVANCE TO {'THE GRAND FINAL' if rr.round_no == 2 else 'ROUND 2'}!",
        38,
        fill=WHITE,
        width=4,
    )
    fr.blit(sub, sub.get_rect(center=(WIDE_W // 2, 178)))

    # Qualified row
    q_n = len(rr.qualified)
    for i, k in enumerate(rr.qualified):
        h = HERO_BY_KEY[k]
        cx = int(WIDE_W * (i + 0.5) / max(1, q_n))
        cy = 410
        card = pygame.Rect(0, 0, min(260, WIDE_W // max(1, q_n) - 24), 250)
        card.center = (cx, cy)
        pygame.draw.rect(fr, BLACK, card.inflate(8, 8), border_radius=24)
        pygame.draw.rect(fr, (20, 83, 45), card, border_radius=22)
        pygame.draw.rect(fr, (74, 222, 128), card, 4, border_radius=22)
        balls.draw_ball(fr, h, None, (cx, cy - 26), 0.0, 0.0, (0, 0), 0.0, "celebrating", "none", 0.0, 1.45)
        nm = hud.fit_width(hud.outlined(h.name.upper(), 34, fill=WHITE, width=3), card.w - 24)
        fr.blit(nm, nm.get_rect(center=(cx, cy + 68)))
        tag = hud.outlined("QUALIFIED", 24, fill=(134, 239, 172), width=3)
        fr.blit(tag, tag.get_rect(center=(cx, cy + 102)))

    # Eliminated row
    e_n = len(rr.eliminated)
    for i, k in enumerate(rr.eliminated):
        h = HERO_BY_KEY[k]
        cx = int(WIDE_W * (i + 0.5) / max(1, e_n))
        cy = 785
        card = pygame.Rect(0, 0, min(250, WIDE_W // max(1, e_n) - 28), 210)
        card.center = (cx, cy)
        pygame.draw.rect(fr, BLACK, card.inflate(6, 6), border_radius=20)
        pygame.draw.rect(fr, (30, 41, 59), card, border_radius=18)
        pygame.draw.rect(fr, (248, 113, 113), card, 3, border_radius=18)
        balls.draw_ball(fr, h, None, (cx, cy - 22), 0.0, 0.0, (0, 0), 0.0, "dizzy", "none", 0.0, 1.18)
        nm = hud.fit_width(hud.outlined(h.name.upper(), 30, fill=(203, 213, 225), width=3), card.w - 20)
        fr.blit(nm, nm.get_rect(center=(cx, cy + 56)))
        tag = hud.outlined("ELIMINATED", 22, fill=(248, 113, 113), width=2)
        fr.blit(tag, tag.get_rect(center=(cx, cy + 86)))
    effects.draw_confetti(fr, t, 31 + rr.round_no, pygame.Rect(0, 0, WIDE_W, 600), n=55)


def _draw_coronation_card(fr: pygame.Surface, bg: pygame.Surface, tourney: FinaleTournament, t: float) -> None:
    fr.blit(bg, (0, 0))
    ov = pygame.Surface((WIDE_W, WIDE_H), pygame.SRCALPHA)
    ov.fill((12, 14, 34, 170))
    fr.blit(ov, (0, 0))
    champ = HERO_BY_KEY[tourney.champion]
    bob = math.sin(t * 3.5) * 10.0
    # Sunburst behind champion
    sb = pygame.Surface((WIDE_W, WIDE_H), pygame.SRCALPHA)
    for i in range(20):
        a0 = t * 0.4 + i * math.pi / 10.0
        a1 = a0 + math.pi / 20.0
        col = (*GOLD, 42) if i % 2 == 0 else (255, 255, 255, 16)
        pygame.draw.polygon(
            sb,
            col,
            [(WIDE_W // 2, 520), (WIDE_W // 2 + math.cos(a0) * 1300, 520 + math.sin(a0) * 1300),
             (WIDE_W // 2 + math.cos(a1) * 1300, 520 + math.sin(a1) * 1300)],
        )
    fr.blit(sb, (0, 0))

    hdr = hud.outlined(f"TOONTOONCASTLE SEASON {tourney.season} CHAMPION!", 76, fill=GOLD, width=7)
    fr.blit(hdr, hdr.get_rect(center=(WIDE_W // 2, 112)))

    balls.draw_ball(fr, champ, None, (WIDE_W // 2, 520 + bob), 0.0, 0.0, (0, 0), 0.0, "celebrating", "none", 0.0, 3.6)
    hud._crown_badge(fr, WIDE_W // 2, 315 + bob, 170)
    hud._draw_trophy_cup(fr, WIDE_W // 2 - 340, 580, scale=2.7)
    hud._draw_trophy_cup(fr, WIDE_W // 2 + 340, 580, scale=2.7)

    nm = hud.outlined(f"ALL HAIL {champ.name.upper()}!", 108, fill=WHITE, outline=BLACK, width=9)
    fr.blit(nm, nm.get_rect(center=(WIDE_W // 2, 835)))
    cta = hud.outlined("SEASON 2 STARTS TOMORROW • SUBSCRIBE & DROP YOUR PICK BELOW!", 34, fill=GOLD, width=4)
    fr.blit(cta, cta.get_rect(center=(WIDE_W // 2, 955)))
    effects.draw_confetti(fr, t, 99, pygame.Rect(0, 0, WIDE_W, WIDE_H), n=150)


def _draw_intro_card(fr: pygame.Surface, bg: pygame.Surface, tourney: FinaleTournament, t: float) -> None:
    fr.blit(bg, (0, 0))
    ov = pygame.Surface((WIDE_W, WIDE_H), pygame.SRCALPHA)
    ov.fill((10, 16, 36, 175))
    fr.blit(ov, (0, 0))
    t1 = hud.outlined(f"SEASON {tourney.season} • WIDESCREEN GRAND FINALE", 80, fill=GOLD, width=7)
    fr.blit(t1, t1.get_rect(center=(WIDE_W // 2, 130)))
    t2 = hud.outlined("20 CONTESTANTS • 3 ELIMINATION ROUNDS • 1 CROWN!", 42, fill=WHITE, width=4)
    fr.blit(t2, t2.get_rect(center=(WIDE_W // 2, 220)))
    for i, h in enumerate(HEROES):
        col, row = i % 5, i // 5
        cx = 320 + col * 320
        cy = 440 + row * 280
        balls.draw_ball(fr, h, None, (cx, cy), 0.0, 0.0, (0, 0), 0.0, "happy", "none", 0.0, 1.55)
        nm = hud.outlined(h.name.upper(), 30, fill=WHITE, width=3)
        fr.blit(nm, nm.get_rect(center=(cx, cy + 88)))
    effects.draw_confetti(fr, t, 19, pygame.Rect(0, 0, WIDE_W, WIDE_H), n=80)


def render_widescreen_finale(
    season: int = 1,
    seed: int = 3030,
    out_mp4: Path = Path("output/widescreen_finale_s1.mp4"),
    use_tts: bool = True,
    stills_dir: Path | None = None,
    max_frames: int | None = None,
    log=print,
) -> dict[str, Any]:
    """Simulates and encodes the full-bleed 1920x1080 3-round Season Finale mega-event."""
    pygame.init()
    t0 = time.time()
    tourney = simulate_widescreen_finale(season, seed)
    theme = THEME_BY_KEY[tourney.theme_key]
    sky_bg, _, _ = _build_wide_parallax(theme)

    # Build stage renderers & shot lists for all 3 rounds
    stage_packs: list[tuple[RoundResult, WidescreenStageRenderer, list[pipeline.Shot]]] = []
    for rr in tourney.rounds:
        ep = pipeline.Episode(
            rr.trace,
            f"S{season} FINALE • R{rr.round_no}",
            season_line=f"SEASON {season} FINALE",
            prompt="",
            flash_event=None,
            outcome=None,
            league_ctx={"season_number": season, "episode_number": 30, "stage": "grand_final"},
        )
        all_shots = [s for s in pipeline.plan_shots(ep) if s.segment != "card"]
        sr = WidescreenStageRenderer(ep, rr.title, len(rr.qualified))
        stage_packs.append((rr, sr, all_shots))

    # Build timeline blocks: Intro (3.8s) -> R1 -> Bracket1 (3.6s) -> R2 -> Bracket2 (3.6s) -> R3 -> Coronation (6.0s)
    blocks: list[tuple[str, int, Any]] = [("intro", int(3.8 * FPS), None)]
    for rr, sr, shots in stage_packs:
        blocks.append((f"round_{rr.round_no}", len(shots), (rr, sr, shots)))
        if rr.round_no < 3:
            blocks.append((f"bracket_{rr.round_no}", int(3.6 * FPS), rr))
    blocks.append(("coronation", int(6.0 * FPS), None))

    total_frames = sum(nf for _, nf, _ in blocks)
    total_s = total_frames / FPS

    # Synthesize MC Tuno commentary + procedural SFX + Royal Finale BGM
    narration_script: list[tuple[float, str, str]] = []
    cur_t = 0.25
    narration_script.append((
        cur_t,
        f"Welcome to the Season {season} Widescreen Finale! Twenty enter, three rounds of carnage, one crown!",
        "hype",
    ))
    blk_t = 0.0
    sfx_events: list[tuple[float, Any, float]] = [(0.1, sfx.airhorn, -6.0), (0.25, sfx.cheer, -8.0)]
    for bname, nf, payload in blocks:
        if bname.startswith("round_"):
            rr, _, shots = payload
            w_name = HERO_BY_KEY[rr.stage_winner].name
            if rr.round_no == 1:
                narration_script.append((blk_t + 0.4, "Round One! Twenty balls storm the Royal Gauntlet! Only six heroes survive!", "hype"))
            elif rr.round_no == 2:
                narration_script.append((blk_t + 0.4, "Round Two! Six survivors on the shrinking crucible! Top three make the Grand Final!", "hype"))
            else:
                f_names = ", ".join(HERO_BY_KEY[k].name for k in rr.heroes_in)
                narration_script.append((blk_t + 0.4, f"The Grand Final! {f_names}! Winner takes the Season {season} crown!", "hype"))
            rep_idx = next((i for i, s in enumerate(shots) if s.segment == "replay"), len(shots) - 45)
            sfx_events.append((blk_t + rep_idx / FPS, sfx.fanfare, -5.0))
            if rr.round_no < 3:
                narration_script.append((blk_t + rep_idx / FPS, f"{w_name} wins Round {rr.round_no}!", "hype"))
            else:
                champ_nm = HERO_BY_KEY[tourney.champion].name
                narration_script.append((blk_t + rep_idx / FPS, f"{champ_nm} crosses first! {champ_nm} wins the Championship!", "hype"))
        elif bname.startswith("bracket_"):
            rr = payload
            elim_nm = HERO_BY_KEY[rr.eliminated[0]].name if rr.eliminated else "Nobody"
            narration_script.append((blk_t + 0.25, f"{elim_nm} and the stragglers are out! Moving on!", "normal"))
            sfx_events.append((blk_t + 0.1, sfx.ding, -8.0))
        elif bname == "coronation":
            champ_nm = HERO_BY_KEY[tourney.champion].name
            narration_script.append((blk_t + 0.4, f"All hail {champ_nm}, your official Season {season} ToonToonCastle Champion!", "hype"))
            sfx_events.append((blk_t + 0.2, sfx.grand_fanfare, -3.0))
            sfx_events.append((blk_t + 0.5, sfx.cheer, -6.0))
        blk_t += nf / FPS

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    wav_path = out_mp4.with_suffix(".wav")
    n_samples = int(math.ceil((total_s + 1.0) * SR))
    voice_buf = np.zeros(n_samples, np.float32)
    fx_buf = np.zeros(n_samples, np.float32)
    captions_tl: list[tuple[float, float, str]] = []
    tts_ok = False
    if use_tts:
        from src.narration import tts
        tts_ok = tts.available()

    last_end = 0.0
    for start_req, text_ln, style in narration_script:
        st_t = max(start_req, last_end + 0.22)
        if st_t >= total_s - 0.8:
            continue
        pcm = None
        if tts_ok:
            from src.narration import tts
            res = tts.synthesize(text_ln, style)
            if res is not None:
                pcm = res[0]
        if pcm is not None:
            dur_ln = pcm.size / SR
            i0 = int(st_t * SR)
            k = min(pcm.size, n_samples - i0)
            if k > 0:
                m = float(np.max(np.abs(pcm))) or 1.0
                voice_buf[i0:i0 + k] += pcm[:k] / m * 0.92
        else:
            dur_ln = 0.4 + len(text_ln.split()) / 3.2
        captions_tl.append((st_t, st_t + dur_ln, text_ln))
        last_end = st_t + dur_ln

    for st_fx, fn_fx, gdb in sfx_events:
        clip = fn_fx()
        i0 = int(max(0.0, st_fx) * SR)
        k = min(clip.size, n_samples - i0)
        if k > 0:
            fx_buf[i0:i0 + k] += clip[:k] * float(10 ** (gdb / 20.0))

    frame_rms = [
        float(np.sqrt(np.mean(voice_buf[int(i * SR / FPS):int((i + 1) * SR / FPS)] ** 2) or 0.0))
        for i in range(total_frames)
    ]
    bed = music.theme_bgm(total_s + 1.0, music.track_for_theme(tourney.theme_key), seed=seed)
    mus = np.zeros(n_samples, np.float32)
    mus[:min(n_samples, bed.size)] = bed[:min(n_samples, bed.size)] * 0.09
    end_i = int(total_s * SR)
    mix_pcm = np.tanh((voice_buf[:end_i] + fx_buf[:end_i] * 0.6 + mus[:end_i]) * 1.04) * 0.94
    pcm16 = (np.clip(mix_pcm, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(np.repeat(pcm16[:, None], 2, axis=1).tobytes())

    n_encode = min(total_frames, max_frames) if max_frames else total_frames
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDE_W}x{WIDE_H}", "-r", str(FPS), "-i", "-",
        "-i", str(wav_path), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "superfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", "-movflags", "+faststart",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    if stills_dir:
        stills_dir.mkdir(parents=True, exist_ok=True)

    canvas = pygame.Surface((WIDE_W, WIDE_H))
    g_fi = 0
    for bname, nf, payload in blocks:
        for li in range(nf):
            if g_fi >= n_encode:
                break
            gt = g_fi / FPS
            lt = li / FPS
            cap = next((txt_c for t_a, t_b, txt_c in captions_tl if t_a <= gt <= t_b + 0.15), None)
            v_rms = frame_rms[g_fi] if g_fi < len(frame_rms) else 0.0

            if bname == "intro":
                _draw_intro_card(canvas, sky_bg, tourney, lt)
                out_surf = canvas
            elif bname.startswith("round_"):
                _, sr, shots = payload
                out_surf = sr.render_wide_shot(shots[li], li, caption=cap, voice_rms=v_rms)
            elif bname.startswith("bracket_"):
                _draw_bracket_card(canvas, sky_bg, payload, season, lt)
                out_surf = canvas
            else:
                _draw_coronation_card(canvas, sky_bg, tourney, lt)
                out_surf = canvas

            proc.stdin.write(pygame.image.tobytes(out_surf, "RGB"))
            if stills_dir and li == nf // 2:
                pygame.image.save(out_surf, str(stills_dir / f"finale_{bname}.png"))
            g_fi += 1
        if g_fi >= n_encode:
            break

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg widescreen_finale encode failed")
    if wav_path.exists():
        wav_path.unlink()

    summary = {
        "mode": WIDESCREEN,
        "season": season,
        "seed": seed,
        "resolution": [WIDE_W, WIDE_H],
        "duration_s": round(n_encode / FPS, 2),
        "frames": n_encode,
        "participant_count": 20,
        "champion": tourney.champion,
        "rounds": [
            {
                "round": rr.round_no,
                "title": rr.title,
                "arena": rr.recipe.arena,
                "heroes_in": rr.heroes_in,
                "qualified": rr.qualified,
                "eliminated": rr.eliminated,
                "stage_winner": rr.stage_winner,
            }
            for rr in tourney.rounds
        ],
        "render_s": round(time.time() - t0, 1),
        "video": str(out_mp4),
    }
    out_mp4.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"[WIDESCREEN FINALE] S{season} champion={tourney.champion} duration={summary['duration_s']}s render={summary['render_s']}s -> {out_mp4}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ToonToonCastle 16:9-Native Season Finale (Race 30)")
    ap.add_argument("--season", type=int, default=1)
    ap.add_argument("--seed", type=int, default=3030)
    ap.add_argument("--out", default="output/widescreen_finale.mp4")
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--max-frames", type=int, default=None)
    a = ap.parse_args(argv)
    out_p = Path(a.out)
    st_dir = (out_p.parent / "finale_stills") if a.stills else None
    render_widescreen_finale(
        season=a.season,
        seed=a.seed,
        out_mp4=out_p,
        use_tts=not a.no_tts,
        stills_dir=st_dir,
        max_frames=a.max_frames,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
