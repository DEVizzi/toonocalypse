"""Renderers for the side_a v6 arenas (src/games/arenas_v6/side_a.py): glass bridge, red light eye, inflatable domes,
spinning logs, lily pads + frogs, rafts, and the shared water / splash / waterfall art.

Bold cartoon look: flat fills + thick BLACK outlines scaled by cam.zoom. Water is drawn twice: an opaque body UNDER
everything (so pits read as a river, not the abyss) and a translucent front layer OVER the props so sunk pads, rafts and
the lower halves of logs / domes look submerged.
"""
from __future__ import annotations

import math

import pygame

from src.config import H, LAYOUT, W
from src.rendering import scenery
from src.rendering.arena_art import over, prop, static, under

BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
VIEW_TOP = LAYOUT["viewport"][0]
WATER_ARENAS = ("big_bubble", "spinning_logs", "lily_pads", "raft_rapids")
_CACHE: dict = {}


def _lw(z: float, base: float, lo: int = 2) -> int:
    return max(lo, int(base * z))


def _water_cols(th) -> tuple:
    base = scenery.mix((46, 150, 226), th.sky_bottom, 0.12)
    deep = scenery.mix(base, (12, 40, 96), 0.5)
    mid = scenery.mix(base, deep, 0.45)
    foam = (236, 250, 255)
    return base, mid, deep, foam


def _alpha_layer(col: tuple, alpha: int) -> pygame.Surface:
    """One cached full-screen translucent fill per colour (blitted with an `area`, never re-allocated)."""
    key = ("alpha", col, alpha)
    s = _CACHE.get(key)
    if s is None:
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((*col, alpha))
        _CACHE[key] = s
    return s


def _label(text: str, size: int, fill) -> pygame.Surface:
    key = ("lbl", text, size, fill)
    s = _CACHE.get(key)
    if s is None:
        f = scenery.font(size)
        core = f.render(text, True, fill)
        out = f.render(text, True, BLACK)
        s = pygame.Surface((core.get_width() + 10, core.get_height() + 10), pygame.SRCALPHA)
        for dx in (-4, -2, 0, 2, 4):
            for dy in (-4, -2, 0, 2, 4):
                if dx or dy:
                    s.blit(out, (5 + dx, 5 + dy))
        s.blit(core, (5, 5))
        _CACHE[key] = s
    return s


def _waters(r) -> list:
    key = ("waters", id(r.meta))
    v = _CACHE.get(key)
    if v is None:
        v = [s for s in r.meta["statics"] if s["type"] == "sa_water"]
        _CACHE[key] = v
    return v


def _prop_index(r, i: int, style: str) -> int:
    """Index of prop i among props of the same style (matches the order of the arena's zone lists)."""
    key = ("pidx", id(r.meta), style)
    m = _CACHE.get(key)
    if m is None:
        m, k = {}, 0
        for j, st in enumerate(r.meta["props"]):
            if st["style"] == style:
                m[j] = k
                k += 1
        _CACHE[key] = m
    return m.get(i, 0)


def _zone(r, fi: int) -> dict:
    return r.tr.zones[fi]


