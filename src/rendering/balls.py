"""v3.2 ball renderer: every contestant is a physical ball whose surface art rotates with the TRUE body angle, a
spring-stabilised face (dizzy spirals and free spin above 9 rad/s), goofy Crash Dummy faces, and retractable event-only
arms (flail / splat / victory). Zero legs anywhere. Drawn directly at screen scale (crisp at any zoom).
"""
from __future__ import annotations

import math

import pygame

from src.characters.roster import Extra, Hero

BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
OUTLINE = 4
GLITCH_CYAN = (0, 245, 255)
GLITCH_CRIMSON = (255, 35, 65)


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def shade(c, k: float):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _rot(cx: float, cy: float, d: float, a: float) -> tuple[float, float]:
    return cx + math.cos(a) * d, cy + math.sin(a) * d


def _poly_pts(cx, cy, shape: str, w: float, h: float, th: float) -> list[tuple[float, float]] | None:
    """Silhouette polygon in screen space (y-down), rotated by the body angle th (radians)."""
    if shape == "oval":
        pts = [(math.cos(a) * w, math.sin(a) * h) for a in [i * math.pi / 14 for i in range(28)]]
    elif shape == "hexagon":
        pts = []
        for i in range(6):                       # chamfered hexagon
            a0, a1 = 2 * math.pi * i / 6, 2 * math.pi * (i + 1) / 6
            for k in (0.12, 0.88):
                x0, y0 = math.cos(a0) * w, math.sin(a0) * w
                x1, y1 = math.cos(a1) * w, math.sin(a1) * w
                pts.append((x0 + (x1 - x0) * k, y0 + (y1 - y0) * k))
    elif shape == "square":
        c = w * 0.32                              # heavy chamfer so the cube reads as tumbling iron
        pts = [(-w + c, -w), (w - c, -w), (w, -w + c), (w, w - c), (w - c, w), (-w + c, w), (-w, w - c), (-w, -w + c)]
    else:
        return None
    ca, sa = math.cos(th), math.sin(th)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def _silhouette(surf, cx, cy, shape, w, h, th, col, grow: float = 0.0) -> None:
    if shape in ("circle", "cloud"):
        pygame.draw.circle(surf, col, (cx, cy), w + grow)
    else:
        pts = _poly_pts(cx, cy, shape, w + grow, h + grow, th)
        pygame.draw.polygon(surf, col, pts)


