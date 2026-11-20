"""Character renderer (§5.3, §9.1): bodies, faces, squash & stretch, stick limbs, name pills, extras.

Bodies are drawn upright on a small local surface (cached per hero/expression/frame bucket), then stretched along the
velocity axis and rotated. Limbs are visual only and drawn directly on the frame.
"""
from __future__ import annotations

import math
from functools import lru_cache

import pygame

from src.characters.expressions import BLACK, WHITE, draw_face
from src.characters.roster import Extra, Hero
from src.config import font_path

OUTLINE = 4
LIMB_W = 5


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _shade(c: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * k))) for v in c)  # type: ignore[return-value]


def _poly(n: int, r: float, cx: float, cy: float, rot: float = 0.0) -> list[tuple[float, float]]:
    return [(cx + math.cos(rot + 2 * math.pi * i / n) * r, cy + math.sin(rot + 2 * math.pi * i / n) * r) for i in range(n)]


def _cloud(r: float, cx: float, cy: float) -> list[tuple[float, float, float]]:
    """Bumpy silhouette as overlapping circles: (x, y, radius)."""
    bumps = [(cx, cy, r * 0.78)]
    for i in range(7):
        a = 2 * math.pi * i / 7 - math.pi / 2
        bumps.append((cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55, r * 0.45))
    return bumps


def _shape(surf: pygame.Surface, hero: Hero, cx: float, cy: float, colour, width: int = 0, grow: float = 0.0) -> None:
    w, h = hero.size
    if hero.shape == "circle":
        pygame.draw.circle(surf, colour, (cx, cy), w + grow, width)
    elif hero.shape == "oval":
        pygame.draw.ellipse(surf, colour, pygame.Rect(cx - w - grow, cy - h - grow, 2 * (w + grow), 2 * (h + grow)), width)
    elif hero.shape == "square":
        r = pygame.Rect(cx - w / 2 - grow, cy - h / 2 - grow, w + 2 * grow, h + 2 * grow)
        pygame.draw.rect(surf, colour, r, width, border_radius=int(8 + grow))
    elif hero.shape in ("hexagon", "octagon"):
        n = 6 if hero.shape == "hexagon" else 8
        pts = _poly(n, w + grow, cx, cy, math.pi / n)
        pygame.draw.polygon(surf, colour, pts, width)
    elif hero.shape == "cloud":
        for bx, by, br in _cloud(w, cx, cy):
            pygame.draw.circle(surf, colour, (bx, by), br + grow, width)


def body_half_extents(hero: Hero) -> tuple[float, float]:
    w, h = hero.size
    if hero.shape == "oval":
        return w, h
    if hero.shape == "square":
        return w / 2, h / 2
    return w, w


@lru_cache(maxsize=2048)
def body_surface(hero: Hero, expression: str, face_bucket: int, look: tuple[float, float] = (0.0, 0.0)) -> pygame.Surface:
    """Upright body + outline + highlight rim + face. face_bucket animates spiral/glitch faces (~10 buckets/s)."""
    hx, hy = body_half_extents(hero)
    pad = OUTLINE + 8
    size = (int(2 * (hx + pad)), int(2 * (hy + pad)))
    s = pygame.Surface(size, pygame.SRCALPHA)
    cx, cy = size[0] / 2, size[1] / 2
    base = hex_rgb(hero.colour)
    _shape(s, hero, cx, cy, BLACK, 0, grow=OUTLINE)            # outline (drawn as a grown silhouette)
    _shape(s, hero, cx, cy, base, 0)                           # fill
    if hero.key == "glitch":                                   # neon static stripes
        t = face_bucket
        for i in (-3, 2, 3):
            col = (150, 230, 40) if (i + t) % 2 else (220, 40, 200)
            y = cy + i * hy * 0.27 + ((t * 7 + i * 13) % 5 - 2)
            pygame.draw.line(s, col, (cx - hx * 0.75, y), (cx + hx * 0.75, y), 2)
        _shape(s, hero, cx, cy, BLACK, OUTLINE, grow=OUTLINE / 2)
    # white inner highlight rim on the upper-left
    rim = pygame.Surface(size, pygame.SRCALPHA)
    _shape(rim, hero, cx, cy, (255, 255, 255, 215), 4, grow=-4)
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (cx - hx * 0.55, cy - hy * 0.55), max(hx, hy) * 0.95)
    rim.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(rim, (0, 0))
    lid = _shade(base, 0.85) if hero.key != "floater" else (225, 228, 232)
    draw_face(s, cx, cy - hy * 0.05, min(hx, hy) * (0.95 if hero.shape != "oval" else 1.05), expression, hero.face,
              lid, look, face_bucket / 10)
    return s


