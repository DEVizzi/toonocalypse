"""Procedural cartoon faces (§9.4). Every face is drawn with pygame primitives relative to a body radius."""
from __future__ import annotations

import math

import pygame

from src.characters.roster import EXPRESSIONS  # noqa: F401  (pygame-free source of truth)
BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
SWEAT = (110, 190, 255)
TONGUE = (255, 105, 135)
GLOW = (120, 255, 220)


def _eye(s: pygame.Surface, c: tuple[float, float], r: float, look: tuple[float, float], lid: float = 0.0,
         pupil: float = 0.48, lid_colour: tuple[int, int, int] = (0, 0, 0)) -> None:
    pygame.draw.circle(s, WHITE, c, r)
    pygame.draw.circle(s, BLACK, c, r, max(2, int(r * 0.18)))
    px, py = c[0] + look[0] * r * 0.35, c[1] + look[1] * r * 0.35
    pygame.draw.circle(s, BLACK, (px, py), r * pupil)
    pygame.draw.circle(s, WHITE, (px - r * 0.15, py - r * 0.18), max(1, r * 0.14))
    if lid > 0:  # upper eyelid (half-closed = smug / chill)
        rect = pygame.Rect(c[0] - r - 1, c[1] - r - 1, 2 * r + 2, (2 * r + 2) * lid)
        pygame.draw.rect(s, lid_colour, rect)
        pygame.draw.line(s, BLACK, (c[0] - r, rect.bottom), (c[0] + r, rect.bottom), max(2, int(r * 0.2)))


def _brows(s, cx, cy, r, ey, kind: str, w: int) -> None:
    dx, L = r * 0.36, r * 0.32
    y = cy - ey - r * 0.36
    if kind == "angry":    # V brows
        pygame.draw.line(s, BLACK, (cx - dx - L / 2, y - 3), (cx - dx + L / 2, y + 5), w)
        pygame.draw.line(s, BLACK, (cx + dx + L / 2, y - 3), (cx + dx - L / 2, y + 5), w)
    elif kind == "worried":
        pygame.draw.line(s, BLACK, (cx - dx - L / 2, y + 4), (cx - dx + L / 2, y - 3), w)
        pygame.draw.line(s, BLACK, (cx + dx + L / 2, y + 4), (cx + dx - L / 2, y - 3), w)
    elif kind == "heavy":
        pygame.draw.line(s, BLACK, (cx - dx - L / 2, y), (cx + dx + L / 2, y), w + 2)
    elif kind == "raised":
        pygame.draw.arc(s, BLACK, (cx - dx - L / 2, y - 6, L, 10), 0.3, 2.8, w)
        pygame.draw.arc(s, BLACK, (cx + dx - L / 2, y - 6, L, 10), 0.3, 2.8, w)


def _mouth(s, cx, my, r, kind: str, w: int) -> None:
    mw = r * 0.62
    if kind == "smile":
        pygame.draw.arc(s, BLACK, (cx - mw / 2, my - mw * 0.35, mw, mw * 0.6), math.pi * 1.1, math.pi * 1.9, w)
    elif kind == "grin":
        pts = [(cx - mw / 2, my - 2), (cx + mw / 2, my - 2), (cx + mw * 0.3, my + mw * 0.32), (cx - mw * 0.3, my + mw * 0.32)]
        pygame.draw.polygon(s, BLACK, pts)
        pygame.draw.polygon(s, WHITE, [(cx - mw * 0.4, my), (cx + mw * 0.4, my), (cx + mw * 0.3, my + mw * 0.1),
                                       (cx - mw * 0.3, my + mw * 0.1)])
    elif kind == "smirk":
        pygame.draw.arc(s, BLACK, (cx - mw * 0.2, my - mw * 0.3, mw * 0.7, mw * 0.5), math.pi * 1.15, math.pi * 1.85, w)
    elif kind == "frown":
        pygame.draw.arc(s, BLACK, (cx - mw / 2, my, mw, mw * 0.5), math.pi * 0.15, math.pi * 0.85, w)
    elif kind == "flat":
        pygame.draw.line(s, BLACK, (cx - mw * 0.35, my + 2), (cx + mw * 0.35, my + 2), w)
    elif kind == "wobble":
        pts = [(cx - mw * 0.4 + i * mw * 0.1, my + 3 + (3 if i % 2 else -3)) for i in range(9)]
        pygame.draw.lines(s, BLACK, False, pts, max(2, w - 1))
    elif kind == "O":
        pygame.draw.ellipse(s, BLACK, (cx - mw * 0.22, my - mw * 0.1, mw * 0.44, mw * 0.55))
    elif kind == "open":  # celebrating / laughing
        pygame.draw.ellipse(s, BLACK, (cx - mw * 0.42, my - mw * 0.12, mw * 0.84, mw * 0.6))
        pygame.draw.ellipse(s, TONGUE, (cx - mw * 0.22, my + mw * 0.18, mw * 0.44, mw * 0.26))
    elif kind == "tongue":
        pygame.draw.line(s, BLACK, (cx - mw * 0.4, my), (cx + mw * 0.4, my), w)
        pygame.draw.ellipse(s, TONGUE, (cx - mw * 0.05, my - 1, mw * 0.32, mw * 0.4))
        pygame.draw.ellipse(s, BLACK, (cx - mw * 0.05, my - 1, mw * 0.32, mw * 0.4), max(1, w - 2))


