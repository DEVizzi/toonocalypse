"""HUD and overlays (§8): header with Lord Tuno, episode badge, survivors counter, hero status strip, banners,
winner card. All text stays inside safe zones (checked by tests/test_layout.py through `TEXT_BOXES`)."""
from __future__ import annotations

import math
from functools import lru_cache

import pygame

from src.characters import renderer
from src.characters.expressions import BLACK, WHITE
from src.characters.roster import Hero
from src.characters.tuno import draw_tuno
from src.config import LAYOUT, W, font_path

HEADER_TOP, HEADER_BOTTOM = LAYOUT["header"]
TEXT_BOXES: list[pygame.Rect] = []      # every text rect drawn this frame (for safe-zone tests)


@lru_cache(maxsize=32)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


def outlined(text: str, size: int, fill=WHITE, outline=BLACK, width: int = 6, face: str = "LuckiestGuy-Regular.ttf"):
    f = font(size, face)
    base = f.render(text, True, fill)
    out = pygame.Surface((base.get_width() + 2 * width, base.get_height() + 2 * width), pygame.SRCALPHA)
    ring = f.render(text, True, outline)
    for a in range(16):
        out.blit(ring, (width + math.cos(a * math.pi / 8) * width, width + math.sin(a * math.pi / 8) * width))
    out.blit(base, (width, width))
    return out


def blit_text(frame: pygame.Surface, surf: pygame.Surface, **anchor) -> pygame.Rect:
    r = surf.get_rect(**anchor)
    frame.blit(surf, r)
    TEXT_BOXES.append(r)
    return r


