"""Polished scenery & HUD art (§8, §15): soft cloud sky with distant towers, castle header with Lord Tuno's balcony,
episode pill, bottom status panel, rocky snow/grass-capped terrain and floating top-down platforms.
Everything is procedural vector art; static layers are built once per episode."""
from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from src.characters import renderer
from src.characters.expressions import BLACK, WHITE
from src.characters.roster import Hero
from src.characters.tuno import draw_tuno
from src.config import H, LAYOUT, W, font_path

HEADER_BOTTOM = LAYOUT["header"][1]
PANEL = pygame.Rect(28, 108, 762, 114)          # Top-left Top-5 Heroes Bar (y=0..255 broadcast header)


def mix(a, b, k: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))  # type: ignore[return-value]


@lru_cache(maxsize=16)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


# ---------------------------------------------------------------------------------------------- sky
def _cloud(s: pygame.Surface, x: float, y: float, w: float, col, shade) -> None:
    rng = random.Random(int(x * 7 + y))
    puffs = [(x + w * k, y - rng.uniform(0.1, 0.45) * w * 0.5, w * rng.uniform(0.22, 0.34)) for k in (0.0, 0.22, 0.45, 0.68, 0.9)]
    for px, py, r in puffs:
        pygame.draw.circle(s, shade, (px, py + r * 0.18), r)
    for px, py, r in puffs:
        pygame.draw.circle(s, col, (px, py), r)
    pygame.draw.rect(s, col, (x - w * 0.05, y - w * 0.12, w * 1.0, w * 0.2), border_radius=int(w * 0.1))