def _x_eye(s, c, r, w):
    pygame.draw.line(s, BLACK, (c[0] - r, c[1] - r), (c[0] + r, c[1] + r), w)
    pygame.draw.line(s, BLACK, (c[0] - r, c[1] + r), (c[0] + r, c[1] - r), w)


def _spiral_eye(s, c, r, w, t):
    pts = []
    for i in range(28):
        a = i * 0.55 + t * 9
        rr = r * i / 28
        pts.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr))
    pygame.draw.lines(s, BLACK, False, pts, max(2, w - 1))


def _star_eye(s, c, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r * (1.25 if i % 2 == 0 else 0.5)
        pts.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr))
    pygame.draw.polygon(s, (255, 214, 0), pts)
    pygame.draw.polygon(s, BLACK, pts, 2)


def _sweat(s, x, y, r):
    pygame.draw.circle(s, SWEAT, (x, y + r * 0.2), r * 0.18)
    pygame.draw.polygon(s, SWEAT, [(x - r * 0.17, y + r * 0.15), (x + r * 0.17, y + r * 0.15), (x, y - r * 0.2)])
    pygame.draw.circle(s, BLACK, (x, y + r * 0.2), r * 0.18, 1)


# signature default faces: (eye lid, brows, mouth, extra)
DEFAULT_FACES = {
    "smug": (0.45, "raised", "smirk", None), "nervous": (0.0, "worried", "wobble", "sweat"),
    "grinning": (0.0, None, "grin", None), "smirking": (0.25, "angry", "smirk", None),
    "scowling": (0.15, "angry", "frown", None), "focused": (0.3, "angry", "flat", None),
    "visor": (0.0, None, "flat", "visor"), "chill": (0.5, None, "smile", None),
    "furrowed": (0.2, "heavy", "frown", None), "dizzy": (0.0, None, "wobble", "mismatch"),
}


def draw_face(s: pygame.Surface, cx: float, cy: float, r: float, expression: str, face_style: str,
              body_colour: tuple[int, int, int], look: tuple[float, float] = (0.0, 0.0), t: float = 0.0) -> None:
    er = max(4.6, r * 0.3)
    r = max(r, 19.0)  # small heroes (Pip) get a slightly oversized, readable face
    ey = r * 0.12
    eyes = [(cx - r * 0.36, cy - ey), (cx + r * 0.36, cy - ey)]
    w = max(2, int(r * 0.11))
    my = cy + r * 0.38
    if expression == "neutral":
        lid, brows, mouth, extra = DEFAULT_FACES.get(face_style, (0.0, None, "smile", None))
        if extra == "visor":
            bar = pygame.Rect(cx - r * 0.78, cy - ey - er * 0.8, r * 1.56, er * 1.6)
            pygame.draw.rect(s, BLACK, bar, border_radius=int(er * 0.8))
            pygame.draw.rect(s, GLOW, bar.inflate(-r * 0.25, -er * 1.05), border_radius=3)
        elif extra == "mismatch":
            _eye(s, eyes[0], er * 1.2, (math.sin(t * 7), 0.3))
            _eye(s, eyes[1], er * 0.75, (-0.4, math.cos(t * 5)))
        else:
            for e in eyes:
                _eye(s, e, er, look, lid, lid_colour=body_colour)
        if brows:
            _brows(s, cx, cy, r, ey, brows, w)
        _mouth(s, cx, my, r, mouth, w)
        if extra == "sweat":
            _sweat(s, cx + r * 0.75, cy - r * 0.45, r)
    elif expression == "happy":
        for e in eyes:
            pygame.draw.arc(s, BLACK, (e[0] - er, e[1] - er * 0.6, er * 2, er * 1.6), 0.2, math.pi - 0.2, w + 1)
        _mouth(s, cx, my, r, "open", w)
    elif expression == "scared":
        for e in eyes:
            _eye(s, e, er * 1.25, (0, -0.2), pupil=0.3)
        _brows(s, cx, cy, r, ey + er * 0.3, "worried", w)
        _mouth(s, cx, my, r, "O", w)
        _sweat(s, cx + r * 0.78, cy - r * 0.5, r)
    elif expression == "dizzy":
        for e in eyes:
            _spiral_eye(s, e, er, w, t)
        _mouth(s, cx, my, r, "wobble", w)
    elif expression == "angry":
        for e in eyes:
            _eye(s, e, er, look, 0.3, lid_colour=body_colour)
        _brows(s, cx, cy, r, ey, "angry", w + 1)
        _mouth(s, cx, my, r, "frown", w)
    elif expression == "celebrating":
        for e in eyes:
            _star_eye(s, e, er)
        _mouth(s, cx, my, r, "open", w)
    elif expression == "eliminated":
        for e in eyes:
            _x_eye(s, e, er * 0.8, w)
        _mouth(s, cx, my, r, "tongue", w)