@lru_cache(maxsize=256)
def extra_surface(colour: str, radius: float, expression: str) -> pygame.Surface:
    """Bot extras: grey round robot with an antenna, outline, highlight and simple eyes (hero-sized, no name)."""
    r = radius
    pad = 8
    size = (int(2 * (r + pad)), int(2 * (r + pad) + r * 0.7))
    s = pygame.Surface(size, pygame.SRCALPHA)
    cx, cy = size[0] / 2, size[1] - r - pad
    base = hex_rgb(colour)
    top = (cx, cy - r - r * 0.55)                                   # antenna
    pygame.draw.line(s, BLACK, (cx, cy - r + 2), top, 4)
    pygame.draw.circle(s, BLACK, top, r * 0.2 + 2)
    pygame.draw.circle(s, (120, 220, 255) if expression != "eliminated" else (150, 150, 160), top, r * 0.2)
    pygame.draw.circle(s, BLACK, (cx, cy), r + OUTLINE)
    pygame.draw.circle(s, base, (cx, cy), r)
    pygame.draw.circle(s, _shade(base, 0.86), (cx + r * 0.18, cy + r * 0.2), r * 0.78)
    pygame.draw.circle(s, base, (cx - r * 0.06, cy - r * 0.04), r * 0.8)
    pygame.draw.arc(s, (255, 255, 255), (cx - r * 0.8, cy - r * 0.8, r * 1.6, r * 1.6), 1.7, 2.9, 4)
    ey = cy - r * 0.08
    if expression == "eliminated":
        for dx in (-r * 0.34, r * 0.34):
            k = r * 0.16
            pygame.draw.line(s, BLACK, (cx + dx - k, ey - k), (cx + dx + k, ey + k), 3)
            pygame.draw.line(s, BLACK, (cx + dx - k, ey + k), (cx + dx + k, ey - k), 3)
    elif expression == "scared":
        for dx in (-r * 0.34, r * 0.34):
            pygame.draw.circle(s, WHITE, (cx + dx, ey), r * 0.2)
            pygame.draw.circle(s, BLACK, (cx + dx, ey), r * 0.2, 2)
            pygame.draw.circle(s, BLACK, (cx + dx, ey), r * 0.08)
        pygame.draw.ellipse(s, BLACK, (cx - r * 0.12, cy + r * 0.3, r * 0.24, r * 0.26))
    else:
        for dx in (-r * 0.34, r * 0.34):
            pygame.draw.ellipse(s, BLACK, (cx + dx - r * 0.09, ey - r * 0.16, r * 0.18, r * 0.3))
        pygame.draw.line(s, _shade(base, 0.5), (cx - r * 0.2, cy + r * 0.42), (cx + r * 0.2, cy + r * 0.42), 3)
    return s


def stretch_factors(vx: float, vy: float, squash: float = 0.0) -> tuple[float, float, float]:
    """(along, across, angle_deg). Stretch up to 1.15x along velocity at speed; squash (0..1) → 1.30 wide / 0.72 tall."""
    speed = math.hypot(vx, vy)
    if squash > 0:
        return 1 + 0.30 * squash, 1 - 0.28 * squash, 0.0
    k = min(1.0, max(0.0, (speed - 250) / 450))
    return 1 + 0.15 * k, 1 - 0.13 * k, math.degrees(math.atan2(vy, vx)) if speed > 1 else 0.0


def blit_body(frame: pygame.Surface, src: pygame.Surface, pos: tuple[float, float], angle_deg: float,
              along: float, across: float, vel_deg: float, zoom: float = 1.0) -> pygame.Rect:
    s = src
    if abs(along - 1) > 0.01 or abs(across - 1) > 0.01:
        s = pygame.transform.rotate(s, vel_deg)                       # velocity axis -> +x
        s = pygame.transform.smoothscale(s, (max(1, int(s.get_width() * along)), max(1, int(s.get_height() * across))))
        s = pygame.transform.rotate(s, -vel_deg)
    s = pygame.transform.rotozoom(s, -angle_deg, zoom)
    r = s.get_rect(center=(int(pos[0]), int(pos[1])))
    frame.blit(s, r)
    return r