def sky(theme) -> pygame.Surface:
    """Full-frame background: gradient, far castle towers, and banks of soft clouds. Seamless horizontally."""
    s = pygame.Surface((W, H))
    top, bot = mix(theme.sky_top, (255, 255, 255), 0.25), mix(theme.sky_bottom, (255, 255, 255), 0.35)
    for y in range(H):
        pygame.draw.line(s, mix(top, bot, y / H), (0, y), (W, y))
    far = mix(theme.castle, bot, 0.55)
    far_d = mix(far, theme.sky_top, 0.15)
    rng = random.Random(11)
    for i in range(5):                       # distant towers (drawn wrapped for seamless parallax)
        x, w, h = i * 240 + rng.randint(-40, 40), rng.randint(70, 120), rng.randint(380, 620)
        for ox in (0, -W, W):
            bx = x + ox
            pygame.draw.rect(s, far, (bx, 1400 - h, w, h + 400))
            for k in range(w // 28 + 1):
                pygame.draw.rect(s, far, (bx + k * 28 - 4, 1400 - h - 22, 18, 24))
            pygame.draw.polygon(s, far_d, [(bx - 10, 1400 - h - 20), (bx + w + 10, 1400 - h - 20), (bx + w / 2, 1400 - h - 120)])
            pygame.draw.rect(s, far_d, (bx + w / 2 - 8, 1400 - h + 60, 16, 30), border_radius=8)
    cloud, shade = mix(WHITE, theme.sky_bottom, 0.08), mix(WHITE, theme.sky_top, 0.3)
    for i in range(7):                       # mid clouds
        x, y = i * 170 + rng.randint(-30, 30), rng.randint(420, 1100)
        for ox in (0, -W, W):
            _cloud(s, x + ox, y, rng.randint(160, 260), cloud, shade)
    for i in range(9):                       # low cloud sea
        x = i * 135 + rng.randint(-20, 20)
        for ox in (0, -W, W):
            _cloud(s, x + ox, 1560 + rng.randint(-30, 40), 240, cloud, shade)
    pygame.draw.rect(s, cloud, (0, 1600, W, H - 1600))
    return s


# ---------------------------------------------------------------------------------------------- broadcast header (v3.1)
CAM_RECT = pygame.Rect(815, 22, 230, 220)       # Top-right: Lord Tuno Royal Reaction Cam


def castle_header(theme) -> pygame.Surface:
    """v3.1: stone-and-gold portrait frame for Lord Tuno in the top-right (full-width brick wall removed)."""
    s = pygame.Surface((260, 260), pygame.SRCALPHA)
    cx, cy, r = 130, 126, 108
    # shadow + outer black + stone ring + gold trim
    pygame.draw.circle(s, (0, 0, 0, 90), (cx + 4, cy + 6), r + 8)
    pygame.draw.circle(s, BLACK, (cx, cy), r + 8)
    pygame.draw.circle(s, (145, 138, 165), (cx, cy), r + 3)
    pygame.draw.circle(s, BLACK, (cx, cy), r - 8)
    pygame.draw.circle(s, (255, 205, 40), (cx, cy), r - 11, 5)
    pygame.draw.circle(s, (46, 36, 72), (cx, cy), r - 16)
    return s


def _outlined_text(text: str, size: int, fill=WHITE, outline=BLACK, w: int = 4) -> pygame.Surface:
    f = font(size)
    base = f.render(text, True, fill)
    ring = f.render(text, True, outline)
    out = pygame.Surface((base.get_width() + 2 * w, base.get_height() + 2 * w), pygame.SRCALPHA)
    for k in range(12):
        ang = k * math.pi / 6
        out.blit(ring, (w + math.cos(ang) * w, w + math.sin(ang) * w))
    out.blit(base, (w, w))
    return out


@lru_cache(maxsize=16)
def episode_ribbon(text: str) -> pygame.Surface:
    """Stylized cartoon episode ribbon with thick black outline (no plain white box)."""
    txt = _outlined_text(text.upper(), 30, fill=(255, 214, 0), outline=BLACK, w=4)
    w = min(540, txt.get_width() + 44)
    h = 58
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pts = [(10, 4), (w - 4, 4), (w - 18, h - 4), (2, h - 4)]
    pygame.draw.polygon(s, BLACK, [(x + 3, y + 4) for x, y in pts])
    pygame.draw.polygon(s, (46, 48, 78), pts)
    pygame.draw.polygon(s, BLACK, pts, 4)
    fit = _fit(txt, w - 34)
    s.blit(fit, fit.get_rect(center=(w / 2, h / 2 + 2)))
    return s


def draw_header(frame: pygame.Surface, portrait_bg: pygame.Surface, ep_label: str, tuno_state: str, t: float,
                text_boxes: list, speech: str = "") -> None:
    """Top-left episode ribbon + Top-right Royal Reaction Cam with 2.5x Lord Tuno & speech tag."""
    rib = episode_ribbon(ep_label.replace(" - ", " • "))
    r = rib.get_rect(topleft=(28, 30))
    frame.blit(rib, r)
    text_boxes.append(r)

    # Top-right Royal Reaction Cam
    cx, cy = CAM_RECT.centerx, CAM_RECT.centery - 6
    frame.blit(portrait_bg, portrait_bg.get_rect(center=(cx, cy)))
    # Render Lord Tuno 2.5x larger inside a circular clip matching the inner frame
    buf = pygame.Surface((220, 220), pygame.SRCALPHA)
    draw_tuno(buf, 110, 214, tuno_state, t, scale=1.65)
    mask = pygame.Surface((220, 220), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (110, 110), 92)
    buf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(buf, buf.get_rect(center=(cx, cy)))
    # Gold bezel highlight on top
    pygame.draw.circle(frame, BLACK, (cx, cy), 100, 4)
    pygame.draw.circle(frame, (255, 205, 40), (cx, cy), 96, 4)
    if speech:
        sp = _outlined_text(speech, 32, fill=(255, 255, 255), outline=BLACK, w=4)
        bw, bh = sp.get_width() + 24, sp.get_height() + 12
        tag = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(tag, BLACK, tag.get_rect(), border_radius=14)
        pygame.draw.rect(tag, (255, 80, 90), tag.get_rect().inflate(-6, -6), border_radius=11)
        tag.blit(sp, sp.get_rect(center=(bw / 2, bh / 2 + 1)))
        tr = tag.get_rect(midright=(cx - 104, cy - 12))
        frame.blit(tag, tr)
        text_boxes.append(tr)


def _crown(frame, cx: float, cy: float, w: float) -> None:
    pts = [(cx - w / 2, cy + w * 0.35), (cx - w / 2, cy - w * 0.1), (cx - w / 4, cy + w * 0.12), (cx, cy - w * 0.25),
           (cx + w / 4, cy + w * 0.12), (cx + w / 2, cy - w * 0.1), (cx + w / 2, cy + w * 0.35)]
    pygame.draw.polygon(frame, (255, 205, 40), pts)
    pygame.draw.polygon(frame, BLACK, pts, 2)


def _fit(surf: pygame.Surface, width: float) -> pygame.Surface:
    if surf.get_width() <= width:
        return surf
    return pygame.transform.smoothscale(surf, (int(width), max(1, int(surf.get_height() * width / surf.get_width()))))


def _icon(frame, h: Hero, c, rad: float, expr: str = "neutral") -> None:
    from src.rendering import balls
    balls.draw_ball(frame, h, None, c, 0.0, 0.0, (0, 0), 0.0, expr, "none", 0.0, rad / max(1.0, h.radius))


def draw_panel(frame: pygame.Surface, survivors: int, total: int, heroes: list[Hero], status: dict[str, str],
               ranks: dict[str, int], text_boxes: list, pulse: float = 0.0) -> None:
    """Top-left ALIVE pill beside the episode ribbon + Top 5 Heroes Bar (#1-#5 over alive heroes only)."""
    # ALIVE: X/13 pill beside the episode ribbon
    k = 1.0 + 0.12 * pulse
    alive_rect = pygame.Rect(584, 30, 206, 58)
    pygame.draw.rect(frame, BLACK, alive_rect.move(3, 4), border_radius=16)
    pygame.draw.rect(frame, (24, 26, 40), alive_rect, border_radius=16)
    pygame.draw.rect(frame, (255, 90, 90) if pulse > 0 else WHITE, alive_rect, 3, border_radius=16)
    lab = font(26).render("ALIVE:", True, WHITE)
    num = font(int(34 * k)).render(f"{survivors}/{total}", True, (255, 214, 0) if survivors <= 3 else (255, 90, 90))
    r1 = frame.blit(lab, lab.get_rect(midleft=(alive_rect.x + 14, alive_rect.centery + 2)))
    r2 = frame.blit(num, num.get_rect(midright=(alive_rect.right - 14, alive_rect.centery + 2)))
    text_boxes += [r1, r2]

    # Top 5 Heroes Bar directly below
    plate = pygame.Surface(PANEL.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 22, 36, 215), plate.get_rect(), border_radius=24)
    pygame.draw.rect(plate, (255, 255, 255, 75), plate.get_rect(), 3, border_radius=24)
    frame.blit(plate, PANEL)
    live = sorted((h for h in heroes if status.get(h.key) != "out"), key=lambda h: ranks.get(h.key, 99))[:5]
    step = (PANEL.width - 24) / 5
    f_rank = font(34)
    for i, h in enumerate(live):
        cx = PANEL.x + 12 + step * i + 44
        cy = PANEL.centery + 2
        _icon(frame, h, (cx, cy), 34, "celebrating" if status.get(h.key) == "crown" else "neutral")
        rank = ranks.get(h.key, i + 1)
        rn = f_rank.render(f"#{rank}", True, (255, 214, 0) if rank == 1 else WHITE)
        rb = frame.blit(rn, rn.get_rect(midleft=(cx + 42, cy + 2)))
        if rank == 1:
            _crown(frame, cx, cy - 42, 24)
        text_boxes.append(rb)


