"""The Tuno Report 16:9 compositor (1920x1080 @ 30 fps): broadcast-style long-form recap with MC Tuno hosting.

Running order: cold-open freeze-frame gag -> title -> roster / "previously" -> every race of the part (real replayed
footage on the left in the Shorts' own vertical look, MC Tuno + facts + results on the right) with a mid-part table
check -> The Tunos (awards) -> [champion ceremony] -> title-race bar chart -> table -> next-part teaser -> end screen.
Audio: edge-tts MC Tuno voice (lip-synced), procedural SFX from real race events, theme music ducked under the voice.
Rendering never touches `state/`.
"""
from __future__ import annotations

import math
import os
import random
import subprocess
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

from src.audio import music, sfx  # noqa: E402
from src.audio.sfx import SR  # noqa: E402
from src.characters.roster import HERO_BY_KEY, HEROES  # noqa: E402
from src.characters.tuno import draw_tuno  # noqa: E402
from src.games.themes import for_season  # noqa: E402
from src.recap.comedy import Award, Line, Writer, name, plural, punch_up_winners  # noqa: E402
from src.recap.data import RaceInfo, SeasonRecap  # noqa: E402
from src.rendering import effects  # noqa: E402
from src.rendering import hud as H  # noqa: E402

W, HH, FPS = 1920, 1080, 30
PHONE = pygame.Rect(96, 0, 608, 1080)
RX0, RX1 = 760, 1860
NAVY = (15, 23, 42)
NAVY2 = (30, 41, 74)
GOLD = (250, 204, 21)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
INK = (17, 17, 24)
MEDALS = [(255, 204, 64), (205, 212, 226), (214, 138, 72)]
LUCKY, BANGERS, FREDOKA, COMIC = "LuckiestGuy-Regular.ttf", "Bangers-Regular.ttf", "Fredoka.ttf", "ComicNeue-Bold.ttf"
GOAL_LABELS = {"reach_finish": "FIRST TO THE FINISH", "last_one_standing": "LAST BALL STANDING",
               "collect_items": "CROWN RUSH", "hold_a_zone": "KING OF THE HILL", "push_others_out": "SHOVE 'EM OUT",
               "survive_timer": "SURVIVE THE CLOCK", "hot_potato_bomb": "HOT POTATO BOMB"}
STAGE_LABELS = {"play_in": "PLAY-IN", "qualifier_1": "QUALIFIER 1", "qualifier_2": "QUALIFIER 2",
                "grand_final": "GRAND FINAL"}
CHAOS_LABELS = {"betrayal": "THE BETRAYAL", "elimination": "THE OOPSIE", "crush_hit": "THE PANCAKING",
                "impact": "THE BONK", "trait": "THE SHOWBOATING"}


# ---------------------------------------------------------------------------------------------- text & sprites
@lru_cache(maxsize=4096)
def txt(text: str, size: int, fill=WHITE, outline=BLACK, width: int = 4, face: str = LUCKY) -> pygame.Surface:
    return H.outlined(text, size, fill=fill, outline=outline, width=width, face=face)


@lru_cache(maxsize=2048)
def plain(text: str, size: int, color=INK, face: str = FREDOKA) -> pygame.Surface:
    return H.font(size, face).render(text, True, color)


def fit(s: pygame.Surface, max_w: int) -> pygame.Surface:
    return H.fit_width(s, max_w)


def wrap(text: str, size: int, max_w: int, face: str = FREDOKA) -> list[str]:
    f = H.font(size, face)
    words, rows, cur = text.split(), [], ""
    for w_ in words:
        cand = (cur + " " + w_).strip()
        if f.size(cand)[0] <= max_w or not cur:
            cur = cand
        else:
            rows.append(cur)
            cur = w_
    if cur:
        rows.append(cur)
    return rows


@lru_cache(maxsize=512)
def ball(key: str, diameter: int, expression: str = "happy") -> pygame.Surface:
    """Crisp in-game ball look (vector-drawn at the target size, never upscaled)."""
    from src.rendering import balls

    hero = HERO_BY_KEY[key]
    pad = int(diameter * 0.9)
    s = pygame.Surface((diameter + pad, diameter + pad), pygame.SRCALPHA)
    zoom = (diameter / 2) / max(1.0, max(hero.size))
    balls.draw_ball(s, hero, None, (s.get_width() / 2, s.get_height() / 2), 0.0, 0.0, (0, 0), 0.0, expression, "none",
                    0.0, zoom)
    return s


@lru_cache(maxsize=16)
def dummy_ball(diameter: int, expression: str = "celebrating") -> pygame.Surface:
    """Crash test dummy in its in-game look."""
    from src.characters.roster import Extra
    from src.rendering import balls

    ex = Extra(1)
    pad = int(diameter * 0.9)
    s = pygame.Surface((diameter + pad, diameter + pad), pygame.SRCALPHA)
    balls.draw_ball(s, None, ex, (s.get_width() / 2, s.get_height() / 2), 0.0, 0.0, (0, 0), 0.0, expression, "none",
                    0.0, (diameter / 2) / ex.radius)
    return s


def blit_c(dst: pygame.Surface, src: pygame.Surface, center) -> pygame.Rect:
    r = src.get_rect(center=(int(center[0]), int(center[1])))
    dst.blit(src, r)
    return r


def panel(dst: pygame.Surface, rect: pygame.Rect, fill=NAVY, border=GOLD, radius: int = 26, alpha: int = 238,
          bw: int = 4) -> None:
    sh = pygame.Surface((rect.w + 16, rect.h + 16), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 110), sh.get_rect().inflate(-8, -8).move(4, 8), border_radius=radius + 4)
    dst.blit(sh, (rect.x - 8, rect.y - 8))
    body = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(body, (*fill, alpha), body.get_rect(), border_radius=radius)
    dst.blit(body, rect.topleft)
    pygame.draw.rect(dst, BLACK, rect.inflate(4, 4), 3, border_radius=radius + 2)
    pygame.draw.rect(dst, border, rect, bw, border_radius=radius)


def chip(text: str, color, size: int = 30, fg=WHITE) -> pygame.Surface:
    t = txt(text, size, fill=fg, width=3)
    s = pygame.Surface((t.get_width() + 30, t.get_height() + 10), pygame.SRCALPHA)
    pygame.draw.rect(s, BLACK, s.get_rect(), border_radius=16)
    pygame.draw.rect(s, color, s.get_rect().inflate(-6, -6), border_radius=14)
    s.blit(t, t.get_rect(center=(s.get_width() / 2, s.get_height() / 2 + 1)))
    return s


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def pop(x: float) -> float:
    """Overshoot scale-in 0 -> 1.12 -> 1."""
    x = max(0.0, min(1.0, x))
    return 1 + 0.12 * math.sin(x * math.pi) if x < 1 else 1.0


def mix(a, b, k: float):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