# ------------------------------------------------------------------------------------------------ surface art
def _pattern(s: pygame.Surface, key: str, cx: float, cy: float, r: float, th: float, t: float, phase: str = "") -> None:
    """Surface geometry that rotates with the body so rolling speed and spin direction read instantly."""
    if key == "bonk":                                            # bowling ball: 3 finger holes
        for k, off in enumerate((-0.42, 0.0, 0.42)):
            d = r * (0.42 if k != 1 else 0.58)
            p = _rot(cx, cy, d, th + off)
            pygame.draw.circle(s, (70, 30, 0), p, r * 0.12)
            pygame.draw.circle(s, (40, 15, 0), p, r * 0.12, 2)
    elif key == "pip":                                           # ping-pong seam
        a, b = _rot(cx, cy, r, th), _rot(cx, cy, r, th + math.pi)
        pygame.draw.line(s, WHITE, a, b, max(2, int(r * 0.16)))
        pygame.draw.circle(s, (255, 150, 0), _rot(cx, cy, r * 0.5, th + math.pi / 2), r * 0.13)
    elif key == "boing":                                         # rubber swirl bands
        for k in range(3):
            pts = [_rot(cx, cy, r * (0.15 + 0.8 * u / 10), th + k * 2 * math.pi / 3 + u * 0.32) for u in range(11)]
            pygame.draw.lines(s, (255, 170, 215), False, pts, max(2, int(r * 0.14)))
    elif key == "sly":                                           # billiard: white racing stripe + number disc
        hw = r * 0.34
        ca, sa = math.cos(th), math.sin(th)
        band = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in ((-r * 1.2, -hw), (r * 1.2, -hw), (r * 1.2, hw), (-r * 1.2, hw))]
        pygame.draw.polygon(s, (250, 250, 245), band)
        p = _rot(cx, cy, r * 0.55, th)
        pygame.draw.circle(s, WHITE, p, r * 0.24)
        pygame.draw.circle(s, BLACK, p, r * 0.24, 2)
    elif key == "grumble":                                       # velcro grip nubs
        for k in range(12):
            pygame.draw.circle(s, (20, 70, 120), _rot(cx, cy, r * 0.84, th + k * math.pi / 6), r * 0.11)
        for k in range(6):
            pygame.draw.circle(s, (60, 140, 200), _rot(cx, cy, r * 0.55, th + k * math.pi / 3 + 0.3), r * 0.06)
    elif key == "dash":                                          # ice-puck crystal facets
        for off in (-0.5, 0.0, 0.5):
            a, b = _rot(cx, cy, r * 0.9, th + off + 0.3), _rot(cx, cy, r * 0.9, th + off + math.pi - 0.3)
            pygame.draw.line(s, (215, 255, 255), a, b, 2)
        pygame.draw.ellipse(s, (180, 250, 255), (cx - r * 0.75, cy - r * 0.42, r * 1.5, r * 0.84), 2)
    elif key == "magneto":                                       # hex plates + bolts + spark glint
        inner = _poly_pts(cx, cy, "hexagon", r * 0.62, r * 0.62, th)
        pygame.draw.polygon(s, (120, 70, 150), inner)
        pygame.draw.polygon(s, (70, 30, 100), inner, 3)
        for i in range(6):
            pygame.draw.circle(s, (220, 220, 235), _rot(cx, cy, r * 0.82, th + i * math.pi / 3 + math.pi / 6), r * 0.07)
        if int(t * 6) % 5 == 0:
            p = _rot(cx, cy, r * 0.7, th + 1.0)
            pygame.draw.line(s, (120, 255, 255), (p[0] - 5, p[1]), (p[0] + 5, p[1]), 2)
            pygame.draw.line(s, (120, 255, 255), (p[0], p[1] - 5), (p[0], p[1] + 5), 2)
    elif key == "floater":                                       # 6-panel beach ball
        cols = ((255, 255, 255), (255, 120, 140), (255, 255, 255), (90, 200, 255), (255, 255, 255), (255, 220, 70))
        for k in range(6):
            a0 = th + k * math.pi / 3
            pts = [(cx, cy)] + [_rot(cx, cy, r * 1.2, a0 + u * (math.pi / 3) / 6) for u in range(7)]
            pygame.draw.polygon(s, cols[k], pts)
        pygame.draw.circle(s, (240, 240, 240), (cx, cy), r * 0.16)
    elif key == "juggernaut":                                    # rivets + hazard corner stripes
        for i in range(4):
            a = th + math.pi / 4 + i * math.pi / 2
            corner = _rot(cx, cy, r * 1.05, a)
            if i % 2 == 0:
                for j in range(3):
                    p0 = _rot(corner[0], corner[1], r * (0.18 + j * 0.16), a + math.pi + 0.8)
                    p1 = _rot(corner[0], corner[1], r * (0.18 + j * 0.16), a + math.pi - 0.8)
                    pygame.draw.line(s, (255, 205, 0) if j % 2 == 0 else BLACK, p0, p1, max(3, int(r * 0.12)))
            pygame.draw.circle(s, (150, 160, 170), _rot(cx, cy, r * 0.62, a), r * 0.08)
            pygame.draw.circle(s, BLACK, _rot(cx, cy, r * 0.62, a), r * 0.08, 1)
    elif key == "glitch":                                        # CRT scanlines: Cyan (FEATHER) vs Crimson (LEAD)
        neon = GLITCH_CRIMSON if phase == "LEAD" else GLITCH_CYAN
        for k in range(-3, 4):
            a, b = _rot(cx, cy, r, th + k * 0.18 - math.pi / 2), _rot(cx, cy, r, th - k * 0.18 + math.pi / 2)
            pygame.draw.line(s, shade(neon, 0.50), a, b, max(1, int(r * 0.07)))
    elif key == "dummy":                                         # yellow/grey 4-quadrant crash-test shell
        for k in (0, 2):
            a0 = th + k * math.pi / 2
            pts = [(cx, cy)] + [_rot(cx, cy, r * 1.2, a0 + u * (math.pi / 2) / 6) for u in range(7)]
            pygame.draw.polygon(s, (255, 205, 20), pts)
        # Outer rim quadrant ticks (keeps center open so goofy cartoon faces read with high contrast)
        lw = max(2, int(r * 0.09))
        for k in range(4):
            ang = th + k * math.pi / 2
            pygame.draw.line(s, BLACK, _rot(cx, cy, r * 0.56, ang), _rot(cx, cy, r * 1.02, ang), lw)


