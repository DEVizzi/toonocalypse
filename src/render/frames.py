"""Frame drawing: eased Ken Burns, code-drawn speech bubbles, word-highlighted captions, SFX words, flash/shake,
"Previously…" banner, moral card and loop tail. Yields RGB frames for ffmpeg."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ASSETS_DIR, settings
from src.render import layout
from src.render.timeline import Line, Timeline

FONT_BUBBLE = ASSETS_DIR / "fonts" / "ComicNeue-Bold.ttf"
FONT_SFX = ASSETS_DIR / "fonts" / "Bangers-Regular.ttf"
FONT_CAPTION = ASSETS_DIR / "fonts" / "Anton-Regular.ttf"
MOVES = ["in", "out", "pan_left", "pan_right", "in_up", "out_down"]


@lru_cache(maxsize=None)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def ease(u: float) -> float:
    return u * u * (3 - 2 * u)


def ken_burns(img: Image.Image, u: float, move: str, amount: float, w: int, h: int) -> Image.Image:
    e = ease(max(0.0, min(1.0, u)))
    if move in ("in", "in_up"):
        z = 1 + amount * e
    elif move in ("out", "out_down"):
        z = 1 + amount * (1 - e)
    else:
        z = 1 + amount
    cw, ch = img.width / z, img.height / z
    free_x, free_y = img.width - cw, img.height - ch
    fx = {"pan_left": 1 - e, "pan_right": e}.get(move, 0.5)
    fy = {"in_up": 0.5 - 0.4 * e, "out_down": 0.1 + 0.4 * e}.get(move, 0.5)
    box = (free_x * fx, free_y * fy, free_x * fx + cw, free_y * fy + ch)
    return img.resize((w, h), Image.BILINEAR, box=box)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


@lru_cache(maxsize=256)
def bubble_image(text: str, position: str, w: int, h: int, slot: int) -> tuple[Image.Image, layout.Box]:
    f = font(str(FONT_BUBBLE), max(18, int(w * 0.045)))
    zone = layout.zones(w, h)["bubbles"]
    rows = wrap(text, f, int(zone.w * 0.78))
    lh = int(f.size * 1.18)
    tw = int(max(f.getlength(r) for r in rows))
    box = layout.bubble_box(w, h, tw, lh * len(rows), position, slot, pad=int(w * 0.03))
    tail = int(w * 0.05)
    canvas = Image.new("RGBA", (box.w + 8, box.h + tail + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((2, 2, box.w + 2, box.h + 2), radius=int(box.h * 0.35), fill="white", outline="black", width=max(3, w // 270))
    sx = int(w * layout.SPEAKER_X.get(position, 0.5)) - box.x0
    sx = max(box.h // 2, min(box.w - box.h // 2, sx))
    d.polygon([(sx - tail // 2, box.h - 2), (sx + tail // 2, box.h - 2), (sx + tail // 4, box.h + tail)], fill="white", outline="black")
    d.line([(sx - tail // 2 + 3, box.h), (sx + tail // 2 - 3, box.h)], fill="white", width=max(4, w // 200))
    y = (box.h - lh * len(rows)) // 2 + 2
    for r in rows:
        d.text(((box.w - f.getlength(r)) / 2 + 2, y), r, font=f, fill="black")
        y += lh
    return canvas, box


@lru_cache(maxsize=512)
def caption_image(chunk: tuple[str, ...], hi: int, w: int, h: int) -> tuple[Image.Image, layout.Box]:
    f = font(str(FONT_CAPTION), max(20, int(w * 0.068)))
    stroke = max(3, w // 200)
    text = " ".join(chunk)
    tw = int(f.getlength(text))
    box = layout.caption_box(w, h, tw, int(f.size * 1.25))
    canvas = Image.new("RGBA", (box.w, box.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    x = (box.w - tw) / 2
    for i, word in enumerate(chunk):
        d.text((x, (box.h - f.size * 1.25) / 2), word, font=f, fill="#FFE14D" if i == hi else "white",
               stroke_width=stroke, stroke_fill="black")
        x += f.getlength(word + " ")
    return canvas, box


@lru_cache(maxsize=64)
def sfx_image(word: str, w: int, h: int) -> tuple[Image.Image, layout.Box]:
    zone = layout.zones(w, h)["sfx"]
    f = font(str(FONT_SFX), max(30, int(w * 0.15)))
    word = word.upper()[:14]
    tw, th = int(f.getlength(word)) + 20, int(f.size * 1.3)
    while tw > zone.w and f.size > 24:
        f = font(str(FONT_SFX), f.size - 6)
        tw, th = int(f.getlength(word)) + 20, int(f.size * 1.3)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((10, 0), word, font=f, fill="#FF4B2B", stroke_width=max(4, w // 150), stroke_fill="#1A1A1A")
    canvas = canvas.rotate(-7, expand=True, resample=Image.BICUBIC)
    x0 = zone.x0 + (zone.w - canvas.width) // 2
    return canvas, layout.Box(x0, zone.y0, x0 + canvas.width, zone.y0 + canvas.height)


def banner(text: str, w: int, h: int, label: str = "Previously…") -> Image.Image:
    f = font(str(FONT_BUBBLE), max(16, int(w * 0.036)))
    zone = layout.zones(w, h)["bubbles"]
    rows = wrap(f"{label} {text}", f, int(zone.w * 0.9))[:2]
    lh = int(f.size * 1.2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((zone.x0, zone.y0, zone.x1, zone.y0 + lh * len(rows) + 24), fill=(255, 225, 77, 235), outline="black", width=3)
    for i, r in enumerate(rows):
        d.text((zone.x0 + 16, zone.y0 + 12 + i * lh), r, font=f, fill="black")
    return img


def moral_card(base: Image.Image, text: str, u: float) -> Image.Image:
    w, h = base.size
    img = base.convert("RGBA")
    shade = Image.new("RGBA", (w, h), (10, 10, 20, int(185 * min(1, u * 4))))
    img.alpha_composite(shade)
    f = font(str(FONT_SFX), max(28, int(w * 0.095)))
    rows = wrap(text, f, int(w * 0.8))
    lh = int(f.size * 1.15)
    y = (h - lh * len(rows)) // 2 - int(h * 0.05)
    d = ImageDraw.Draw(img)
    for r in rows:
        d.text(((w - f.getlength(r)) / 2, y), r, font=f, fill="#FFE14D", stroke_width=max(3, w // 220), stroke_fill="black")
        y += lh
    return img


def active_line(lines: list[Line], t: float, panel_end: float) -> tuple[Line | None, int]:
    """Line whose bubble/caption is showing at t (holds until the next line or panel end)."""
    for i, ln in enumerate(lines):
        nxt = lines[i + 1].start if i + 1 < len(lines) else panel_end
        if ln.start <= t < nxt:
            return ln, i
    return None, -1


def caption_chunk(line: Line, t: float, size: int = 4) -> tuple[tuple[str, ...], int]:
    words = [w["word"] for w in line.words] or line.text.split()
    idx = 0
    for i, w in enumerate(line.words):
        if w["start"] <= t:
            idx = i
    start = (idx // size) * size
    return tuple(words[start:start + size]), idx - start


def frames(tl: Timeline, images: dict[str, Image.Image], w: int, h: int, fps: int) -> Iterator[bytes]:
    v = settings()["video"]
    amount = [v["ken_burns_pct"]["min"] / 100, v["ken_burns_pct"]["max"] / 100]
    shake_frames = v["shake_frames"]
    flash = v["transition_frames"]
    total = int(round(tl.duration * fps))
    last_panel = tl.panels[-1]
    for n in range(total):
        t = n / fps
        ev = next((e for e in tl.panels if e.start <= t < e.end), last_panel)
        src = images[ev.image_key]
        local = n - int(ev.start * fps)
        u = (t - ev.start) / max(0.01, ev.end - ev.start)
        amt = amount[ev.index % 2]
        in_moral = tl.moral_start is not None and t >= tl.moral_start
        in_loop = tl.loop_tail and t >= tl.duration - tl.loop_tail
        if in_loop:  # match-cut back to the hook image at its opening framing -> seamless loop
            frame = ken_burns(images[tl.panels[0].image_key], 0.0, MOVES[0], amount[0], w, h).convert("RGBA")
        elif in_moral:
            base = ken_burns(src, (t - tl.moral_start) / 3.0, "in", 0.05, w, h)
            frame = moral_card(base, tl.moral, (t - tl.moral_start) / 3)
        else:
            frame = ken_burns(src, u, MOVES[ev.index % len(MOVES)], amt, w, h).convert("RGBA")
            if ev.action and local < shake_frames:
                off = 12 if local % 2 == 0 else -12
                frame = frame.transform((w, h), Image.AFFINE, (1, 0, off * w / 1080, 0, 1, -off * h / 1920),
                                        resample=Image.BILINEAR)
            if ev.index == 0 and tl.previously and t < 3.0:
                frame.alpha_composite(banner(tl.previously, w, h))
            ln, _ = active_line(ev.lines, t, ev.end)
            if ln is not None and not ln.narration:
                slot = 1 if (ev.index == 0 and tl.previously and t < 3.0) else 0
                bub, box = bubble_image(ln.text, ln.position, w, h, slot)
                pop = min(1.0, (t - ln.start) * fps / 4)
                if pop < 1.0:
                    s = 0.6 + 0.4 * pop
                    bub = bub.resize((max(1, int(bub.width * s)), max(1, int(bub.height * s))), Image.BILINEAR)
                frame.alpha_composite(bub, (box.x0 + (box.w - bub.width) // 2 if pop < 1 else box.x0, box.y0))
            if ln is not None:
                chunk, hi = caption_chunk(ln, t)
                if chunk:
                    cap, cbox = caption_image(chunk, hi, w, h)
                    frame.alpha_composite(cap, (cbox.x0, cbox.y0))
            if ev.sfx and 0.1 <= t - ev.start <= 1.1:
                sfx, sbox = sfx_image(ev.sfx, w, h)
                frame.alpha_composite(sfx, (sbox.x0, sbox.y0))
            if ev.action and ev.index > 0 and local < flash:
                frame.alpha_composite(Image.new("RGBA", (w, h), (255, 255, 255, int(255 * (1 - local / flash)))))
        yield frame.convert("RGB").tobytes()


def cover(image: Image.Image, words: str, part: int, total: int, out: Path) -> Path:
    w, h = image.size
    img = image.convert("RGBA")
    f = font(str(FONT_SFX), int(w * 0.16))
    small = font(str(FONT_SFX), int(w * 0.075))
    d = ImageDraw.Draw(img)
    words = " ".join(words.split()[:3]).upper()
    rows = wrap(words, f, int(w * 0.86))
    y = int(h * 0.12)
    for r in rows:
        d.text(((w - f.getlength(r)) / 2, y), r, font=f, fill="#FFE14D", stroke_width=w // 90, stroke_fill="black")
        y += int(f.size * 1.05)
    tag = f"PT {part}/{total}"
    d.rounded_rectangle((w - small.getlength(tag) - 90, int(h * 0.72), w - 40, int(h * 0.72) + small.size + 30), radius=20, fill="#E53935")
    d.text((w - small.getlength(tag) - 65, int(h * 0.72) + 12), tag, font=small, fill="white")
    img.convert("RGB").save(out, quality=92)
    return out
