"""M5/v3.4 Modern Shorts Borderless Pop Captions (y = 1480..1620):
- Zero dark background box.
- Bold uppercase comic text (64px, thick 7px black outline + soft drop shadow) grouped into 3-4 word chunks synced to
  WordBoundary timestamps.
- Active spoken word pops to 1.12x scale in bright yellow (#FACC15).
- Hides cleanly 0.20s after the narrator stops speaking (zero stale captions)."""
from __future__ import annotations

import math
from functools import lru_cache

import pygame

from src.config import LAYOUT, W, font_path

ZONE_TOP, ZONE_BOTTOM = LAYOUT["captions"]["y"]
MAX_W = 960
BLACK = (12, 12, 16)
WHITE = (255, 255, 255)
HILITE = (250, 204, 21)   # #FACC15 bright yellow


@lru_cache(maxsize=8)
def _font(size: int) -> pygame.font.Font:
    return pygame.font.Font(font_path("LuckiestGuy-Regular.ttf"), size)


@lru_cache(maxsize=512)
def _word_surf(word: str, size: int, col: tuple[int, int, int], outline_w: int = 7) -> pygame.Surface:
    """Renders one uppercase comic word with soft drop shadow + thick 7px black outline."""
    f = _font(size)
    base = f.render(word, True, col)
    ring = f.render(word, True, BLACK)
    sh_dark = f.render(word, True, (0, 0, 0))
    sh_dark.set_alpha(135)
    sh_soft = f.render(word, True, (0, 0, 0))
    sh_soft.set_alpha(75)

    pad_x = outline_w + 8
    pad_y = outline_w + 11
    out = pygame.Surface((base.get_width() + 2 * pad_x, base.get_height() + 2 * pad_y), pygame.SRCALPHA)
    ox, oy = pad_x, outline_w + 2

    # Soft multi-tap drop shadow
    for sdx, sdy in ((4, 7), (6, 9), (2, 8)):
        out.blit(sh_soft, (ox + sdx, oy + sdy))
    out.blit(sh_dark, (ox + 4, oy + 7))

    # Thick 7px 16-direction comic black outline
    for k in range(16):
        ang = k * math.pi / 8.0
        dx = round(math.cos(ang) * outline_w)
        dy = round(math.sin(ang) * outline_w)
        out.blit(ring, (ox + dx, oy + dy))
    for k in range(8):
        ang = k * math.pi / 4.0
        dx = round(math.cos(ang) * (outline_w * 0.55))
        dy = round(math.sin(ang) * (outline_w * 0.55))
        out.blit(ring, (ox + dx, oy + dy))

    out.blit(base, (ox, oy))
    return out


def chunk_indices(n: int) -> list[list[int]]:
    """Splits n words into balanced 2-4 word chunks (zero 1-word orphans)."""
    if n <= 0:
        return []
    if n <= 4:
        return [list(range(n))]
    out: list[list[int]] = []
    i = 0
    while i < n:
        rem = n - i
        if rem <= 4:
            step = rem
        elif rem in (5, 6, 9):
            step = 3
        else:
            step = 4
        out.append(list(range(i, i + step)))
        i += step
    return out


def _row_width(words: list[str], idxs: list[int], size: int, space: int) -> int:
    if not idxs:
        return 0
    return sum(_word_surf(words[idx], size, WHITE).get_width() for idx in idxs) + space * (len(idxs) - 1)


def _wrap_chunk(words: list[str], idxs: list[int], size: int) -> list[list[int]]:
    """v4.0 Balanced Caption Wrapping:
    - 1..3 word chunks stay strictly on a single line (step down font size if > MAX_W; NEVER wrap 2+1!).
    - 4-word chunks stay on 1 line if compact, else split strictly as balanced 2+2 (NEVER 3+1 or 1+3!)."""
    space = max(10, _font(size).size(" ")[0] - 4)
    if _row_width(words, idxs, size, space) <= MAX_W:
        return [list(idxs)]
    if len(idxs) == 4:
        top_half, bot_half = idxs[:2], idxs[2:]
        if _row_width(words, top_half, size, space) <= MAX_W and _row_width(words, bot_half, size, space) <= MAX_W:
            return [top_half, bot_half]
    return []


def draw_caption(frame: pygame.Surface, speech: list[dict], out_t: float, text_boxes: list | None = None) -> None:
    # Hide captions strictly 0.20s after speech ends
    line = next((ln for ln in speech if ln["t0"] - 0.03 <= out_t <= ln["t1"] + 0.20), None)
    if line is None:
        return
    words = [w.upper() for w in line["text"].split() if w.strip()]
    if not words:
        return

    timings = line.get("words") or []
    cur = 0
    if timings:
        for i, (w0, _w1, _) in enumerate(timings[: len(words)]):
            if out_t >= w0 - 0.02:
                cur = i
    else:
        frac = max(0.0, (out_t - line["t0"]) / max(0.1, line["t1"] - line["t0"]))
        cur = min(len(words) - 1, int(frac * len(words)))

    chunks = chunk_indices(len(words))
    active_chunk = next((ch for ch in chunks if cur in ch), chunks[-1])

    size = 64
    lay = _wrap_chunk(words, active_chunk, size)
    while not lay and size > 34:
        size -= 4
        lay = _wrap_chunk(words, active_chunk, size)
    if not lay:
        lay = [active_chunk[:2], active_chunk[2:]] if len(active_chunk) == 4 else [active_chunk]

    space = max(10, _font(size).size(" ")[0] - 4)
    rows: list[list[pygame.Surface]] = []
    for row_idxs in lay:
        surfs: list[pygame.Surface] = []
        for i in row_idxs:
            active = i == cur and out_t <= line["t1"] + 0.06
            s = _word_surf(words[i], size, HILITE if active else WHITE, outline_w=7)
            if active:
                s = pygame.transform.rotozoom(s, 0.0, 1.12)
            surfs.append(s)
        rows.append(surfs)

    row_h = max(s.get_height() for r in rows for s in r)
    total_h = row_h * len(rows) + 2 * (len(rows) - 1)
    cy_zone = (ZONE_TOP + ZONE_BOTTOM) / 2.0
    y = max(float(ZONE_TOP - 8), min(float(ZONE_BOTTOM - total_h + 8), cy_zone - total_h / 2.0))

    bbox_union: pygame.Rect | None = None
    for r in rows:
        rw = sum(s.get_width() for s in r) + space * (len(r) - 1)
        x = W / 2.0 - rw / 2.0
        for s in r:
            ry = y + (row_h - s.get_height()) / 2.0
            rect = frame.blit(s, (int(x), int(ry)))
            bbox_union = rect if bbox_union is None else bbox_union.union(rect)
            x += s.get_width() + space
        y += row_h + 2

    if text_boxes is not None and bbox_union is not None:
        text_boxes.append(bbox_union)
