"""Renderers for v6 top-down group B (gravity_wells, giant_ball_brawl, duel_dome, triangle_throne)."""
from __future__ import annotations

import math
import random

import pygame

from src.rendering.arena_art import over, prop, static, under
from src.rendering.arena_art.fixed import BLACK, WHITE, _circ, _seg, _text, _w


def _rim(r, cam, pts, top, side, z) -> None:
    skirt = [(x, y + 22 * z) for x, y in pts]
    pygame.draw.polygon(r.frame, BLACK, [(x, y + 4) for x, y in skirt])
    pygame.draw.polygon(r.frame, side, skirt)
    pygame.draw.polygon(r.frame, top, pts)
    pygame.draw.polygon(r.frame, BLACK, pts, _w(cam, 6))


# ================================================================================================ GRAVITY WELLS
_STARS = [(random.Random(7).uniform(-1, 1), random.Random(k).uniform(-1, 1), k % 3) for k in range(1, 140)]


@under("gravity_wells")
def gw_under(r, cam, fi, zone, t, play_t):
    R = float(zone.get("gw_R", 450.0)) * float(zone.get("edge_k", 1.0))
    c = cam.to_screen(0, 0)
    rr = R * cam.zoom
    pygame.draw.circle(r.frame, BLACK, (c[0], c[1] + 20 * cam.zoom), rr + 6)
    pygame.draw.circle(r.frame, (40, 20, 70), (c[0], c[1] + 20 * cam.zoom), rr)
    pygame.draw.circle(r.frame, BLACK, c, rr + 6)
    pygame.draw.circle(r.frame, (22, 18, 58), c, rr)
    for k, col in ((0.75, (60, 30, 110)), (0.45, (40, 50, 120))):          # nebula bands
        pygame.draw.circle(r.frame, col, (c[0] - rr * 0.2, c[1] + rr * 0.15), rr * k)
    rng = random.Random(11)
    for _ in range(90):
        a, d = rng.uniform(0, 6.283), rr * math.sqrt(rng.random())
        tw = 1.5 + (math.sin(t * 3 + a * 7) + 1)
        pygame.draw.circle(r.frame, (230, 230, 255), (c[0] + math.cos(a) * d, c[1] + math.sin(a) * d), tw)
    for px, py, pr in zone.get("gw_pl") or []:                            # gravity ripple rings
        p = cam.to_screen(px, py)
        for k in range(3):
            ph = ((t * 0.6 + k / 3) % 1.0)
            pygame.draw.circle(r.frame, (120, 160, 255), p, (pr + 30 + 120 * (1 - ph)) * cam.zoom, max(1, _w(cam, 2)))
    pygame.draw.circle(r.frame, (150, 120, 255), c, rr * 0.97, _w(cam, 4))


@prop("gw_planet")
def gw_planet(r, cam, st, i, x, y, ang, fi):
    rad = st["shapes"][0]["r"]
    cols = [(255, 140, 60), (90, 200, 255), (160, 255, 120), (255, 100, 160)]
    col = cols[i % len(cols)]
    p = cam.to_screen(x, y)
    rr = rad * cam.zoom
    ring = pygame.Rect(0, 0, rr * 3.0, rr * 1.0)
    ring.center = p
    pygame.draw.ellipse(r.frame, BLACK, ring.inflate(8, 8), _w(cam, 6))
    _circ(r, cam, (x, y), rad, col)
    pygame.draw.circle(r.frame, tuple(int(c * 0.75) for c in col), (p[0] + rr * 0.3, p[1] + rr * 0.2), rr * 0.25)
    pygame.draw.ellipse(r.frame, (255, 240, 200), ring, _w(cam, 3))


@prop("gw_asteroid")
def gw_asteroid(r, cam, st, i, x, y, ang, fi):
    rad = st["shapes"][0]["r"]
    p = cam.to_screen(x, y)
    pts = [(p[0] + math.cos(ang + k * 0.785) * rad * cam.zoom * (1.0 if k % 2 else 0.82),
            p[1] + math.sin(ang + k * 0.785) * rad * cam.zoom * (1.0 if k % 2 else 0.82)) for k in range(8)]
    pygame.draw.polygon(r.frame, (130, 120, 115), pts)
    pygame.draw.polygon(r.frame, BLACK, pts, _w(cam, 4))


