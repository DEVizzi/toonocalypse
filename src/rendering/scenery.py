"""Polished scenery & HUD art (§8, §15): soft cloud sky with distant towers, castle header with Lord Tuno's balcony,
episode pill, bottom status panel, rocky snow/grass-capped terrain and floating top-down platforms.
Everything is procedural vector art; static layers are built once per episode."""
from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from src.characters import renderer
from src.characters.expressions import BLACK, WHITE
from src.characters.roster import Hero
from src.characters.tuno import draw_tuno
from src.config import H, LAYOUT, W, font_path

HEADER_BOTTOM = LAYOUT["header"][1]
PANEL = pygame.Rect(28, 1462, 922, 172)        # bottom status panel (left of the right UI column, above the band)


def mix(a, b, k: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))  # type: ignore[return-value]


@lru_cache(maxsize=16)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


# ---------------------------------------------------------------------------------------------- sky
def _cloud(s: pygame.Surface, x: float, y: float, w: float, col, shade) -> None:
    rng = random.Random(int(x * 7 + y))
    puffs = [(x + w * k, y - rng.uniform(0.1, 0.45) * w * 0.5, w * rng.uniform(0.22, 0.34)) for k in (0.0, 0.22, 0.45, 0.68, 0.9)]
    for px, py, r in puffs:
        pygame.draw.circle(s, shade, (px, py + r * 0.18), r)
    for px, py, r in puffs:
        pygame.draw.circle(s, col, (px, py), r)
    pygame.draw.rect(s, col, (x - w * 0.05, y - w * 0.12, w * 1.0, w * 0.2), border_radius=int(w * 0.1))


