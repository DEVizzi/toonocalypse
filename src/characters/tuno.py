"""Lord Tuno (§9.3, v3.1): Royal Reaction Cam portrait in Royal Purple, tilted gold crown, thick black outline,
expressive eyebrows, and royal ermine collar. States: idle (NORMAL), laughing, shocked, evil (EVIL_GRIN), crowning.
"""
from __future__ import annotations

import math

import pygame

from src.characters.expressions import BLACK, WHITE

ROBE = (118, 36, 178)       # Royal Purple
ROBE_HI = (156, 68, 218)
SKIN = (255, 214, 170)
GOLD = (255, 205, 40)
STATES = ("idle", "laughing", "shocked", "lever", "crowning", "evil")


def _crown(s: pygame.Surface, cx: float, cy: float, w: float, tilt_deg: float = -8.0) -> None:
    cw, ch = int(w * 1.4), int(w * 0.9)
    cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
    ox, oy = cw / 2, ch * 0.72
    pts = [(ox - w / 2, oy), (ox - w / 2, oy - w * 0.42), (ox - w / 4, oy - w * 0.18), (ox, oy - w * 0.56),
           (ox + w / 4, oy - w * 0.18), (ox + w / 2, oy - w * 0.42), (ox + w / 2, oy)]
    pygame.draw.polygon(cs, GOLD, pts)
    pygame.draw.polygon(cs, BLACK, pts, 4)
    for gx, col in ((ox - w / 4, (230, 40, 60)), (ox, (40, 150, 255)), (ox + w / 4, (40, 200, 90))):
        pygame.draw.circle(cs, col, (gx, oy - w * 0.1), max(3, int(w * 0.065)))
    rot = pygame.transform.rotozoom(cs, tilt_deg, 1.0)
    s.blit(rot, rot.get_rect(center=(cx, cy)))


def draw_tuno(s: pygame.Surface, cx: float, base_y: float, state: str, t: float, scale: float = 1.0) -> None:
    """Draws Lord Tuno bust inside his portrait frame (clipped by caller if needed)."""
    r = 56 * scale
    bob = math.sin(t * 2.5) * 2.5 * scale
    shake = math.sin(t * 40) * 3 * scale if state == "laughing" else 0.0
    bx, by = cx + shake, base_y - r * 0.42 + bob
    # Royal Purple robe shoulders
    pygame.draw.circle(s, BLACK, (bx, by + r * 0.25), r * 1.08 + 5)
    pygame.draw.circle(s, ROBE, (bx, by + r * 0.25), r * 1.08)
    pygame.draw.arc(s, ROBE_HI, (bx - r, by - r * 0.7, r * 2, r * 1.8), 1.6, 2.8, max(3, int(5 * scale)))
    # Royal ermine collar
    pygame.draw.ellipse(s, BLACK, (bx - r * 0.88, by + r * 0.14 - 3, r * 1.76, r * 0.48 + 6))
    pygame.draw.ellipse(s, WHITE, (bx - r * 0.85, by + r * 0.16, r * 1.70, r * 0.44))
    for i in range(5):
        pygame.draw.circle(s, BLACK, (bx - r * 0.54 + i * r * 0.27, by + r * 0.37), max(2, int(2.6 * scale)))
    # Head
    pygame.draw.ellipse(s, BLACK, (bx - r * 0.68 - 4, by - r * 0.78 - 4, r * 1.36 + 8, r * 1.04 + 8))
    pygame.draw.ellipse(s, SKIN, (bx - r * 0.68, by - r * 0.78, r * 1.36, r * 1.04))
    fy = by - r * 0.32
    lw = max(3, int(3.5 * scale))
    # Eyes + expressive eyebrows
    if state == "laughing":
        for side in (-1, 1):
            ex = bx + side * 0.27 * r
            pygame.draw.arc(s, BLACK, (ex - r * 0.15, fy - r * 0.12, r * 0.3, r * 0.22), 0.2, math.pi - 0.2, lw + 1)
            pygame.draw.line(s, BLACK, (ex - side * r * 0.16, fy - r * 0.24), (ex + side * r * 0.14, fy - r * 0.18), lw)
    elif state in ("lever", "evil"):
        for side in (-1, 1):
            ex = bx + side * 0.27 * r
            pygame.draw.ellipse(s, BLACK, (ex - r * 0.12, fy - r * 0.04, r * 0.24, r * 0.1))
            pygame.draw.line(s, BLACK, (ex - side * r * 0.2, fy - r * 0.2), (ex + side * r * 0.14, fy - r * 0.08), lw + 1)
    elif state == "shocked":
        for dx in (-0.27, 0.27):
            ex = bx + dx * r
            pygame.draw.circle(s, WHITE, (ex, fy), r * 0.18)
            pygame.draw.circle(s, BLACK, (ex, fy), r * 0.18, lw)
            pygame.draw.circle(s, BLACK, (ex, fy), r * 0.06)
            pygame.draw.arc(s, BLACK, (ex - r * 0.16, fy - r * 0.34, r * 0.32, r * 0.16), 0.2, math.pi - 0.2, lw)
    else:
        for side in (-1, 1):
            ex = bx + side * 0.27 * r
            pygame.draw.circle(s, WHITE, (ex, fy), r * 0.14)
            pygame.draw.circle(s, BLACK, (ex, fy), r * 0.14, 2)
            pygame.draw.circle(s, BLACK, (ex, fy), r * 0.07)
            pygame.draw.line(s, BLACK, (ex - r * 0.15, fy - r * 0.2), (ex + r * 0.15, fy - r * 0.17), lw)
    # Nose + moustache
    pygame.draw.circle(s, (255, 165, 135), (bx, fy + r * 0.14), r * 0.11)
    for side in (-1, 1):
        pts = [(bx, fy + r * 0.23), (bx + side * r * 0.44, fy + r * 0.12 - (r * 0.08 if state == "laughing" else 0)),
               (bx + side * r * 0.52, fy + r * 0.02), (bx + side * r * 0.32, fy + r * 0.32)]
        pygame.draw.polygon(s, (85, 55, 38), pts)
        pygame.draw.polygon(s, BLACK, pts, 2)
    # Mouth
    if state in ("laughing", "crowning"):
        pygame.draw.ellipse(s, BLACK, (bx - r * 0.20, fy + r * 0.30, r * 0.40, r * 0.24))
        pygame.draw.ellipse(s, (230, 80, 95), (bx - r * 0.12, fy + r * 0.40, r * 0.24, r * 0.11))
    elif state in ("lever", "evil"):
        pts = [(bx - r * 0.32, fy + r * 0.28), (bx + r * 0.32, fy + r * 0.28), (bx, fy + r * 0.48)]
        pygame.draw.polygon(s, BLACK, pts)
        pygame.draw.polygon(s, WHITE, [(bx - r * 0.26, fy + r * 0.30), (bx + r * 0.26, fy + r * 0.30), (bx, fy + r * 0.36)])
    elif state == "shocked":
        pygame.draw.ellipse(s, BLACK, (bx - r * 0.11, fy + r * 0.30, r * 0.22, r * 0.26))
    # Bold tilted gold crown
    lift = r * 0.20 * abs(math.sin(t * 10)) if state == "shocked" else 0.0
    _crown(s, bx - r * 0.06, by - r * 0.92 - lift, r * 0.92, tilt_deg=-10.0)