def draw_header(frame: pygame.Surface, ep_label: str, survivors: int, total: int, heroes: list[Hero],
                status: dict[str, str], tuno_state: str, t: float, pulse: float = 0.0) -> None:
    """status per hero key: alive | out | crown."""
    # translucent header plate
    plate = pygame.Surface((W, HEADER_BOTTOM - HEADER_TOP + 10), pygame.SRCALPHA)
    plate.fill((20, 14, 40, 110))
    frame.blit(plate, (0, HEADER_TOP))
    draw_tuno(frame, W / 2, HEADER_TOP + 118, tuno_state, t, scale=0.82)
    # episode badge (left)
    badge = outlined(ep_label, 30, width=4)
    blit_text(frame, badge, topleft=(28, HEADER_TOP + 14))
    # survivors (right) — pulses red on mass eliminations
    col = (255, 80, 80) if pulse > 0 else WHITE
    k = 1.0 + 0.18 * max(0.0, pulse)
    s = outlined(f"SURVIVORS {survivors}/{total}", 30, fill=col, width=4)
    if k != 1.0:
        s = pygame.transform.rotozoom(s, 0, k)
    blit_text(frame, s, topright=(W - 28, HEADER_TOP + 14))
    # compact hero strip: 3 left of Tuno, 3 right (more on Sundays wrap evenly)
    n = len(heroes)
    left = heroes[: (n + 1) // 2]
    right = heroes[(n + 1) // 2:]
    for group, x0, step in ((left, 40, 1), (right, W - 40, -1)):
        for i, h in enumerate(group):
            cx = x0 + step * (i * 78 + 32)
            cy = HEADER_TOP + 112
            _status_chip(frame, h, (cx, cy), status.get(h.key, "alive"))


def _status_chip(frame, hero: Hero, c, state: str) -> None:
    r = 28
    col = renderer.hex_rgb(hero.colour) if state != "out" else (90, 86, 100)
    pygame.draw.circle(frame, BLACK, c, r + 4)
    pygame.draw.circle(frame, col, c, r)
    letter = font(30).render(hero.initial, True, BLACK if hero.key in ("pip", "floater", "dash") else WHITE)
    frame.blit(letter, letter.get_rect(center=(c[0], c[1] + 2)))
    if state == "out":
        pygame.draw.line(frame, (230, 40, 60), (c[0] - 20, c[1] - 20), (c[0] + 20, c[1] + 20), 7)
        pygame.draw.line(frame, (230, 40, 60), (c[0] - 20, c[1] + 20), (c[0] + 20, c[1] - 20), 7)
    elif state == "crown":
        pts = [(c[0] - 16, c[1] - 26), (c[0] - 16, c[1] - 38), (c[0] - 8, c[1] - 31), (c[0], c[1] - 42),
               (c[0] + 8, c[1] - 31), (c[0] + 16, c[1] - 38), (c[0] + 16, c[1] - 26)]
        pygame.draw.polygon(frame, (255, 205, 40), pts)
        pygame.draw.polygon(frame, BLACK, pts, 2)


def draw_banner(frame: pygame.Surface, text: str, age: float, y: float = 560, colour=(255, 214, 0)) -> None:
    """Big slam-in banner for 1.2 s (SPEED UP!, OVERTIME CHAOS!, FINAL!, twist names)."""
    if age < 0 or age > 1.2:
        return
    k = 1.6 - 0.6 * min(1.0, age / 0.12) if age < 0.12 else (1.0 if age < 0.95 else max(0.0, 1 - (age - 0.95) / 0.25))
    s = outlined(text, 92, fill=colour, width=8)
    s = pygame.transform.rotozoom(s, -4, k)
    blit_text(frame, s, center=(W / 2, y))


def draw_pick_your_fighter(frame: pygame.Surface, heroes: list[Hero], t: float) -> None:
    s = outlined("PICK YOUR FIGHTER!", 78, fill=(255, 214, 0), width=7)
    blit_text(frame, pygame.transform.rotozoom(s, -3, 1.0 + 0.04 * math.sin(t * 20)), center=(W / 2, 520))
    pills = [renderer.name_pill(h, size=30) for h in heroes]
    rows = [pills[:3], pills[3:6], pills[6:]]
    y = 640
    for row in rows:
        if not row:
            continue
        total = sum(p.get_width() for p in row) + 20 * (len(row) - 1)
        x = W / 2 - total / 2
        for p in row:
            blit_text(frame, p, topleft=(x, y))
            x += p.get_width() + 20
        y += 64


def draw_winner_card(frame: pygame.Surface, hero: Hero | None, name: str, colour: tuple[int, int, int], points: str,
                     prompt: str, t: float, bot=None) -> None:
    panel = pygame.Rect(90, 520, W - 180, 700)
    shadow = panel.move(10, 12)
    pygame.draw.rect(frame, BLACK, shadow, border_radius=36)
    pygame.draw.rect(frame, (255, 248, 230), panel, border_radius=36)
    pygame.draw.rect(frame, BLACK, panel, 6, border_radius=36)
    pop = 1.0 + 0.35 * math.exp(-t * 5) * math.cos(t * 18)          # springy winner bounce
    blit_text(frame, pygame.transform.rotozoom(outlined("WINNER!", 96, fill=(255, 214, 0), width=8), 0, pop),
              center=(W / 2, panel.top + 80))
    if hero is not None:
        from src.rendering import balls
        hop = abs(math.sin(t * 7)) * 26
        balls.draw_ball(frame, hero, None, (W / 2, panel.top + 280 - hop), 0.0, 0.0, (0, 0), 0.0, "celebrating",
                        "victory", t, 2.6 / max(0.6, hero.radius / 25) * pop, force_grin=True)
    elif bot is not None:
        from src.rendering import balls
        balls.draw_ball(frame, None, bot, (W / 2, panel.top + 280), 0.0, 0.0, (0, 0), 0.0, "neutral", "victory", t, 2.8)
    else:
        pygame.draw.circle(frame, BLACK, (W / 2, panel.top + 270), 64)
        pygame.draw.circle(frame, colour, (W / 2, panel.top + 270), 58)
    blit_text(frame, outlined(name.upper(), 72, fill=colour, width=6), center=(W / 2, panel.top + 440))
    blit_text(frame, outlined(points, 40, width=4), center=(W / 2, panel.top + 515))
    blit_text(frame, outlined(prompt, 40, fill=(255, 255, 255), width=4, face="Fredoka.ttf"), center=(W / 2, panel.top + 585))
    bob = 4 * math.sin(t * 6)
    blit_text(frame, outlined("COMMENT YOUR PICK!", 44, fill=(255, 214, 0), width=5), center=(W / 2, panel.top + 650 + bob))


def draw_decor(frame: pygame.Surface, theme, t: float) -> None:
    """Decorative battlements in the top sky band and castle wall in the bottom band (no information)."""
    top = LAYOUT["top_sky"][1]
    castle = theme.castle
    dark = tuple(max(0, int(c * 0.7)) for c in castle)
    pygame.draw.rect(frame, dark, (0, top - 46, W, 46))
    for x in range(0, W, 90):
        pygame.draw.rect(frame, dark, (x, top - 80, 50, 40))
    y0 = LAYOUT["bottom_band"][0]
    pygame.draw.rect(frame, dark, (0, y0, W, frame.get_height() - y0))
    for row, y in enumerate(range(y0, frame.get_height(), 52)):
        off = 0 if row % 2 else 60
        for x in range(-off, W, 120):
            pygame.draw.rect(frame, castle, (x + 4, y + 4, 112, 44), border_radius=6)
