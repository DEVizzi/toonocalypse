"""Renderers for the v6 TOP_DOWN group A arenas (src/games/arenas_v6/top_a.py):
Color Floor, Tilt Table, Whirlpool Drain, Spotlight Panic.

Bold cartoon style: flat fills + thick black outlines scaled by cam.zoom; theme colours for structure (terrain, rock,
accent, hazard) so seasonal themes still apply. Cheap per frame: polygons/circles only, plus ONE cached SRCALPHA layer
for the translucent laser beams.
"""
from __future__ import annotations

import math

import pygame

from src.config import H, LAYOUT, W
from src.rendering import scenery
from src.rendering.arena_art import over, prop, static, under

BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
TAU = 2.0 * math.pi
VIEW_TOP, VIEW_BOTTOM = LAYOUT["viewport"]

PALETTE = ((236, 62, 70), (46, 122, 245), (52, 200, 92), (255, 208, 36), (168, 88, 232))
NAMES = ("RED", "BLUE", "GREEN", "YELLOW", "PURPLE")

_TXT: dict = {}


def _text(s: str, size: int, fill=WHITE, w: int = 4) -> pygame.Surface:
    key = (s, size, fill, w)
    surf = _TXT.get(key)
    if surf is None:
        if len(_TXT) > 64:
            _TXT.clear()
        surf = scenery._outlined_text(s, size, fill=fill, outline=BLACK, w=w)
        _TXT[key] = surf
    return surf


def _lw(z: float, base: float = 4.0) -> int:
    return max(2, int(base * z))


def _mix(a, b, k):
    return scenery.mix(a, b, k)


def _find(r, kind: str):
    cache = r.__dict__.setdefault("_top_a_statics", {})
    if kind not in cache:
        cache[kind] = next((s for s in r.meta["statics"] if s.get("type") == kind), None)
    return cache[kind]


def _k(r, zone) -> float:
    return zone.get("edge_k", 1.0) * zone.get("shrink", 1.0)


def _skirt_disc(fr, cx, cy, rad, z, theme, depth=None, off=(0.0, 0.0)):
    """Floating-island underside (rock skirt) below a round floor."""
    _, rock, dark, _ = scenery.rock_colours(theme)
    h = depth if depth is not None else max(12.0, 0.12 * rad)
    ox, oy = off
    pygame.draw.circle(fr, BLACK, (cx + ox, cy + h + oy), rad + 5)
    pygame.draw.circle(fr, dark, (cx + ox, cy + h + oy), rad)
    pygame.draw.rect(fr, dark, (cx - rad, cy, 2 * rad, h))


# meta-only static descriptors: the floors are drawn by the UNDER hooks below
@static("cf_grid")
@static("tilt_plate")
@static("whirl_pool")
@static("spot_stage")
def _meta_static(r, cam, s, zone, t_anim, play_t):
    return None