# ================================================================================================ GIANT BALL BRAWL
@under("giant_ball_brawl")
def gbb_under(r, cam, fi, zone, t, play_t):
    half = float(zone.get("gbb_half", 420.0)) * float(zone.get("gbb_k", 1.0))
    mw = float(zone.get("gbb_mw", 100.0))
    md = min(float(zone.get("gbb_md", 118.0)), half * 0.45)
    pts = [cam.to_screen(-half, -half), cam.to_screen(half, -half), cam.to_screen(half, half), cam.to_screen(-half, half)]
    _rim(r, cam, pts, (70, 170, 70), (40, 100, 40), cam.zoom)
    for k in range(-4, 5, 2):                                              # mowing stripes
        a, b = cam.to_screen(k * half / 5, -half), cam.to_screen((k + 1) * half / 5, half)
        pygame.draw.rect(r.frame, (84, 186, 84), (a[0], a[1], b[0] - a[0], b[1] - a[1]))
    pygame.draw.polygon(r.frame, BLACK, pts, _w(cam, 6))
    c = cam.to_screen(0, 0)
    pygame.draw.circle(r.frame, WHITE, c, 110 * cam.zoom, _w(cam, 4))
    pygame.draw.line(r.frame, WHITE, cam.to_screen(-half, 0), cam.to_screen(half, 0), _w(cam, 3))
    for ox, oy, horiz in ((0, -half, True), (half, 0, False), (0, half, True), (-half, 0, False)):   # goal holes + nets
        if horiz:
            rect = (ox - mw, oy - (md if oy < 0 else 0), ox + mw, oy + (0 if oy < 0 else md))
            rect = (ox - mw, min(oy, oy - md if oy < 0 else oy + md), ox + mw, max(oy, oy - md if oy < 0 else oy + md))
            if oy < 0:
                rect = (ox - mw, oy, ox + mw, oy + md)
            else:
                rect = (ox - mw, oy - md, ox + mw, oy)
        else:
            rect = (ox, oy - mw, ox + md, oy + mw) if ox < 0 else (ox - md, oy - mw, ox, oy + mw)
        x0, y0, x1, y1 = rect
        q = [cam.to_screen(x0, y0), cam.to_screen(x1, y0), cam.to_screen(x1, y1), cam.to_screen(x0, y1)]
        pygame.draw.polygon(r.frame, (10, 10, 20), q)
        for k in range(1, 6):
            u = k / 6
            pygame.draw.line(r.frame, (200, 200, 210), (q[0][0] + (q[1][0] - q[0][0]) * u, q[0][1]),
                             (q[3][0] + (q[2][0] - q[3][0]) * u, q[3][1]), 1)
        pygame.draw.polygon(r.frame, WHITE, q, _w(cam, 4))


@prop("gbb_ball")
def gbb_ball(r, cam, st, i, x, y, ang, fi):
    rad = st["shapes"][0]["r"]
    p = cam.to_screen(x, y)
    rr = rad * cam.zoom
    pygame.draw.circle(r.frame, BLACK, p, rr + _w(cam, 5))
    pygame.draw.circle(r.frame, WHITE, p, rr)
    for k in range(5):                                                      # rotating panels
        a = ang + k * 1.2566
        q = (p[0] + math.cos(a) * rr * 0.55, p[1] + math.sin(a) * rr * 0.55)
        pygame.draw.circle(r.frame, (30, 30, 40), q, rr * 0.22)
    pygame.draw.circle(r.frame, (230, 40, 60), p, rr * 0.2)
    pygame.draw.circle(r.frame, (255, 255, 255), (p[0] - rr * 0.35, p[1] - rr * 0.4), rr * 0.14)


@prop("gbb_post")
def gbb_post(r, cam, st, i, x, y, ang, fi):
    _circ(r, cam, (x, y), st["shapes"][0]["r"], (255, 255, 255), hi=False)


@over("giant_ball_brawl")
def gbb_over(r, cam, fi, zone, t, play_t):
    g = zone.get("gbb_goal")
    if g and isinstance(g, (list, tuple)) and len(g) >= 2:
        try:
            gt = float(g[-1]) if isinstance(g[-1], (int, float)) else float(g[1])
        except (TypeError, ValueError):
            gt = -9.0
        if 0 <= t - gt < 1.6:
            _text(r, "GOAL!", max(30, int(120 * cam.zoom)), cam.to_screen(0, -40), fill=(255, 230, 60))
    goals = zone.get("gbb_goals") or {}
    if goals:
        lead = sorted(goals.items(), key=lambda kv: -kv[1])[:3]
        txt = "  ".join(f"{k.upper()} {v}" for k, v in lead)
        _text(r, txt, max(14, int(30 * cam.zoom)), cam.to_screen(0, float(zone.get("gbb_half", 420)) + 70),
              fill=(255, 255, 255))


