"""Cartoon juice effects (§5.3): impact starburst popups, elimination ghosts, dust, trails, sparks, confetti."""
from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from src.characters.expressions import BLACK, WHITE
from src.config import font_path

POPUP_WORDS = ("BONK!", "YEET!", "SPLAT!", "BOING!", "OOF!", "BETRAYAL!")
CONTEXT_POPUPS = {"grumble": "SPITE!", "dash": "NO BRAKES!", "pip": "LIFTOFF!", "juggernaut": "STRIKE!",
                  "glitch": "ERROR!", "boing": "BOING x2!", "magneto": "CLUNK!", "floater": "BYE!", "bonk": "THUD!",
                  "sly": "SNEAKY!"}
POPUP_COLOURS = {"BONK!": (255, 214, 0), "YEET!": (0, 229, 255), "SPLAT!": (255, 77, 166), "BOING!": (46, 204, 113),
                 "OOF!": (255, 122, 0), "BETRAYAL!": (230, 40, 60)}
POPUP_S = 0.45


@lru_cache(maxsize=16)
def _font(size: int) -> pygame.font.Font:
    return pygame.font.Font(font_path("LuckiestGuy-Regular.ttf"), size)


@lru_cache(maxsize=128)
def starburst(word: str, size: int = 56, seed: int = 0) -> pygame.Surface:
    rng = random.Random(f"{word}{seed}")
    text = _font(size).render(word, True, BLACK)
    rw, rh = text.get_width() * 0.78 + 30, text.get_height() * 1.05 + 30
    w, h = int(rw * 2 + 20), int(rh * 2 + 20)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2, h / 2
    pts = []
    n = 18
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1.0 if i % 2 == 0 else rng.uniform(0.62, 0.75)
        pts.append((cx + math.cos(a) * rw * k, cy + math.sin(a) * rh * k))
    col = POPUP_COLOURS.get(word, (255, 236, 80))
    pygame.draw.polygon(s, BLACK, [(x + 5, y + 6) for x, y in pts])
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, BLACK, pts, 5)
    # white-outlined black text
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
        s.blit(_font(size).render(word, True, WHITE), text.get_rect(center=(cx + dx, cy + dy)))
    s.blit(text, text.get_rect(center=(cx, cy)))
    return s


def popup_scale(age: float) -> float:
    """Pop-in overshoot then shrink-out over POPUP_S seconds."""
    if age < 0.08:
        return 0.4 + 0.9 * age / 0.08
    if age < 0.16:
        return 1.3 - 0.3 * (age - 0.08) / 0.08
    return max(0.0, 1.0 - max(0.0, age - 0.33) / 0.12)


def draw_popup(frame: pygame.Surface, word: str, pos: tuple[float, float], age: float, seed: int = 0) -> pygame.Rect | None:
    k = popup_scale(age)
    if k <= 0.02:
        return None
    s = starburst(word, 56, seed)
    s = pygame.transform.rotozoom(s, (seed % 21) - 10, k)
    r = s.get_rect(center=(int(pos[0]), int(pos[1])))
    frame.blit(s, r)
    return r


def draw_ghost(frame: pygame.Surface, pos: tuple[float, float], age: float, colour=(255, 255, 255)) -> None:
    """Small rising ghost + poof for an elimination (age 0..0.9 s)."""
    if age > 0.9:
        return
    a = max(0, int(255 * (1 - age / 0.9)))
    x, y = pos[0], pos[1] - age * 160
    s = pygame.Surface((60, 70), pygame.SRCALPHA)
    body = [(30, 6), (48, 18), (52, 40), (50, 64), (42, 56), (34, 64), (26, 56), (18, 64), (10, 56), (8, 40), (12, 18)]
    pygame.draw.polygon(s, (*colour, a), body)
    pygame.draw.polygon(s, (0, 0, 0, a), body, 3)
    for ex in (22, 38):
        pygame.draw.line(s, (0, 0, 0, a), (ex - 4, 26), (ex + 4, 34), 3)
        pygame.draw.line(s, (0, 0, 0, a), (ex - 4, 34), (ex + 4, 26), 3)
    frame.blit(s, s.get_rect(center=(int(x + math.sin(age * 12) * 6), int(y))))
    if age < 0.35:  # poof ring
        rr = 18 + age * 120
        pygame.draw.circle(frame, (255, 255, 255), (int(pos[0]), int(pos[1])), int(rr), 4)


def draw_dust(frame: pygame.Surface, pos: tuple[float, float], age: float, seed: int) -> None:
    if age > 0.4:
        return
    rng = random.Random(seed)
    for _ in range(3):
        dx, dy = rng.uniform(-14, 14), rng.uniform(-6, 2)
        r = 4 + age * 18
        col = (235, 225, 205)
        pygame.draw.circle(frame, col, (int(pos[0] + dx * (1 + age * 3)), int(pos[1] + dy - age * 20)), int(r))


def draw_sparks(frame: pygame.Surface, pos: tuple[float, float], age: float, seed: int) -> None:
    if age > 0.3:
        return
    rng = random.Random(seed)
    for _ in range(8):
        a = rng.uniform(0, 2 * math.pi)
        d0, d1 = 10 + age * 160, 22 + age * 220
        p0 = (pos[0] + math.cos(a) * d0, pos[1] + math.sin(a) * d0)
        p1 = (pos[0] + math.cos(a) * d1, pos[1] + math.sin(a) * d1)
        pygame.draw.line(frame, (255, 240, 120), p0, p1, 4)


def draw_confetti(frame: pygame.Surface, t: float, seed: int, area: pygame.Rect, n: int = 90) -> None:
    rng = random.Random(seed)
    cols = [(255, 214, 0), (255, 77, 166), (0, 229, 255), (46, 204, 113), (255, 122, 0), (155, 89, 182)]
    for _ in range(n):
        x0 = rng.uniform(area.left, area.right)
        sp = rng.uniform(220, 420)
        y = area.top - 40 + ((t * sp + rng.uniform(0, area.height)) % (area.height + 80))
        x = x0 + math.sin(t * rng.uniform(2, 5) + x0) * 30
        w, h = rng.uniform(8, 14), rng.uniform(4, 8)
        rect = pygame.Surface((w, h), pygame.SRCALPHA)
        rect.fill(rng.choice(cols))
        rect = pygame.transform.rotate(rect, (t * rng.uniform(90, 400)) % 360)
        frame.blit(rect, (x, y))
