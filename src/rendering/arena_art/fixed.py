"""Renderers for the v6 FIXED single-screen arenas (needle_drop, plinko_cashout, pinball_pit, wall_rush)."""
from __future__ import annotations

import math

import pygame

from src.rendering.arena_art import over, prop, static, under

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------------------------- helpers
def _w(cam, v: float, lo: int = 2) -> int:
    return max(lo, int(v * cam.zoom))


def _seg(r, cam, s, col, outline=BLACK, extra: float = 0.0) -> None:
    a, b = cam.to_screen(*s["a"]), cam.to_screen(*s["b"])
    w = _w(cam, s.get("r", 8) * 2 + extra, 4)
    pygame.draw.line(r.frame, outline, a, b, w + _w(cam, 8))
    pygame.draw.line(r.frame, col, a, b, w)
    for p in (a, b):
        pygame.draw.circle(r.frame, outline, p, w / 2 + _w(cam, 4))
        pygame.draw.circle(r.frame, col, p, w / 2)


def _circ(r, cam, c, rad, col, ring=None, hi=True) -> None:
    p = cam.to_screen(*c)
    rr = rad * cam.zoom
    pygame.draw.circle(r.frame, BLACK, p, rr + _w(cam, 4))
    pygame.draw.circle(r.frame, col, p, rr)
    if ring:
        pygame.draw.circle(r.frame, ring, p, rr * 0.62, _w(cam, 4))
    if hi:
        pygame.draw.circle(r.frame, WHITE, (p[0] - rr * 0.33, p[1] - rr * 0.33), max(1.5, rr * 0.22))


def _rect_poly(cam, rect):
    x0, y0, x1, y1 = rect
    return [cam.to_screen(x0, y0), cam.to_screen(x1, y0), cam.to_screen(x1, y1), cam.to_screen(x0, y1)]