def draw_pick_strip(frame: pygame.Surface, heroes: list[Hero], t: float, text_boxes: list) -> None:
    """Cold-open PICK YOUR FIGHTER strip in the top-left bar slot (y=108..222), never over the balls."""
    plate = pygame.Surface(PANEL.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 22, 36, 225), plate.get_rect(), border_radius=24)
    pygame.draw.rect(plate, (255, 214, 0, 210), plate.get_rect(), 4, border_radius=24)
    frame.blit(plate, PANEL)
    lab = font(28).render("PICK YOUR FIGHTER!", True, (255, 214, 0))
    text_boxes.append(frame.blit(lab, lab.get_rect(midtop=(PANEL.centerx, PANEL.y + 6))))
    n = len(heroes)
    step = (PANEL.width - 30) / max(1, n)
    for i, h in enumerate(heroes):
        cx = PANEL.x + 15 + step * (i + 0.5)
        bob = 3 * math.sin(t * 9 + i)
        _icon(frame, h, (cx, PANEL.y + 74 + bob), 24, "happy")


# ---------------------------------------------------------------------------------------------- terrain
def rock_colours(theme) -> tuple:
    cap = theme.terrain
    rock = mix(mix(theme.castle, (150, 150, 160), 0.4), theme.terrain_outline, 0.25)
    return cap, rock, mix(rock, BLACK, 0.22), mix(rock, WHITE, 0.18)