# ============================================================================================== COLOR FLOOR
@under("color_floor")
def cf_under(r, cam, fi, zone, t_anim, play_t):
    s = _find(r, "cf_grid")
    st = zone.get("cf")
    if s is None or st is None:
        return
    fr, z = r.frame, cam.zoom
    n, S, half = int(s["n"]), float(s["S"]), float(s["half"])
    cols, phase, call, left, tot, pt, _ri = st
    lw = _lw(z, 4)
    # thin steel frame around the board so the grid reads as one arena even with holes in it
    x0, y0 = cam.to_screen(-half - 10, -half - 10)
    x1, y1 = cam.to_screen(half + 10, half + 10)
    _, rock, dark, light = scenery.rock_colours(r.theme)
    frame_r = pygame.Rect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
    pygame.draw.rect(fr, BLACK, frame_r.inflate(lw * 2 + 6, lw * 2 + 6), _lw(z, 8), border_radius=int(14 * z))
    pygame.draw.rect(fr, rock, frame_r.inflate(lw, lw), _lw(z, 5), border_radius=int(12 * z))
    side_h = 12.0 * z
    gap = 4.0
    blink = phase == 1 and left < 0.9 and int(t_anim * 10) % 2 == 0
    for i, col in enumerate(cols):
        if col < 0:
            continue
        iy, ix = divmod(i, n)
        wx, wy = -half + ix * S + gap, -half + iy * S + gap
        sx, sy = cam.to_screen(wx, wy)
        size = (S - 2 * gap) * z
        safe = col == call
        scale, drop_y, shade = 1.0, 0.0, 0.0
        if phase == 2 and not safe:
            u = pt / 0.45
            if u >= 1.0:
                continue                                   # fallen away: the void shows through
            scale = 1.0 - 0.55 * u
            drop_y = 40.0 * z * u * u
            shade = 0.55 * u
        elif phase == 0 and pt < 0.3:
            scale = 0.55 + 0.45 * (pt / 0.3)              # new colours pop back in
        jx = 0.0
        if phase == 1 and not safe and left < 0.9:
            jx = math.sin(t_anim * 70.0 + i * 1.7) * 2.5 * z   # doomed tiles rattle
        cs = size * scale
        rx = sx + (size - cs) / 2 + jx
        ry = sy + (size - cs) / 2 + drop_y
        base = PALETTE[col % len(PALETTE)]
        topc = _mix(base, BLACK, shade)
        sidec = _mix(topc, BLACK, 0.38)
        rect = pygame.Rect(int(rx), int(ry), max(2, int(cs)), max(2, int(cs)))
        side = rect.move(0, int(side_h * scale))
        rad = max(2, int(10 * z * scale))
        pygame.draw.rect(fr, BLACK, side.inflate(lw, lw), border_radius=rad)
        pygame.draw.rect(fr, sidec, side, border_radius=rad)
        pygame.draw.rect(fr, BLACK, rect.inflate(lw, lw), border_radius=rad)
        pygame.draw.rect(fr, topc, rect, border_radius=rad)
        if cs > 16:
            # bevel: light top-left lip + darker bottom-right inset
            inner = rect.inflate(-int(cs * 0.22), -int(cs * 0.22))
            pygame.draw.rect(fr, _mix(topc, WHITE, 0.18), inner, border_radius=max(2, rad - 3))
            pygame.draw.line(fr, _mix(topc, WHITE, 0.55), (rect.left + rad, rect.top + 3),
                             (rect.right - rad, rect.top + 3), max(2, int(3 * z)))
        if safe and phase in (1, 2):
            pulse = 0.5 + 0.5 * math.sin(t_anim * 12.0)
            ring_c = WHITE if not blink else (255, 240, 120)
            pygame.draw.rect(fr, ring_c, rect.inflate(int(6 * z), int(6 * z)), max(2, int((3 + 3 * pulse) * z)),
                             border_radius=rad + 3)