def _limb(frame, a, b, zoom=1.0):
    w = max(2, int(LIMB_W * zoom))
    pygame.draw.line(frame, BLACK, a, b, w)
    pygame.draw.circle(frame, BLACK, b, w * 0.6)


def draw_limbs(frame: pygame.Surface, pos: tuple[float, float], hx: float, hy: float, state: str, t: float,
               vx: float = 0.0, zoom: float = 1.0) -> None:
    """state: running | airborne | stunned | victory | idle. Limbs are visual only."""
    x, y = pos
    hx, hy = hx * zoom, hy * zoom
    leg = max(10.0, hy * 0.75)
    arm = max(9.0, hx * 0.7)
    hip_l, hip_r = (x - hx * 0.35, y + hy * 0.85), (x + hx * 0.35, y + hy * 0.85)
    sh_l, sh_r = (x - hx * 0.92, y + hy * 0.05), (x + hx * 0.92, y + hy * 0.05)
    if state == "running":
        f = 4 + abs(vx) / 60
        ph = math.sin(t * f * 2 * math.pi / 4)
        _limb(frame, hip_l, (hip_l[0] + ph * leg * 0.6, hip_l[1] + leg), zoom)
        _limb(frame, hip_r, (hip_r[0] - ph * leg * 0.6, hip_r[1] + leg), zoom)
        _limb(frame, sh_l, (sh_l[0] - arm * 0.6, sh_l[1] - ph * arm * 0.8 + arm * 0.3), zoom)
        _limb(frame, sh_r, (sh_r[0] + arm * 0.6, sh_r[1] + ph * arm * 0.8 + arm * 0.3), zoom)
    elif state == "airborne":
        fl = math.sin(t * 25)
        _limb(frame, hip_l, (hip_l[0] - leg * 0.5, hip_l[1] + leg * (0.6 + 0.3 * fl)), zoom)
        _limb(frame, hip_r, (hip_r[0] + leg * 0.5, hip_r[1] + leg * (0.6 - 0.3 * fl)), zoom)
        _limb(frame, sh_l, (sh_l[0] - arm, sh_l[1] - arm * (0.7 + 0.5 * fl)), zoom)
        _limb(frame, sh_r, (sh_r[0] + arm, sh_r[1] - arm * (0.7 - 0.5 * fl)), zoom)
    elif state == "stunned":
        lag = math.sin(t * 9) * 0.6
        _limb(frame, hip_l, (hip_l[0] - leg * (0.7 + lag), hip_l[1] + leg * 0.4), zoom)
        _limb(frame, hip_r, (hip_r[0] + leg * (0.7 - lag), hip_r[1] + leg * 0.5), zoom)
        _limb(frame, sh_l, (sh_l[0] - arm * 1.0, sh_l[1] + arm * (0.6 + lag)), zoom)
        _limb(frame, sh_r, (sh_r[0] + arm * 1.0, sh_r[1] + arm * (0.6 - lag)), zoom)
    elif state == "victory":
        hop = abs(math.sin(t * 6)) * 6 * zoom
        _limb(frame, (hip_l[0], hip_l[1] - hop), (hip_l[0] - leg * 0.3, hip_l[1] + leg - hop), zoom)
        _limb(frame, (hip_r[0], hip_r[1] - hop), (hip_r[0] + leg * 0.3, hip_r[1] + leg - hop), zoom)
        _limb(frame, (sh_l[0], sh_l[1] - hop), (sh_l[0] - arm * 0.7, sh_l[1] - arm * 1.2 - hop), zoom)
        _limb(frame, (sh_r[0], sh_r[1] - hop), (sh_r[0] + arm * 0.7, sh_r[1] - arm * 1.2 - hop), zoom)
    else:  # idle
        _limb(frame, hip_l, (hip_l[0] - leg * 0.15, hip_l[1] + leg), zoom)
        _limb(frame, hip_r, (hip_r[0] + leg * 0.15, hip_r[1] + leg), zoom)
        _limb(frame, sh_l, (sh_l[0] - arm * 0.5, sh_l[1] + arm * 0.7), zoom)
        _limb(frame, sh_r, (sh_r[0] + arm * 0.5, sh_r[1] + arm * 0.7), zoom)