# ------------------------------------------------------------------------------------------------ face
STYLE_MOUTH = {"smug": "smirk", "nervous": "wobble", "grinning": "grin", "smirking": "smirk", "scowling": "frown",
               "focused": "flat", "visor": "flat", "chill": "smile", "furrowed": "frown", "dizzy": "zig", "dot": "dot"}


def _spiral(s, c, rr, t, col=BLACK):
    pts = [_rot(c[0], c[1], rr * u / 14, t * 9 + u * 0.9) for u in range(15)]
    pygame.draw.lines(s, col, False, pts, 2)


def _star(s, c, rr, col=(255, 210, 0)):
    pts = [_rot(c[0], c[1], rr if i % 2 == 0 else rr * 0.45, -math.pi / 2 + i * math.pi / 5) for i in range(10)]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, BLACK, pts, 1)


def draw_face(s, cx, cy, r, fa: float, expression: str, style: str, look=(0.0, 0.0), t: float = 0.0,
              force_grin: bool = False, dummy: bool = False, falling: bool = False) -> None:
    """Face in its own frame rotated by fa (radians). Readable at every size."""
    def P(x, y):
        return cx + x * math.cos(fa) - y * math.sin(fa), cy + x * math.sin(fa) + y * math.cos(fa)

    ex, ey, er = r * 0.34, -r * 0.12, r * 0.24
    lw = max(2, int(r * 0.09))
    if dummy:
        # v3.2 Crash Dummy goofy faces: FALLING (O_O scream) | HIT (X_X + tongue) | NORMAL (googly + tiny "o")
        my = r * 0.34
        if falling or expression == "scared":
            for sx in (-1, 1):
                c = P(sx * r * 0.36, -r * 0.14)
                rr = er * 1.38
                pygame.draw.circle(s, BLACK, c, rr + 2)
                pygame.draw.circle(s, WHITE, c, rr)
                pygame.draw.circle(s, BLACK, c, max(2, int(rr * 0.24)))
            mc = P(0, my + r * 0.04)
            scream = pygame.Rect(mc[0] - r * 0.22, mc[1] - r * 0.26, r * 0.44, r * 0.52)
            pygame.draw.ellipse(s, BLACK, scream.inflate(4, 4))
            pygame.draw.ellipse(s, (95, 16, 32), scream)
            pygame.draw.ellipse(s, (245, 92, 115), (mc[0] - r * 0.13, mc[1] + r * 0.04, r * 0.26, r * 0.18))
        elif expression in ("dizzy", "eliminated"):
            for sx in (-1, 1):
                c = P(sx * ex, ey)
                rr = er * 1.08
                pygame.draw.circle(s, WHITE, c, rr)
                pygame.draw.circle(s, BLACK, c, rr, max(1, lw - 1))
                k = rr * 0.62
                pygame.draw.line(s, BLACK, (c[0] - k, c[1] - k), (c[0] + k, c[1] + k), lw + 1)
                pygame.draw.line(s, BLACK, (c[0] - k, c[1] + k), (c[0] + k, c[1] - k), lw + 1)
            # Dazed mouth + pink tongue sticking out
            pygame.draw.line(s, BLACK, P(-r * 0.28, my), P(r * 0.28, my), lw + 1)
            tc = P(r * 0.08, my + r * 0.16)
            pygame.draw.circle(s, BLACK, tc, r * 0.15 + 2)
            pygame.draw.circle(s, (250, 90, 118), tc, r * 0.15)
            pygame.draw.line(s, BLACK, P(r * 0.08, my + r * 0.03), P(r * 0.08, my + r * 0.22), max(1, lw - 1))
        else:
            # Vacant wide googly eyes + tiny clueless "o" mouth
            for idx, sx in enumerate((-1, 1)):
                c = P(sx * r * 0.35, ey)
                rr = er * (1.24 if idx == 0 else 1.08)
                pygame.draw.circle(s, BLACK, c, rr + 2)
                pygame.draw.circle(s, WHITE, c, rr)
                # Derpy wall-eyed off-kilter pupils
                wob = math.sin(t * 4.5 + idx * 2.3) * rr * 0.14
                px = c[0] + sx * rr * 0.34 + wob
                py = c[1] + (-rr * 0.18 if idx == 0 else rr * 0.22)
                pygame.draw.circle(s, BLACK, (px, py), max(2, int(rr * 0.42)))
            mc = P(0, my + r * 0.02)
            pygame.draw.circle(s, BLACK, mc, max(3, int(r * 0.13)) + 2)
            pygame.draw.circle(s, (80, 20, 30), mc, max(2, int(r * 0.11)))
        return

    if style == "visor" and expression in ("neutral", "angry"):    # Magneto's visor
        a, b = P(-r * 0.62, ey), P(r * 0.62, ey)
        pygame.draw.line(s, BLACK, a, b, int(r * 0.42) + 4)
        pygame.draw.line(s, (90, 255, 240), a, b, int(r * 0.34))
    else:
        for sx in (-1, 1):
            c = P(sx * ex, ey)
            if expression == "eliminated":
                k = er * 0.8
                pygame.draw.line(s, BLACK, (c[0] - k, c[1] - k), (c[0] + k, c[1] + k), lw + 1)
                pygame.draw.line(s, BLACK, (c[0] - k, c[1] + k), (c[0] + k, c[1] - k), lw + 1)
            elif expression == "dizzy":
                pygame.draw.circle(s, WHITE, c, er)
                _spiral(s, c, er, t + sx)
            elif expression in ("celebrating",) or force_grin:
                _star(s, c, er * 1.15)
            elif expression == "happy":
                pygame.draw.arc(s, BLACK, (c[0] - er, c[1] - er * 0.4, er * 2, er * 1.6), 0.3, math.pi - 0.3, lw)
            else:
                big = 1.25 if expression == "scared" else 1.0
                pygame.draw.circle(s, WHITE, c, er * big)
                pygame.draw.circle(s, BLACK, c, er * big, 2)
                pr = er * (0.32 if expression == "scared" else 0.5)
                pygame.draw.circle(s, BLACK, (c[0] + look[0] * er * 0.4, c[1] + look[1] * er * 0.4), pr)
                if style == "smug" and expression == "neutral":     # heavy lids
                    pygame.draw.rect(s, shade((255, 122, 0), 0.8), (c[0] - er - 1, c[1] - er - 1, er * 2 + 2, er * 1.0))
            if expression == "angry" or (style in ("scowling", "furrowed") and expression == "neutral"):
                a, b = P(sx * (ex + er), ey - er * 1.5), P(sx * (ex - er * 0.6), ey - er * 0.9)
                pygame.draw.line(s, BLACK, a, b, lw + 1)
    # mouth
    my = r * 0.38
    mouth = "grin" if force_grin or expression in ("celebrating", "happy") else STYLE_MOUTH.get(style, "smile")
    if expression == "scared":
        mouth = "o"
    if expression == "eliminated":
        mouth = "tongue"
    if expression == "angry":
        mouth = "frown"
    if mouth == "grin":
        pts = [P(-r * 0.36, my - r * 0.08), P(r * 0.36, my - r * 0.08), P(0, my + r * 0.26)]
        pygame.draw.polygon(s, (120, 20, 40), pts)
        pygame.draw.polygon(s, BLACK, pts, 2)
        pygame.draw.polygon(s, WHITE, [P(-r * 0.3, my - r * 0.07), P(r * 0.3, my - r * 0.07), P(0, my + r * 0.02)])
    elif mouth == "o":
        pygame.draw.circle(s, BLACK, P(0, my), r * 0.14)
    elif mouth == "tongue":
        pygame.draw.line(s, BLACK, P(-r * 0.25, my), P(r * 0.25, my), lw)
        pygame.draw.circle(s, (240, 90, 110), P(r * 0.08, my + r * 0.1), r * 0.1)
    elif mouth == "frown":
        pygame.draw.lines(s, BLACK, False, [P(-r * 0.24, my + r * 0.08), P(0, my - r * 0.02), P(r * 0.24, my + r * 0.08)], lw)
    elif mouth == "smirk":
        pygame.draw.lines(s, BLACK, False, [P(-r * 0.22, my), P(r * 0.1, my + r * 0.04), P(r * 0.26, my - r * 0.08)], lw)
    elif mouth == "wobble":
        pygame.draw.lines(s, BLACK, False, [P(-r * 0.24 + i * r * 0.12, my + (r * 0.04 if i % 2 else -r * 0.03)) for i in range(5)], lw)
    elif mouth == "zig":
        pygame.draw.lines(s, BLACK, False, [P(-r * 0.24 + i * r * 0.12, my + (r * 0.06 if i % 2 else -r * 0.06)) for i in range(5)], lw)
    elif mouth == "flat":
        pygame.draw.line(s, BLACK, P(-r * 0.2, my), P(r * 0.2, my), lw)
    else:
        pygame.draw.lines(s, BLACK, False, [P(-r * 0.24, my - r * 0.04), P(0, my + r * 0.08), P(r * 0.24, my - r * 0.04)], lw)
    if style == "nervous" and expression not in ("eliminated", "celebrating"):
        pygame.draw.circle(s, (120, 200, 255), P(r * 0.75, -r * 0.45 + (t * 40) % (r * 0.3)), r * 0.1)