# ================================================================================================ water (shared)
def _water_under(r, cam, fi, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    base, mid, deep, foam = _water_cols(r.theme)
    flow = 1.0 if r.meta["recipe"].get("arena") == "raft_rapids" else 0.25
    for w in _waters(r):
        sx0, sy = cam.to_screen(w["x0"], w["y"])
        sx1, _ = cam.to_screen(w["x1"], w["y"])
        if sx1 < -10 or sx0 > W + 10 or sy > H:
            continue
        x0, x1 = max(-4, int(sx0)), min(W + 4, int(sx1))
        top = int(sy)
        pygame.draw.rect(fr, base, (x0, top, x1 - x0, H - top))
        pygame.draw.rect(fr, mid, (x0, top + int(70 * z), x1 - x0, H))
        pygame.draw.rect(fr, deep, (x0, top + int(190 * z), x1 - x0, H))
        # current streaks drifting downstream
        step = max(40, int(120 * z))
        for row in range(3):
            yy = top + int((26 + row * 48) * z)
            off = (t_anim * 90 * flow * (1 + row * 0.4) * z + row * 53) % step
            xx = x0 - step + off
            while xx < x1:
                a = (max(x0, xx), yy)
                b = (min(x1, xx + step * 0.42), yy)
                if b[0] > a[0]:
                    pygame.draw.line(fr, scenery.mix(base, foam, 0.45), a, b, _lw(z, 4))
                xx += step


def _waterfall(r, cam, s, t_anim) -> None:
    fr, z = r.frame, cam.zoom
    base, mid, deep, foam = _water_cols(r.theme)
    a = cam.to_screen(s["x0"], s["y0"])
    b = cam.to_screen(s["x1"], s["y1"])
    if b[0] < -60 or a[0] > W + 60:
        return
    th = 26 * z
    poly = [(a[0] - 6 * z, a[1] - th), (b[0] + 10 * z, b[1] - th), (b[0] + 10 * z, b[1] + 8 * z), (a[0] - 6 * z, a[1])]
    pygame.draw.polygon(fr, base, poly)
    for k in range(5):
        u = ((t_anim * 1.6 + k * 0.2) % 1.0)
        px = a[0] + (b[0] - a[0]) * u
        py = a[1] + (b[1] - a[1]) * u - th * 0.5
        pygame.draw.line(fr, foam, (px - 18 * z, py - 4 * z), (px + 18 * z, py + 10 * z), _lw(z, 4))
    pygame.draw.polygon(fr, BLACK, poly, _lw(z, 4))
    for k in range(6):                                              # foam churn at the bottom
        ang = t_anim * 5 + k
        pygame.draw.circle(fr, foam, (b[0] + (k - 2) * 16 * z, b[1] + 4 * z + math.sin(ang) * 4 * z), _lw(z, 11))


def _splashes(r, cam, zone) -> None:
    fr, z = r.frame, cam.zoom
    base, _, _, foam = _water_cols(r.theme)
    for x, y, age in zone.get("sa_splash", []):
        if age > 1.0:
            continue
        sx, sy = cam.to_screen(x, y)
        if not (-80 < sx < W + 80):
            continue
        k = age / 1.0
        rw = (40 + 120 * k) * z
        pygame.draw.ellipse(fr, foam, (sx - rw, sy - rw * 0.18, rw * 2, rw * 0.36), _lw(z, 5 * (1 - k) + 1))
        if age < 0.7:
            for j in range(9):
                a = math.pi * (0.15 + 0.7 * j / 8)
                v = (330 + (j * 37) % 120) * z
                dx = math.cos(a) * v * age * (1 if j % 2 else -1) * 0.6
                dy = -math.sin(a) * v * age + 0.5 * 1500 * z * age * age
                rr = max(2, int((10 - 10 * age) * z))
                p = (sx + dx, sy + dy)
                if dy < 4 * z:
                    pygame.draw.circle(fr, BLACK, p, rr + 2)
                    pygame.draw.circle(fr, foam if j % 3 else base, p, rr)
            col_h = (130 * (1 - k * 1.4)) * z
            if col_h > 4:
                pts = [(sx - 22 * z, sy), (sx - 8 * z, sy - col_h), (sx + 8 * z, sy - col_h * 0.8), (sx + 22 * z, sy)]
                pygame.draw.polygon(fr, foam, pts)
                pygame.draw.polygon(fr, BLACK, pts, _lw(z, 3))


def _water_over(r, cam, fi, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    base, mid, deep, foam = _water_cols(r.theme)
    for s in r.meta["statics"]:
        if s["type"] == "sa_waterfall":
            _waterfall(r, cam, s, t_anim)
    lay = _alpha_layer(scenery.mix(base, deep, 0.3), 120)
    for w in _waters(r):
        sx0, sy = cam.to_screen(w["x0"], w["y"])
        sx1, _ = cam.to_screen(w["x1"], w["y"])
        if sx1 < -10 or sx0 > W + 10 or sy > H:
            continue
        x0, x1 = max(0, int(sx0)), min(W, int(sx1))
        top = max(VIEW_TOP, int(sy + 4 * z))
        if x1 > x0 and top < H:
            fr.blit(lay, (x0, top), pygame.Rect(0, 0, x1 - x0, H - top))
        # wavy surface line with a black ink edge
        pts = []
        xx = x0
        while xx <= x1:
            pts.append((xx, sy + 4 * z * math.sin(t_anim * 3.2 + xx * 0.035)))
            xx += 18
        if len(pts) > 1:
            pygame.draw.lines(fr, BLACK, False, [(p[0], p[1] + 2) for p in pts], _lw(z, 7))
            pygame.draw.lines(fr, foam, False, pts, _lw(z, 4))
    _splashes(r, cam, zone)


for _k in WATER_ARENAS:
    under(_k)(_water_under)


# ================================================================================================ 1. glass bridge
@static("sa_glass")
def draw_glass(r, cam, s, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    a = cam.to_screen(*s["a"])
    b = cam.to_screen(*s["b"])
    if b[0] < -40 or a[0] > W + 40:
        return
    rr = s["r"] * z
    thick = 24 * z
    poly = [(a[0], a[1] - rr), (b[0], b[1] - rr), (b[0], b[1] - rr + thick), (a[0], a[1] - rr + thick)]
    pygame.draw.polygon(fr, (176, 238, 255), poly)
    lower = [(a[0], a[1] - rr + thick * 0.55), (b[0], b[1] - rr + thick * 0.55), poly[2], poly[3]]
    pygame.draw.polygon(fr, (112, 204, 238), lower)
    # glints (identical on real and fake panels)
    L = b[0] - a[0]
    for u, w_ in ((0.18, 0.12), (0.62, 0.07)):
        gx = a[0] + L * u
        gy = a[1] + (b[1] - a[1]) * u - rr
        pygame.draw.line(fr, WHITE, (gx, gy + thick * 0.8), (gx + L * w_, gy + 2 * z), _lw(z, 3))
    pygame.draw.polygon(fr, BLACK, poly, _lw(z, 4, 3))
    for e in (a, b):                                               # steel clamps
        pygame.draw.rect(fr, BLACK, (e[0] - 5 * z, e[1] - rr - 3 * z, 10 * z, thick + 6 * z))
        pygame.draw.rect(fr, (150, 158, 176), (e[0] - 3 * z, e[1] - rr - 1 * z, 6 * z, thick + 2 * z))


@over("glass_bridge")
def glass_over(r, cam, fi, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    for x0, y0, x1, y1, age in zone.get("sa_shards", []):
        sx0, sy0 = cam.to_screen(x0, y0)
        sx1, sy1 = cam.to_screen(x1, y1)
        if sx1 < -80 or sx0 > W + 80:
            continue
        if age < 0.16:                                             # white crack flash
            cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
            rad = (30 + 260 * age) * z
            pts = [(cx + math.cos(k * math.pi / 5) * rad * (1.0 if k % 2 == 0 else 0.45),
                    cy + math.sin(k * math.pi / 5) * rad * (1.0 if k % 2 == 0 else 0.45)) for k in range(10)]
            pygame.draw.polygon(fr, WHITE, pts)
            pygame.draw.polygon(fr, BLACK, pts, _lw(z, 3))
        seed = int(x0) % 97
        for k in range(10):
            u = (k + 0.5) / 10
            px = sx0 + (sx1 - sx0) * u + ((seed * (k + 3)) % 23 - 11) * age * 9 * z
            py = sy0 + (sy1 - sy0) * u + (120 * age + 0.5 * 1600 * age * age) * z * (0.8 + (k % 3) * 0.15)
            if py > H + 30:
                continue
            ang = age * (6 + k) * (1 if k % 2 else -1) + k
            sz = (9 + (k * 7) % 8) * z
            tri = [(px + math.cos(ang + q * 2.1) * sz, py + math.sin(ang + q * 2.1) * sz * 0.8) for q in range(3)]
            pygame.draw.polygon(fr, (176, 238, 255) if k % 2 else (120, 210, 240), tri)
            pygame.draw.polygon(fr, BLACK, tri, _lw(z, 2))


# ================================================================================================ 2. red light eye
LIGHT_COLS = {0: (64, 222, 96), 1: (255, 208, 40), 2: (242, 50, 50)}


@over("red_light")
def red_light_over(r, cam, fi, zone, t_anim, play_t) -> None:
    fr = r.frame
    st = int(zone.get("sa_light", 0))
    age = float(zone.get("sa_light_age", 0.0))
    col = LIGHT_COLS.get(st, LIGHT_COLS[0])
    ex, ey = W // 2, VIEW_TOP + 175
    # zap bolts first (they start at the eye)
    for x, y, za in zone.get("sa_zaps", []):
        if za > 0.4:
            continue
        tx, ty = cam.to_screen(x, y)
        n = 7
        pts = [(ex, ey + 40)]
        for k in range(1, n):
            u = k / n
            jit = ((k * 37 + int(x)) % 41 - 20) * 2.2
            pts.append((ex + (tx - ex) * u + jit, ey + 40 + (ty - ey - 40) * u))
        pts.append((tx, ty))
        pygame.draw.lines(fr, BLACK, False, pts, 14)
        pygame.draw.lines(fr, (255, 236, 90), False, pts, 8)
        pygame.draw.lines(fr, WHITE, False, pts, 3)
        rad = 40 * (1 - za / 0.4) + 14
        star = [(tx + math.cos(k * math.pi / 6) * rad * (1 if k % 2 == 0 else 0.4),
                 ty + math.sin(k * math.pi / 6) * rad * (1 if k % 2 == 0 else 0.4)) for k in range(12)]
        pygame.draw.polygon(fr, (255, 240, 120), star)
        pygame.draw.polygon(fr, BLACK, star, 4)
    # pulsing coloured border around the gameplay view
    pulse = 0.5 + 0.5 * math.sin(t_anim * (14 if st else 4))
    bw = 8 if st == 0 else (int(10 + 10 * pulse) if st == 2 else (14 if pulse > 0.5 else 6))
    wr = r.world_rect
    pygame.draw.rect(fr, BLACK, wr, bw + 6)
    pygame.draw.rect(fr, col, wr.inflate(-6, -6), bw)
    # the giant stone eye
    _, rock, dark, light = scenery.rock_colours(r.theme)
    sock = pygame.Rect(0, 0, 330, 196)
    sock.center = (ex, ey)
    pygame.draw.ellipse(fr, BLACK, sock.inflate(14, 14))
    pygame.draw.ellipse(fr, rock, sock)
    for k in range(-2, 3):                                         # carved stone blocks
        pygame.draw.line(fr, dark, (ex + k * 62, sock.top + 14), (ex + k * 62 + 8, sock.bottom - 14), 4)
    pygame.draw.arc(fr, light, sock.inflate(-16, -16), math.radians(30), math.radians(150), 6)
    # eyeball, lids blink shut a little on yellow
    open_k = 1.0 if st != 1 else 0.55 + 0.45 * abs(math.cos(age * 12))
    ball = pygame.Rect(0, 0, 250, int(140 * open_k))
    ball.center = (ex, ey + 4)
    pygame.draw.ellipse(fr, (250, 246, 236), ball)
    if st == 2:                                                    # red glow halo + veins
        halo = pygame.Rect(0, 0, int(150 + 30 * pulse), int(150 + 30 * pulse))
        halo.center = (ex, ey + 4)
        pygame.draw.ellipse(fr, (255, 150, 140), halo.clip(ball))
        for k in range(4):
            vx = ball.left + 12 + k * 6
            pygame.draw.line(fr, (220, 60, 60), (vx, ey - 10 + k * 8), (vx + 30, ey + k * 4), 3)
            pygame.draw.line(fr, (220, 60, 60), (ball.right - 12 - k * 6, ey - 10 + k * 8),
                             (ball.right - 42 - k * 6, ey + k * 4), 3)
    look = math.sin(t_anim * 0.9) * 26 if st == 0 else 0
    iris_r = int(min(58, ball.height * 0.46))
    if iris_r > 6:
        pygame.draw.circle(fr, BLACK, (ex + look, ey + 8), iris_r + 4)
        pygame.draw.circle(fr, col, (ex + look, ey + 8), iris_r)
        pygame.draw.circle(fr, scenery.mix(col, WHITE, 0.4), (ex + look, ey + 8), int(iris_r * 0.7), 4)
        pygame.draw.circle(fr, BLACK, (ex + look, ey + 8), int(iris_r * (0.36 if st == 2 else 0.48)))
        pygame.draw.circle(fr, WHITE, (ex + look - iris_r * 0.35, ey + 8 - iris_r * 0.35), max(3, iris_r // 5))
    pygame.draw.ellipse(fr, BLACK, ball, 6)
    pygame.draw.ellipse(fr, BLACK, sock, 6)
    # brow ridge: angry on red
    tilt = 26 if st == 2 else (10 if st == 1 else 0)
    pygame.draw.line(fr, BLACK, (ex - 150, ey - 92 + tilt * 0.2), (ex - 20, ey - 96 + tilt), 22)
    pygame.draw.line(fr, BLACK, (ex + 150, ey - 92 + tilt * 0.2), (ex + 20, ey - 96 + tilt), 22)
    pygame.draw.line(fr, dark, (ex - 146, ey - 92 + tilt * 0.2), (ex - 24, ey - 96 + tilt), 12)
    pygame.draw.line(fr, dark, (ex + 146, ey - 92 + tilt * 0.2), (ex + 24, ey - 96 + tilt), 12)
    word = ("GO!", "WAIT...", "STOP!")[st]
    lab = _label(word, 54, col)
    if st == 2:
        lab = pygame.transform.rotozoom(lab, 0, 1.0 + 0.12 * pulse)
    fr.blit(lab, lab.get_rect(center=(ex, sock.bottom + 40)))


# ================================================================================================ 3. inflatable domes
@prop("sa_dome")
def draw_dome(r, cam, st, i, x, y, ang, fi) -> None:
    fr, z = r.frame, cam.zoom
    R = st["shapes"][0]["r"]
    zone = _zone(r, fi)
    loads = zone.get("sa_domes", [])
    k = _prop_index(r, i, "sa_dome")
    sq = loads[k] if k < len(loads) else 0.0
    wob = math.sin(fi * 0.45 + k) * 0.03
    rx = R * z * (1 + 0.07 * sq + wob)
    ry = R * z * (1 - 0.07 * sq - wob)
    cx, cy = cam.to_screen(x, y)
    th = r.theme
    c1 = scenery.mix(th.hazard, (255, 80, 80), 0.3) if k % 2 == 0 else scenery.mix(th.accent, (255, 170, 40), 0.4)
    c2 = (252, 250, 244)
    rect = pygame.Rect(0, 0, int(rx * 2), int(ry * 2))
    rect.center = (int(cx), int(cy))
    pygame.draw.ellipse(fr, BLACK, rect.inflate(_lw(z, 10), _lw(z, 10)))
    pygame.draw.ellipse(fr, c2, rect)
    n = 10
    for s_i in range(0, n, 2):                                     # stripes rotate with the rocking dome
        a0 = ang + s_i * 2 * math.pi / n
        a1 = a0 + 2 * math.pi / n
        pts = [(cx, cy)] + [(cx + math.cos(a0 + (a1 - a0) * q / 6) * rx, cy + math.sin(a0 + (a1 - a0) * q / 6) * ry)
                            for q in range(7)]
        pygame.draw.polygon(fr, c1, pts)
    hl = pygame.Rect(0, 0, int(rx * 0.7), int(ry * 0.32))
    hl.center = (int(cx - rx * 0.32), int(cy - ry * 0.58))
    pygame.draw.ellipse(fr, WHITE, hl)
    pygame.draw.circle(fr, WHITE, (cx + rx * 0.12, cy - ry * 0.74), max(3, int(8 * z)))
    pygame.draw.ellipse(fr, BLACK, rect, _lw(z, 5, 3))
    pygame.draw.circle(fr, BLACK, (cx, cy), max(4, int(10 * z)))                 # valve
    pygame.draw.circle(fr, (230, 230, 240), (cx, cy), max(2, int(6 * z)))


@over("big_bubble")
def bubble_over(r, cam, fi, zone, t_anim, play_t) -> None:
    _water_over(r, cam, fi, zone, t_anim, play_t)


# ================================================================================================ 4. spinning logs
@prop("sa_log")
def draw_log(r, cam, st, i, x, y, ang, fi) -> None:
    fr, z = r.frame, cam.zoom
    R = st["shapes"][0]["r"] * z
    c = cam.to_screen(x, y)
    bark, wood, ring = (112, 66, 34), (226, 176, 112), (184, 124, 68)
    pygame.draw.circle(fr, BLACK, c, R + _lw(z, 4))
    pygame.draw.circle(fr, bark, c, R)
    for k in range(10):                                            # bark notches rotate with the log
        a = ang + k * math.pi / 5
        p0 = (c[0] + math.cos(a) * R * 0.86, c[1] + math.sin(a) * R * 0.86)
        p1 = (c[0] + math.cos(a + 0.12) * R, c[1] + math.sin(a + 0.12) * R)
        pygame.draw.line(fr, BLACK, p0, p1, _lw(z, 3))
    pygame.draw.circle(fr, wood, c, R * 0.8)
    for kk in (0.62, 0.42, 0.22):
        pygame.draw.circle(fr, ring, c, max(2, R * kk), _lw(z, 3))
    a = ang
    pygame.draw.line(fr, scenery.mix(ring, BLACK, 0.3), c, (c[0] + math.cos(a) * R * 0.78, c[1] + math.sin(a) * R * 0.78),
                     _lw(z, 4))                                    # radial crack
    kn = (c[0] + math.cos(a + 2.4) * R * 0.5, c[1] + math.sin(a + 2.4) * R * 0.5)
    pygame.draw.circle(fr, scenery.mix(ring, BLACK, 0.35), kn, max(2, R * 0.12))
    pygame.draw.circle(fr, BLACK, c, R * 0.8, _lw(z, 3))
    pygame.draw.circle(fr, BLACK, c, R, _lw(z, 4, 3))


@static("sa_island")
def draw_island(r, cam, s, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    a = cam.to_screen(*s["a"])
    b = cam.to_screen(*s["b"])
    if b[0] < -60 or a[0] > W + 60:
        return
    _, rock, dark, light = scenery.rock_colours(r.theme)
    rr = s["r"] * z
    top_a, top_b = a[1] - rr, b[1] - rr
    body = [(a[0] - 8 * z, top_a), (b[0] + 8 * z, top_b), (b[0] - 6 * z, top_b + 80 * z),
            ((a[0] + b[0]) / 2, max(top_a, top_b) + 104 * z), (a[0] + 6 * z, top_a + 80 * z)]
    pygame.draw.polygon(fr, rock, body)
    pygame.draw.polygon(fr, dark, [body[1], body[2], body[3]])
    pygame.draw.polygon(fr, BLACK, body, _lw(z, 4, 3))
    cap = [(a[0] - 10 * z, top_a - 4 * z), (b[0] + 10 * z, top_b - 4 * z), (b[0] + 10 * z, top_b + 12 * z),
           (a[0] - 10 * z, top_a + 12 * z)]
    pygame.draw.polygon(fr, r.theme.terrain, cap)
    pygame.draw.polygon(fr, BLACK, cap, _lw(z, 4, 3))
    for k in range(4):                                             # grass tufts
        gx = a[0] + (b[0] - a[0]) * (0.15 + 0.23 * k)
        gy = top_a + (top_b - top_a) * (0.15 + 0.23 * k) - 4 * z
        pygame.draw.line(fr, r.theme.terrain_outline, (gx, gy), (gx - 4 * z, gy - 10 * z), _lw(z, 3))
        pygame.draw.line(fr, r.theme.terrain_outline, (gx, gy), (gx + 4 * z, gy - 9 * z), _lw(z, 3))


@over("spinning_logs")
def logs_over(r, cam, fi, zone, t_anim, play_t) -> None:
    _water_over(r, cam, fi, zone, t_anim, play_t)


# ================================================================================================ 5. lily pads + frog
@prop("sa_pad")
def draw_pad(r, cam, st, i, x, y, ang, fi) -> None:
    fr, z = r.frame, cam.zoom
    vs = st["shapes"][0]["verts"]
    w = (max(v[0] for v in vs) - min(v[0] for v in vs)) * z
    k = _prop_index(r, i, "sa_pad")
    states = _zone(r, fi).get("sa_pads", [])
    state = states[k] if k < len(states) else 0
    cx, cy = cam.to_screen(x, y)
    top = cy - 10 * z
    green = scenery.mix(r.theme.terrain, (70, 190, 70), 0.6)
    if state == 1:
        green = scenery.mix(green, (230, 200, 60), 0.35 + 0.25 * math.sin(fi * 1.3))
    rect = pygame.Rect(0, 0, int(w + 12 * z), int(34 * z))
    rect.center = (int(cx), int(top + 8 * z))
    pygame.draw.ellipse(fr, scenery.mix(green, BLACK, 0.35), rect.move(0, int(6 * z)))
    pygame.draw.ellipse(fr, green, rect)
    # notch wedge
    nx = cx + w * 0.18 * (1 if k % 2 else -1)
    pygame.draw.polygon(fr, scenery.mix(green, BLACK, 0.45),
                        [(nx, rect.centery), (nx - 14 * z, rect.top + 2 * z), (nx + 14 * z, rect.top + 2 * z)])
    for q in range(5):                                             # veins
        a = math.pi * (0.1 + 0.2 * q)
        pygame.draw.line(fr, scenery.mix(green, WHITE, 0.3), rect.center,
                         (rect.centerx + math.cos(a) * rect.width * 0.42, rect.centery - math.sin(a) * rect.height * 0.36),
                         _lw(z, 2))
    pygame.draw.ellipse(fr, BLACK, rect, _lw(z, 4, 3))
    if k % 3 == 1 and state == 0:                                  # little lotus flower
        fx, fy = rect.right - 22 * z, rect.top + 4 * z
        for q in range(5):
            a = -math.pi / 2 + (q - 2) * 0.5
            p = (fx + math.cos(a) * 9 * z, fy + math.sin(a) * 9 * z)
            pygame.draw.circle(fr, BLACK, p, max(3, int(7 * z)))
            pygame.draw.circle(fr, (255, 160, 200), p, max(2, int(5 * z)))
        pygame.draw.circle(fr, (255, 220, 70), (fx, fy), max(2, int(4 * z)))
    if state in (1, 2):                                            # trouble bubbles / ripples
        for q in range(3):
            u = ((fi / 30.0) * 1.8 + q / 3) % 1.0
            bx = cx + (q - 1) * w * 0.3
            by = top + 6 * z - u * 30 * z
            pygame.draw.circle(fr, WHITE, (bx, by), max(2, int((3 + 4 * u) * z)), _lw(z, 2))


def _frog(r, cam, fx, fy, ext, d, tx, ty) -> None:
    fr, z = r.frame, cam.zoom
    c = cam.to_screen(fx, fy)
    if not (-120 < c[0] < W + 120):
        return
    body_c = (78, 186, 62)
    belly = (210, 236, 140)
    mouth = (c[0] + d * 24 * z, c[1] + 2 * z)
    if ext > 0.02:                                                 # the tongue
        tgt = cam.to_screen(tx, ty)
        dx, dy = tgt[0] - mouth[0], tgt[1] - mouth[1]
        dist = math.hypot(dx, dy) or 1.0
        L = min(dist, 230 * z) * ext
        tip = (mouth[0] + dx / dist * L, mouth[1] + dy / dist * L)
        pygame.draw.line(fr, BLACK, mouth, tip, _lw(z, 14))
        pygame.draw.line(fr, (255, 104, 140), mouth, tip, _lw(z, 8))
        pygame.draw.circle(fr, BLACK, tip, max(5, int(13 * z)))
        pygame.draw.circle(fr, (255, 104, 140), tip, max(4, int(10 * z)))
    squat = 1.0 - 0.15 * ext
    body = pygame.Rect(0, 0, int(72 * z), int(52 * z * squat))
    body.midbottom = (int(c[0]), int(c[1] + 26 * z))
    pygame.draw.ellipse(fr, BLACK, body.inflate(_lw(z, 8), _lw(z, 8)))
    pygame.draw.ellipse(fr, body_c, body)
    bl = pygame.Rect(0, 0, int(44 * z), int(26 * z * squat))
    bl.midbottom = (body.centerx + int(d * 6 * z), body.bottom - int(2 * z))
    pygame.draw.ellipse(fr, belly, bl)
    for s_ in (-1, 1):                                             # bulging eyes
        e = (c[0] + s_ * 16 * z + d * 6 * z, body.top + 2 * z)
        pygame.draw.circle(fr, BLACK, e, max(5, int(14 * z)))
        pygame.draw.circle(fr, body_c, e, max(4, int(11 * z)))
        pygame.draw.circle(fr, WHITE, e, max(3, int(8 * z)))
        pygame.draw.circle(fr, BLACK, (e[0] + d * 3 * z, e[1]), max(2, int(4 * z)))
    pygame.draw.arc(fr, BLACK, pygame.Rect(c[0] - 22 * z + d * 10 * z, c[1] - 12 * z, 44 * z, 22 * z),
                    math.pi * 1.1, math.pi * 1.9, _lw(z, 3))
    for s_ in (-1, 1):                                             # feet
        pygame.draw.ellipse(fr, BLACK, (c[0] + s_ * 30 * z - 12 * z, body.bottom - 8 * z, 24 * z, 12 * z))
        pygame.draw.ellipse(fr, body_c, (c[0] + s_ * 30 * z - 10 * z, body.bottom - 6 * z, 20 * z, 8 * z))


@over("lily_pads")
def lily_over(r, cam, fi, zone, t_anim, play_t) -> None:
    _water_over(r, cam, fi, zone, t_anim, play_t)
    for f in zone.get("sa_frogs", []):
        _frog(r, cam, *f)


# ================================================================================================ 6. rafts
@prop("sa_raft")
def draw_raft(r, cam, st, i, x, y, ang, fi) -> None:
    fr, z = r.frame, cam.zoom
    vs = st["shapes"][0]["verts"]
    hw = max(v[0] for v in vs)
    hh = max(v[1] for v in vs)
    k = _prop_index(r, i, "sa_raft")
    rafts = _zone(r, fi).get("sa_rafts", [])
    dip, sunk, load = rafts[k] if k < len(rafts) else (0.0, 0, 0.0)
    ca, sa = math.cos(ang), math.sin(ang)

    def P(px, py):
        return cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca)

    wood, dark = (196, 136, 72), (138, 88, 44)
    n = 6
    for q in range(n):                                             # logs/planks
        x0 = -hw + 2 * hw * q / n
        x1 = x0 + 2 * hw / n
        pts = [P(x0, -hh), P(x1, -hh), P(x1, hh), P(x0, hh)]
        pygame.draw.polygon(fr, wood if q % 2 else scenery.mix(wood, dark, 0.3), pts)
        pygame.draw.polygon(fr, BLACK, pts, _lw(z, 2))
    for u in (-0.62, 0.62):                                        # rope lashings
        a, b = P(hw * u - 6, -hh - 2), P(hw * u + 6, hh + 2)
        pygame.draw.line(fr, BLACK, (a[0], a[1]), (b[0], b[1]), _lw(z, 9))
        pygame.draw.line(fr, (236, 210, 140), (a[0], a[1]), (b[0], b[1]), _lw(z, 5))
    outline = [P(-hw, -hh), P(hw, -hh), P(hw, hh), P(-hw, hh)]
    pygame.draw.polygon(fr, BLACK, outline, _lw(z, 4, 3))
    # load gauge flag: 6 pips (capacity), turns red when overloaded
    fx, fy = P(hw - 16, -hh)
    pole_top = (fx, fy - 54 * z)
    pygame.draw.line(fr, BLACK, (fx, fy), pole_top, _lw(z, 6))
    pygame.draw.line(fr, (120, 80, 40), (fx, fy), pole_top, _lw(z, 3))
    over_cap = load > 6.0 or sunk
    for q in range(6):
        on = load >= q + 0.5
        col = (240, 60, 50) if over_cap else ((90, 220, 90) if on else (240, 240, 230))
        pr = pygame.Rect(0, 0, int(10 * z), int(7 * z))
        pr.midright = (int(pole_top[0] - 2 * z), int(pole_top[1] + 6 * z + q * 7 * z))
        pygame.draw.rect(fr, col, pr)
        pygame.draw.rect(fr, BLACK, pr, max(1, int(2 * z)))
    if sunk and dip > 20:
        lab = _label("GLUG!", 34, (120, 200, 255))
        c = cam.to_screen(x, y - 70)
        fr.blit(lab, lab.get_rect(center=(c[0], c[1] - dip * 0.3 * z)))


@over("raft_rapids")
def raft_over(r, cam, fi, zone, t_anim, play_t) -> None:
    fr, z = r.frame, cam.zoom
    _water_over(r, cam, fi, zone, t_anim, play_t)
    for w in _waters(r):                                           # mooring posts at both banks
        for wx in (w["x0"] + 4, w["x1"] - 4):
            sx, sy = cam.to_screen(wx, w["y"])
            if not (-40 < sx < W + 40):
                continue
            post = pygame.Rect(0, 0, int(16 * z), int(70 * z))
            post.midbottom = (int(sx), int(sy + 30 * z))
            pygame.draw.rect(fr, BLACK, post.inflate(_lw(z, 6), _lw(z, 6)), border_radius=4)
            pygame.draw.rect(fr, (150, 98, 52), post, border_radius=3)
            pygame.draw.line(fr, (236, 210, 140), (post.left, post.top + 14 * z), (post.right, post.top + 18 * z), _lw(z, 4))