@lru_cache(maxsize=64)
def _pill_font(size: int) -> pygame.font.Font:
    return pygame.font.Font(font_path("LuckiestGuy-Regular.ttf"), size)


@lru_cache(maxsize=64)
def name_pill(hero: Hero, crown: bool = False, size: int = 26) -> pygame.Surface:
    """Rounded pill: initial-letter disc (colour-blind safe) + name, in the hero colour."""
    f = _pill_font(size)
    name = f.render(hero.name.upper(), True, WHITE)
    letter = f.render(hero.initial, True, BLACK)
    h = size + 12
    w = name.get_width() + h + 18
    s = pygame.Surface((w, h + (14 if crown else 0)), pygame.SRCALPHA)
    oy = 14 if crown else 0
    base = hex_rgb(hero.colour)
    pygame.draw.rect(s, BLACK, (0, oy, w, h), border_radius=h // 2)
    pygame.draw.rect(s, _shade(base, 0.8) if hero.key not in ("floater",) else (90, 96, 104), (3, oy + 3, w - 6, h - 6),
                     border_radius=h // 2)
    pygame.draw.circle(s, WHITE, (h // 2 + 2, oy + h // 2), h // 2 - 5)
    s.blit(letter, letter.get_rect(center=(h // 2 + 2, oy + h // 2 + 1)))
    s.blit(name, (h + 6, oy + (h - name.get_height()) // 2 + 2))
    if crown:
        cx = w // 2
        pts = [(cx - 14, 14), (cx - 14, 4), (cx - 7, 9), (cx, 0), (cx + 7, 9), (cx + 14, 4), (cx + 14, 14)]
        pygame.draw.polygon(s, (255, 205, 40), pts)
        pygame.draw.polygon(s, BLACK, pts, 2)
    return s


def cult_badge(number: int) -> pygame.Surface:
    f = _pill_font(16)
    t = f.render(str(number), True, BLACK)
    s = pygame.Surface((t.get_width() + 12, 22), pygame.SRCALPHA)
    pygame.draw.rect(s, (255, 236, 160), s.get_rect(), border_radius=11)
    pygame.draw.rect(s, BLACK, s.get_rect(), 2, border_radius=11)
    s.blit(t, t.get_rect(center=s.get_rect().center))
    return s


def draw_hero(frame: pygame.Surface, hero: Hero, pos, angle_deg: float, vel, expression: str, limb_state: str,
              t: float, squash: float = 0.0, zoom: float = 1.0) -> pygame.Rect:
    vx, vy = vel
    hx, hy = body_half_extents(hero)
    draw_limbs(frame, pos, hx, hy, limb_state, t, vx, zoom)
    along, across, vdeg = stretch_factors(vx, vy, squash)
    look = (max(-1.0, min(1.0, vx / 300)), max(-1.0, min(1.0, vy / 300)))
    look = (round(look[0], 1), round(look[1], 1))
    src = body_surface(hero, expression, int(t * 10) % 20 if expression in ("dizzy",) or hero.key == "glitch" else 0, look)
    return blit_body(frame, src, pos, angle_deg, along, across, vdeg, zoom)


def draw_extra(frame: pygame.Surface, extra: Extra, pos, angle_deg: float, expression: str, zoom: float = 1.0,
               limb_state: str = "idle", t: float = 0.0, vx: float = 0.0) -> None:
    r = extra.radius
    draw_limbs(frame, pos, r, r, limb_state, t, vx, zoom)
    s = extra_surface(extra.colour, r, "eliminated" if expression == "eliminated" else
                      ("scared" if expression in ("scared", "dizzy") else "neutral"))
    s = pygame.transform.rotozoom(s, -angle_deg * 0.3, zoom)
    # the bot surface is taller than wide (antenna): anchor the body centre on pos
    off = (s.get_height() - s.get_width()) / 2
    frame.blit(s, s.get_rect(center=(int(pos[0]), int(pos[1] - off))))
    if extra.cult:
        b = cult_badge(extra.number)
        frame.blit(b, b.get_rect(midbottom=(int(pos[0]), int(pos[1] - r * 1.8 * zoom - 2))))
