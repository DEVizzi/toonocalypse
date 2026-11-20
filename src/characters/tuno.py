"""Lord Tuno (§9.3): round crowned castle ruler on his balcony. States: idle, laughing, shocked, lever, crowning."""
from __future__ import annotations

import math

import pygame

from src.characters.expressions import BLACK, WHITE

ROBE = (122, 40, 160)
ROBE_DARK = (86, 26, 118)
SKIN = (255, 214, 170)
GOLD = (255, 200, 40)
STONE = (150, 140, 170)
STONE_DARK = (100, 92, 122)
STATES = ("idle", "laughing", "shocked", "lever", "crowning")


def _crown(s: pygame.Surface, cx: float, top: float, w: float, lift: float = 0.0) -> None:
    y = top - lift
    pts = [(cx - w / 2, y + w * 0.45), (cx - w / 2, y + w * 0.05), (cx - w / 4, y + w * 0.28), (cx, y - w * 0.1),
           (cx + w / 4, y + w * 0.28), (cx + w / 2, y + w * 0.05), (cx + w / 2, y + w * 0.45)]
    pygame.draw.polygon(s, GOLD, pts)
    pygame.draw.polygon(s, BLACK, pts, 3)
    for gx, col in ((cx - w / 4, (230, 40, 60)), (cx, (40, 140, 255)), (cx + w / 4, (40, 200, 90))):
        pygame.draw.circle(s, col, (gx, y + w * 0.36), w * 0.06)


def draw_tuno(s: pygame.Surface, cx: float, base_y: float, state: str, t: float, scale: float = 1.0) -> None:
    """Draws Lord Tuno standing behind a balcony whose top edge is at base_y."""
    r = 52 * scale
    bob = math.sin(t * 2.2) * 3 * scale
    shake = math.sin(t * 40) * 3 * scale if state == "laughing" else 0.0
    bx, by = cx + shake, base_y - r * 0.55 + bob
    # lever (right side)
    lx, ly = cx + r * 1.9, base_y - r * 0.2
    pull = 1.0 if state == "lever" else 0.0
    ang = math.radians(-60 + 110 * pull)
    tip = (lx + math.cos(ang) * r * 0.9, ly + math.sin(ang) * r * 0.9)
    pygame.draw.rect(s, STONE_DARK, (lx - r * 0.25, ly - r * 0.1, r * 0.5, r * 0.3), border_radius=4)
    pygame.draw.line(s, BLACK, (lx, ly), tip, int(7 * scale))
    pygame.draw.circle(s, (230, 40, 60), tip, r * 0.16)
    pygame.draw.circle(s, BLACK, tip, r * 0.16, 2)
    # body
    pygame.draw.circle(s, BLACK, (bx, by), r + 4)
    pygame.draw.circle(s, ROBE, (bx, by), r)
    pygame.draw.ellipse(s, SKIN, (bx - r * 0.62, by - r * 0.72, r * 1.24, r * 0.95))
    pygame.draw.ellipse(s, BLACK, (bx - r * 0.62, by - r * 0.72, r * 1.24, r * 0.95), 3)
    # ermine collar
    pygame.draw.ellipse(s, WHITE, (bx - r * 0.8, by + r * 0.12, r * 1.6, r * 0.42))
    for i in range(5):
        pygame.draw.circle(s, BLACK, (bx - r * 0.55 + i * r * 0.27, by + r * 0.33), 2)
    fy = by - r * 0.3
    # eyes
    if state == "laughing":
        for dx in (-0.25, 0.25):
            pygame.draw.arc(s, BLACK, (bx + dx * r - r * 0.12, fy - r * 0.1, r * 0.24, r * 0.2), 0.2, math.pi - 0.2, 4)
    elif state == "shocked":
        for dx in (-0.25, 0.25):
            pygame.draw.circle(s, WHITE, (bx + dx * r, fy), r * 0.15)
            pygame.draw.circle(s, BLACK, (bx + dx * r, fy), r * 0.15, 3)
            pygame.draw.circle(s, BLACK, (bx + dx * r, fy), r * 0.05)
    else:
        for dx in (-0.25, 0.25):
            pygame.draw.circle(s, BLACK, (bx + dx * r, fy), r * 0.07)
    # nose + moustache
    pygame.draw.circle(s, (255, 170, 140), (bx, fy + r * 0.13), r * 0.1)
    for side in (-1, 1):
        pts = [(bx, fy + r * 0.22), (bx + side * r * 0.42, fy + r * 0.12 - (r * 0.08 if state == "laughing" else 0)),
               (bx + side * r * 0.5, fy + r * 0.02), (bx + side * r * 0.3, fy + r * 0.3)]
        pygame.draw.polygon(s, (90, 60, 40), pts)
    # mouth
    if state in ("laughing", "crowning"):
        pygame.draw.ellipse(s, BLACK, (bx - r * 0.18, fy + r * 0.28, r * 0.36, r * 0.22))
    elif state == "shocked":
        pygame.draw.ellipse(s, BLACK, (bx - r * 0.09, fy + r * 0.28, r * 0.18, r * 0.24))
    # crown
    lift = r * 0.25 * abs(math.sin(t * 10)) if state == "shocked" else 0.0
    _crown(s, bx, by - r * 1.05, r * 0.95, lift)
    # arms
    if state == "lever":
        pygame.draw.line(s, BLACK, (bx + r * 0.8, by), tip, int(9 * scale))
    elif state == "crowning":
        for side in (-1, 1):
            pygame.draw.line(s, BLACK, (bx + side * r * 0.85, by), (bx + side * r * 1.1, by - r * 1.0), int(9 * scale))
        _crown(s, bx, by - r * 1.75 - math.sin(t * 6) * 4, r * 0.6)
    elif state == "laughing":
        for side in (-1, 1):
            pygame.draw.line(s, BLACK, (bx + side * r * 0.85, by), (bx + side * r * 1.15, by - r * 0.45 + shake), int(9 * scale))
    # balcony (covers his lower half)
    bw = r * 3.4
    pygame.draw.rect(s, STONE, (cx - bw / 2, base_y, bw, r * 0.7))
    pygame.draw.rect(s, BLACK, (cx - bw / 2, base_y, bw, r * 0.7), 3)
    for i in range(7):
        x = cx - bw / 2 + 8 + i * (bw - 16) / 6
        pygame.draw.line(s, STONE_DARK, (x, base_y + 6), (x, base_y + r * 0.62), 5)
    pygame.draw.rect(s, STONE_DARK, (cx - bw / 2 - 8, base_y - 8, bw + 16, 12), border_radius=4)
    pygame.draw.rect(s, BLACK, (cx - bw / 2 - 8, base_y - 8, bw + 16, 12), 2, border_radius=4)
