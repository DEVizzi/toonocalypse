"""Renderers for the v6 side_b arenas (Sweeper Circuit, Knock-Knock Doors, Swing Canyon, Clockwork Cogs, Inferno Ascent).

Bold cartoon style: flat fills, thick BLACK outlines scaled by cam.zoom, theme colours where it makes sense.
"""
from __future__ import annotations

import math

import pygame

from src.config import H, W
from src.rendering import effects
from src.rendering.arena_art import over, prop, static, under
from src.rendering.scenery import mix, rock_colours

BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
WOOD = (176, 112, 58)
WOOD_D = (122, 72, 36)
WOOD_L = (214, 156, 96)
BRASS = (222, 170, 62)
BRASS_D = (160, 110, 34)
BRASS_L = (250, 214, 120)
STEEL = (150, 160, 178)
STEEL_D = (92, 100, 118)


def _ow(z: float, base: float = 4.5) -> int:
    return int(max(3, min(6, round(base * z))))


def _rot(pts, x, y, ang, cam):
    ca, sa = math.cos(ang), math.sin(ang)
    return [cam.to_screen(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts]


def _box_local(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _box_wh(st) -> tuple[float, float]:
    vs = st["shapes"][0].get("verts") or [(-20, -10), (20, 10)]
    xs, ys = [v[0] for v in vs], [v[1] for v in vs]
    return max(xs) - min(xs), max(ys) - min(ys)


def _play_t(r, fi: int) -> float:
    return (fi - getattr(r, "pre", 0)) / 30.0


# ================================================================================================ SWEEPER CIRCUIT
@static("sweeper_hub")
def _sweeper_hub(r, cam, s, zone, t_anim, play_t):
    z = cam.zoom
    hx, fy, h = s["x"], s["y"], s["h"]
    sx, sy = cam.to_screen(hx, fy)
    if sx < -120 or sx > W + 120:
        return
    top = cam.to_screen(hx, fy - h - (34 if s["low"] else 46))[1]
    pw = max(10, int(26 * z))
    rect = pygame.Rect(int(sx - pw / 2), int(top), pw, int(sy - top))
    pygame.draw.rect(r.frame, BLACK, rect.inflate(_ow(z) * 2, _ow(z)), border_radius=4)
    pygame.draw.rect(r.frame, STEEL, rect, border_radius=3)
    pygame.draw.rect(r.frame, STEEL_D, (rect.right - pw // 3, rect.top, pw // 3, rect.height))
    base = pygame.Rect(int(sx - pw), int(sy - 14 * z), pw * 2, int(14 * z))
    pygame.draw.rect(r.frame, BLACK, base.inflate(_ow(z), _ow(z)), border_radius=4)
    pygame.draw.rect(r.frame, r.theme.accent, base, border_radius=3)
    # spinning hub cap at arm height
    cy = cam.to_screen(hx, fy - h)[1]
    rr = max(8, int(17 * z))
    pygame.draw.circle(r.frame, BLACK, (sx, cy), rr + _ow(z))
    pygame.draw.circle(r.frame, r.theme.hazard, (sx, cy), rr)
    a = t_anim * 6.0
    for k in range(3):
        aa = a + k * 2.094
        pygame.draw.line(r.frame, WHITE, (sx, cy), (sx + math.cos(aa) * rr * 0.8, cy + math.sin(aa) * rr * 0.8),
                         max(2, int(3 * z)))
    pygame.draw.circle(r.frame, BLACK, (sx, cy), max(3, rr // 3))


@prop("sweeper_arm")
def _sweeper_arm(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    sh = st["shapes"][0]
    hx = sh["hub"][0]
    low = sh.get("low", True)
    br = sh.get("r", 8.0)
    fr = r.frame
    a = cam.to_screen(hx, y)
    b = cam.to_screen(x, y)
    if max(a[0], b[0]) < -60 or min(a[0], b[0]) > W + 60:
        return
    wd = max(8, int((br * 2 + 6) * z))
    c1 = (255, 214, 40) if low else (236, 44, 60)
    c2 = BLACK if low else WHITE
    glow = mix(c1, WHITE, 0.55)
    # motion trail: ghost tips from the last frames
    props = r.tr.props
    prev = []
    for k in (6, 4, 2):
        j = fi - k
        if 0 <= j < len(props) and i < len(props[j]):
            prev.append((k, float(props[j][i][0])))
    for k, px in prev:
        p = cam.to_screen(px, y)
        col = mix(glow, (255, 255, 255), 0.3)
        w2 = max(2, int(wd * (0.25 + 0.06 * (6 - k))))
        pygame.draw.line(fr, col, p, b, w2)
        pygame.draw.circle(fr, col, (int(p[0]), int(p[1])), max(2, w2 // 2 + 1))
    pygame.draw.line(fr, glow, a, b, wd + _ow(z) * 2 + 6)
    pygame.draw.line(fr, BLACK, a, b, wd + _ow(z) * 2)
    pygame.draw.line(fr, c1, a, b, wd)
    # diagonal-ish hazard stripes along the arm
    dx = b[0] - a[0]
    n = int(abs(dx) / max(8.0, 22 * z))
    for k in range(n):
        if k % 2 == 0:
            continue
        u0, u1 = k / max(1, n), (k + 0.6) / max(1, n)
        p0 = (a[0] + dx * u0, a[1])
        p1 = (a[0] + dx * u1, a[1])
        pygame.draw.line(fr, c2, p0, p1, max(3, wd - 4))
    pygame.draw.line(fr, mix(c1, WHITE, 0.6), (a[0], a[1] - wd * 0.28), (b[0], b[1] - wd * 0.28), max(1, int(2 * z)))
    rr = max(6, int((br + 5) * z))
    pygame.draw.circle(fr, glow, (int(b[0]), int(b[1])), rr + _ow(z) + 3)
    pygame.draw.circle(fr, BLACK, (int(b[0]), int(b[1])), rr + _ow(z))
    pygame.draw.circle(fr, c1, (int(b[0]), int(b[1])), rr)
    pygame.draw.circle(fr, WHITE, (int(b[0] - rr * 0.3), int(b[1] - rr * 0.3)), max(2, rr // 3))


# ================================================================================================ KNOCK-KNOCK DOORS
def _bricks(fr, rect: pygame.Rect, z: float, base, dark, light, offset: float = 0.0) -> None:
    pygame.draw.rect(fr, base, rect)
    bh = max(8, int(24 * z))
    bw = max(16, int(48 * z))
    row = 0
    y = rect.bottom
    while y > rect.top:
        y0 = max(rect.top, y - bh)
        pygame.draw.line(fr, dark, (rect.left, y0), (rect.right - 1, y0), max(1, int(2 * z)))
        xo = (bw // 2) if row % 2 else 0
        xx = rect.left + xo
        while xx < rect.right:
            pygame.draw.line(fr, dark, (xx, y0), (xx, y), max(1, int(2 * z)))
            xx += bw
        pygame.draw.line(fr, light, (rect.left + 2, y0 + 2), (rect.right - 3, y0 + 2), 1)
        y -= bh
        row += 1


@static("kd_wall")
def _kd_wall(r, cam, s, zone, t_anim, play_t):
    z = cam.zoom
    fr = r.frame
    x, w, fy, dh = s["x"], s["w"], s["floor"], s["door_h"]
    sx0, _ = cam.to_screen(x, fy)
    sx1, sy = cam.to_screen(x + w, fy)
    if sx1 < -80 or sx0 > W + 80:
        return
    door_top = cam.to_screen(x, fy - dh)[1]
    top = max(-10, int(cam.to_screen(x, fy - 1500)[1]))
    _, rock, dark, light = rock_colours(r.theme)
    brick = mix(r.theme.castle, (178, 92, 70), 0.45)
    ow = _ow(z)
    states = zone.get("kd_doors") or ()
    st = states[s["idx"]] if s["idx"] < len(states) else (0, 0, -1.0, 0)
    # dark doorway behind the door
    hole = pygame.Rect(int(sx0), int(door_top), int(sx1 - sx0), int(sy - door_top))
    pygame.draw.rect(fr, (34, 26, 40), hole)
    # brick wall above the doorway
    wall = pygame.Rect(int(sx0), top, int(sx1 - sx0), int(door_top - top))
    if wall.height > 0:
        _bricks(fr, wall, z, brick, mix(brick, BLACK, 0.35), mix(brick, WHITE, 0.25))
        pygame.draw.rect(fr, BLACK, wall, ow)
    # stone lintel + jambs
    lint = pygame.Rect(int(sx0 - 8 * z), int(door_top - 18 * z), int(sx1 - sx0 + 16 * z), int(20 * z))
    pygame.draw.rect(fr, rock, lint)
    pygame.draw.rect(fr, BLACK, lint, ow)
    for jx in (sx0, sx1):
        j = pygame.Rect(int(jx - 7 * z), int(door_top), int(14 * z), int(sy - door_top))
        pygame.draw.rect(fr, rock, j)
        pygame.draw.rect(fr, BLACK, j, max(2, ow - 1))
    # keystone
    kx = (sx0 + sx1) / 2
    ks = [(kx - 12 * z, door_top - 20 * z), (kx + 12 * z, door_top - 20 * z), (kx + 7 * z, door_top + 2),
          (kx - 7 * z, door_top + 2)]
    pygame.draw.polygon(fr, light, ks)
    pygame.draw.polygon(fr, BLACK, ks, max(2, ow - 1))
    # remnants once opened
    if st[0] == 1:          # smashed: jagged stubs on the hinges
        for k, yy in enumerate((0.12, 0.5, 0.86)):
            cy = door_top + (sy - door_top) * yy
            stub = [(sx0 + 4 * z, cy - 10 * z), (sx0 + (22 - 6 * k) * z, cy - 4 * z),
                    (sx0 + 12 * z, cy + 2 * z), (sx0 + (26 - 4 * k) * z, cy + 9 * z), (sx0 + 4 * z, cy + 12 * z)]
            pygame.draw.polygon(fr, WOOD, stub)
            pygame.draw.polygon(fr, BLACK, stub, 2)
    elif st[0] == 2:        # trapdoor wall: the door swung open (thin slab seen edge-on)
        slab = pygame.Rect(int(sx1 - 2 * z), int(door_top + 4 * z), int(10 * z), int(sy - door_top - 6 * z))
        pygame.draw.rect(fr, WOOD_D, slab)
        pygame.draw.rect(fr, BLACK, slab, 2)


@prop("kd_door")
def _kd_door(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    sh = st["shapes"][0]
    w, h = _box_wh(st)
    zone = r.tr.zones[fi]
    states = zone.get("kd_doors") or ()
    idx = sh.get("idx", 0)
    hits = states[idx][1] if idx < len(states) else 0
    trig = states[idx][3] if idx < len(states) else 0
    jx = math.sin(fi * 2.7) * 3 * z if trig else 0.0
    pts = _rot(_box_local(w, h), x, y, ang, cam)
    pts = [(px + jx, py) for px, py in pts]
    pygame.draw.polygon(fr, WOOD, pts)
    (x0, y0), (x1, _), (_, y1) = pts[0], pts[1], pts[2]
    # vertical planks
    for k in (1, 2):
        xx = x0 + (x1 - x0) * k / 3
        pygame.draw.line(fr, WOOD_D, (xx, y0 + 3), (xx, y1 - 3), max(2, int(2.5 * z)))
    pygame.draw.line(fr, WOOD_L, (x0 + 4 * z, y0 + 4), (x0 + 4 * z, y1 - 4), max(1, int(2 * z)))
    # iron bands with rivets
    for u in (0.18, 0.82):
        yy = y0 + (y1 - y0) * u
        pygame.draw.line(fr, BLACK, (x0, yy), (x1, yy), max(4, int(8 * z)))
        pygame.draw.line(fr, STEEL_D, (x0 + 2, yy), (x1 - 2, yy), max(2, int(5 * z)))
        for rx in (x0 + 5 * z, x1 - 5 * z):
            pygame.draw.circle(fr, STEEL, (int(rx), int(yy)), max(2, int(2.5 * z)))
    # cracks after tough hits
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for k in range(min(4, hits)):
        a = -1.2 + k * 0.9
        p = [(cx, cy)]
        for s in (0.35, 0.7, 1.0):
            p.append((cx + math.cos(a + s * 0.5) * (x1 - x0) * 0.5 * s, cy + math.sin(a) * (y1 - y0) * 0.42 * s))
        pygame.draw.lines(fr, BLACK, False, p, max(2, int(3 * z)))
    pygame.draw.polygon(fr, BLACK, pts, _ow(z))
    # brass knocker ring + face plate
    kx, ky = x0 - 2 * z, y0 + (y1 - y0) * 0.5
    pygame.draw.circle(fr, BLACK, (int(kx), int(ky - 8 * z)), max(4, int(7 * z)))
    pygame.draw.circle(fr, BRASS, (int(kx), int(ky - 8 * z)), max(3, int(5 * z)))
    pygame.draw.circle(fr, BLACK, (int(kx), int(ky + 4 * z)), max(6, int(11 * z)), max(4, int(6 * z)))
    pygame.draw.circle(fr, BRASS, (int(kx), int(ky + 4 * z)), max(5, int(10 * z)), max(2, int(3 * z)))


@prop("kd_plank")
def _kd_plank(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    w, h = _box_wh(st)
    zone = r.tr.zones[fi]
    states = zone.get("kd_doors") or ()
    idx = st["shapes"][0].get("idx", 0)
    trig = states[idx][3] if idx < len(states) else 0
    jy = math.sin(fi * 3.1) * 2.5 * z if trig else 0.0
    pts = [(px, py + jy) for px, py in _rot(_box_local(w, h), x, y, ang, cam)]
    pygame.draw.polygon(fr, WOOD, pts)
    # board seams along the plank
    for k in (1, 2, 3):
        u = k / 4
        a = (pts[0][0] + (pts[1][0] - pts[0][0]) * u, pts[0][1] + (pts[1][1] - pts[0][1]) * u)
        b = (pts[3][0] + (pts[2][0] - pts[3][0]) * u, pts[3][1] + (pts[2][1] - pts[3][1]) * u)
        pygame.draw.line(fr, WOOD_D, a, b, max(2, int(2.5 * z)))
    pygame.draw.line(fr, WOOD_L, pts[0], pts[1], max(2, int(3 * z)))
    pygame.draw.polygon(fr, BLACK, pts, _ow(z))
    for p in (pts[0], pts[1]):
        pygame.draw.circle(fr, STEEL_D, (int(p[0] + (4 * z if p is pts[0] else -4 * z)), int(p[1] + 5 * z)),
                           max(2, int(3 * z)))


@over("knock_doors")
def _kd_over(r, cam, fi, zone, t_anim, play_t):
    states = zone.get("kd_doors") or ()
    walls = getattr(r, "_kd_walls", None)
    if walls is None:
        walls = {s["idx"]: s for s in r.meta["statics"] if s.get("type") == "kd_wall"}
        r._kd_walls = walls
    z = cam.zoom
    for idx, stt in enumerate(states):
        if stt[0] == 0 or stt[2] < 0:
            continue
        age = play_t - stt[2]
        if not (0.0 <= age < 0.9):
            continue
        s = walls.get(idx)
        if s is None:
            continue
        wx = s["x"] + s["w"] / 2
        cy = s["floor"] - s["door_h"] / 2
        if not cam.visible(wx, cy, 300):
            continue
        sx, sy = cam.to_screen(wx, cy)
        if stt[0] == 1:
            # splinters flying forward + dust
            for k in range(9):
                a = -1.9 + k * 0.42 + (k % 3) * 0.1
                d = (40 + 30 * (k % 4)) * age * 4.0 * z
                px = sx + math.cos(a) * d + 30 * age * z
                py = sy + math.sin(a) * d + 380 * age * age * z
                rot = a + age * 12
                L = (14 + 4 * (k % 3)) * z
                pts = [(px + math.cos(rot) * L, py + math.sin(rot) * L),
                       (px + math.cos(rot + 2.6) * L * 0.4, py + math.sin(rot + 2.6) * L * 0.4),
                       (px - math.cos(rot) * L, py - math.sin(rot) * L)]
                pygame.draw.polygon(r.frame, WOOD_L if k % 2 else WOOD, pts)
                pygame.draw.polygon(r.frame, BLACK, pts, 2)
            effects.draw_dust(r.frame, (sx, sy + s["door_h"] * 0.4 * z), age * 0.8, idx * 13 + 1)
            effects.draw_popup(r.frame, "SMASH!", (sx, sy - s["door_h"] * 0.7 * z), age, seed=idx)
        else:
            effects.draw_popup(r.frame, "TRAPDOOR!", (sx - 60 * z, sy - s["door_h"] * 0.7 * z), age, seed=idx + 7)


# ================================================================================================ SWING CANYON
def _chain(fr, a, b, z):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    pygame.draw.line(fr, BLACK, a, b, max(3, int(5 * z)))
    n = max(2, int(d / max(6.0, 14 * z)))
    for k in range(n + 1):
        u = k / n
        p = (int(a[0] + dx * u), int(a[1] + dy * u))
        rr = max(2, int(4 * z))
        pygame.draw.circle(fr, BLACK, p, rr + 2)
        pygame.draw.circle(fr, STEEL if k % 2 else mix(STEEL, WHITE, 0.3), p, rr)


@prop("swing_deck")
def _swing_deck(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    sh = st["shapes"][0]
    pvx, pvy = sh["pivot"]
    xA, xB, yA = sh["beam"]
    w, h = _box_wh(st)
    ow = _ow(z)
    beam_y = pvy - 16
    # posts + crossbeam (gallows frame spanning the canyon)
    for px in (xA - 18, xB + 18):
        a = cam.to_screen(px, yA + 4)
        b = cam.to_screen(px, beam_y)
        pw = max(8, int(18 * z))
        rect = pygame.Rect(int(a[0] - pw / 2), int(b[1]), pw, int(a[1] - b[1]))
        pygame.draw.rect(fr, WOOD_D, rect)
        pygame.draw.rect(fr, BLACK, rect, ow)
    b0, b1 = cam.to_screen(xA - 34, beam_y), cam.to_screen(xB + 34, beam_y)
    bh = max(10, int(22 * z))
    beam = pygame.Rect(int(b0[0]), int(b0[1] - bh / 2), int(b1[0] - b0[0]), bh)
    pygame.draw.rect(fr, WOOD, beam)
    pygame.draw.line(fr, WOOD_L, (beam.left + 4, beam.top + 4), (beam.right - 4, beam.top + 4), max(2, int(3 * z)))
    pygame.draw.rect(fr, BLACK, beam, ow)
    pv = cam.to_screen(pvx, pvy)
    # chains to both deck ends
    corners = _rot([(-w * 0.42, -h / 2), (w * 0.42, -h / 2)], x, y, ang, cam)
    for c in corners:
        _chain(fr, pv, c, z)
    pygame.draw.circle(fr, BLACK, (int(pv[0]), int(pv[1])), max(7, int(13 * z)))
    pygame.draw.circle(fr, BRASS, (int(pv[0]), int(pv[1])), max(5, int(9 * z)))
    # wooden deck
    pts = _rot(_box_local(w, h), x, y, ang, cam)
    pygame.draw.polygon(fr, WOOD, pts)
    n = 5
    for k in range(1, n):
        u = k / n
        a = (pts[0][0] + (pts[1][0] - pts[0][0]) * u, pts[0][1] + (pts[1][1] - pts[0][1]) * u)
        b = (pts[3][0] + (pts[2][0] - pts[3][0]) * u, pts[3][1] + (pts[2][1] - pts[3][1]) * u)
        pygame.draw.line(fr, WOOD_D, a, b, max(2, int(2.5 * z)))
    pygame.draw.line(fr, WOOD_L, pts[0], pts[1], max(2, int(4 * z)))
    pygame.draw.polygon(fr, BLACK, pts, ow)
    for c in corners:
        pygame.draw.circle(fr, BLACK, (int(c[0]), int(c[1])), max(4, int(6 * z)))
        pygame.draw.circle(fr, STEEL, (int(c[0]), int(c[1])), max(2, int(4 * z)))


# ================================================================================================ CLOCKWORK COGS
@prop("cog_gear")
def _cog_gear(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    sh = st["shapes"][0]
    R = sh["r"]
    n = sh.get("teeth", 12)
    c = cam.to_screen(x, y)
    rr = R * z
    tooth = 15 * z
    pts = []
    for k in range(n):
        a0 = ang + 2 * math.pi * k / n
        da = 2 * math.pi / n
        for a, rad in ((a0 - da * 0.32, rr - 2), (a0 - da * 0.2, rr + tooth), (a0 + da * 0.2, rr + tooth),
                       (a0 + da * 0.32, rr - 2)):
            pts.append((c[0] + math.cos(a) * rad, c[1] + math.sin(a) * rad))
    ow = _ow(z, 5)
    pygame.draw.polygon(fr, BLACK, pts, 0)
    inner = [(c[0] + (px - c[0]) * (1 - ow / max(rr + tooth, 1)), c[1] + (py - c[1]) * (1 - ow / max(rr + tooth, 1)))
             for px, py in pts]
    pygame.draw.polygon(fr, BRASS, inner)
    pygame.draw.circle(fr, BRASS_D, c, rr * 0.78)
    pygame.draw.circle(fr, BLACK, c, rr * 0.78, max(2, ow - 1))
    pygame.draw.circle(fr, BRASS, c, rr * 0.62)
    # spokes (cut-outs) rotating with the body
    for k in range(5):
        a = ang + k * 2 * math.pi / 5 + math.pi / 5
        hole = (c[0] + math.cos(a) * rr * 0.45, c[1] + math.sin(a) * rr * 0.45)
        pygame.draw.circle(fr, BLACK, (int(hole[0]), int(hole[1])), max(4, int(rr * 0.13)) + 2)
        pygame.draw.circle(fr, (44, 34, 30), (int(hole[0]), int(hole[1])), max(3, int(rr * 0.13)))
    # highlight arc
    pygame.draw.arc(fr, BRASS_L, (c[0] - rr * 0.7, c[1] - rr * 0.7, rr * 1.4, rr * 1.4), 1.9, 2.9,
                    max(2, int(4 * z)))
    # hub + bolts
    hr = max(6, int(rr * 0.2))
    pygame.draw.circle(fr, BLACK, c, hr + 3)
    pygame.draw.circle(fr, STEEL, c, hr)
    for k in range(6):
        a = ang + k * math.pi / 3
        b = (int(c[0] + math.cos(a) * hr * 0.62), int(c[1] + math.sin(a) * hr * 0.62))
        pygame.draw.circle(fr, STEEL_D, b, max(1, int(2 * z)))
    pygame.draw.circle(fr, BLACK, c, max(2, hr // 3))
    # spin direction arrow on the rim (helps read "this one pulls you back")
    spin = sh.get("spin", 1.0)
    a = -math.pi / 2
    ar = rr * 0.7
    tip = (c[0] + math.cos(a + 0.35 * math.copysign(1, spin)) * ar, c[1] + math.sin(a + 0.35 * math.copysign(1, spin)) * ar)
    pygame.draw.arc(fr, WHITE, (c[0] - ar, c[1] - ar, ar * 2, ar * 2), math.pi / 2 - 0.35, math.pi / 2 + 0.35,
                    max(2, int(3 * z)))
    pygame.draw.circle(fr, WHITE, (int(tip[0]), int(tip[1])), max(2, int(4 * z)))


@prop("cog_piston")
def _cog_piston(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    sh = st["shapes"][0]
    w, h = _box_wh(st)
    base_y = sh["base"]
    ow = _ow(z)
    top = cam.to_screen(x, y)
    bot = cam.to_screen(x, base_y)
    # cylinder housing + shaft
    hw = max(10, int(34 * z))
    house = pygame.Rect(int(bot[0] - hw / 2), int(bot[1] - 40 * z), hw, int(H))
    pygame.draw.rect(fr, STEEL_D, house)
    pygame.draw.rect(fr, BLACK, house, ow)
    sw = max(6, int(14 * z))
    shaft = pygame.Rect(int(top[0] - sw / 2), int(top[1]), sw, int(max(0, house.top - top[1]) + 2))
    pygame.draw.rect(fr, mix(STEEL, WHITE, 0.3), shaft)
    pygame.draw.rect(fr, BLACK, shaft, max(2, ow - 2))
    # striped pad
    pts = _rot(_box_local(w, h), x, y, ang, cam)
    pygame.draw.polygon(fr, (255, 206, 40), pts)
    x0, y0 = pts[0]
    x1, y1 = pts[2]
    k = 0
    xx = x0
    while xx < x1:
        if k % 2:
            pygame.draw.polygon(fr, BLACK, [(xx, y0), (min(x1, xx + 10 * z), y0), (min(x1, xx + 4 * z), y1),
                                            (max(x0, xx - 6 * z), y1)])
        xx += 10 * z
        k += 1
    pygame.draw.polygon(fr, BLACK, pts, ow)
    # steam puffs while low / blasting up
    lo, hi = sh["lo"], sh["hi"]
    s = (y - hi) / max(1.0, lo - hi)
    if s > 0.55:
        for kk in range(4):
            ph = (fi * 0.09 + kk * 0.25) % 1.0
            px = bot[0] + (-1 if kk % 2 else 1) * (hw * 0.6 + ph * 40 * z)
            py = house.top - ph * 50 * z
            rad = max(3, int((6 + 12 * ph) * z))
            pygame.draw.circle(fr, BLACK, (int(px), int(py)), rad + 2)
            pygame.draw.circle(fr, (236, 240, 246), (int(px), int(py)), rad)


# ================================================================================================ INFERNO ASCENT
def _lava_cols(th):
    return (getattr(th, "wall_outer", (195, 42, 16)), getattr(th, "wall_mid", (255, 96, 20)),
            getattr(th, "wall_core", (255, 232, 118)))


@under("inferno_ascent")
def _ia_under(r, cam, fi, zone, t_anim, play_t):
    fr = r.frame
    z = cam.zoom
    x0 = cam.to_screen(210, 0)[0]
    x1 = cam.to_screen(1110, 0)[0]
    shaft = mix(r.theme.castle, (40, 26, 30), 0.72)
    pygame.draw.rect(fr, shaft, (int(x0), 0, int(x1 - x0), H))
    # faint back bricks (scroll with the camera)
    dark = mix(shaft, BLACK, 0.3)
    bh = max(14, int(46 * z))
    off = int(cam.to_screen(0, 0)[1]) % bh
    for k, yy in enumerate(range(off - bh, H, bh)):
        pygame.draw.line(fr, dark, (x0, yy), (x1, yy), 2)
        xo = (bh if k % 2 else 0)
        for xx in range(int(x0) + xo, int(x1), bh * 2):
            pygame.draw.line(fr, dark, (xx, yy), (xx, yy + bh), 2)
    # heat glow bands above the lava
    ly = cam.to_screen(0, zone.get("lava_y", 300.0))[1]
    outer, mid, _ = _lava_cols(r.theme)
    for k in range(5):
        top = ly - (5 - k) * 70 * z
        if top > H:
            continue
        col = mix(shaft, outer, 0.10 + 0.09 * k)
        pygame.draw.rect(fr, col, (int(x0), int(top), int(x1 - x0), int(70 * z) + 1))


@static("ia_ledge")
def _ia_ledge(r, cam, s, zone, t_anim, play_t):
    if s["i"] not in (zone.get("ia_crumble") or ()):
        return
    z = cam.zoom
    a = cam.to_screen(s["x0"], s["y"])
    b = cam.to_screen(s["x1"], s["y"])
    if a[1] < -50 or a[1] > H + 50:
        return
    jx = math.sin(t_anim * 70) * 4 * z
    for k in range(5):
        u = (k + 0.5) / 5
        cx = a[0] + (b[0] - a[0]) * u + jx
        pts = [(cx, a[1] - 4 * z), (cx + 8 * z, a[1] + 10 * z), (cx - 5 * z, a[1] + 20 * z), (cx + 6 * z, a[1] + 34 * z)]
        pygame.draw.lines(r.frame, BLACK, False, pts, max(3, int(4 * z)))
    for k in range(4):
        px = a[0] + (b[0] - a[0]) * ((k * 0.27 + t_anim * 1.3) % 1.0)
        py = a[1] + 30 * z + ((t_anim * 160 + k * 37) % 60) * z
        pygame.draw.rect(r.frame, BLACK, (int(px), int(py), int(9 * z), int(9 * z)))


@static("ia_pad")
def _ia_pad(r, cam, s, zone, t_anim, play_t):
    if s["i"] in (zone.get("ia_gone") or ()):
        return
    z = cam.zoom
    fr = r.frame
    x0, y0 = cam.to_screen(s["x0"], s["y"])
    x1, _ = cam.to_screen(s["x1"], s["y"])
    if y0 < -60 or y0 > H + 60:
        return
    fired = s["i"] in (zone.get("ia_fired") or ())
    ow = _ow(z)
    ext = (26 if fired else 10) * z
    base = pygame.Rect(int(x0), int(y0 - 8 * z), int(x1 - x0), int(8 * z))
    pygame.draw.rect(fr, STEEL_D, base)
    pygame.draw.rect(fr, BLACK, base, max(2, ow - 1))
    # zig-zag coil
    cx = (x0 + x1) / 2
    hw = (x1 - x0) * 0.32
    n = 4
    ytop = y0 - 8 * z - ext
    pts = [(cx - hw if k % 2 else cx + hw, y0 - 8 * z - ext * k / n) for k in range(n + 1)]
    pygame.draw.lines(fr, BLACK, False, pts, max(4, int(7 * z)))
    pygame.draw.lines(fr, (210, 216, 230), False, pts, max(2, int(3 * z)))
    plate = pygame.Rect(int(x0 - 4 * z), int(ytop - 10 * z), int(x1 - x0 + 8 * z), int(10 * z))
    pygame.draw.rect(fr, r.theme.hazard if fired else (64, 220, 120), plate, border_radius=3)
    pygame.draw.rect(fr, BLACK, plate, max(2, ow - 1), border_radius=3)
    # chevron arrow pointing to the next ledge
    d = s["dir"]
    ay = ytop - 30 * z - 6 * z * abs(math.sin(t_anim * 5))
    ar = [(cx - 12 * z * d, ay + 10 * z), (cx + 14 * z * d, ay - 10 * z), (cx - 2 * z * d, ay + 12 * z)]
    pygame.draw.polygon(fr, WHITE, ar)
    pygame.draw.polygon(fr, BLACK, ar, 2)


@static("ia_updraft")
def _ia_updraft(r, cam, s, zone, t_anim, play_t):
    if s["i"] in (zone.get("ia_gone") or ()):
        return
    z = cam.zoom
    fr = r.frame
    x0, y0 = cam.to_screen(s["x0"], s["y0"])
    x1, y1 = cam.to_screen(s["x1"], s["y1"])
    if y1 < -40 or y0 > H + 40:
        return
    col = (150, 236, 255)
    edge = (90, 190, 235)
    pygame.draw.line(fr, edge, (x0, y0), (x0, y1), max(2, int(3 * z)))
    pygame.draw.line(fr, edge, (x1, y0), (x1, y1), max(2, int(3 * z)))
    hgt = max(1.0, y1 - y0)
    for k in range(7):
        u = ((k * 0.143) - t_anim * 0.9) % 1.0
        yy = y0 + hgt * u
        xx = x0 + (x1 - x0) * (0.15 + 0.7 * ((k * 0.37) % 1.0))
        L = 34 * z
        wob = math.sin(t_anim * 6 + k) * 6 * z
        pygame.draw.line(fr, col, (xx + wob, yy), (xx - wob, yy + L), max(2, int(4 * z)))
        pygame.draw.polygon(fr, col, [(xx + wob, yy - 8 * z), (xx + wob - 7 * z, yy + 3 * z),
                                      (xx + wob + 7 * z, yy + 3 * z)])
    # fan grate at the bottom
    fy = y1
    pygame.draw.rect(fr, BLACK, (int(x0), int(fy - 12 * z), int(x1 - x0), int(16 * z)))
    for k in range(6):
        a = t_anim * 14 + k
        xx = x0 + (x1 - x0) * (k + 0.5) / 6
        pygame.draw.line(fr, STEEL, (xx - math.cos(a) * 9 * z, fy - 4 * z), (xx + math.cos(a) * 9 * z, fy - 4 * z),
                         max(2, int(4 * z)))


@static("ia_crown")
def _ia_crown(r, cam, s, zone, t_anim, play_t):
    z = cam.zoom
    fr = r.frame
    a = cam.to_screen(s["x0"] + 30, s["y"])
    b = cam.to_screen(s["x1"] - 30, s["y"])
    if a[1] < -300 or a[1] > H + 40:
        return
    ow = _ow(z)
    ph = 150 * z
    for p in (a, b):
        post = pygame.Rect(int(p[0] - 6 * z), int(p[1] - ph), int(12 * z), int(ph))
        pygame.draw.rect(fr, WHITE, post)
        pygame.draw.rect(fr, BLACK, post, max(2, ow - 1))
    # checkered banner
    top = a[1] - ph
    bw = b[0] - a[0]
    cells = 10
    for k in range(cells):
        for row in range(2):
            col = BLACK if (k + row) % 2 else WHITE
            rect = pygame.Rect(int(a[0] + bw * k / cells), int(top + row * 16 * z), int(bw / cells) + 1, int(16 * z))
            pygame.draw.rect(fr, col, rect)
    pygame.draw.rect(fr, BLACK, (int(a[0]), int(top), int(bw), int(32 * z)), ow)
    # bobbing crown
    cx = (a[0] + b[0]) / 2
    cy = top - 34 * z - 6 * z * math.sin(t_anim * 3)
    cw = 46 * z
    pts = [(cx - cw, cy + 18 * z), (cx - cw, cy - 10 * z), (cx - cw * 0.5, cy + 4 * z), (cx, cy - 20 * z),
           (cx + cw * 0.5, cy + 4 * z), (cx + cw, cy - 10 * z), (cx + cw, cy + 18 * z)]
    pygame.draw.polygon(fr, (255, 206, 40), pts)
    pygame.draw.polygon(fr, BLACK, pts, ow)
    for px in (cx - cw * 0.5, cx, cx + cw * 0.5):
        pygame.draw.circle(fr, (235, 50, 75), (int(px), int(cy + 9 * z)), max(3, int(5 * z)))


@prop("ia_elevator")
def _ia_elevator(r, cam, st, i, x, y, ang, fi):
    z = cam.zoom
    fr = r.frame
    w, h = _box_wh(st)
    ow = _ow(z)
    pts = _rot(_box_local(w, h), x, y, ang, cam)
    # cables up out of frame
    for u in (0.2, 0.8):
        px = pts[0][0] + (pts[1][0] - pts[0][0]) * u
        pygame.draw.line(fr, BLACK, (px, pts[0][1]), (px, -10), max(3, int(5 * z)))
        pygame.draw.line(fr, STEEL, (px, pts[0][1]), (px, -10), max(1, int(2 * z)))
    pygame.draw.polygon(fr, STEEL, pts)
    x0, y0 = pts[0]
    x1, y1 = pts[2]
    k = 0
    xx = x0
    while xx < x1:
        if k % 2:
            pygame.draw.polygon(fr, (255, 206, 40), [(xx, y0), (min(x1, xx + 12 * z), y0),
                                                     (min(x1, xx + 4 * z), y1), (max(x0, xx - 8 * z), y1)])
        xx += 12 * z
        k += 1
    pygame.draw.polygon(fr, BLACK, pts, ow)
    # bracket + warning lamp
    mx = (x0 + x1) / 2
    lamp_on = (fi // 8) % 2 == 0
    pygame.draw.circle(fr, BLACK, (int(mx), int(y1 + 8 * z)), max(5, int(9 * z)))
    pygame.draw.circle(fr, (255, 80, 60) if lamp_on else (130, 40, 30), (int(mx), int(y1 + 8 * z)), max(3, int(6 * z)))


@over("inferno_ascent")
def _ia_over(r, cam, fi, zone, t_anim, play_t):
    fr = r.frame
    z = cam.zoom
    ly = cam.to_screen(0, zone.get("lava_y", 300.0))[1]
    if ly > H + 20:
        return
    outer, mid, core = _lava_cols(r.theme)
    # heat shimmer: wavy pale lines rising above the surface
    for k in range(3):
        yy = ly - (40 + 45 * k) * z - ((t_anim * 40) % 45) * z
        if yy > H or yy < -20:
            continue
        pts = [(x, yy + 4 * z * math.sin(t_anim * 7 + x * 0.03 + k)) for x in range(0, W + 30, 30)]
        pygame.draw.lines(fr, mix(core, WHITE, 0.4), False, pts, max(1, int(2 * z)))
    y = max(-10, ly)
    pygame.draw.rect(fr, outer, (0, int(y + 14 * z), W, int(H - y)))
    wave = [(x, ly + 8 * z * math.sin(t_anim * 4.0 + x * 0.02)) for x in range(0, W + 24, 24)]
    pygame.draw.polygon(fr, mid, wave + [(W, H + 10), (0, H + 10)])
    deep = [(x, ly + 40 * z + 6 * z * math.sin(t_anim * 3.1 + x * 0.015 + 1.7)) for x in range(0, W + 24, 24)]
    pygame.draw.polygon(fr, outer, deep + [(W, H + 10), (0, H + 10)])
    pygame.draw.lines(fr, BLACK, False, wave, max(3, int(6 * z)))
    pygame.draw.lines(fr, core, False, [(x, yy - 2) for x, yy in wave], max(2, int(4 * z)))
    # bubbles that swell and pop
    for k in range(9):
        cyc = (t_anim * 0.8 + k * 0.37) % 1.0
        bx = (k * 131 + 47) % W
        by = ly + (16 + (k % 3) * 22) * z - cyc * 18 * z
        rad = max(3, int((5 + 12 * cyc) * z))
        if cyc < 0.85:
            pygame.draw.circle(fr, BLACK, (int(bx), int(by)), rad + 2)
            pygame.draw.circle(fr, core, (int(bx), int(by)), rad)
            pygame.draw.circle(fr, WHITE, (int(bx - rad * 0.3), int(by - rad * 0.3)), max(1, rad // 3))
        else:
            for a in range(4):
                aa = a * 1.57 + 0.6
                pygame.draw.line(fr, core, (bx + math.cos(aa) * rad, by + math.sin(aa) * rad),
                                 (bx + math.cos(aa) * rad * 1.9, by + math.sin(aa) * rad * 1.9), max(2, int(3 * z)))