# ---------------------------------------------------------------------------------------------- backdrops
def studio_bg(theme, seed: int = 1) -> pygame.Surface:
    """Theme sky gradient + dusk overlay + castle skyline + light shafts + vignette (pre-rendered once)."""
    s = pygame.Surface((W, HH))
    top, bot = mix(theme.sky_top, NAVY, 0.45), mix(theme.sky_bottom, NAVY, 0.55)
    for y in range(HH):
        pygame.draw.line(s, mix(top, bot, y / HH), (0, y), (W, y))
    rays = pygame.Surface((W, HH), pygame.SRCALPHA)
    for k, x in enumerate((260, 760, 1300, 1700)):
        pygame.draw.polygon(rays, (255, 255, 255, 16 if k % 2 else 10), [(x - 60, 0), (x + 60, 0), (x + 420, HH), (x + 120, HH)])
    s.blit(rays, (0, 0))
    rng = random.Random(seed)
    sky_col = mix(theme.castle, NAVY, 0.62)
    edge = mix(theme.castle, NAVY, 0.4)
    x = -40
    while x < W + 40:
        tw = rng.randint(70, 150)
        th = rng.randint(120, 300)
        rect = pygame.Rect(x, HH - th, tw, th)
        pygame.draw.rect(s, sky_col, rect)
        for cx in range(rect.left, rect.right, 26):
            pygame.draw.rect(s, sky_col, (cx, rect.top - 18, 14, 18))
        if rng.random() < 0.45:
            pygame.draw.polygon(s, sky_col, [(rect.left - 8, rect.top - 18), (rect.right + 8, rect.top - 18),
                                             (rect.centerx, rect.top - 18 - tw * 0.9)])
            pygame.draw.rect(s, mix(theme.accent, NAVY, 0.25), (rect.centerx - 6, rect.top + 20, 12, 22))
        pygame.draw.line(s, edge, rect.topleft, rect.bottomleft, 2)
        x += tw + rng.randint(-10, 30)
    arr = pygame.surfarray.pixels3d(s)                   # smooth radial vignette (W, H, 3)
    xs = np.linspace(-1.0, 1.0, W, dtype=np.float32)[:, None]
    ys = np.linspace(-1.0, 1.0, HH, dtype=np.float32)[None, :]
    d = np.sqrt((xs * 0.92) ** 2 + (ys * 1.08) ** 2)
    f = 1.0 - 0.42 * np.clip((d - 0.55) / 0.85, 0.0, 1.0) ** 1.6
    arr[:] = (arr.astype(np.float32) * f[:, :, None]).astype(np.uint8)
    del arr
    return s


def sunburst(dst: pygame.Surface, center, t: float, col_a, col_b, n: int = 18, r: float = 1400) -> None:
    cx, cy = center
    for i in range(n):
        a0 = t * 0.35 + i * 2 * math.pi / n
        a1 = a0 + math.pi / n
        pygame.draw.polygon(dst, col_a if i % 2 else col_b,
                            [(cx, cy), (cx + math.cos(a0) * r, cy + math.sin(a0) * r), (cx + math.cos(a1) * r, cy + math.sin(a1) * r)])


# ---------------------------------------------------------------------------------------------- MC Tuno corner
def tuno_booth(dst: pygame.Surface, rect: pygame.Rect, state: str, t: float, rms: float, scale: float) -> None:
    panel(dst, rect, fill=(28, 20, 56), border=GOLD, radius=28, alpha=250)
    inner = rect.inflate(-14, -14)
    buf = pygame.Surface(inner.size, pygame.SRCALPHA)
    for x in range(10, inner.w, 30):
        pygame.draw.line(buf, (40, 30, 80, 255), (x, 0), (x, inner.h), 6)
    pygame.draw.polygon(buf, (90, 56, 160, 120), [(0, 0), (inner.w * 0.35, 0), (inner.w * 0.85, inner.h), (inner.w * 0.4, inner.h)])
    pygame.draw.circle(buf, (0, 229, 255, 50), (int(inner.w * 0.58), int(inner.h * 0.45)), int(min(inner.size) * 0.36), 6)
    draw_tuno(buf, inner.w * 0.55, inner.h - 4, state, t, scale=scale, voice_rms=rms)
    mask = pygame.Surface(inner.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=22)
    buf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    dst.blit(buf, inner.topleft)
    live = chip("MC TUNO", (220, 38, 38), 24)
    dst.blit(live, (rect.x + 18, rect.y + 16))


def bubble(dst: pygame.Surface, rect: pygame.Rect, text: str, tail_to: tuple[int, int] | None = None,
           size: int = 40) -> None:
    if not text:
        return
    rows = wrap(text, size, rect.w - 56, COMIC)
    while len(rows) > 4 and size > 26:
        size -= 3
        rows = wrap(text, size, rect.w - 56, COMIC)
    lh = int(size * 1.18)
    h = max(110, lh * len(rows) + 46)
    r = pygame.Rect(rect.x, rect.y, rect.w, h)
    if tail_to:
        base_x = r.left + 40 if tail_to[0] < r.centerx else r.right - 40
        pygame.draw.polygon(dst, BLACK, [(base_x - 26, r.bottom - 6), (base_x + 26, r.bottom - 6), (tail_to[0], tail_to[1])])
        pygame.draw.polygon(dst, WHITE, [(base_x - 18, r.bottom - 10), (base_x + 18, r.bottom - 10),
                                         (tail_to[0] + (8 if tail_to[0] < base_x else -8), tail_to[1] - 10)])
    pygame.draw.rect(dst, BLACK, r.inflate(8, 8), border_radius=30)
    pygame.draw.rect(dst, WHITE, r, border_radius=26)
    y = r.y + 23
    for row in rows:
        s = plain(row, size, INK, COMIC)
        dst.blit(s, s.get_rect(midtop=(r.centerx, y)))
        y += lh


def lower_third(dst: pygame.Surface, text: str, t_in: float) -> None:
    """Bottom-left caption bar for non-race segments (MC Tuno corner sits bottom-right)."""
    if not text:
        return
    rows = wrap(text, 38, 1180, COMIC)[:2]
    h = 30 + 46 * len(rows)
    k = ease(t_in / 0.18)
    r = pygame.Rect(60, HH - 40 - h + int((1 - k) * 40), 1300, h)
    panel(dst, r, fill=WHITE, border=INK, radius=22, alpha=245, bw=4)
    y = r.y + 15
    for row in rows:
        dst.blit(plain(row, 38, INK, COMIC), (r.x + 30, y))
        y += 46


# ---------------------------------------------------------------------------------------------- clip reader
class ClipReader:
    """Sequential RGB frame reader for a worker clip (ffmpeg decode pipe). Holds the last frame past the end."""

    def __init__(self, path: str | None, w: int = 608, h: int = 1080) -> None:
        self.w, self.h, self.idx = w, h, -1
        self.last: pygame.Surface | None = None
        self.proc = None
        if path and Path(path).is_file():
            self.proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def frame(self, i: int) -> pygame.Surface | None:
        while self.proc is not None and self.idx < i:
            assert self.proc.stdout is not None
            buf = self.proc.stdout.read(self.w * self.h * 3)
            if len(buf) < self.w * self.h * 3:
                self.close()
                break
            self.last = pygame.image.frombuffer(buf, (self.w, self.h), "RGB").copy()
            self.idx += 1
        return self.last

    def close(self) -> None:
        if self.proc is not None:
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
                self.proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
            self.proc = None


# ---------------------------------------------------------------------------------------------- voice bank
class VoiceBank:
    """edge-tts MC Tuno lines (cached). Falls back to a word-count duration estimate when TTS is unavailable."""

    def __init__(self, use_tts: bool = True, log=print) -> None:
        self.cache: dict[tuple[str, str], tuple[np.ndarray | None, float]] = {}
        self.log = log
        self.use_tts = use_tts
        self.ok = 0
        self.failed = 0
        if use_tts:
            from src.narration import tts
            self.use_tts = tts.available()
            if not self.use_tts:
                log("  [RECAP VOICE] edge-tts/ffmpeg unavailable -> silent timing estimates")

    def get(self, line: Line) -> tuple[np.ndarray | None, float]:
        key = (line.text, line.style)
        if key not in self.cache:
            pcm = None
            if self.use_tts:
                from src.narration import tts
                res = tts.synthesize(line.text, line.style)
                if res is not None:
                    pcm = res[0]
            if pcm is not None:
                self.ok += 1
                self.cache[key] = (pcm, pcm.size / SR)
            else:
                self.failed += 1 if self.use_tts else 0
                self.cache[key] = (None, 0.35 + len(line.text.split()) / 3.3)
        return self.cache[key]

    def dur(self, line: Line) -> float:
        return self.get(line)[1]


# ---------------------------------------------------------------------------------------------- segments
@dataclass
class Segment:
    name: str
    duration: float
    draw: Callable[[pygame.Surface, float, "Ctx"], None]
    voice: list[tuple[float, Line]] = field(default_factory=list)
    sfx: list[tuple[float, str, float]] = field(default_factory=list)
    chapter: str | None = None
    caption_mode: str = "lower"            # lower | none (race segments draw their own speech bubble)
    on_start: Callable[[], None] | None = None
    on_end: Callable[[], None] | None = None