@over("color_floor")
def cf_over(r, cam, fi, zone, t_anim, play_t):
    st = zone.get("cf")
    if st is None:
        return
    cols, phase, call, left, tot, pt, ri = st
    if phase not in (1, 2):
        return
    fr = r.frame
    col = PALETTE[call % len(PALETTE)]
    name = NAMES[call % len(NAMES)]
    cy = VIEW_BOTTOM - 120
    cx = W // 2
    # call panel: colour swatch + name + countdown ring
    pw, ph = 600, 128
    panel = pygame.Rect(cx - pw // 2, cy - ph // 2, pw, ph)
    pop = min(1.0, pt / 0.18) if phase == 1 else 1.0
    if pop < 1.0:
        panel = panel.inflate(-int(pw * 0.3 * (1 - pop)), -int(ph * 0.3 * (1 - pop)))
    pygame.draw.rect(fr, BLACK, panel.inflate(12, 12), border_radius=34)
    pygame.draw.rect(fr, (34, 30, 52), panel, border_radius=30)
    pygame.draw.rect(fr, col, panel.inflate(-12, -12), 8, border_radius=26)
    # countdown ring (left)
    rc = (panel.left + 70, panel.centery)
    rr = 44
    pygame.draw.circle(fr, BLACK, rc, rr + 7)
    pygame.draw.circle(fr, col, rc, rr)
    frac = max(0.0, min(1.0, left / max(0.05, tot)))
    if phase == 1 and frac > 0.0:
        pts = [rc] + [(rc[0] + math.sin(TAU * u / 40 * frac) * (rr + 1), rc[1] - math.cos(TAU * u / 40 * frac) * (rr + 1))
                      for u in range(41)]
        pygame.draw.polygon(fr, WHITE, pts)
        pygame.draw.circle(fr, col, rc, int(rr * 0.62))
        num = _text(str(max(1, math.ceil(left))), 52, WHITE, 4)
        fr.blit(num, num.get_rect(center=rc))
    else:
        pygame.draw.circle(fr, WHITE, rc, int(rr * 0.62))
        chk = [(rc[0] - 16, rc[1]), (rc[0] - 4, rc[1] + 13), (rc[0] + 18, rc[1] - 14)]
        pygame.draw.lines(fr, BLACK, False, chk, 8)
    pygame.draw.circle(fr, BLACK, rc, rr + 7, 6)
    label = _text(name + "!" if phase == 1 else "STAY ON " + name, 74 if phase == 1 else 58, col, 6)
    label = scenery._fit(label, pw - 170)
    fr.blit(label, label.get_rect(midleft=(panel.left + 140, panel.centery + 2)))
    rtxt = _text(f"ROUND {ri + 1}", 28, WHITE, 3)
    fr.blit(rtxt, rtxt.get_rect(midbottom=(panel.centerx + 60, panel.top - 4)))


# ============================================================================================== TILT TABLE
def _ellipse_pts(cx, cy, rad, ux, uy, squash, n=48):
    """Circle squashed by `squash` along unit axis (ux, uy) -> polygon (screen space)."""
    vx, vy = -uy, ux
    out = []
    for i in range(n):
        a = TAU * i / n
        p, q = math.cos(a) * rad * squash, math.sin(a) * rad
        out.append((cx + ux * p + vx * q, cy + uy * p + vy * q))
    return out


@under("tilt_table")
def tilt_under(r, cam, fi, zone, t_anim, play_t):
    s = _find(r, "tilt_plate")
    if s is None:
        return
    fr, z, th = r.frame, cam.zoom, r.theme
    k = _k(r, zone)
    rad = s["r"] * k * z
    if rad < 4:
        return
    cx, cy = cam.to_screen(0.0, 0.0)
    tx, ty = zone.get("tilt", (0.0, 0.0))
    m = min(1.0, math.hypot(tx, ty))
    ux, uy = (tx / m, ty / m) if m > 1e-3 else (1.0, 0.0)
    lw = _lw(z, 5)
    _, rock, dark, light = scenery.rock_colours(th)
    # pivot column + underside, pushed toward the LOW side (that rim dips, revealing more underside)
    dip = (10.0 + 26.0 * m) * z
    pygame.draw.circle(fr, BLACK, (cx, cy + 30 * z), rad * 0.22 + 5)
    pygame.draw.circle(fr, dark, (cx, cy + 30 * z), rad * 0.22)
    under_pts = _ellipse_pts(cx + ux * dip, cy + uy * dip + 14 * z, rad, ux, uy, 1.0 - 0.06 * m)
    pygame.draw.polygon(fr, BLACK, [(px, py + 4) for px, py in under_pts])
    pygame.draw.polygon(fr, dark, under_pts)
    pygame.draw.polygon(fr, BLACK, under_pts, lw)
    # the plate (slightly squashed along the tilt axis)
    plate = _ellipse_pts(cx, cy, rad, ux, uy, 1.0 - 0.07 * m)
    top = th.terrain
    pygame.draw.polygon(fr, top, plate)
    # low-side shading crescent + high-side highlight
    n = len(plate)
    if m > 0.05:
        low = [p for i, p in enumerate(plate) if math.cos(TAU * i / n) > 0.62 - 0.12 * m]
        if len(low) > 2:
            pygame.draw.polygon(fr, _mix(top, BLACK, 0.08 + 0.18 * m), low)
        hi = [p for i, p in enumerate(plate) if math.cos(TAU * i / n) < -0.45]
        if len(hi) > 2:
            pygame.draw.lines(fr, _mix(top, WHITE, 0.35 + 0.3 * m), False, hi, max(3, int((4 + 6 * m) * z)))
    # rings + spokes
    trim = _mix(top, WHITE, 0.32)
    for f in (0.72, 0.44):
        pygame.draw.polygon(fr, trim, _ellipse_pts(cx, cy, rad * f, ux, uy, 1.0 - 0.07 * m, 40), max(2, int(3 * z)))
    for j in range(8):
        a = TAU * j / 8
        ex, ey = math.cos(a) * rad * 0.92, math.sin(a) * rad * 0.92
        pygame.draw.line(fr, _mix(top, BLACK, 0.12), (cx + ex * 0.2, cy + ey * 0.2), (cx + ex, cy + ey), max(2, int(2 * z)))
    pygame.draw.polygon(fr, BLACK, plate, lw)
    # chevrons pointing downhill near the low rim
    if m > 0.28:
        col = th.hazard
        for j in (-1, 0, 1):
            vx, vy = -uy, ux
            bx = cx + ux * rad * 0.80 + vx * j * rad * 0.22
            by = cy + uy * rad * 0.80 + vy * j * rad * 0.22
            sz = 18 * z
            pts = [(bx - ux * sz + vx * sz, by - uy * sz + vy * sz), (bx, by), (bx - ux * sz - vx * sz, by - uy * sz - vy * sz)]
            pygame.draw.lines(fr, BLACK, False, pts, max(4, int(9 * z)))
            pygame.draw.lines(fr, col, False, pts, max(2, int(5 * z)))
    # spirit level in the middle: the bubble floats to the HIGH side
    lr = max(14.0, 46.0 * z * max(0.6, k))
    pygame.draw.circle(fr, BLACK, (cx, cy), lr + 5)
    pygame.draw.circle(fr, (196, 236, 120), (cx, cy), lr)
    pygame.draw.circle(fr, (150, 206, 84), (cx, cy), lr, max(2, int(4 * z)))
    pygame.draw.line(fr, BLACK, (cx - lr * 0.5, cy), (cx + lr * 0.5, cy), 2)
    pygame.draw.line(fr, BLACK, (cx, cy - lr * 0.5), (cx, cy + lr * 0.5), 2)
    pygame.draw.circle(fr, BLACK, (cx, cy), lr * 0.42, 2)
    bxb = cx - ux * m * lr * 0.58
    byb = cy - uy * m * lr * 0.58
    br = lr * 0.32
    pygame.draw.circle(fr, BLACK, (bxb, byb), br + 3)
    pygame.draw.circle(fr, (250, 255, 235), (bxb, byb), br)
    pygame.draw.circle(fr, WHITE, (bxb - br * 0.35, byb - br * 0.35), br * 0.35)


# ============================================================================================== WHIRLPOOL DRAIN
WATER = (44, 150, 222)
WATER_D = (22, 92, 168)
WATER_DD = (14, 52, 110)


@under("whirlpool_drain")
def whirl_under(r, cam, fi, zone, t_anim, play_t):
    s = _find(r, "whirl_pool")
    if s is None:
        return
    fr, z, th = r.frame, cam.zoom, r.theme
    cx, cy = cam.to_screen(0.0, 0.0)
    R = s["r"]
    rad = R * z
    spin = float(s.get("dir", 1.0))
    rd = float(zone.get("drain_r", 52.0))
    flush = float(zone.get("flush", 0.0))
    _skirt_disc(fr, cx, cy, rad + 16 * z, z, th, depth=max(14.0, 0.1 * rad))
    # water: concentric bands darkening toward the plughole
    bands = 6
    for b in range(bands):
        f = 1.0 - b / bands
        rr = rd * z + (rad - rd * z) * f
        pygame.draw.circle(fr, _mix(WATER, WATER_DD, b / (bands + 1) * 0.9), (cx, cy), rr)
    # spiral swirl lines (rotate with time; faster during a FLUSH)
    arms = 9
    rot = t_anim * (1.3 + 1.4 * min(1.0, flush)) * spin
    lw = max(2, int(4 * z))
    for a_i in range(arms):
        a0 = TAU * a_i / arms + rot
        pts = []
        for j in range(14):
            u = j / 13.0
            rr = rad * 0.97 - (rad * 0.97 - (rd + 14) * z) * u
            ang = a0 + spin * 2.4 * u * u
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
        col = _mix(WATER, WHITE, 0.30 + 0.25 * (a_i % 2))
        pygame.draw.lines(fr, col, False, pts, lw)
    # little foam flecks drifting inward
    for j in range(18):
        ph = (t_anim * 0.35 + j * 0.137) % 1.0
        rr = rad * 0.95 - (rad * 0.95 - (rd + 20) * z) * ph
        ang = j * 2.39996 + spin * (ph * 5.0 + t_anim * 0.8)
        pygame.draw.circle(fr, (225, 245, 255), (cx + math.cos(ang) * rr, cy + math.sin(ang) * rr), max(2, 4 * z))
    # drain: foam ring + dark hole with a spiral
    dr = rd * z
    for j in range(16):
        ang = TAU * j / 16 + t_anim * 2.2 * spin
        wob = 1.0 + 0.08 * math.sin(t_anim * 9 + j)
        pygame.draw.circle(fr, WHITE, (cx + math.cos(ang) * dr * 1.08 * wob, cy + math.sin(ang) * dr * 1.08 * wob),
                           max(3, (9 + 3 * math.sin(j * 1.7 + t_anim * 6)) * z))
    pygame.draw.circle(fr, BLACK, (cx, cy), dr + 3)
    pygame.draw.circle(fr, (8, 14, 30), (cx, cy), dr)
    for a_i in range(3):
        pts = []
        for j in range(12):
            u = j / 11.0
            ang = TAU * a_i / 3 + t_anim * 4.0 * spin + spin * 3.0 * u
            pts.append((cx + math.cos(ang) * dr * (0.9 - 0.8 * u), cy + math.sin(ang) * dr * (0.9 - 0.8 * u)))
        pygame.draw.lines(fr, (36, 70, 120), False, pts, max(2, int(3 * z)))
    pygame.draw.circle(fr, (120, 200, 255), (cx, cy), dr, max(2, int(3 * z)))
    # guard rail: thick bumper ring + bolts
    rail_r = (R + 10) * z
    pygame.draw.circle(fr, BLACK, (cx, cy), rail_r + 14 * z, max(6, int(30 * z)))
    pygame.draw.circle(fr, th.accent, (cx, cy), rail_r + 12 * z, max(4, int(18 * z)))
    pygame.draw.circle(fr, _mix(th.accent, WHITE, 0.45), (cx, cy), rail_r + 5 * z, max(2, int(4 * z)))
    for j in range(24):
        ang = TAU * j / 24
        px, py = cx + math.cos(ang) * (rail_r + 12 * z), cy + math.sin(ang) * (rail_r + 12 * z)
        pygame.draw.circle(fr, BLACK, (px, py), max(3, 7 * z))
        pygame.draw.circle(fr, (235, 235, 245) if j % 2 == 0 else th.hazard, (px, py), max(2, 4.5 * z))


@over("whirlpool_drain")
def whirl_over(r, cam, fi, zone, t_anim, play_t):
    flush = float(zone.get("flush", 0.0))
    if flush <= 0.0:
        return
    fr, z = r.frame, cam.zoom
    cx, cy = cam.to_screen(0.0, 0.0)
    rd = float(zone.get("drain_r", 52.0)) * z
    # pulsing suction rings during a FLUSH
    for j in range(3):
        ph = (t_anim * 2.2 + j / 3.0) % 1.0
        rr = rd + (1.0 - ph) * 230 * z
        pygame.draw.circle(fr, (210, 245, 255), (cx, cy), rr, max(2, int(4 * z * (1 - ph) + 1)))


# ============================================================================================== SPOTLIGHT PANIC
def _stage_cols(theme):
    floor = _mix(theme.terrain, (34, 30, 66), 0.55)
    return floor, _mix(floor, BLACK, 0.25), _mix(floor, WHITE, 0.18)


@under("spotlight_panic")
def spot_under(r, cam, fi, zone, t_anim, play_t):
    s = _find(r, "spot_stage")
    if s is None:
        return
    fr, z, th = r.frame, cam.zoom, r.theme
    k = _k(r, zone)
    rad = s["r"] * k * z
    if rad < 4:
        return
    cx, cy = cam.to_screen(0.0, 0.0)
    floor, dark, light = _stage_cols(th)
    _skirt_disc(fr, cx, cy, rad, z, th)
    pygame.draw.circle(fr, BLACK, (cx, cy), rad + 5)
    pygame.draw.circle(fr, floor, (cx, cy), rad)
    # checker-ish stage boards: alternating ring sectors
    for ring in range(4):
        r0 = rad * (0.25 + ring * 0.19)
        r1 = rad * (0.25 + (ring + 1) * 0.19)
        for j in range(12):
            if (j + ring) % 2:
                continue
            a0, a1 = TAU * j / 12, TAU * (j + 1) / 12
            pts = [(cx + math.cos(a0 + (a1 - a0) * u / 4) * r1, cy + math.sin(a0 + (a1 - a0) * u / 4) * r1) for u in range(5)]
            pts += [(cx + math.cos(a1 - (a1 - a0) * u / 4) * min(r0, rad), cy + math.sin(a1 - (a1 - a0) * u / 4) * min(r0, rad))
                    for u in range(5)]
            pygame.draw.polygon(fr, dark, pts)
    pygame.draw.circle(fr, light, (cx, cy), rad * 0.94, max(2, int(4 * z)))
    # rim footlights (warm bulbs keep the stage readable)
    for j in range(20):
        ang = TAU * j / 20
        px, py = cx + math.cos(ang) * rad * 0.97, cy + math.sin(ang) * rad * 0.97
        on = (j + int(t_anim * 4)) % 4 != 0
        pygame.draw.circle(fr, BLACK, (px, py), max(3, 7 * z))
        pygame.draw.circle(fr, (255, 226, 120) if on else (120, 104, 70), (px, py), max(2, 5 * z))


def _beam_layer(r, rect: pygame.Rect) -> pygame.Surface:
    surf = r.__dict__.get("_top_a_beam_surf")
    if surf is None:
        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        r.__dict__["_top_a_beam_surf"] = surf
    surf.fill((0, 0, 0, 0), rect)
    return surf


@over("spotlight_panic")
def spot_over(r, cam, fi, zone, t_anim, play_t):
    s = _find(r, "spot_stage")
    if s is None:
        return
    fr, z = r.frame, cam.zoom
    k = _k(r, zone)
    rad = s["r"] * k * z
    cx, cy = cam.to_screen(0.0, 0.0)
    beams = zone.get("beams", ())
    hw = float(zone.get("beam_hw", s.get("hw", 0.17)))
    on = float(zone.get("beam_on", 1.0))
    flick = on if on >= 1.0 else on * (0.5 + 0.5 * (int(t_anim * 18) % 2))
    rect = pygame.Rect(int(cx - rad - 20), int(cy - rad - 20), int(2 * rad + 40), int(2 * rad + 40)).clip(fr.get_rect())
    if rect.w <= 0 or rect.h <= 0:
        return
    lay = _beam_layer(r, rect)
    n_arc = 8
    for b in beams:
        for widen, alpha in ((1.6, 60), (1.0, 120), (0.35, 190)):
            a0, a1 = b - hw * widen, b + hw * widen
            pts = [(cx, cy)] + [(cx + math.cos(a0 + (a1 - a0) * u / n_arc) * rad, cy + math.sin(a0 + (a1 - a0) * u / n_arc) * rad)
                                for u in range(n_arc + 1)]
            col = (255, 40, 50, int(alpha * flick)) if widen > 0.5 else (255, 210, 200, int(alpha * flick))
            pygame.draw.polygon(lay, col, pts)
    ch = zone.get("chord")
    if ch is not None:
        phi, off, hwid = ch
        nx, ny = math.cos(phi), math.sin(phi)
        tx, ty = -ny, nx
        rr = s["r"] * k
        if abs(off) < rr:
            for wmul, alpha in ((2.0, 55), (1.0, 120), (0.3, 200)):
                w_ = hwid * wmul
                o1, o2 = off + w_, off - w_
                h1 = math.sqrt(max(0.0, rr * rr - o1 * o1))
                h2 = math.sqrt(max(0.0, rr * rr - o2 * o2))
                hm = math.sqrt(max(0.0, rr * rr - off * off))
                quad = [(o1, -h1), (off, -hm), (o2, -h2), (o2, h2), (off, hm), (o1, h1)]
                pts = [cam.to_screen(nx * a + tx * b, ny * a + ty * b) for a, b in quad]
                col = (255, 40, 50, alpha) if wmul > 0.5 else (255, 210, 200, alpha)
                pygame.draw.polygon(lay, col, pts)
    fr.blit(lay, rect.topleft, area=rect)
    # hot balls sizzle (rings under the balls grow as the zap timer fills)
    for x, y, frac in zone.get("spot_hot", ()):
        px, py = cam.to_screen(x, y)
        rr = (30 + 10 * frac) * z
        col = (255, int(220 - 160 * frac), 40)
        for j in range(6):
            a = t_anim * 14 + j * TAU / 6
            pygame.draw.line(fr, col, (px + math.cos(a) * rr * 0.8, py + math.sin(a) * rr * 0.8),
                             (px + math.cos(a + 0.4) * rr * 1.15, py + math.sin(a + 0.4) * rr * 1.15), max(2, int(4 * z)))
    # zap bursts
    for x, y, age in zone.get("spot_zaps", ()):
        px, py = cam.to_screen(x, y)
        u = min(1.0, age / 0.7)
        rr = (30 + 90 * u) * z
        for j in range(10):
            a = j * TAU / 10 + 0.3
            p0 = (px + math.cos(a) * rr * 0.35, py + math.sin(a) * rr * 0.35)
            p1 = (px + math.cos(a) * rr, py + math.sin(a) * rr)
            pygame.draw.line(fr, BLACK, p0, p1, max(4, int(9 * z * (1 - u) + 2)))
            pygame.draw.line(fr, (255, 240, 90) if j % 2 else WHITE, p0, p1, max(2, int(5 * z * (1 - u) + 1)))
        if u < 0.4:
            pygame.draw.circle(fr, WHITE, (px, py), (26 + 30 * u) * z)
    # turret cap on top of the beams
    tr = 34 * z
    pygame.draw.circle(fr, BLACK, (cx, cy), tr + 6)
    pygame.draw.circle(fr, (70, 74, 92), (cx, cy), tr)
    for b in beams:
        ex, ey = cx + math.cos(b) * tr * 1.05, cy + math.sin(b) * tr * 1.05
        pygame.draw.circle(fr, BLACK, (ex, ey), 11 * z + 3)
        pygame.draw.circle(fr, (255, 60, 60) if flick > 0.6 else (130, 40, 40), (ex, ey), 11 * z)
        pygame.draw.circle(fr, WHITE, (ex - 3 * z, ey - 3 * z), 3.5 * z)
    pygame.draw.circle(fr, (110, 116, 138), (cx, cy), tr * 0.6)
    pygame.draw.circle(fr, (255, 70, 70) if flick > 0.6 else (90, 40, 40), (cx, cy), tr * 0.3)
    pygame.draw.circle(fr, BLACK, (cx, cy), tr * 0.6, max(2, int(3 * z)))


@prop("spot_turret")
def spot_turret(r, cam, st, i, x, y, ang, fi):
    """Turret base plate (the cap + emitters are drawn in the OVER hook, above the beams)."""
    fr, z = r.frame, cam.zoom
    sx, sy = cam.to_screen(x, y)
    pygame.draw.circle(fr, BLACK, (sx, sy + 6 * z), 40 * z + 5)
    pygame.draw.circle(fr, (44, 46, 60), (sx, sy + 6 * z), 40 * z)