# ------------------------------------------------------------------------------------------------ limbs
def _limb(s, a, b, w):
    pygame.draw.line(s, BLACK, a, b, w)
    pygame.draw.circle(s, BLACK, b, w * 0.75)


def draw_limbs(s, cx, cy, r, fa, pose: str, vel, angvel: float, t: float, zoom: float, hit_dir=None) -> None:
    """v3.1+: ZERO legs anywhere. Retractable event-only arms: ONLY on flail (falling/launched), splat (heavy impact),
    and victory (winner card). Normal rolling/bouncing draws NO arms at all."""
    if pose not in ("flail", "splat", "victory"):
        return
    w = max(2, int(5 * zoom))
    vx, vy = vel
    sp = math.hypot(vx, vy)
    L = r * 0.80
    sh = [(-r * 0.94, 0.02 * r), (r * 0.94, 0.02 * r)]

    def P(x, y):
        return cx + x * math.cos(fa) - y * math.sin(fa), cy + x * math.sin(fa) + y * math.cos(fa)

    if pose == "flail":                                    # \o/ arms shoot up waving frantically overhead
        f = 14 + abs(vy) / 60 + abs(angvel) * 0.8
        for k, (x, y) in enumerate(sh):
            base = P(x, y)
            side = -1 if k == 0 else 1
            wave = math.sin(t * f + k * 2.1) * 0.45
            ang = fa - math.pi / 2 + side * 0.55 + wave
            _limb(s, base, _rot(base[0], base[1], L * 1.15, ang), w)
    elif pose == "splat":                                    # splayed flat for 0.22 s right after heavy hit/betrayal
        hd = hit_dir if hit_dir is not None else (math.atan2(vy, vx) if sp > 1 else 0.0)
        for k in (0, 1):
            ang = hd + math.pi / 2 + (math.pi if k else 0.0)
            base = _rot(cx, cy, r * 0.85, ang)
            _limb(s, base, _rot(base[0], base[1], L * 1.05, ang), w)
    elif pose == "victory":                                  # celebratory waving arms on the winner card
        hop = abs(math.sin(t * 7)) * r * 0.20
        for k, (x, y) in enumerate(sh):
            base = P(x, y - hop / max(1, r) * r)
            wave = math.sin(t * 12 + k * 1.5) * 0.45
            ang = fa - math.pi / 2 + (-0.6 if k == 0 else 0.6) + wave
            _limb(s, base, _rot(base[0], base[1], L * 1.2, ang), w)