@dataclass
class Ctx:
    index: int
    rms: float
    line: Line | None
    line_t: float          # seconds since the current line started


SFX_LIB: dict[str, Callable[[], np.ndarray]] = {
    "record_scratch": sfx.record_scratch, "airhorn": sfx.airhorn, "fanfare": sfx.fanfare, "cheer": sfx.cheer,
    "grand_fanfare": sfx.grand_fanfare, "sad": sfx.sad_slide_whistle, "pop": sfx.pop, "ding": sfx.ding,
    "riser": sfx.riser, "rewind": sfx.rewind, "bonk": lambda: sfx.bonk(1.0), "thud": sfx.thud,
    "comic_bonk": sfx.comic_bonk, "fall": lambda: sfx.fall_whistle(), "fall_short": lambda: sfx.fall_whistle(0.55),
    "splat": sfx.splat, "betrayal": sfx.betrayal_sting, "glitch": sfx.glitch_zip, "zap": sfx.zap,
    "crowd_ooh": sfx.crowd_ooh, "gate": sfx.gate_clank, "boing": sfx.boing,
}


class RecapVideo:
    def __init__(self, recap: SeasonRecap, clips: dict[int, dict], cold: dict | None, out_dir: Path,
                 use_tts: bool = True, log=print) -> None:
        pygame.init()
        self.recap = recap
        self.clips = clips
        self.cold = cold
        self.out_dir = out_dir
        self.log = log
        self.theme = for_season(recap.season)
        self.bg = studio_bg(self.theme, seed=recap.season)
        self.writer = Writer(recap, log=log)
        self.bank = VoiceBank(use_tts=use_tts, log=log)
        self.frame = pygame.Surface((W, HH))
        self.segments: list[Segment] = []
        self.awards: list[Award] = []

    # ------------------------------------------------------------------ planning
    def plan(self) -> list[Segment]:
        r, wr = self.recap, self.writer
        segs: list[Segment] = []
        race_lines = {}
        prev = None
        for ri in r.part_races:
            has = bool(self.clips.get(ri.race, {}).get("ok"))
            race_lines[ri.race] = wr.race_lines(ri, prev, has)
            prev = ri
        punch_up_winners([(ri, race_lines[ri.race].verdict[0]) for ri in r.part_races
                          if race_lines[ri.race].verdict and ri.stage != "grand_final"], log=self.log)
        if self.cold:
            segs.append(self._seg_cold(self.cold))
        segs.append(self._seg_title())
        if r.start_race == 1:
            segs.append(self._seg_roster())
        else:
            segs.append(self._seg_table(r.stats_entering(r.start_race), f"PREVIOUSLY... AFTER RACE {r.start_race - 1}",
                                        wr.previously(), "previously", chapter="Previously"))
        mid = r.part_races[len(r.part_races) // 2 - 1].race if len(r.part_races) >= 6 else None
        for ri in r.part_races:
            if ri.stage == "play_in":
                segs.append(self._seg_card("THE PLAYOFFS", "PLAY-IN • QUALIFIER 1 • QUALIFIER 2 • GRAND FINAL",
                                           wr.playoffs_card(), "playoffs", chapter="The Playoffs"))
            segs.append(self._seg_race(ri, race_lines[ri.race]))
            if mid is not None and ri.race == mid and ri.stage == "league":
                segs.append(self._seg_table(ri.stats_after, f"TABLE CHECK • AFTER RACE {ri.race}", wr.table_check(ri),
                                            "table_check"))
        self.awards = wr.awards()
        if self.awards:
            segs.append(self._seg_card("THE TUNOS", f"SEASON {r.season} • {self._part_label()} AWARDS",
                                       wr.awards_intro(), "awards_intro", chapter="The Tunos (Awards)", trophy=True))
            for a in self.awards:
                segs.append(self._seg_award(a))
        if r.champion:
            segs.append(self._seg_champion())
        segs.append(self._seg_chart())
        segs.append(self._seg_table(r.final_stats, "FINAL TABLE" if r.end_race >= 30 else f"THE TABLE • AFTER RACE {r.end_race}",
                                    wr.standings(), "standings", chapter="Standings"))
        segs.append(self._seg_teaser())
        segs.append(self._seg_end())
        self.segments = segs
        return segs

    def _part_label(self) -> str:
        return f"PART {self.recap.part}" if self.recap.part else "SO FAR"

    def _voice_seq(self, lines: list[Line], start: float = 0.25, gap: float = 0.28) -> tuple[list[tuple[float, Line]], float]:
        out, t = [], start
        for ln in lines:
            out.append((t, ln))
            t += self.bank.dur(ln) + gap
        return out, t

    # ------------------------------------------------------------------ cold open
    def _seg_cold(self, cold: dict) -> Segment:
        lines = self.writer.cold_open(cold["victim"])
        n_clip = int(cold.get("frames") or 0)
        clip_s = n_clip / FPS
        voice, end = self._voice_seq(lines, start=clip_s + 0.55, gap=0.25)
        reader = {"r": None}
        pos = cold.get("pos") or [304, 540]
        victim = cold["victim"]
        px = (W - PHONE.w) // 2

        def start():
            reader["r"] = ClipReader(cold.get("path"))

        def stop():
            if reader["r"]:
                reader["r"].close()

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            i = min(int(t * FPS), max(0, n_clip - 1))
            surf = reader["r"].frame(i) if reader["r"] else None
            frozen = t >= clip_s
            if surf is not None:
                img = surf
                if frozen:
                    k = ease((t - clip_s) / 0.35)
                    gray = pygame.transform.grayscale(surf)
                    img = surf.copy()
                    gray.set_alpha(int(255 * k))
                    img.blit(gray, (0, 0))
                    z = 1.0 + 0.10 * k
                    zw, zh = int(PHONE.w * z), int(PHONE.h * z)
                    big = pygame.transform.smoothscale(img, (zw, zh))
                    ox, oy = (zw - PHONE.w) * pos[0] / PHONE.w, (zh - PHONE.h) * pos[1] / PHONE.h
                    img = big.subsurface(pygame.Rect(int(ox), int(oy), PHONE.w, PHONE.h)).copy()
                fr.blit(img, (px, 0))
                pygame.draw.rect(fr, BLACK, (px - 8, -4, PHONE.w + 16, HH + 8), 8)
                pygame.draw.rect(fr, GOLD, (px - 3, -4, PHONE.w + 6, HH + 8), 3)
                if frozen:
                    k = ease((t - clip_s) / 0.3)
                    cx, cy = px + pos[0], pos[1]
                    pygame.draw.circle(fr, (235, 40, 50), (int(cx), int(cy)), int(70 + 30 * (1 - k)), 8)
                    pygame.draw.line(fr, (235, 40, 50), (px + PHONE.w + 30, 330), (cx + 60, cy - 40), 8)
            if frozen:
                k = ease((t - clip_s - 0.1) / 0.3)
                if k > 0:
                    blit_c(fr, txt("*RECORD SCRATCH*", 46, fill=(255, 255, 255), width=4), (px / 2, 200))
                    s = txt(f"YEP. THAT'S {name(victim).upper()}.", 84, fill=GOLD, width=7)
                    s = fit(s, W - (px + PHONE.w) - 60)
                    fr.blit(s, s.get_rect(midleft=(px + PHONE.w + 40 - int((1 - k) * 60), 300)))
                    blit_c(fr, ball(victim, 200, "dizzy"), ((px + PHONE.w + W) / 2, 600))
                    blit_c(fr, ball(victim, 200, "dizzy"), (px / 2, 600))

        return Segment("cold_open", end + 0.5, draw, voice=voice,
                       sfx=[(clip_s + 0.02, "record_scratch", -3.0)], chapter="Intro", on_start=start, on_end=stop)

    # ------------------------------------------------------------------ title
    def _seg_title(self) -> Segment:
        r = self.recap
        line = self.writer.title()
        voice, end = self._voice_seq([line], start=0.35)
        rng_label = f"RACES {r.start_race}-{r.end_race}"
        sub = f"SEASON {r.season} • {self._part_label()} • {rng_label}"
        theme_name = self.theme.name.upper()

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            k = ease(t / 0.5)
            sb = pygame.Surface((W, HH), pygame.SRCALPHA)
            sunburst(sb, (W / 2, 420), t, (*GOLD, 26), (255, 255, 255, 10))
            fr.blit(sb, (0, 0))
            logo1 = txt("THE TUNO", 150, fill=GOLD, width=10)
            logo2 = txt("REPORT", 190, fill=WHITE, width=12)
            s1 = pygame.transform.rotozoom(logo1, -3, pop(t / 0.45) * k + 1e-3)
            s2 = pygame.transform.rotozoom(logo2, -3, pop((t - 0.12) / 0.45) * ease((t - 0.12) / 0.45) + 1e-3)
            blit_c(fr, s1, (W / 2 - 300, 190))
            blit_c(fr, s2, (W / 2 - 260, 350))
            if t > 0.4:
                c = chip(sub, (220, 38, 38), 40)
                blit_c(fr, c, (W / 2 - 280, 500))
                blit_c(fr, chip(f"{theme_name} SEASON", NAVY2, 30), (W / 2 - 280, 572))
            booth = pygame.Rect(1200, 160, 600, 520)
            tuno_booth(fr, booth, ctx.line.mood if ctx.line else "HYPED_TALKING", t, ctx.rms, 2.35)
            for i, h in enumerate(HEROES):
                kk = ease((t - 0.5 - i * 0.06) / 0.3)
                if kk > 0:
                    blit_c(fr, ball(h.key, 92, "happy"), (150 + i * 175, 770 + (1 - kk) * 60))
            if t < 1.6:
                effects.draw_confetti(fr, t, 7, pygame.Rect(0, 0, W, HH), n=90)

        return Segment("title", max(4.0, end + 0.4), draw, voice=voice,
                       sfx=[(0.05, "airhorn", -5.0), (0.15, "cheer", -9.0)], chapter=None if self.cold else "Intro")

    def _seg_roster(self) -> Segment:
        line = self.writer.roster()
        voice, end = self._voice_seq([line], start=0.2)

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            blit_c(fr, txt("MEET THE IDIOTS", 92, fill=GOLD, width=7), (W / 2, 110))
            for i, h in enumerate(HEROES):
                col, row = i % 5, i // 5
                cx, cy = 250 + col * 355, 330 + row * 330
                kk = ease((t - 0.15 - i * 0.12) / 0.25)
                if kk <= 0:
                    continue
                card = pygame.Rect(0, 0, 300, 290)
                card.center = (cx, cy + int((1 - kk) * 40))
                panel(fr, card, fill=NAVY, border=(255, 255, 255), radius=24, bw=3)
                blit_c(fr, ball(h.key, 130, "happy"), (card.centerx, card.y + 105))
                blit_c(fr, fit(txt(h.name.upper(), 46, fill=WHITE, width=4), 270), (card.centerx, card.y + 205))
                blit_c(fr, fit(plain(h.archetype, 26, (203, 213, 225)), 270), (card.centerx, card.y + 252))

        sfx_ = [(0.15 + i * 0.12, "pop", -12.0) for i in range(10)]
        return Segment("roster", max(4.2, end + 0.5), draw, voice=voice, sfx=sfx_, chapter="Meet the Cast")

    def _seg_card(self, title: str, subtitle: str, line: Line, nm: str, chapter: str | None = None,
                  trophy: bool = False) -> Segment:
        voice, end = self._voice_seq([line], start=0.25)

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            sb = pygame.Surface((W, HH), pygame.SRCALPHA)
            sunburst(sb, (W / 2 - 200, 420), t, (*GOLD, 22), (255, 255, 255, 8))
            fr.blit(sb, (0, 0))
            k = pop(t / 0.4) * ease(t / 0.4)
            blit_c(fr, pygame.transform.rotozoom(txt(title, 170, fill=GOLD, width=11), -2, k + 1e-3), (W / 2 - 220, 360))
            if t > 0.3:
                blit_c(fr, chip(subtitle, (220, 38, 38), 38), (W / 2 - 220, 520))
            if trophy:
                H._draw_trophy_cup(fr, W / 2 - 220, 700, 2.4 + 0.08 * math.sin(t * 4))

        return Segment(nm, max(3.0, end + 0.4), draw, voice=voice, sfx=[(0.05, "riser", -8.0), (0.4, "ding", -8.0)],
                       chapter=chapter)

    # ------------------------------------------------------------------ races
    def _race_header(self, ri: RaceInfo) -> pygame.Surface:
        from src.publish.metadata import arena_display_name

        s = pygame.Surface((RX1 - RX0, 190), pygame.SRCALPHA)
        panel(s, pygame.Rect(6, 6, s.get_width() - 12, 178), radius=26)
        stage = STAGE_LABELS.get(ri.stage)
        s.blit(txt("RACE", 34, fill=(203, 213, 225), width=3), (36, 24))
        s.blit(txt(f"{ri.race}", 110, fill=GOLD, width=7), (30, 52))
        s.blit(txt("/30", 40, fill=(203, 213, 225), width=3), (36 + txt(f"{ri.race}", 110, width=7).get_width(), 118))
        x0 = 250
        s.blit(fit(txt(arena_display_name(ri.arena).upper(), 58, fill=WHITE, width=5), s.get_width() - x0 - 30), (x0, 26))
        x = x0
        chips_ = [chip(stage, (220, 38, 38), 28)] if stage else []
        chips_.append(chip(GOAL_LABELS.get(ri.goal, ri.goal.replace("_", " ").upper()), (37, 99, 235), 26))
        for hz in ri.hazards[:2]:
            chips_.append(chip(hz.replace("_", " ").upper(), (71, 85, 105), 24))
        if ri.twist:
            chips_.append(chip("TWIST: " + ri.twist.replace("_", " ").upper(), (147, 51, 234), 24))
        for c in chips_:
            if x + c.get_width() > s.get_width() - 24:
                break
            s.blit(c, (x, 112))
            x += c.get_width() + 10
        return s

    def _results_card(self, ri: RaceInfo, k: float) -> pygame.Surface:
        s = pygame.Surface((RX1 - RX0, 260), pygame.SRCALPHA)
        panel(s, pygame.Rect(6, 6, s.get_width() - 12, 248), radius=26)
        playoff = ri.stage != "league"
        podium = ri.hero_ranking[:3]
        for i, key in enumerate(podium):
            kk = ease((k - i * 0.12) / 0.35)
            if kk <= 0:
                continue
            cx = 120 + i * 230
            cy = 120 + int((1 - kk) * 40)
            pygame.draw.circle(s, MEDALS[i], (cx, cy), 74)
            pygame.draw.circle(s, BLACK, (cx, cy), 74, 5)
            blit_c(s, ball(key, 104, "celebrating" if i == 0 else "happy"), (cx, cy - 4))
            blit_c(s, txt(["1ST", "2ND", "3RD"][i], 30, fill=MEDALS[i], width=3), (cx, cy - 92))
            blit_c(s, fit(txt(name(key).upper(), 30, fill=WHITE, width=3), 210), (cx, cy + 92))
            pts = ri.points.get(key, 0) - (2 if key == ri.ko_bonus else 0)
            if not playoff and pts > 0:
                blit_c(s, chip(f"+{pts}", (22, 163, 74), 26), (cx + 66, cy - 58))
        x = 760
        if ri.ko_bonus and not playoff:
            blit_c(s, chip(f"+2 KO: {name(ri.ko_bonus).upper()}", (234, 88, 12), 26), (x + 130, 50))
        if playoff:
            pill = (ri.outcome.winner_points_pill or "").upper()
            blit_c(s, fit(chip(pill, (220, 38, 38), 28), 320), (x + 130, 60))
        else:
            lead = ri.leader_after
            lp = int(ri.stats_after[lead]["points"])
            blit_c(s, txt("TABLE LEADER", 26, fill=(203, 213, 225), width=3), (x + 130, 112))
            blit_c(s, ball(lead, 64, "happy"), (x + 50, 170))
            s.blit(fit(txt(f"{name(lead).upper()} {lp}", 34, fill=GOLD, width=3), 220), (x + 90, 150))
            if ri.lead_changed:
                blit_c(s, chip("NEW LEADER!", (220, 38, 38), 24), (x + 130, 228))
        return s

    def _seg_race(self, ri: RaceInfo, rl) -> Segment:
        clip = self.clips.get(ri.race) or {}
        has = bool(clip.get("ok"))
        cinfo = clip.get("clip") or {}
        n_clip = int(cinfo.get("frames") or 0) if has else 0
        timeline = cinfo.get("timeline") or []
        decisive_i = int(cinfo.get("decisive_index") or n_clip)
        clip_s = n_clip / FPS
        lines = [rl.intro] + ([rl.lost] if rl.lost else [])
        voice, t_after = self._voice_seq(lines, start=0.3, gap=0.25)
        decisive_t = decisive_i / FPS if has else max(2.2, t_after)
        vt = max(decisive_t + 0.1, t_after + 0.15)
        v2, end_v = self._voice_seq(rl.verdict, start=vt, gap=0.25)
        voice += v2
        results_t = max(decisive_t, vt - 0.2)
        dur = max((clip_s + 2.4) if has else 0.0, end_v + 0.8, 7.0)
        header = self._race_header(ri)
        reader = {"r": None}
        boundaries = []
        for i in range(1, len(timeline)):
            if timeline[i][1] != timeline[i - 1][1] and timeline[i][1] in ("final",):
                boundaries.append(i / FPS)
        chaos_kind = cinfo.get("chaos_kind")
        chaos_lbl = CHAOS_LABELS.get(chaos_kind or "", "THE CHAOS")
        if chaos_kind == "elimination":
            ev = next((e for e in clip.get("events", []) if abs(float(e["t"]) - float(cinfo.get("chaos_t") or -9)) < 1e-3), None)
            if ev and ev.get("data", {}).get("by_hero"):
                chaos_lbl = "THE BETRAYAL"
        sfx_ = self._race_sfx(clip, timeline, decisive_i) if has else []
        sfx_ += [(results_t, "fanfare", -5.0), (results_t + 0.15, "cheer", -9.0)]
        if not has:
            sfx_.append((0.2, "zap", -10.0))
        tuno_c = (RX0 + 270, 230 + 250)

        def start():
            reader["r"] = ClipReader(cinfo.get("path")) if has else None

        def stop():
            if reader["r"]:
                reader["r"].close()

        noise = [self._noise_frame(i) for i in range(4)] if not has else []

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            if has:
                surf = reader["r"].frame(min(int(t * FPS), n_clip - 1)) if reader["r"] else None
                if surf is not None:
                    fr.blit(surf, PHONE.topleft)
                seg = timeline[min(int(t * FPS), len(timeline) - 1)][1] if timeline else "final"
                if t < 1.3 and timeline and timeline[0][1] == "chaos":
                    blit_c(fr, chip(chaos_lbl, (220, 38, 38), 34), (PHONE.centerx, 300))
                for b in boundaries:
                    if 0 <= t - b < 0.12:
                        fl = pygame.Surface(PHONE.size, pygame.SRCALPHA)
                        fl.fill((255, 255, 255, int(200 * (1 - (t - b) / 0.12))))
                        fr.blit(fl, PHONE.topleft)
                    if 0 <= t - b < 1.2:
                        blit_c(fr, chip("THE FINISH", (37, 99, 235), 34), (PHONE.centerx, 300))
                if seg == "replay" and t < clip_s:
                    blit_c(fr, chip("INSTANT REPLAY", (147, 51, 234), 30), (PHONE.centerx, 1000))
            else:
                fr.blit(noise[int(t * 12) % len(noise)], PHONE.topleft)
                dim = pygame.Surface(PHONE.size, pygame.SRCALPHA)
                dim.fill((0, 0, 0, 120))
                fr.blit(dim, PHONE.topleft)
                blit_c(fr, txt("FOOTAGE LOST", 74, fill=(255, 80, 80), width=6), (PHONE.centerx, 300))
                sub = "CORRUPTED BY GLITCH" if ri.winner == "glitch" else "THE TAPE GOT EATEN"
                blit_c(fr, txt(sub, 40, fill=WHITE, width=4), (PHONE.centerx, 380))
                bob = math.sin(t * 3) * 10
                blit_c(fr, ball(ri.winner, 240, "celebrating"), (PHONE.centerx, 640 + bob))
                H._crown_badge(fr, PHONE.centerx, 500 + bob, 120)
            pygame.draw.rect(fr, BLACK, PHONE.inflate(16, 8), 8)
            pygame.draw.rect(fr, GOLD, PHONE.inflate(6, 8), 3)
            fr.blit(header, (RX0, 24))
            booth = pygame.Rect(RX0, 236, 540, 500)
            mood = ctx.line.mood if ctx.line else ("TROPHY_CHEER" if t >= results_t else "HYPED_TALKING")
            if has and ctx.line is None and t < results_t and timeline:
                seg = timeline[min(int(t * FPS), len(timeline) - 1)][1]
                mood = "SWEATING_INTENSE" if seg == "final" and (results_t - t) < 3 else mood
            tuno_booth(fr, booth, mood, t, ctx.rms, 2.2)
            if ctx.line is not None:
                bubble(fr, pygame.Rect(RX0 + 570, 250, RX1 - RX0 - 570, 300), ctx.line.text,
                       tail_to=(RX0 + 520, 470), size=38)
            else:
                self._prerace_strip(fr, ri, pygame.Rect(RX0 + 570, 250, RX1 - RX0 - 570, 300))
            if t >= results_t:
                fr.blit(self._results_card(ri, t - results_t), (RX0, 780 + int((1 - ease((t - results_t) / 0.3)) * 120)))
            else:
                self._progress_dots(fr, ri)

        ch = f"Race {ri.race}: {STAGE_LABELS.get(ri.stage, '').title() or self._arena_name(ri.arena)}"
        return Segment(f"race_{ri.race}", dur, draw, voice=voice, sfx=sfx_, chapter=ch, caption_mode="none",
                       on_start=start, on_end=stop)

    def _arena_name(self, a: str) -> str:
        from src.publish.metadata import arena_display_name
        return arena_display_name(a)

    def _prerace_strip(self, fr: pygame.Surface, ri: RaceInfo, rect: pygame.Rect) -> None:
        panel(fr, rect, fill=NAVY, border=(255, 255, 255), radius=24, bw=3)
        blit_c(fr, txt("BEFORE THE RACE", 30, fill=(203, 213, 225), width=3), (rect.centerx, rect.y + 36))
        order = ri.standings_before[:3]
        for i, (k, p) in enumerate(order):
            y = rect.y + 92 + i * 66
            fr.blit(txt(f"#{i + 1}", 34, fill=MEDALS[i], width=3), (rect.x + 26, y - 18))
            blit_c(fr, ball(k, 50, "happy"), (rect.x + 120, y))
            fr.blit(fit(txt(name(k).upper(), 32, width=3), 200), (rect.x + 158, y - 18))
            ps = txt(f"{p}", 34, fill=GOLD, width=3)
            fr.blit(ps, ps.get_rect(midright=(rect.right - 26, y)))

    def _progress_dots(self, fr: pygame.Surface, ri: RaceInfo) -> None:
        r = self.recap
        n = r.end_race - r.start_race + 1
        rect = pygame.Rect(RX0, 800, RX1 - RX0, 200)
        panel(fr, rect, fill=NAVY, border=(255, 255, 255), radius=24, bw=3)
        blit_c(fr, txt(f"SEASON {r.season} • {self._part_label()}", 34, fill=(203, 213, 225), width=3), (rect.centerx, rect.y + 44))
        gap = (rect.w - 120) / max(1, n - 1)
        for i in range(n):
            race = r.start_race + i
            cx = rect.x + 60 + i * gap
            done = race < ri.race
            cur = race == ri.race
            col = GOLD if cur else ((34, 197, 94) if done else (71, 85, 105))
            pygame.draw.circle(fr, BLACK, (int(cx), rect.y + 128), 30 if cur else 22)
            pygame.draw.circle(fr, col, (int(cx), rect.y + 128), 26 if cur else 18)
            blit_c(fr, txt(str(race), 26 if cur else 20, fill=WHITE, width=3), (cx, rect.y + 129))

    def _noise_frame(self, i: int) -> pygame.Surface:
        """Chunky VHS static (76x135 grey noise upscaled with nearest-neighbour)."""
        rng = np.random.default_rng(1000 + i)
        small = rng.integers(20, 235, size=(76, 135), dtype=np.uint8)      # (width, height)
        s = pygame.surfarray.make_surface(np.stack([small] * 3, axis=-1))
        return pygame.transform.scale(s, PHONE.size)

    def _race_sfx(self, clip: dict, timeline: list, decisive_i: int) -> list[tuple[float, str, float]]:
        out: list[tuple[float, str, float]] = []
        side = clip.get("mode") == "SIDE_VIEW"
        evs = sorted(clip.get("events") or [], key=lambda e: e["t"])
        for i in range(1, min(len(timeline), decisive_i)):
            t0, t1 = timeline[i - 1][0], timeline[i][0]
            if timeline[i][1] != timeline[i - 1][1] or t1 <= t0:
                continue
            lt = i / FPS
            for e in evs:
                if not (t0 < e["t"] <= t1):
                    continue
                d, k = e.get("data") or {}, e["kind"]
                if k == "elimination":
                    hero = bool(d.get("hero"))
                    if side:
                        out += [(max(0.0, lt - 0.4), "fall", -6.0 if hero else -12.0), (lt + 0.03, "splat", -7.0 if hero else -13.0)]
                    else:
                        out.append((lt, "fall_short", -6.0 if hero else -12.0))
                    if hero and d.get("by_hero"):
                        out.append((lt, "betrayal", -5.0))
                elif k == "impact" and d.get("hero_pair") and float(d.get("impulse") or 0) > 900:
                    out.append((lt, "bonk", -6.0))
                elif k == "crush_hit":
                    out += [(lt, "thud", -7.0), (lt + 0.02, "comic_bonk", -9.0)]
                elif k == "glitch_blink":
                    out.append((lt, "glitch", -8.0))
                elif k == "escalation":
                    out.append((lt, "airhorn", -9.0))
        out.append((decisive_i / FPS, "rewind", -8.0))
        out.sort()
        kept, last = [], {}
        for t, nm, g in out:                      # de-clutter: same sound at most every 0.25 s
            if t - last.get(nm, -9) >= 0.25:
                kept.append((t, nm, g))
                last[nm] = t
        return kept

    # ------------------------------------------------------------------ table / awards / champion / chart
    def _seg_table(self, stats: dict, title: str, line: Line, nm: str, chapter: str | None = None) -> Segment:
        from src.state import league

        order = league.sorted_standings(stats)
        voice, end = self._voice_seq([line], start=0.3)
        reigning = self.recap.reigning_champion

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            blit_c(fr, fit(txt(title, 74, fill=GOLD, width=6), 1700), (W / 2, 80))
            for i, (k, v) in enumerate(order):
                col, row = i // 5, i % 5
                kk = ease((t - 0.1 - i * 0.05) / 0.3)
                if kk <= 0:
                    continue
                x0 = 80 + col * 900 - int((1 - kk) * 60)
                y = 150 + row * 116
                rect = pygame.Rect(x0, y, 860, 104)
                panel(fr, rect, fill=(NAVY2 if i == 0 else NAVY), border=(MEDALS[i] if i < 3 else (148, 163, 184)),
                      radius=20, bw=4 if i < 3 else 2)
                fr.blit(txt(str(i + 1), 52, fill=MEDALS[i] if i < 3 else WHITE, width=4), (x0 + 22, y + 20))
                blit_c(fr, ball(k, 76, "celebrating" if i == 0 else ("dizzy" if i == len(order) - 1 else "happy")),
                       (x0 + 150, y + 52))
                nm_s = name(k).upper() + (" ★" if k == reigning else "")
                fr.blit(fit(txt(nm_s, 44, width=4), 330), (x0 + 205, y + 26))
                stat = f"{v['wins']}W  {v['kos']}KO"
                fr.blit(plain(stat, 30, (203, 213, 225), FREDOKA), (x0 + 560, y + 36))
                ps = txt(f"{v['points']}", 58, fill=GOLD, width=4)
                fr.blit(ps, ps.get_rect(midright=(x0 + 840, y + 52)))
            self._corner(fr, t, ctx)

        return Segment(nm, max(4.5, end + 0.8), draw, voice=voice, sfx=[(0.1, "ding", -9.0)], chapter=chapter)

    def _corner(self, fr: pygame.Surface, t: float, ctx: Ctx) -> None:
        tuno_booth(fr, pygame.Rect(1440, 724, 420, 290), ctx.line.mood if ctx.line else "HYPED_TALKING", t, ctx.rms, 1.4)

    def _seg_award(self, a: Award) -> Segment:
        voice, end = self._voice_seq([a.line], start=0.55)
        col_a = (*GOLD, 34) if a.positive else (148, 163, 184, 26)
        col_b = (255, 255, 255, 10)
        expr = "celebrating" if a.positive else ("dizzy" if a.key in ("dummy", "speedrun") else "scared")
        sfx_ = [(0.1, "fanfare" if a.positive else "sad", -5.0 if a.positive else -6.0),
                (0.2, "cheer" if a.positive else "crowd_ooh", -10.0)]

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            sb = pygame.Surface((W, HH), pygame.SRCALPHA)
            sunburst(sb, (620, 560), t, col_a, col_b)
            fr.blit(sb, (0, 0))
            k = ease(t / 0.35)
            blit_c(fr, fit(txt(a.title, 104, fill=GOLD if a.positive else (226, 232, 240), width=8), 1180), (620, 120 - (1 - k) * 60))
            blit_c(fr, txt(a.subtitle, 40, fill=WHITE, width=4), (620, 215))
            ped = pygame.Rect(0, 0, 420, 90)
            ped.center = (620, 820)
            pygame.draw.rect(fr, BLACK, ped.inflate(10, 10), border_radius=16)
            pygame.draw.rect(fr, (120, 80, 30) if a.positive else (100, 116, 139), ped, border_radius=14)
            bob = math.sin(t * 3.2) * 8
            sc = pop((t - 0.15) / 0.4) * ease((t - 0.15) / 0.4)
            if sc > 0.02:
                sp = ball(a.hero, 330, expr)
                sp = pygame.transform.rotozoom(sp, (math.sin(t * 2) * 4) if a.positive else -8, sc)
                blit_c(fr, sp, (620, 560 + bob))
            if a.positive:
                H._crown_badge(fr, 620, 370 + bob, 130)
            if a.key == "dummy" and t > 0.45:
                kd = pop((t - 0.45) / 0.4) * ease((t - 0.45) / 0.4)
                blit_c(fr, pygame.transform.rotozoom(dummy_ball(190, "celebrating"), math.sin(t * 3) * 6, kd + 1e-3),
                       (1000, 600 - bob))
                H._crown_badge(fr, 1000, 470 - bob, 96)
                blit_c(fr, chip("THE WINNER", (22, 163, 74), 30), (1000, 730))
            blit_c(fr, txt(name(a.hero).upper(), 64, fill=WHITE, width=6), (620, 820))
            if t > 0.5:
                blit_c(fr, chip(a.stat, (220, 38, 38) if not a.positive else (22, 163, 74), 40), (620, 930))
            if a.key == "participation" and t > 0.6:
                card = pygame.Rect(930, 640, 120, 150)
                pygame.draw.rect(fr, (196, 156, 102), card, border_radius=8)
                pygame.draw.rect(fr, BLACK, card, 4, border_radius=8)
                blit_c(fr, txt("1ST?", 30, fill=WHITE, width=3), card.center)
            bubble(fr, pygame.Rect(1220, 110, 640, 300), ctx.line.text if ctx.line else "", tail_to=(1470, 548), size=38)
            tuno_booth(fr, pygame.Rect(1300, 556, 520, 454), ctx.line.mood if ctx.line else a.line.mood, t, ctx.rms, 1.95)
            if a.positive and t < 2.0:
                effects.draw_confetti(fr, t, 11, pygame.Rect(0, 0, 1240, HH), n=70)

        return Segment(f"award_{a.key}", max(4.2, end + 0.7), draw, voice=voice, sfx=sfx_, caption_mode="none")

    def _seg_champion(self) -> Segment:
        lines = self.writer.champion()
        voice, end = self._voice_seq(lines, start=1.0, gap=0.3)
        c = self.recap.champion

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            sb = pygame.Surface((W, HH), pygame.SRCALPHA)
            sunburst(sb, (W / 2, 520), t, (*GOLD, 40), (255, 255, 255, 14), n=24)
            fr.blit(sb, (0, 0))
            k = pop((t - 0.6) / 0.6) * ease((t - 0.6) / 0.6)
            if k > 0.02:
                blit_c(fr, pygame.transform.rotozoom(ball(c, 420, "celebrating"), math.sin(t * 2) * 5, k), (W / 2, 560))
                H._crown_badge(fr, W / 2, 330 + math.sin(t * 3) * 8, 200)
                H._draw_trophy_cup(fr, W / 2 + 380, 640, 3.0)
                H._draw_trophy_cup(fr, W / 2 - 380, 640, 3.0)
            blit_c(fr, txt(f"SEASON {self.recap.season} CHAMPION", 92, fill=GOLD, width=8), (W / 2, 110))
            if t > 1.2:
                blit_c(fr, txt(name(c).upper(), 150, fill=WHITE, width=10), (W / 2, 900))
            effects.draw_confetti(fr, t, 17, pygame.Rect(0, 0, W, HH), n=140)
            self._corner(fr, t, ctx)

        return Segment("champion", max(8.0, end + 1.0), draw, voice=voice,
                       sfx=[(0.6, "grand_fanfare", -2.0), (0.8, "cheer", -5.0), (2.2, "cheer", -7.0)],
                       chapter="The Champion")

    def _seg_chart(self) -> Segment:
        line = self.writer.title_race()
        races = self.recap.races
        steps = [{h.key: 0 for h in HEROES}] + [{k: int(v["points"]) for k, v in r.stats_after.items()} for r in races]
        per = min(0.6, 9.0 / max(1, len(steps) - 1))
        voice, end = self._voice_seq([line], start=0.3)
        dur = max(end + 0.6, 1.0 + per * (len(steps) - 1) + 2.4)
        top = max(1, max(max(s.values()) for s in steps))
        ys: dict[str, float] = {}

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            x = min(len(steps) - 1.0, max(0.0, (t - 0.8) / per))
            i0 = int(x)
            fk = ease(x - i0)
            a, b = steps[i0], steps[min(i0 + 1, len(steps) - 1)]
            cur = {k: a[k] + (b[k] - a[k]) * fk for k in a}
            order = sorted(cur, key=lambda k: (-cur[k], k))
            race_no = min(len(steps) - 1, i0 + (1 if fk > 0.5 else 0))
            blit_c(fr, txt("THE TITLE RACE", 80, fill=GOLD, width=6), (620, 70))
            rs = txt(f"AFTER RACE {race_no}", 64, fill=WHITE, width=5)
            fr.blit(rs, rs.get_rect(topright=(1840, 34)))
            maxw = 940
            for idx, k in enumerate(order):
                target = 140 + idx * 80
                ys[k] = ys.get(k, target) + (target - ys.get(k, target)) * 0.3
                y = ys[k]
                hero = HERO_BY_KEY[k]
                bw_ = max(12, int(maxw * cur[k] / top))
                fr.blit(fit(txt(hero.name.upper(), 40, width=4), 250), (60, y + 14))
                col = tuple(int(hero.colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
                bar = pygame.Rect(330, y + 10, bw_, 60)
                pygame.draw.rect(fr, BLACK, bar.inflate(6, 6), border_radius=14)
                pygame.draw.rect(fr, col if k != "glitch" else (60, 60, 70), bar, border_radius=12)
                blit_c(fr, ball(k, 64, "happy"), (330 + bw_ + 40, y + 40))
                fr.blit(txt(str(int(round(cur[k]))), 44, fill=GOLD, width=4), (330 + bw_ + 84, y + 14))
            self._corner(fr, t, ctx)

        return Segment("chart", dur, draw, voice=voice, sfx=[(0.8, "riser", -10.0)], chapter="The Title Race")

    def _seg_teaser(self) -> Segment:
        r = self.recap
        line = self.writer.teaser()
        voice, end = self._voice_seq([line], start=0.3)
        if r.kind == "part1":
            big, sub = "PART 2", "RACES 11-20 • DROPS AFTER RACE 20"
        elif r.kind == "part2":
            big, sub = "PART 3", "PLAYOFFS + GRAND FINAL • AFTER RACE 30"
        elif r.kind == "part3":
            nxt = for_season(r.season + 1)
            big, sub = f"SEASON {r.season + 1}", f"{nxt.name.upper()} • STARTS TOMORROW"
        else:
            big, sub = "NEW RACE", "EVERY DAY • 8 PM IST"

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            if r.kind == "part3":
                nxt = for_season(r.season + 1)
                ov = pygame.Surface((W, HH), pygame.SRCALPHA)
                ov.fill((*nxt.sky_top, int(110 * ease(t / 0.6))))
                fr.blit(ov, (0, 0))
            blit_c(fr, txt("COMING UP", 64, fill=WHITE, width=5), (W / 2 - 220, 170))
            k = pop(t / 0.45) * ease(t / 0.45)
            blit_c(fr, pygame.transform.rotozoom(txt(big, 220, fill=GOLD, width=12), -3, k + 1e-3), (W / 2 - 220, 380))
            if t > 0.35:
                blit_c(fr, chip(sub, (220, 38, 38), 42), (W / 2 - 220, 570))
            for i, h in enumerate(HEROES):
                kk = ease((t - 0.4 - i * 0.05) / 0.3)
                if kk > 0:
                    sp = ball(h.key, 110, "angry" if i % 2 else "happy")
                    blit_c(fr, sp, (130 + i * 128, 800 + math.sin(t * 4 + i) * 10))
            self._corner(fr, t, ctx)

        return Segment("teaser", max(5.0, end + 0.6), draw, voice=voice, sfx=[(0.1, "airhorn", -7.0)],
                       chapter="Coming Up")

    def _seg_end(self) -> Segment:
        line = self.writer.outro()
        voice, _ = self._voice_seq([line], start=0.4)

        def draw(fr: pygame.Surface, t: float, ctx: Ctx) -> None:
            blit_c(fr, txt("THANKS FOR WATCHING!", 96, fill=GOLD, width=7), (W / 2, 100))
            blit_c(fr, txt("NEW RACE EVERY DAY • 8 PM IST • @TOONTOONCASTLE", 40, fill=WHITE, width=4), (W / 2, 190))
            for x0 in (120, 1140):         # YouTube end-screen video tiles (safe zones)
                r_ = pygame.Rect(x0, 300, 660, 372)
                pygame.draw.rect(fr, (255, 255, 255), r_, 4, border_radius=20)
            pygame.draw.circle(fr, GOLD, (W // 2, 486), 110, 6)
            tuno_booth(fr, pygame.Rect(W // 2 - 260, 700, 520, 320), ctx.line.mood if ctx.line else "HYPED_TALKING",
                       t, ctx.rms, 1.6)

        return Segment("end", 15.0, draw, voice=voice, chapter="End", caption_mode="none")

    # ------------------------------------------------------------------ audio
    def build_audio(self, total: float, starts: list[float], wav: Path) -> tuple[list[float], list[tuple[float, float, Line]]]:
        from src.narration import tts

        n = int(math.ceil(total * SR)) + SR
        voice = np.zeros(n, np.float32)
        fx = np.zeros(n, np.float32)
        spoken: list[tuple[float, float, Line]] = []
        for seg, s0 in zip(self.segments, starts):
            for lt, ln in seg.voice:
                pcm, d = self.bank.get(ln)
                t0 = s0 + lt
                spoken.append((t0, t0 + d, ln))
                if pcm is not None:
                    i0 = int(t0 * SR)
                    m = float(np.max(np.abs(pcm))) or 1.0
                    k = min(pcm.size, n - i0)
                    voice[i0:i0 + k] += pcm[:k] / m * 0.92
            for lt, nm, gdb in seg.sfx:
                fn = SFX_LIB.get(nm)
                if fn is None:
                    continue
                clip = fn()
                i0 = int(max(0.0, s0 + lt) * SR)
                k = min(clip.size, n - i0)
                if k > 0:
                    fx[i0:i0 + k] += clip[:k] * float(10 ** (gdb / 20.0))
        if self.bank.ok:
            voice = tts.booth_mic_eq(voice)
        rms = [float(np.sqrt(np.mean(voice[int(i * SR / FPS):int((i + 1) * SR / FPS)] ** 2) or 0.0))
               for i in range(int(round(total * FPS)))]
        win = max(1, int(SR / FPS))
        env = np.sqrt(np.convolve(voice * voice, np.ones(win, np.float32) / win, mode="same"))
        gate = (env > 0.02).astype(np.float32)
        duck = np.clip(np.convolve(gate, np.ones(int(0.14 * SR), np.float32) / int(0.14 * SR), mode="same") * 1.35, 0, 1)
        fx *= (10.0 ** ((-6.0 * duck - 5.0) / 20.0)).astype(np.float32)
        bed = music.theme_bgm(total + 1.0, music.track_for_theme(self.theme.key), seed=self.recap.season * 10 + (self.recap.part or 0))
        mus = np.zeros(n, np.float32)
        mus[:min(n, bed.size)] = bed[:min(n, bed.size)]
        mus *= (10.0 ** ((-20.0 - 7.0 * duck) / 20.0)).astype(np.float32)
        fade = int(1.5 * SR)
        end_i = int(total * SR)
        mus[max(0, end_i - fade):end_i] *= np.linspace(1, 0, min(fade, end_i), dtype=np.float32)
        mus[end_i:] = 0
        mixd = np.tanh((voice + fx + mus)[:end_i] * 1.05) * 0.94
        pcm16 = (np.clip(mixd, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(wav), "wb") as w_:
            w_.setnchannels(2)
            w_.setsampwidth(2)
            w_.setframerate(SR)
            w_.writeframes(np.repeat(pcm16[:, None], 2, axis=1).tobytes())
        return rms, spoken

    # ------------------------------------------------------------------ render
    def render(self, out_mp4: Path, stills_dir: Path | None = None, max_frames: int | None = None) -> dict[str, Any]:
        segs = self.segments or self.plan()
        starts, t = [], 0.0
        for s in segs:
            starts.append(t)
            t += s.duration
        total = t
        wav = out_mp4.with_suffix(".wav")
        rms, spoken = self.build_audio(total, starts, wav)
        n_frames = int(round(total * FPS))
        if max_frames:
            n_frames = min(n_frames, max_frames)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{HH}",
               "-r", str(FPS), "-i", "-", "-i", str(wav), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", "-movflags", "+faststart", str(out_mp4)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        if stills_dir:
            stills_dir.mkdir(parents=True, exist_ok=True)
        seg_i = -1
        spoken_sorted = sorted(spoken, key=lambda x: x[0])
        for fi in range(n_frames):
            gt = fi / FPS
            while seg_i + 1 < len(segs) and gt >= starts[seg_i + 1]:
                if seg_i >= 0 and segs[seg_i].on_end:
                    segs[seg_i].on_end()
                seg_i += 1
                if segs[seg_i].on_start:
                    segs[seg_i].on_start()
            seg = segs[seg_i]
            lt = gt - starts[seg_i]
            cur = next(((a, ln) for a, b, ln in spoken_sorted if a <= gt <= b + 0.25 and starts[seg_i] <= a), None)
            ctx = Ctx(fi, rms[fi] if fi < len(rms) else 0.0, cur[1] if cur else None, gt - cur[0] if cur else 0.0)
            self.frame.blit(self.bg, (0, 0))
            seg.draw(self.frame, lt, ctx)
            if seg.caption_mode == "lower" and ctx.line is not None:
                lower_third(self.frame, ctx.line.text, ctx.line_t)
            self._brand(self.frame)
            if lt < 0.2 and seg_i > 0:
                fl = pygame.Surface((W, HH), pygame.SRCALPHA)
                fl.fill((255, 255, 255, int(150 * (1 - lt / 0.2))))
                self.frame.blit(fl, (0, 0))
            proc.stdin.write(pygame.image.tobytes(self.frame, "RGB"))
            if stills_dir and abs(lt - min(seg.duration * 0.62, seg.duration - 0.2)) < 0.5 / FPS:
                pygame.image.save(self.frame, str(stills_dir / f"{fi // FPS:04d}s_{seg.name}.png"))
        if seg_i >= 0 and segs[seg_i].on_end:
            segs[seg_i].on_end()
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg recap encode failed")
        if wav.exists():
            wav.unlink()
        chapters, last = [], -99.0
        for s, s0 in zip(segs, starts):
            if s.chapter and s0 - last >= 10.0:
                chapters.append((s0, s.chapter))
                last = s0
        if chapters:
            chapters[0] = (0.0, chapters[0][1])
        return {"duration": total, "frames": n_frames, "chapters": chapters,
                "voice_ok": self.bank.ok, "voice_failed": self.bank.failed,
                "lines": [ln.text for _, _, ln in spoken_sorted]}

    def _brand(self, fr: pygame.Surface) -> None:
        wm = getattr(self, "_wm", None)
        if wm is None:
            wm = H.outlined("@ToonToonCastle", 30, fill=WHITE, outline=BLACK, width=4, face=FREDOKA).copy()
            wm.fill((255, 255, 255, 150), special_flags=pygame.BLEND_RGBA_MULT)
            self._wm = wm
        fr.blit(wm, wm.get_rect(bottomright=(W - 26, HH - 4)))


# ---------------------------------------------------------------------------------------------- thumbnail
def render_thumbnail(recap: SeasonRecap, awards: list[Award], out_png: Path) -> Path:
    pygame.init()
    theme = for_season(recap.season)
    big = studio_bg(theme, seed=recap.season)
    img = pygame.transform.smoothscale(big, (1280, 720))
    sb = pygame.Surface((1280, 720), pygame.SRCALPHA)
    sunburst(sb, (900, 380), 0.3, (*GOLD, 40), (255, 255, 255, 12), r=1000)
    img.blit(sb, (0, 0))
    label = f"PART {recap.part}" if recap.part else "SO FAR"
    img.blit(pygame.transform.rotozoom(txt(label, 150, fill=GOLD, width=10), 4, 1.0), (30, 40))
    sub = {"part1": "10 RACES OF CHAOS", "part2": "IT GOT WORSE", "part3": "WHO WINS THE CROWN?"}.get(recap.kind,
                                                                                                  "THE STORY SO FAR")
    img.blit(fit(txt(sub, 74, fill=WHITE, width=7), 640), (40, 250))
    img.blit(chip(f"SEASON {recap.season} • THE TUNO REPORT", (220, 38, 38), 34), (40, 360))
    hero_a = next((a.hero for a in awards if a.positive), recap.races[-1].winner)
    hero_b = next((a.hero for a in awards if not a.positive), recap.races[0].hero_ranking[-1])
    blit_c(img, ball(hero_a, 300, "celebrating"), (900, 330))
    H._crown_badge(img, 900, 150, 120)
    blit_c(img, pygame.transform.rotozoom(ball(hero_b, 210, "dizzy"), -18, 1.0), (1150, 560))
    tb = pygame.Surface((330, 300), pygame.SRCALPHA)
    draw_tuno(tb, 165, 296, "SHOCKED_JAWDROP", 0.4, scale=1.9, voice_rms=0.12)
    img.blit(tb, (40, 420))
    pygame.draw.rect(img, BLACK, img.get_rect(), 10)
    pygame.image.save(img, str(out_png))
    return out_png
