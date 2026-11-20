"""M5 karaoke captions (§8): the current narration line, word-highlighted in sync with the TTS word boundaries, drawn
inside the reserved lower-third safe zone (y = 1440..1620) on a rounded dark pill. Max 2 lines, auto-fit <= 900 px."""
from __future__ import annotations

from functools import lru_cache

import pygame

from src.config import W, font_path

ZONE_TOP, ZONE_BOTTOM = 1440, 1620
MAX_W = 900
BLACK = (17, 17, 17)
WHITE = (255, 255, 255)
HILITE = (255, 214, 0)


@lru_cache(maxsize=8)
def _font(size: int) -> pygame.font.Font:
    return pygame.font.Font(font_path("LuckiestGuy-Regular.ttf"), size)


@lru_cache(maxsize=512)
def _word(word: str, size: int, col: tuple[int, int, int]) -> pygame.Surface:
    f = _font(size)
    base = f.render(word, True, col)
    ring = f.render(word, True, BLACK)
    w = 4
    out = pygame.Surface((base.get_width() + 2 * w, base.get_height() + 2 * w), pygame.SRCALPHA)
    for dx, dy in ((-w, 0), (w, 0), (0, -w), (0, w), (-3, -3), (3, 3), (-3, 3), (3, -3)):
        out.blit(ring, (w + dx, w + dy))
    out.blit(base, (w, w))
    return out


def _layout(words: list[str], size: int) -> list[list[int]]:
    """Greedy wrap into lines of indices; returns [] if it doesn't fit in 2 lines at this size."""
    space = _font(size).size(" ")[0]
    lines: list[list[int]] = [[]]
    width = 0
    for i, wd in enumerate(words):
        ww = _word(wd, size, WHITE).get_width()
        if lines[-1] and width + space + ww > MAX_W - 40:
            lines.append([])
            width = 0
        width += (space if lines[-1] else 0) + ww
        lines[-1].append(i)
    return lines if len(lines) <= 2 else []


def draw_caption(frame: pygame.Surface, speech: list[dict], out_t: float, text_boxes: list | None = None) -> None:
    line = next((ln for ln in speech if ln["t0"] - 0.05 <= out_t <= ln["t1"] + 0.25), None)
    if line is None:
        return
    words = line["text"].split()
    if not words:
        return
    size = 54
    lay = _layout(words, size)
    while not lay and size > 30:
        size -= 4
        lay = _layout(words, size)
    if not lay:
        lay = [list(range(len(words)))]
    timings = line.get("words") or []
    cur = -1
    if timings:
        for i, (w0, _w1, _) in enumerate(timings[: len(words)]):
            if out_t >= w0 - 0.02:
                cur = i
    else:                                           # no word timings: sweep proportionally to the line duration
        frac = (out_t - line["t0"]) / max(0.1, line["t1"] - line["t0"])
        cur = min(len(words) - 1, int(frac * len(words)))
    space = _font(size).size(" ")[0]
    rows = []
    for idxs in lay:
        surfs = [_word(words[i], size, HILITE if i == cur else WHITE) for i in idxs]
        if any(i == cur for i in idxs):
            k = idxs.index(cur)
            surfs[k] = pygame.transform.rotozoom(surfs[k], 0, 1.12)
        rows.append(surfs)
    row_h = max(s.get_height() for r in rows for s in r)
    total_h = row_h * len(rows) + 6 * (len(rows) - 1)
    max_row_w = max(sum(s.get_width() for s in r) + space * (len(r) - 1) for r in rows)
    pill = pygame.Rect(0, 0, min(W - 60, max_row_w + 56), total_h + 28)
    pill.center = (W // 2, (ZONE_TOP + ZONE_BOTTOM) // 2)
    pill.top = max(ZONE_TOP, pill.top)
    pill.bottom = min(ZONE_BOTTOM, pill.bottom)
    plate = pygame.Surface(pill.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (16, 14, 32, 205), plate.get_rect(), border_radius=26)
    pygame.draw.rect(plate, (255, 214, 0, 160), plate.get_rect(), 3, border_radius=26)
    frame.blit(plate, pill)
    y = pill.centery - total_h / 2
    for r in rows:
        rw = sum(s.get_width() for s in r) + space * (len(r) - 1)
        x = W / 2 - rw / 2
        for s in r:
            frame.blit(s, (x, y + (row_h - s.get_height()) / 2))
            x += s.get_width() + space
        y += row_h + 6
    if text_boxes is not None:
        text_boxes.append(pill)
