"""HUD and overlays (§8, v3.2): auto-fitted event banners (max_width = 900 px, zero edge clipping) and bold game-show
Winner Card with spinning comic sunburst glow, stylized header ribbon, crowned champion, and lively confetti."""
from __future__ import annotations

import math
from functools import lru_cache

import pygame

from src.characters import renderer
from src.characters.expressions import BLACK, WHITE
from src.characters.roster import Hero
from src.characters.tuno import draw_tuno
from src.config import H, LAYOUT, W, font_path
from src.rendering import effects

HEADER_TOP, HEADER_BOTTOM = LAYOUT["header"]
TEXT_BOXES: list[pygame.Rect] = []      # every text rect drawn this frame (for safe-zone tests)
MAX_BANNER_W = 900


@lru_cache(maxsize=32)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


def outlined(text: str, size: int, fill=WHITE, outline=BLACK, width: int = 6, face: str = "LuckiestGuy-Regular.ttf"):
    f = font(size, face)
    base = f.render(text, True, fill)
    out = pygame.Surface((base.get_width() + 2 * width, base.get_height() + 2 * width), pygame.SRCALPHA)
    ring = f.render(text, True, outline)
    for a in range(16):
        out.blit(ring, (width + math.cos(a * math.pi / 8) * width, width + math.sin(a * math.pi / 8) * width))
    out.blit(base, (width, width))
    return out


def fit_width(surf: pygame.Surface, max_w: int = MAX_BANNER_W) -> pygame.Surface:
    """v3.2: Strictly auto-scale centered banner surfaces to fit inside max_w with zero edge clipping."""
    if surf.get_width() <= max_w:
        return surf
    ratio = max_w / max(1, surf.get_width())
    return pygame.transform.smoothscale(surf, (max_w, max(1, int(surf.get_height() * ratio))))


def blit_text(frame: pygame.Surface, surf: pygame.Surface, **anchor) -> pygame.Rect:
    r = surf.get_rect(**anchor)
    frame.blit(surf, r)
    TEXT_BOXES.append(r)
    return r


def draw_header(frame: pygame.Surface, ep_label: str, survivors: int, total: int, heroes: list[Hero],
                status: dict[str, str], tuno_state: str, t: float, pulse: float = 0.0) -> None:
    """Legacy fallback header."""
    plate = pygame.Surface((W, HEADER_BOTTOM - HEADER_TOP + 10), pygame.SRCALPHA)
    plate.fill((20, 14, 40, 110))
    frame.blit(plate, (0, HEADER_TOP))
    draw_tuno(frame, W / 2, HEADER_TOP + 118, tuno_state, t, scale=0.82)
    badge = outlined(ep_label, 30, width=4)
    blit_text(frame, badge, topleft=(28, HEADER_TOP + 14))
    col = (255, 80, 80) if pulse > 0 else WHITE
    s = outlined(f"SURVIVORS {survivors}/{total}", 30, fill=col, width=4)
    blit_text(frame, s, topright=(W - 28, HEADER_TOP + 14))


def draw_banner(frame: pygame.Surface, text: str, age: float, y: float = 540, colour=(255, 214, 0)) -> None:
    """Big slam-in banner for 1.2 s (SPEED BOOST ZONES!, OVERTIME CHAOS!, FINAL!), auto-fitted to <= 900 px."""
    if age < 0 or age > 1.2:
        return
    k = 1.45 - 0.45 * min(1.0, age / 0.12) if age < 0.12 else (1.0 if age < 0.95 else max(0.0, 1 - (age - 0.95) / 0.25))
    if k <= 0.02:
        return
    base = fit_width(outlined(text, 86, fill=colour, width=8), 780)
    s = fit_width(pygame.transform.rotozoom(base, -3, k), MAX_BANNER_W)
    blit_text(frame, s, center=(W / 2, y))