def _bg(r, cam, top, bottom, rect=(0, -400, 1080, 1520)) -> None:
    x0, y0, x1, y1 = rect
    sx0, sy0 = cam.to_screen(x0, y0)
    sx1, sy1 = cam.to_screen(x1, y1)
    h = max(1, int(sy1 - sy0))
    band = max(4, h // 40)
    for k in range(0, h, band):
        u = k / h
        col = tuple(int(top[i] + (bottom[i] - top[i]) * u) for i in range(3))
        pygame.draw.rect(r.frame, col, (sx0, sy0 + k, sx1 - sx0, band + 1))


def _shape_pts(sh, x, y, ang, cam):
    ca, sa = math.cos(ang), math.sin(ang)
    return [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in sh["verts"]]


def _prop_shapes(r, cam, st, x, y, ang, fill, outline=BLACK, lw=4):
    ca, sa = math.cos(ang), math.sin(ang)
    for sh in st["shapes"]:
        if sh["type"] == "poly":
            pts = _shape_pts(sh, x, y, ang, cam)
            pygame.draw.polygon(r.frame, fill, pts)
            pygame.draw.polygon(r.frame, outline, pts, _w(cam, lw))
        elif sh["type"] == "seg":
            a = cam.to_screen(x + sh["a"][0] * ca - sh["a"][1] * sa, y + sh["a"][0] * sa + sh["a"][1] * ca)
            b = cam.to_screen(x + sh["b"][0] * ca - sh["b"][1] * sa, y + sh["b"][0] * sa + sh["b"][1] * ca)
            w = _w(cam, sh["r"] * 2, 4)
            pygame.draw.line(r.frame, outline, a, b, w + _w(cam, 8))
            pygame.draw.line(r.frame, fill, a, b, w)
            for p in (a, b):
                pygame.draw.circle(r.frame, outline, p, w / 2 + _w(cam, 4))
                pygame.draw.circle(r.frame, fill, p, w / 2)
        else:
            ox, oy = sh["c"]
            _circ(r, cam, (x + ox * ca - oy * sa, y + ox * sa + oy * ca), sh["r"], fill)


def _spikes(r, cam, a, b, normal, size=26.0, col=(196, 204, 222)) -> None:
    (ax, ay), (bx, by) = a, b
    L = math.hypot(bx - ax, by - ay)
    n = max(2, int(L / size))
    nx, ny = normal
    for k in range(n):
        u0, u1 = k / n, (k + 1) / n
        p0 = (ax + (bx - ax) * u0, ay + (by - ay) * u0)
        p1 = (ax + (bx - ax) * u1, ay + (by - ay) * u1)
        tip = ((p0[0] + p1[0]) / 2 + nx * size * 1.05, (p0[1] + p1[1]) / 2 + ny * size * 1.05)
        pts = [cam.to_screen(*p0), cam.to_screen(*p1), cam.to_screen(*tip)]
        pygame.draw.polygon(r.frame, col, pts)
        pygame.draw.polygon(r.frame, BLACK, pts, _w(cam, 3))


def _text(r, txt, size, center, fill=(255, 230, 60)) -> None:
    from src.rendering import hud
    s = hud.outlined(txt, size, fill=fill, width=4)
    r.frame.blit(s, s.get_rect(center=(int(center[0]), int(center[1]))))


# ================================================================================================ NEEDLE DROP
@under("needle_drop")
def nd_under(r, cam, fi, zone, t, play_t):
    _bg(r, cam, (44, 52, 78), (18, 20, 34))
    for y in range(-300, 1500, 120):                         # riveted steel panel seams
        a, b = cam.to_screen(26, y), cam.to_screen(1054, y)
        pygame.draw.line(r.frame, (60, 70, 100), a, b, _w(cam, 3))
    # chamber glow
    pygame.draw.polygon(r.frame, (52, 20, 30), _rect_poly(cam, (26, 1090, 1054, 1470)))


@static("nd_wall")
def nd_wall(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (118, 128, 152))


@static("nd_needles")
def nd_needles(r, cam, s, zone, t, play_t):
    side = s.get("side", "F")
    normal = {"L": (1, 0), "R": (-1, 0), "F": (0, -1)}[side]
    _seg(r, cam, s, (90, 96, 112))
    _spikes(r, cam, s["a"], s["b"], normal, 24.0)


@static("nd_deflector")
def nd_deflector(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (250, 196, 40))
    a, b = s["a"], s["b"]
    for u in (0.25, 0.5, 0.75):                              # hazard chevrons
        p = cam.to_screen(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        pygame.draw.circle(r.frame, BLACK, p, _w(cam, 4))


@static("nd_peg")
def nd_peg(r, cam, s, zone, t, play_t):
    _circ(r, cam, s["c"], s["r"], (235, 50, 75), ring=WHITE)


@static("nd_net")
def nd_net(r, cam, s, zone, t, play_t):
    if not zone.get("nd_net", False):
        return
    a, b = cam.to_screen(*s["a"]), cam.to_screen(*s["b"])
    pygame.draw.line(r.frame, (80, 220, 255), a, b, _w(cam, 6))
    n = 18
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        pygame.draw.line(r.frame, (80, 220, 255), (x, a[1]), (x, a[1] + 16 * cam.zoom), _w(cam, 2))


@prop("nd_pad")
def nd_pad(r, cam, st, i, x, y, ang, fi):
    pads = r.tr.zones[fi].get("nd_pads") or []
    state, frac = 0, 0.0
    if pads:
        best = min(pads, key=lambda p: abs(p[0] - x) + abs(p[1] - y))
        state, frac = int(best[3]), float(best[4])
    if state == 2:
        return
    col = (60, 220, 110)
    if state == 1:
        col = (240, 50, 60) if (fi // 3) % 2 == 0 else (255, 210, 60)
    _prop_shapes(r, cam, st, x, y, ang, col)
    sx, sy = cam.to_screen(x, y)
    if state == 0:
        glow = pygame.Surface((int(260 * cam.zoom), int(40 * cam.zoom)), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (120, 255, 160, 70), glow.get_rect())
        r.frame.blit(glow, glow.get_rect(center=(sx, sy - 6 * cam.zoom)))


@over("needle_drop")
def nd_over(r, cam, fi, zone, t, play_t):
    fy = float(zone.get("nd_flame", -240.0))
    if fy > -200:
        x0, sy = cam.to_screen(26, fy)
        x1, _ = cam.to_screen(1054, fy)
        top = cam.to_screen(26, -400)[1]
        pygame.draw.rect(r.frame, (150, 30, 10), (x0, top, x1 - x0, sy - top))
        for k in range(24):
            fx = x0 + (x1 - x0) * (k + 0.5) / 24
            h = (26 + 16 * math.sin(t * 9 + k * 1.7)) * cam.zoom
            pygame.draw.polygon(r.frame, (255, 150, 30), [(fx - 22 * cam.zoom, sy), (fx + 22 * cam.zoom, sy), (fx, sy + h)])
            pygame.draw.polygon(r.frame, (255, 230, 90), [(fx - 10 * cam.zoom, sy), (fx + 10 * cam.zoom, sy), (fx, sy + h * 0.6)])
    rd = int(zone.get("nd_round", 0) or 0)
    if rd:
        _text(r, f"ROUND {rd + 1}", max(20, int(40 * cam.zoom)), cam.to_screen(540, 1035), fill=(255, 120, 90))


# ================================================================================================ PLINKO CASHOUT
@under("plinko_cashout")
def pc_under(r, cam, fi, zone, t, play_t):
    _bg(r, cam, (74, 24, 120), (24, 10, 60))
    for k in range(14):                                      # marquee bulbs down both sides
        on = (k + fi // 6) % 2 == 0
        for x in (40, 1040):
            p = cam.to_screen(x, 120 + k * 95)
            pygame.draw.circle(r.frame, (255, 220, 80) if on else (120, 90, 40), p, _w(cam, 7))
    for s in r.meta["statics"]:
        if s.get("type") != "pc_bins":
            continue
        top, bot = float(s["top"]), 1478.0
        for x0, x1, kind in s["bins"]:
            col = {"gold": (250, 196, 30), "spike": (190, 30, 40), "safe": (40, 120, 200)}.get(kind, (60, 60, 80))
            pygame.draw.polygon(r.frame, col, _rect_poly(cam, (x0, top, x1, bot)))


@static("pc_bins")
def pc_bins(r, cam, s, zone, t, play_t):
    top = float(s["top"])
    for x0, x1, kind in s["bins"]:
        cx = (x0 + x1) / 2
        lbl = {"gold": "$$$", "spike": "X", "safe": "UP!"}.get(kind, "")
        _text(r, lbl, max(16, int(34 * cam.zoom)), cam.to_screen(cx, top + 110),
              fill={"gold": (255, 248, 160), "spike": (255, 120, 120)}.get(kind, (180, 230, 255)))


@static("pc_floor")
def pc_floor(r, cam, s, zone, t, play_t):
    kind = s.get("bin", "safe")
    _seg(r, cam, s, {"gold": (255, 214, 40), "spike": (110, 30, 36)}.get(kind, (90, 200, 255)))
    if kind == "spike":
        _spikes(r, cam, s["a"], s["b"], (0, -1), 22.0)
    elif kind == "safe":
        a, b = s["a"], s["b"]
        for u in (0.3, 0.7):                                  # spring coils
            c = cam.to_screen(a[0] + (b[0] - a[0]) * u, a[1] - 14)
            pygame.draw.circle(r.frame, BLACK, c, _w(cam, 9), _w(cam, 3))


@static("pc_wall")
def pc_wall(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (150, 90, 220))


@static("pc_chute")
def pc_chute(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (255, 120, 200))


@static("pc_divider")
def pc_divider(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (230, 230, 245))


@static("pc_cap")
def pc_cap(r, cam, s, zone, t, play_t):
    _circ(r, cam, s["c"], s["r"], (255, 214, 40))


@static("pc_peg")
def pc_peg(r, cam, s, zone, t, play_t):
    _circ(r, cam, s["c"], s["r"], (250, 250, 255))


@static("pc_kicker")
def pc_kicker(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (80, 240, 200))


@prop("pc_gate")
def pc_gate(r, cam, st, i, x, y, ang, fi):
    _prop_shapes(r, cam, st, x, y, ang, (255, 80, 60))


@prop("pc_lid")
def pc_lid(r, cam, st, i, x, y, ang, fi):
    _prop_shapes(r, cam, st, x, y, ang, (120, 240, 255))


@over("plinko_cashout")
def pc_over(r, cam, fi, zone, t, play_t):
    _text(r, "PLINKO CASHOUT", max(18, int(46 * cam.zoom)), cam.to_screen(540, 60), fill=(255, 230, 60))
    nxt = zone.get("pc_next_open")
    if nxt is not None and float(nxt) < 0.6:
        _text(r, "GOLD OPEN!", max(16, int(34 * cam.zoom)), cam.to_screen(540, 1190), fill=(255, 250, 170))
    sp = zone.get("pc_spring")
    if sp and t - float(sp[1]) < 0.4:
        pass


# ================================================================================================ PINBALL PIT
@under("pinball_pit")
def pp_under(r, cam, fi, zone, t, play_t):
    _bg(r, cam, (16, 18, 60), (6, 6, 24))
    for k in range(9):                                       # neon arrows down the playfield
        y = 380 + k * 110
        col = (255, 60, 160) if (k + fi // 5) % 3 == 0 else (60, 40, 110)
        a, b, c = cam.to_screen(520, y), cam.to_screen(560, y), cam.to_screen(540, y - 34)
        pygame.draw.polygon(r.frame, col, [a, b, c])
    jy = cam.to_screen(540, 112)
    pygame.draw.circle(r.frame, (255, 214, 40) if zone.get("pp_door") else (90, 70, 20), jy, _w(cam, 36))
    _text(r, "JACKPOT", max(14, int(30 * cam.zoom)), cam.to_screen(540, 30), fill=(255, 230, 60))


@static("pp_rail")
def pp_rail(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (60, 220, 255))


@static("pp_sling")
def pp_sling(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (255, 80, 180))


@static("pp_lane")
def pp_lane(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (255, 214, 40))


@static("pp_door")
def pp_door(r, cam, s, zone, t, play_t):
    if zone.get("pp_door"):
        return
    _seg(r, cam, s, (255, 70, 70))


@static("pp_bumper")
def pp_bumper(r, cam, s, zone, t, play_t):
    bump = zone.get("pp_bump") or []
    i = int(s.get("idx", 0))
    lit = i < len(bump) and float(bump[i]) < 0.25
    _circ(r, cam, s["c"], s["r"] * (1.12 if lit else 1.0), (255, 240, 120) if lit else (240, 60, 120), ring=WHITE)


@prop("pp_spinner")
def pp_spinner(r, cam, st, i, x, y, ang, fi):
    _prop_shapes(r, cam, st, x, y, ang, (160, 255, 120))
    _circ(r, cam, (x, y), 12, (255, 214, 40), hi=False)


@prop("pp_flipper")
def pp_flipper(r, cam, st, i, x, y, ang, fi):
    _prop_shapes(r, cam, st, x, y, ang, (255, 255, 255))
    _circ(r, cam, (x, y), 14, (255, 70, 70), hi=False)


@prop("pp_post")
def pp_post(r, cam, st, i, x, y, ang, fi):
    _circ(r, cam, (x, y), 24, (255, 214, 40), ring=BLACK)


@over("pinball_pit")
def pp_over(r, cam, fi, zone, t, play_t):
    tl = zone.get("pp_tilt")
    if tl and 0 <= t - float(tl[0]) < 1.4:
        _text(r, "TILT!", max(30, int(110 * cam.zoom)), cam.to_screen(540, 700), fill=(255, 70, 70))
    dl = cam.to_screen(540, 1430)
    _text(r, "DRAIN", max(14, int(28 * cam.zoom)), dl, fill=(255, 120, 120))


# ================================================================================================ WALL RUSH
@under("wall_rush")
def wr_under(r, cam, fi, zone, t, play_t):
    _bg(r, cam, (14, 30, 54), (6, 10, 22))
    for x in range(0, 1100, 90):                             # cyber grid
        pygame.draw.line(r.frame, (24, 60, 96), cam.to_screen(x, -400), cam.to_screen(x, 1520), _w(cam, 2))
    for y in range(-400, 1520, 90):
        pygame.draw.line(r.frame, (24, 60, 96), cam.to_screen(0, y), cam.to_screen(1080, y), _w(cam, 2))
    # the drop shaft on the left
    pygame.draw.polygon(r.frame, (40, 6, 16), _rect_poly(cam, (0, 200, 140, 1520)))


@static("wr_lane")
def wr_lane(r, cam, s, zone, t, play_t):
    col = [(0, 236, 255), (255, 60, 200), (255, 214, 40)][int(s.get("lane", 0)) % 3]
    _seg(r, cam, s, col)


@static("wr_stop")
def wr_stop(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (90, 100, 130))


@static("wr_shaft")
def wr_shaft(r, cam, s, zone, t, play_t):
    _seg(r, cam, s, (180, 40, 60))


@prop("wr_wall")
def wr_wall(r, cam, st, i, x, y, ang, fi):
    if x > 5000:
        return
    _prop_shapes(r, cam, st, x, y, ang, (120, 130, 170))
    for sh in st["shapes"]:                                  # hazard stripes on the leading edge
        pts = _shape_pts(sh, x, y, ang, cam)
        pygame.draw.line(r.frame, (255, 214, 40), pts[0], pts[3], _w(cam, 6))


@over("wall_rush")
def wr_over(r, cam, fi, zone, t, play_t):
    w = zone.get("wr_warn")
    lanes = (560.0, 900.0, 1240.0)
    if w:
        g, left = int(w[0]), float(w[1])
        if (fi // 4) % 2 == 0 and 0 <= g < 3:
            p = cam.to_screen(1030, lanes[g] - 110)
            s = cam.zoom
            pygame.draw.polygon(r.frame, (60, 255, 120), [(p[0] + 30 * s, p[1] - 40 * s), (p[0] + 30 * s, p[1] + 40 * s),
                                                          (p[0] - 40 * s, p[1])])
            _text(r, "GAP!", max(14, int(32 * cam.zoom)), (p[0] - 70 * s, p[1]), fill=(120, 255, 160))