def draw_cliff(frame: pygame.Surface, pts: list, zoom: float, theme, mat: str) -> None:
    """SIDE ground section: stone cliff body with strata and a rounded cap (grass/snow/ice/mud) on top."""
    cap, rock, dark, light = rock_colours(theme)
    (ax, ay), (bx, by) = pts[0], pts[1]
    span = bx - ax
    if span < 2:
        return
    n = max(2, int(span / (70 * zoom)))
    rng = random.Random(int(span / zoom) * 31 + int((by - ay) / zoom))
    depth = 300 * zoom
    bottom = []
    for i in range(n + 1):                    # jagged, tapering underside: a floating rock rather than a slab
        k = i / n
        edge = min(k, 1 - k)
        d = depth * (0.35 + 0.65 * min(1.0, edge * 3.2)) * rng.uniform(0.82, 1.0)
        taper = min(span * 0.08, 45 * zoom)
        x = ax + span * k + (taper * (1 if k < 0.5 else -1) if 0 < k < 1 else 0)
        bottom.append((x, ay + (by - ay) * k + d))
    poly = [(ax, ay), (bx, by)] + bottom[::-1]
    pygame.draw.polygon(frame, rock, poly)
    # strata + shading
    for f, col in ((0.28, light), (0.55, dark)):
        line = [(x, ay + (by - ay) * ((x - ax) / span) + (y - ay - (by - ay) * ((x - ax) / span)) * f) for x, y in bottom]
        pygame.draw.lines(frame, col, False, line, max(2, int(4 * zoom)))
    shade = [(x, y) for x, y in bottom]
    pygame.draw.lines(frame, dark, False, shade, max(3, int(10 * zoom)))
    pygame.draw.polygon(frame, BLACK, poly, max(3, int(4 * zoom)))


def draw_cap(frame: pygame.Surface, a, b, zoom: float, theme, mat: str) -> None:
    cap = {"ice": (205, 238, 255), "mud": (120, 84, 50), "bouncy": (255, 110, 185), "conveyor": (70, 72, 86),
           "plank": (176, 122, 70)}.get(mat, theme.terrain)
    w = max(8, int(26 * zoom))
    pygame.draw.line(frame, BLACK, a, b, w + 8)
    for p in (a, b):
        pygame.draw.circle(frame, BLACK, p, (w + 8) / 2)
    pygame.draw.line(frame, cap, a, b, w)
    for p in (a, b):
        pygame.draw.circle(frame, cap, p, w / 2)
    hi = mix(cap, WHITE, 0.45)
    pygame.draw.line(frame, hi, (a[0] + 4, a[1] - w * 0.25), (b[0] - 4, b[1] - w * 0.25), max(2, w // 5))


def draw_floating_platform(frame: pygame.Surface, centre, radius: float, zoom: float, theme, shape: str = "disc",
                           half: float = 0.0, spin_deg: float | None = None) -> None:
    """TOP_DOWN arena floor as a floating island: thick stone side wall below, capped surface with an outline."""
    cap, rock, dark, light = rock_colours(theme)
    cx, cy = centre
    depth = 46 * zoom
    if shape == "square":
        r = pygame.Rect(cx - half, cy - half, 2 * half, 2 * half)
        pygame.draw.rect(frame, BLACK, r.move(0, depth).inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, dark, r.move(0, depth), border_radius=20)
        pygame.draw.rect(frame, BLACK, r.inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, theme.terrain, r, border_radius=20)
        pygame.draw.rect(frame, mix(theme.terrain, WHITE, 0.35), r.inflate(-24, -24), 4, border_radius=16)
        return
    pygame.draw.circle(frame, BLACK, (cx, cy + depth), radius + 5)
    pygame.draw.circle(frame, dark, (cx, cy + depth), radius)
    pygame.draw.rect(frame, dark, (cx - radius, cy, 2 * radius, depth))
    pygame.draw.line(frame, BLACK, (cx - radius - 3, cy), (cx - radius - 3, cy + depth), 6)
    pygame.draw.line(frame, BLACK, (cx + radius + 3, cy), (cx + radius + 3, cy + depth), 6)
    pygame.draw.circle(frame, BLACK, (cx, cy), radius + 5)
    pygame.draw.circle(frame, theme.terrain, (cx, cy), radius)
    if spin_deg is not None and radius > 8:       # high-contrast radial pie stripes: spin speed reads instantly
        a0 = math.radians(spin_deg)
        dark = mix(theme.terrain, BLACK, 0.28)
        for k in range(0, 12, 2):
            pts = [(cx, cy)] + [(cx + math.cos(a0 + (k + u / 4) * math.pi / 6) * radius,
                                 cy + math.sin(a0 + (k + u / 4) * math.pi / 6) * radius) for u in range(5)]
            pygame.draw.polygon(frame, dark, pts)
        pygame.draw.circle(frame, BLACK, (cx, cy), radius * 0.16 + 3)
        pygame.draw.circle(frame, (255, 205, 40), (cx, cy), radius * 0.16)
    pygame.draw.circle(frame, mix(theme.terrain, WHITE, 0.3), (cx, cy), radius * 0.92, max(2, int(4 * zoom)))


def shadow(frame: pygame.Surface, pos, r: float) -> None:
    s = pygame.Surface((int(r * 2.4), int(r * 0.9)), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), s.get_rect())
    frame.blit(s, s.get_rect(center=(pos[0], pos[1] + r * 0.95)))
