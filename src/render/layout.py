"""Pure layout math for bubbles, captions and SFX: safe zones and collision checks (§9). Tested without rendering."""
from __future__ import annotations

from dataclasses import dataclass

from src.common.config import settings


@dataclass(frozen=True)
class Box:
    x0: int
    y0: int
    x1: int
    y1: int

    def overlaps(self, o: "Box") -> bool:
        return not (self.x1 <= o.x0 or o.x1 <= self.x0 or self.y1 <= o.y0 or o.y1 <= self.y0)

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0


def zones(w: int, h: int) -> dict[str, Box]:
    sz = settings()["safe_zone"]
    top = int(h * sz["top_clear_pct"] / 100)
    bottom = int(h * (1 - sz["bottom_clear_pct"] / 100))
    margin = int(w * sz["sfx_margin_pct"] / 100)
    bubble_bottom = top + int(h * sz["bubble_area_top_pct"] / 100)
    return {
        "usable": Box(margin, top, w - margin, bottom),
        "bubbles": Box(margin, top, w - margin, bubble_bottom),
        "captions": Box(margin, int(h * 0.60), w - margin, bottom),
        "sfx": Box(margin, bubble_bottom, w - margin, int(h * 0.58)),
    }


SPEAKER_X = {"left": 0.27, "center": 0.5, "right": 0.73}


def bubble_box(w: int, h: int, text_w: int, text_h: int, position: str, slot: int = 0, pad: int = 36) -> Box:
    """Place a bubble inside the bubble zone, horizontally near its speaker; slot stacks a second bubble below."""
    z = zones(w, h)["bubbles"]
    bw, bh = min(z.w, text_w + 2 * pad), text_h + 2 * pad
    cx = int(w * SPEAKER_X.get(position, 0.5))
    x0 = max(z.x0, min(z.x1 - bw, cx - bw // 2))
    y0 = z.y0 + slot * (bh + 18)
    y0 = min(y0, z.y1 - bh) if bh <= z.h else z.y0
    return Box(x0, y0, x0 + bw, y0 + bh)


def caption_box(w: int, h: int, text_w: int, text_h: int, pad: int = 24) -> Box:
    z = zones(w, h)["captions"]
    bw, bh = min(z.w, text_w + 2 * pad), text_h + 2 * pad
    x0 = (w - bw) // 2
    y1 = z.y1 - int(h * 0.04)
    return Box(x0, y1 - bh, x0 + bw, y1)


def check_layout(w: int, h: int, boxes: dict[str, list[Box]]) -> list[str]:
    """Return problems: anything outside the usable safe area, or bubbles/captions/SFX overlapping each other."""
    z = zones(w, h)["usable"]
    errs = []
    flat = [(k, b) for k, bs in boxes.items() for b in bs]
    for k, b in flat:
        if b.x0 < z.x0 or b.y0 < z.y0 or b.x1 > z.x1 or b.y1 > z.y1:
            errs.append(f"{k} outside safe zone: {b}")
    for i, (ka, a) in enumerate(flat):
        for kb, b in flat[i + 1:]:
            if ka != kb and a.overlaps(b):
                errs.append(f"{ka} overlaps {kb}")
    return errs