# ================================================================================================ DUEL DOME
@static("dd_dome")
def dd_dome_static(r, cam, s, zone, t, play_t):
    pass                                     # floor is drawn under everything (UNDER hook below)


@under("duel_dome")
def dd_under(r, cam, fi, zone, t, play_t):
    s = next(x for x in r.meta["statics"] if x.get("type") == "dd_dome")
    A, C = float(s["A"]), float(s["C"])
    e = C - A
    pts = [cam.to_screen(x, y) for x, y in ((A, -e), (A, e), (e, A), (-e, A), (-A, e), (-A, -e), (-e, -A), (e, -A))]
    _rim(r, cam, pts, (176, 120, 70), (110, 70, 40), cam.zoom)
    c = cam.to_screen(0, 0)
    for k in (0.85, 0.6):
        pygame.draw.circle(r.frame, (200, 150, 95), c, A * k * cam.zoom, _w(cam, 4))
    pr = float(zone.get("dd_pocket", 0.0))
    if pr > 2:
        pygame.draw.circle(r.frame, (255, 110, 40), c, (pr + 8) * cam.zoom)
        pygame.draw.circle(r.frame, BLACK, c, (pr + 2) * cam.zoom)
        pygame.draw.circle(r.frame, (12, 8, 22), c, pr * cam.zoom)
    _text(r, "DUEL DOME", max(14, int(34 * cam.zoom)), cam.to_screen(0, -A - 70), fill=(255, 214, 40))


@static("dd_rail")
def dd_rail(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (255, 82, 168))


@static("dd_bumper")
def dd_bumper(r, cam, s, zone, t, play_t):
    _circ(r, cam, s["c"], s["r"], (255, 196, 36), ring=(238, 48, 82))


# ================================================================================================ TRIANGLE THRONE
@static("tt_tri")
def tt_tri_static(r, cam, s, zone, t, play_t):
    pass


@under("triangle_throne")
def tt_under(r, cam, fi, zone, t, play_t):
    s = next(x for x in r.meta["statics"] if x.get("type") == "tt_tri")
    k = float(zone.get("edge_k", 1.0))
    Rt = float(s["Rt"]) * k
    us = [(math.cos(a), math.sin(a)) for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)]
    pts = [cam.to_screen(ux * Rt, uy * Rt) for ux, uy in us]
    _rim(r, cam, pts, (120, 60, 170), (70, 30, 110), cam.zoom)
    inner = [cam.to_screen(ux * Rt * 0.78, uy * Rt * 0.78) for ux, uy in us]
    pygame.draw.polygon(r.frame, (255, 214, 40), inner, _w(cam, 5))
    pr = float(zone.get("tt_pocket", 0.0)) * k
    pk = float(s["Rt"]) * 0.66 * k
    for ux, uy in us:
        p = cam.to_screen(ux * pk, uy * pk)
        if pr > 2:
            pygame.draw.circle(r.frame, (255, 214, 40), p, (pr + 7) * cam.zoom)
            pygame.draw.circle(r.frame, (14, 8, 26), p, pr * cam.zoom)


@static("tt_throne")
def tt_throne(r, cam, s, zone, t, play_t):
    p = cam.to_screen(*s["c"])
    rr = s["r"] * cam.zoom
    back = pygame.Rect(0, 0, rr * 1.5, rr * 1.6)
    back.midbottom = (p[0], p[1] - rr * 0.2)
    pygame.draw.rect(r.frame, BLACK, back.inflate(8, 8), border_radius=int(rr * 0.4))
    pygame.draw.rect(r.frame, (230, 170, 30), back, border_radius=int(rr * 0.4))
    _circ(r, cam, s["c"], s["r"], (255, 214, 40), ring=(180, 40, 60))
    from src.rendering import hud
    hud._crown_badge(r.frame, p[0], back.top - rr * 0.2, max(14, rr * 0.9))