def _crown_badge(frame: pygame.Surface, cx: float, cy: float, w: float) -> None:
    pts = [
        (cx - w * 0.5, cy + w * 0.28),
        (cx - w * 0.56, cy - w * 0.26),
        (cx - w * 0.22, cy + w * 0.02),
        (cx, cy - w * 0.42),
        (cx + w * 0.22, cy + w * 0.02),
        (cx + w * 0.56, cy - w * 0.26),
        (cx + w * 0.5, cy + w * 0.28),
    ]
    pygame.draw.polygon(frame, (255, 210, 36), pts)
    pygame.draw.polygon(frame, BLACK, pts, 5)
    for gx, col in ((cx - w * 0.24, (235, 45, 75)), (cx, (40, 175, 255)), (cx + w * 0.24, (46, 214, 115))):
        pygame.draw.circle(frame, col, (gx, cy + w * 0.08), max(4, int(w * 0.09)))
        pygame.draw.circle(frame, BLACK, (gx, cy + w * 0.08), max(4, int(w * 0.09)), 2)


def draw_winner_card(frame: pygame.Surface, hero: Hero | None, name: str, colour: tuple[int, int, int], points: str,
                     prompt: str, t: float, bot=None) -> None:
    """v3.2: Bold game-show victory card with spinning comic sunburst, stylized header ribbon, and lively confetti."""
    # Background celebratory confetti behind & around the card
    effects.draw_confetti(frame, t + 0.4, 19, pygame.Rect(0, 260, W, H - 260), n=120)

    panel = pygame.Rect(74, 470, W - 148, 760)
    pygame.draw.rect(frame, (0, 0, 0, 150), panel.move(12, 16), border_radius=40)
    pygame.draw.rect(frame, BLACK, panel.inflate(14, 14), border_radius=42)

    # Rich game-show card interior with spinning comic sunburst clipped inside
    card = pygame.Surface(panel.size, pygame.SRCALPHA)
    cw, ch = panel.size
    for row in range(0, ch, 4):
        kk = row / max(1, ch)
        col_row = (int(36 + 28 * kk), int(22 + 16 * kk), int(78 + 44 * kk))
        pygame.draw.rect(card, col_row, (0, row, cw, 4))

    # Spinning comic sunburst glow behind the champion
    scx, scy = cw / 2, 290
    n_rays = 16
    base_ang = t * 0.95
    ray_r = max(cw, ch) * 0.95
    burst = pygame.Surface(panel.size, pygame.SRCALPHA)
    for i in range(n_rays):
        a0 = base_ang + 2 * math.pi * i / n_rays
        a1 = base_ang + 2 * math.pi * (i + 0.52) / n_rays
        pts = [(scx, scy), (scx + math.cos(a0) * ray_r, scy + math.sin(a0) * ray_r),
               (scx + math.cos(a1) * ray_r, scy + math.sin(a1) * ray_r)]
        pygame.draw.polygon(burst, (255, 214, 40, 95 if i % 2 == 0 else 45), pts)
    pygame.draw.circle(burst, (255, 230, 90, 140), (scx, scy), 155)
    pygame.draw.circle(burst, (255, 255, 255, 110), (scx, scy), 112)
    card.blit(burst, (0, 0))

    # Mask card to rounded rect + gold marquee border
    mask = pygame.Surface(panel.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=36)
    card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(card, panel.topleft)
    pygame.draw.rect(frame, BLACK, panel, 7, border_radius=36)
    pygame.draw.rect(frame, (255, 208, 36), panel.inflate(-18, -18), 5, border_radius=28)

    # Thick stylized game-show header ribbon across the top of the card
    pop = 1.0 + 0.28 * math.exp(-t * 5) * math.cos(t * 18)
    rib_w, rib_h = 680, 108
    rx, ry = W / 2 - rib_w / 2, panel.top - 26
    # Ribbon side tails
    for side in (-1, 1):
        tx = W / 2 + side * (rib_w / 2 - 12)
        tail = [
            (tx, ry + 26),
            (tx + side * 56, ry + 26),
            (tx + side * 36, ry + 62),
            (tx + side * 56, ry + 98),
            (tx, ry + 98),
        ]
        pygame.draw.polygon(frame, (175, 24, 52), tail)
        pygame.draw.polygon(frame, BLACK, tail, 5)
    rib = pygame.Rect(int(rx), int(ry), rib_w, rib_h)
    pygame.draw.rect(frame, BLACK, rib.move(0, 6), border_radius=24)
    pygame.draw.rect(frame, (232, 42, 74), rib, border_radius=24)
    pygame.draw.rect(frame, (255, 212, 44), rib.inflate(-12, -12), 4, border_radius=18)
    pygame.draw.rect(frame, BLACK, rib, 6, border_radius=24)
    win_txt = fit_width(pygame.transform.rotozoom(outlined("CHAMPION!", 82, fill=(255, 224, 48), width=7), 0, pop), 610)
    blit_text(frame, win_txt, center=rib.center)

    # Champion character + bouncing crown
    champ_y = panel.top + 295
    hop = abs(math.sin(t * 7.5)) * 24
    if hero is not None:
        from src.rendering import balls
        balls.draw_ball(frame, hero, None, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "celebrating",
                        "victory", t, 2.7 / max(0.6, hero.radius / 25) * pop, force_grin=True)
        _crown_badge(frame, W / 2, champ_y - hop - 108, 74)
    elif bot is not None:
        from src.rendering import balls
        balls.draw_ball(frame, None, bot, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "neutral", "victory", t, 2.8)
    else:
        pygame.draw.circle(frame, BLACK, (W / 2, champ_y), 64)
        pygame.draw.circle(frame, colour, (W / 2, champ_y), 58)

    # Champion Name + Season Points Pill + CTA Ribbon
    name_col = colour if sum(colour) > 160 else (0, 245, 255)
    blit_text(frame, fit_width(outlined(name.upper(), 76, fill=name_col, width=7), 780), center=(W / 2, panel.top + 468))

    pts_pill = pygame.Rect(W // 2 - 250, panel.top + 522, 500, 62)
    pygame.draw.rect(frame, BLACK, pts_pill.move(0, 4), border_radius=20)
    pygame.draw.rect(frame, (22, 18, 44), pts_pill, border_radius=20)
    pygame.draw.rect(frame, (0, 229, 255), pts_pill, 3, border_radius=20)
    blit_text(frame, fit_width(outlined(points, 38, fill=(255, 255, 255), width=4), 460), center=pts_pill.center)

    blit_text(frame, fit_width(outlined(prompt, 38, fill=(220, 235, 255), width=4, face="Fredoka.ttf"), 820),
              center=(W / 2, panel.top + 628))
    bob = 4 * math.sin(t * 6.5)
    blit_text(frame, fit_width(outlined("COMMENT YOUR PICK!", 46, fill=(255, 214, 0), width=5), 820),
              center=(W / 2, panel.top + 694 + bob))

    # Foreground celebratory confetti accents
    effects.draw_confetti(frame, t, 73, panel.inflate(80, 60), n=36)


def draw_decor(frame: pygame.Surface, theme, t: float) -> None:
    top = LAYOUT["top_sky"][1]
    castle = theme.castle
    dark = tuple(max(0, int(c * 0.7)) for c in castle)
    pygame.draw.rect(frame, dark, (0, top - 46, W, 46))
    for x in range(0, W, 90):
        pygame.draw.rect(frame, dark, (x, top - 80, 50, 40))
    y0 = LAYOUT["bottom_band"][0]
    pygame.draw.rect(frame, dark, (0, y0, W, frame.get_height() - y0))
    for row, y in enumerate(range(y0, frame.get_height(), 52)):
        off = 0 if row % 2 else 60
        for x in range(-off, W, 120):
            pygame.draw.rect(frame, castle, (x + 4, y + 4, 112, 44), border_radius=6)