def sky(theme) -> pygame.Surface:
    """Full-frame background: gradient, far castle towers, and banks of soft clouds. Seamless horizontally."""
    s = pygame.Surface((W, H))
    top, bot = mix(theme.sky_top, (255, 255, 255), 0.25), mix(theme.sky_bottom, (255, 255, 255), 0.35)
    for y in range(H):
        pygame.draw.line(s, mix(top, bot, y / H), (0, y), (W, y))
    far = mix(theme.castle, bot, 0.55)
    far_d = mix(far, theme.sky_top, 0.15)
    rng = random.Random(11)
    for i in range(5):                       # distant towers (drawn wrapped for seamless parallax)
        x, w, h = i * 240 + rng.randint(-40, 40), rng.randint(70, 120), rng.randint(380, 620)
        for ox in (0, -W, W):
            bx = x + ox
            pygame.draw.rect(s, far, (bx, 1400 - h, w, h + 400))
            for k in range(w // 28 + 1):
                pygame.draw.rect(s, far, (bx + k * 28 - 4, 1400 - h - 22, 18, 24))
            pygame.draw.polygon(s, far_d, [(bx - 10, 1400 - h - 20), (bx + w + 10, 1400 - h - 20), (bx + w / 2, 1400 - h - 120)])
            pygame.draw.rect(s, far_d, (bx + w / 2 - 8, 1400 - h + 60, 16, 30), border_radius=8)
    cloud, shade = mix(WHITE, theme.sky_bottom, 0.08), mix(WHITE, theme.sky_top, 0.3)
    for i in range(7):                       # mid clouds
        x, y = i * 170 + rng.randint(-30, 30), rng.randint(420, 1100)
        for ox in (0, -W, W):
            _cloud(s, x + ox, y, rng.randint(160, 260), cloud, shade)
    for i in range(9):                       # low cloud sea
        x = i * 135 + rng.randint(-20, 20)
        for ox in (0, -W, W):
            _cloud(s, x + ox, 1560 + rng.randint(-30, 40), 240, cloud, shade)
    pygame.draw.rect(s, cloud, (0, 1600, W, H - 1600))
    return s


# ---------------------------------------------------------------------------------------------- castle header
def castle_header(theme) -> pygame.Surface:
    """Castle wall with crenellations across the top band, a central tower with an arched window for the balcony."""
    s = pygame.Surface((W, HEADER_BOTTOM + 40), pygame.SRCALPHA)
    stone = mix(theme.castle, (165, 165, 175), 0.55)
    dark, light = mix(stone, BLACK, 0.28), mix(stone, WHITE, 0.25)
    wall_top = 150
    pygame.draw.rect(s, stone, (0, wall_top, W, 120))
    for x in range(-20, W, 96):                                          # merlons
        pygame.draw.rect(s, stone, (x, wall_top - 46, 60, 50))
        pygame.draw.rect(s, BLACK, (x, wall_top - 46, 60, 50), 4)
    pygame.draw.line(s, BLACK, (0, wall_top), (W, wall_top), 4)
    for row, y in enumerate(range(wall_top + 8, wall_top + 120, 34)):     # bricks
        off = 0 if row % 2 else 48
        for x in range(-off, W, 96):
            pygame.draw.rect(s, dark, (x + 4, y, 88, 28), 2, border_radius=4)
    pygame.draw.rect(s, dark, (0, wall_top + 112, W, 10))
    pygame.draw.line(s, BLACK, (0, wall_top + 122), (W, wall_top + 122), 4)
    tw = 300                                                              # central tower
    tx = W / 2 - tw / 2
    pygame.draw.rect(s, stone, (tx, 0, tw, wall_top + 122))
    for row, y in enumerate(range(8, wall_top + 110, 34)):
        off = 0 if row % 2 else 36
        for x in range(int(tx) - off, int(tx + tw), 72):
            r = pygame.Rect(x + 4, y, 64, 28).clip(pygame.Rect(tx, 0, tw, wall_top + 122))
            if r.w > 6:
                pygame.draw.rect(s, dark, r, 2, border_radius=4)
    pygame.draw.rect(s, BLACK, (tx, -10, tw, wall_top + 132), 5)
    arch = pygame.Rect(W / 2 - 96, 40, 192, 220)                          # arched window (dark interior)
    pygame.draw.rect(s, (52, 44, 70), arch, border_top_left_radius=96, border_top_right_radius=96)
    pygame.draw.rect(s, BLACK, arch, 5, border_top_left_radius=96, border_top_right_radius=96)
    pygame.draw.rect(s, light, (arch.x + 10, arch.y + 10, 10, 120), border_radius=5)
    return s


def draw_header(frame: pygame.Surface, castle: pygame.Surface, ep_label: str, tuno_state: str, t: float,
                text_boxes: list) -> None:
    frame.blit(castle, (0, 0))
    draw_tuno(frame, W / 2, 262, tuno_state, t, scale=1.12)
    pill = episode_pill(ep_label)
    r = pill.get_rect(topright=(W - 26, 150))
    frame.blit(pill, r)
    text_boxes.append(r)


@lru_cache(maxsize=8)
def episode_pill(text: str) -> pygame.Surface:
    f = font(30, "Fredoka.ttf")
    f.set_bold(True)
    t = f.render(text, True, (20, 20, 28))
    s = pygame.Surface((t.get_width() + 44, t.get_height() + 20), pygame.SRCALPHA)
    rect = s.get_rect()
    pygame.draw.rect(s, BLACK, rect, border_radius=16)
    pygame.draw.rect(s, WHITE, rect.inflate(-8, -8), border_radius=13)
    s.blit(t, t.get_rect(center=rect.center))
    return s


# ---------------------------------------------------------------------------------------------- bottom panel
def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _crown(frame, cx: float, cy: float, w: float) -> None:
    pts = [(cx - w / 2, cy + w * 0.35), (cx - w / 2, cy - w * 0.1), (cx - w / 4, cy + w * 0.12), (cx, cy - w * 0.25),
           (cx + w / 4, cy + w * 0.12), (cx + w / 2, cy - w * 0.1), (cx + w / 2, cy + w * 0.35)]
    pygame.draw.polygon(frame, (255, 205, 40), pts)
    pygame.draw.polygon(frame, BLACK, pts, 2)


def draw_panel(frame: pygame.Surface, survivors: int, total: int, heroes: list[Hero], status: dict[str, str],
               ranks: dict[str, int], text_boxes: list, pulse: float = 0.0) -> None:
    """Dark rounded status panel: SURVIVORS n/N + hero portraits with live rank (crossed out when eliminated)."""
    plate = pygame.Surface(PANEL.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (24, 26, 40, 205), plate.get_rect(), border_radius=28)
    pygame.draw.rect(plate, (255, 255, 255, 60), plate.get_rect(), 3, border_radius=28)
    frame.blit(plate, PANEL)
    lab = font(30).render("SURVIVORS:", True, WHITE)
    r1 = frame.blit(lab, (PANEL.x + 26, PANEL.y + 26))
    k = 1.0 + 0.15 * pulse
    num = font(int(64 * k)).render(f"{survivors}", True, (255, 74, 74))
    tot = font(int(64 * k)).render(f" / {total}", True, WHITE)
    r2 = frame.blit(num, (PANEL.x + 26, PANEL.y + 66))
    r3 = frame.blit(tot, (r2.right, PANEL.y + 66))
    text_boxes += [r1, r2, r3]
    n = len(heroes)
    x0 = PANEL.x + 250
    two_rows = n > 6                        # Sunday: 10 heroes in 2 rows of 5
    cols = 5 if two_rows else max(1, n)
    step = (PANEL.right - 16 - x0) / cols
    rad = 26 if two_rows else min(40, step * 0.42)
    small = font(20 if two_rows else int(min(23, step * 0.2)))
    for i, h in enumerate(heroes):
        if two_rows:
            cx, cy = x0 + step * (i % cols) + rad + 4, PANEL.y + 14 + rad + (i // cols) * 80
        else:
            cx, cy = x0 + step * (i + 0.5), PANEL.y + 16 + rad
        st = status.get(h.key, "alive")
        face = renderer.body_surface(h, "eliminated" if st == "out" else ("celebrating" if st == "crown" else "neutral"), 0)
        sz = int(rad * 2.1)
        f = pygame.transform.smoothscale(face, (sz, int(sz * face.get_height() / face.get_width())))
        if st == "out":
            f.set_alpha(110)
        frame.blit(f, f.get_rect(center=(cx, cy)))
        if st == "out":
            pygame.draw.line(frame, (60, 64, 80), (cx - rad * 0.8, cy - rad * 0.8), (cx + rad * 0.8, cy + rad * 0.8), 9)
            pygame.draw.line(frame, (60, 64, 80), (cx - rad * 0.8, cy + rad * 0.8), (cx + rad * 0.8, cy - rad * 0.8), 9)
        col = WHITE if st != "out" else (120, 124, 140)
        nm = small.render(h.name, True, col)
        rn = small.render(_ordinal(ranks[h.key]) if h.key in ranks else "", True, (255, 214, 0) if st != "out" else col)
        if two_rows:
            ra = frame.blit(nm, nm.get_rect(bottomleft=(cx + rad + 6, cy + 2)))
            rb = frame.blit(rn, rn.get_rect(topleft=(cx + rad + 6, cy + 2)))
        else:
            ra = frame.blit(nm, nm.get_rect(midtop=(cx, cy + rad + 6)))
            rb = frame.blit(rn, rn.get_rect(midtop=(cx - (10 if ranks.get(h.key) == 1 else 0), ra.bottom + 1)))
        if ranks.get(h.key) == 1 and st != "out":
            _crown(frame, rb.right + 14, rb.centery, 20)
        text_boxes += [ra, rb]


# ---------------------------------------------------------------------------------------------- terrain
def rock_colours(theme) -> tuple:
    cap = theme.terrain
    rock = mix(mix(theme.castle, (150, 150, 160), 0.4), theme.terrain_outline, 0.25)
    return cap, rock, mix(rock, BLACK, 0.22), mix(rock, WHITE, 0.18)


def draw_cliff(frame: pygame.Surface, pts: list, zoom: float, theme, mat: str) -> None:
    """SIDE ground section: stone cliff body with strata and a rounded cap (grass/snow/ice/mud) on top."""
    cap, rock, dark, light = rock_colours(theme)
    (ax, ay), (bx, by) = pts[0], pts[1]
    span = bx - ax
    if span < 2:
        return
    n = max(2, int(span / (70 * zoom)))
    rng = random.Random(int(span / zoom) * 31 + int((by - ay) / zoom))
    depth = 300 * zoom
    bottom = []
    for i in range(n + 1):                    # jagged, tapering underside: a floating rock rather than a slab
        k = i / n
        edge = min(k, 1 - k)
        d = depth * (0.35 + 0.65 * min(1.0, edge * 3.2)) * rng.uniform(0.82, 1.0)
        x = ax + span * k + (span * 0.08 * (1 if k < 0.5 else -1) if 0 < k < 1 else 0)
        bottom.append((x, ay + (by - ay) * k + d))
    poly = [(ax, ay), (bx, by)] + bottom[::-1]
    pygame.draw.polygon(frame, rock, poly)
    # strata + shading
    for f, col in ((0.28, light), (0.55, dark)):
        line = [(x, ay + (by - ay) * ((x - ax) / span) + (y - ay - (by - ay) * ((x - ax) / span)) * f) for x, y in bottom]
        pygame.draw.lines(frame, col, False, line, max(2, int(4 * zoom)))
    shade = [(x, y) for x, y in bottom]
    pygame.draw.lines(frame, dark, False, shade, max(3, int(10 * zoom)))
    pygame.draw.polygon(frame, BLACK, poly, max(3, int(4 * zoom)))


def draw_cap(frame: pygame.Surface, a, b, zoom: float, theme, mat: str) -> None:
    cap = {"ice": (205, 238, 255), "mud": (120, 84, 50), "bouncy": (255, 110, 185), "conveyor": (70, 72, 86),
           "plank": (176, 122, 70)}.get(mat, theme.terrain)
    w = max(8, int(26 * zoom))
    pygame.draw.line(frame, BLACK, a, b, w + 8)
    for p in (a, b):
        pygame.draw.circle(frame, BLACK, p, (w + 8) / 2)
    pygame.draw.line(frame, cap, a, b, w)
    for p in (a, b):
        pygame.draw.circle(frame, cap, p, w / 2)
    hi = mix(cap, WHITE, 0.45)
    pygame.draw.line(frame, hi, (a[0] + 4, a[1] - w * 0.25), (b[0] - 4, b[1] - w * 0.25), max(2, w // 5))


def draw_floating_platform(frame: pygame.Surface, centre, radius: float, zoom: float, theme, shape: str = "disc",
                           half: float = 0.0) -> None:
    """TOP_DOWN arena floor as a floating island: thick stone side wall below, capped surface with an outline."""
    cap, rock, dark, light = rock_colours(theme)
    cx, cy = centre
    depth = 46 * zoom
    if shape == "square":
        r = pygame.Rect(cx - half, cy - half, 2 * half, 2 * half)
        pygame.draw.rect(frame, BLACK, r.move(0, depth).inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, dark, r.move(0, depth), border_radius=20)
        pygame.draw.rect(frame, BLACK, r.inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, theme.terrain, r, border_radius=20)
        pygame.draw.rect(frame, mix(theme.terrain, WHITE, 0.35), r.inflate(-24, -24), 4, border_radius=16)
        return
    pygame.draw.circle(frame, BLACK, (cx, cy + depth), radius + 5)
    pygame.draw.circle(frame, dark, (cx, cy + depth), radius)
    pygame.draw.rect(frame, dark, (cx - radius, cy, 2 * radius, depth))
    pygame.draw.line(frame, BLACK, (cx - radius - 3, cy), (cx - radius - 3, cy + depth), 6)
    pygame.draw.line(frame, BLACK, (cx + radius + 3, cy), (cx + radius + 3, cy + depth), 6)
    pygame.draw.circle(frame, BLACK, (cx, cy), radius + 5)
    pygame.draw.circle(frame, theme.terrain, (cx, cy), radius)
    pygame.draw.circle(frame, mix(theme.terrain, WHITE, 0.3), (cx, cy), radius * 0.92, max(2, int(4 * zoom)))
    pygame.draw.circle(frame, mix(theme.terrain, BLACK, 0.1), (cx, cy), radius * 0.5, max(2, int(3 * zoom)))


def shadow(frame: pygame.Surface, pos, r: float) -> None:
    s = pygame.Surface((int(r * 2.4), int(r * 0.9)), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), s.get_rect())
    frame.blit(s, s.get_rect(center=(pos[0], pos[1] + r * 0.95)))