# ------------------------------------------------------------------------------------------------ the ball
def pose_for(falling: bool, vy: float, over_drop: bool, heavy_impact: bool, winner_card: bool) -> str:
    """Strict event-only arm states (v3.1+): none during normal rolling/sliding/bouncing."""
    if winner_card:
        return "victory"
    if falling or (over_drop and vy > 420):
        return "flail"
    if heavy_impact:
        return "splat"
    return "none"


def draw_ball(frame: pygame.Surface, hero: Hero | None, extra: Extra | None, pos, angle_deg: float, face_deg: float,
              vel, angvel: float, expression: str, pose: str, t: float, zoom: float, squash: float = 0.0,
              scale: float = 1.0, alpha: int = 255, force_grin: bool = False, phase: str = "", look=(0.0, 0.0),
              tint: tuple[int, int, int] | None = None) -> None:
    key = hero.key if hero else "dummy"
    shape = hero.shape if hero else "circle"
    if hero:
        w0, h0 = hero.size
    else:
        w0 = h0 = extra.radius if extra else 20
    k = zoom * scale
    w, h = w0 * k, h0 * k
    r = max(w, h)
    rr = r if shape != "square" else w * 1.15
    size = int(rr * 2 + 32)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size / 2
    th = math.radians(angle_deg)
    fa = math.radians(face_deg)
    if tint is not None:
        # Pure flat chromatic silhouette ghost (used for Glitch RGB split & Dash ice afterimages)
        _silhouette(s, cx, cy, shape, w, h, th, (*tint, alpha))
        frame.blit(s, s.get_rect(center=(int(pos[0]), int(pos[1]))))
        return

    base = rgb(hero.colour) if hero else (216, 220, 226)
    if hero and hero.key == "glitch":
        base = (17, 17, 22)
        neon = GLITCH_CRIMSON if phase == "LEAD" else GLITCH_CYAN
        # Outer neon aura ring toggling Cyan (Featherweight) <-> Crimson Red (Lead Heavy)
        pygame.draw.circle(s, (*neon, 85), (cx, cy), w * 1.24)
    # outline + fill
    _silhouette(s, cx, cy, shape, w, h, th, BLACK, grow=OUTLINE * max(0.6, min(1.3, zoom)))
    _silhouette(s, cx, cy, shape, w, h, th, base)
    # rotating surface art, clipped to the silhouette
    pat = pygame.Surface((size, size), pygame.SRCALPHA)
    _pattern(pat, key, cx, cy, min(w, h) if shape == "oval" else w, th, t, phase)
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    _silhouette(mask, cx, cy, shape, w - 1, h - 1, th, (255, 255, 255, 255))
    pat.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(pat, (0, 0))
    if hero and hero.key == "glitch":
        neon = GLITCH_CRIMSON if phase == "LEAD" else GLITCH_CYAN
        pts = [_rot(cx, cy, w * (1.0 if i % 2 else 1.18), th + i * math.pi / 9) for i in range(18)]
        pygame.draw.polygon(s, neon, pts, max(2, int(3.5 * zoom)))
    # lighting: static specular highlight (upper-left) and soft lower shade
    hl = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.ellipse(hl, (255, 255, 255, 120 if key != "dummy" else 90), (cx - r * 0.72, cy - r * 0.78, r * 0.62, r * 0.36))
    pygame.draw.circle(hl, (0, 0, 0, 38), (cx + r * 0.25, cy + r * 0.3), r * 0.8)
    hl.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(hl, (0, 0))
    draw_face(s, cx, cy, min(w, h) * (1.0 if shape != "oval" else 1.15), fa, expression,
              hero.face if hero else "dot", look, t, force_grin, dummy=hero is None, falling=(pose == "flail"))
    # squash & stretch along the velocity / impact axis
    vx, vy = vel
    sp = math.hypot(vx, vy)
    if key == "dash":
        # v3.2: sleek rigid ice puck — zero vertical jellybean bloat
        along = 1.0 + 0.05 * squash
        across = 1.0 - 0.04 * squash
    elif key == "boing":
        # v3.2: exaggerated rubber superball squash-stretch
        along = 1.0 + 0.48 * squash if squash > 0 else 1.0 + 0.24 * min(1.0, max(0.0, (sp - 220) / 480))
        across = 1.0 - 0.36 * squash if squash > 0 else 1.0 - 0.18 * min(1.0, max(0.0, (sp - 220) / 480))
    else:
        along = 1.0 + 0.30 * squash if squash > 0 else 1.0 + 0.12 * min(1.0, max(0.0, (sp - 300) / 600))
        across = 1.0 - 0.28 * squash if squash > 0 else 1.0 - 0.10 * min(1.0, max(0.0, (sp - 300) / 600))
    if abs(along - 1) > 0.02 and key != "dash":
        vdeg = math.degrees(math.atan2(vy, vx)) if sp > 1 else 0.0
        s = pygame.transform.rotate(s, vdeg)
        s = pygame.transform.smoothscale(s, (max(1, int(s.get_width() * across if squash > 0 else s.get_width() * along)),
                                             max(1, int(s.get_height() * along if squash > 0 else s.get_height() * across))))
        s = pygame.transform.rotate(s, -vdeg)
    if alpha < 255:
        s.set_alpha(alpha)
    # limbs behind the body
    if pose != "none":
        draw_limbs(frame, pos[0], pos[1], rr * 0.96, fa, pose, vel, angvel, t, zoom * scale)
    frame.blit(s, s.get_rect(center=(int(pos[0]), int(pos[1]))))


def body_radius(hero: Hero | None, extra: Extra | None) -> float:
    if hero:
        return hero.radius
    return extra.radius if extra else 20
