"""HUD and overlays (§8, v4.0):
- Auto-fitted event banners (max_width = 900 px, zero edge clipping).
- IPL-Style 30-Episode Season League Winner Card (y = 366..1364, zero overlap with y=0..255 header or y=1480..1620 captions):
  1) Top Ribbon: `SEASON {S} • RACE {E} / 30` (or Play-In / Q1 / Q2 / GRAND FINAL)
  2) Spinning Sunburst + Crowned Champion (+ Championship Trophy Cup on Ep 30) + `+10 PTS` & `+2 KO BONUS` pills
  3) Season Standings Strip: `[Crown] LEADER: [Icon] {NAME} ({PTS} PTS)` (+ `NEW LEADER!` badge) | `[Timer] {30-E} RACES LEFT`
  4) Compact Top-3 Mini-Row: `#1 [Icon] 64   #2 [Icon] 58   #3 [Icon] 51`
  5) Exact Verbatim CTA spoken by MC Tuno at the bottom."""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import pygame

from src.characters.expressions import BLACK, WHITE
from src.characters.roster import HERO_BY_KEY, Hero
from src.characters.tuno import draw_tuno
from src.config import H, LAYOUT, W, font_path
from src.rendering import effects, scenery

HEADER_TOP, HEADER_BOTTOM = LAYOUT["header"]
TEXT_BOXES: list[pygame.Rect] = []
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
    if surf.get_width() <= max_w:
        return surf
    ratio = max_w / max(1, surf.get_width())
    return pygame.transform.smoothscale(surf, (int(max_w), max(1, int(surf.get_height() * ratio))))


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
    """Big slam-in banner for 1.2 s (SPEED UP!, OVERTIME CHAOS!), auto-fitted to <= 900 px."""
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
    pygame.draw.polygon(frame, BLACK, pts, max(2, int(w * 0.07)))
    if w >= 40:
        for gx, col in ((cx - w * 0.24, (235, 45, 75)), (cx, (40, 175, 255)), (cx + w * 0.24, (46, 214, 115))):
            pygame.draw.circle(frame, col, (gx, cy + w * 0.08), max(4, int(w * 0.09)))
            pygame.draw.circle(frame, BLACK, (gx, cy + w * 0.08), max(4, int(w * 0.09)), 2)


def _draw_trophy_cup(frame: pygame.Surface, cx: float, cy: float, scale: float = 1.0) -> None:
    """Draws a gleaming golden Season Championship Trophy Cup beside the Grand Final Champion."""
    s = scale
    # Pedestal base
    ped = pygame.Rect(int(cx - 26 * s), int(cy + 26 * s), int(52 * s), int(16 * s))
    pygame.draw.rect(frame, BLACK, ped.inflate(6, 6), border_radius=5)
    pygame.draw.rect(frame, (112, 72, 24), ped, border_radius=4)
    # Stem
    pygame.draw.rect(frame, BLACK, (int(cx - 9 * s), int(cy + 8 * s), int(18 * s), int(22 * s)))
    pygame.draw.rect(frame, (245, 192, 28), (int(cx - 6 * s), int(cy + 8 * s), int(12 * s), int(20 * s)))
    # Side handles
    for sgn in (-1, 1):
        hr = pygame.Rect(int(cx + sgn * 22 * s - 14 * s), int(cy - 24 * s), int(28 * s), int(28 * s))
        pygame.draw.ellipse(frame, BLACK, hr.inflate(6, 6), max(3, int(6 * s)))
        pygame.draw.ellipse(frame, (255, 214, 38), hr, max(2, int(4 * s)))
    # Cup bowl
    bowl = [
        (cx - 30 * s, cy - 32 * s),
        (cx + 30 * s, cy - 32 * s),
        (cx + 20 * s, cy + 10 * s),
        (cx - 20 * s, cy + 10 * s),
    ]
    pygame.draw.polygon(frame, BLACK, [(x, y) for x, y in bowl], 8)
    pygame.draw.polygon(frame, (255, 214, 38), bowl)
    pygame.draw.polygon(frame, (255, 246, 175), [
        (cx - 22 * s, cy - 28 * s), (cx - 8 * s, cy - 28 * s),
        (cx - 4 * s, cy + 4 * s), (cx - 14 * s, cy + 4 * s),
    ])
    pygame.draw.polygon(frame, BLACK, bowl, max(2, int(4 * s)))
    scenery.draw_gold_star(frame, cx, cy - 11 * s, 11 * s)


def _draw_flame_icon(frame: pygame.Surface, cx: float, cy: float, r: float) -> None:
    pts = [
        (cx, cy - r * 1.15),
        (cx + r * 0.72, cy - r * 0.15),
        (cx + r * 0.52, cy + r * 0.85),
        (cx, cy + r * 1.05),
        (cx - r * 0.52, cy + r * 0.85),
        (cx - r * 0.72, cy - r * 0.15),
    ]
    pygame.draw.polygon(frame, BLACK, pts, 4)
    pygame.draw.polygon(frame, (255, 94, 20), pts)
    pygame.draw.circle(frame, (255, 234, 92), (int(cx), int(cy + r * 0.35)), max(3, int(r * 0.42)))


def _draw_hourglass_icon(frame: pygame.Surface, cx: float, cy: float, r: float) -> None:
    top_tri = [(cx - r * 0.7, cy - r * 0.85), (cx + r * 0.7, cy - r * 0.85), (cx, cy)]
    bot_tri = [(cx - r * 0.7, cy + r * 0.85), (cx + r * 0.7, cy + r * 0.85), (cx, cy)]
    for tri in (top_tri, bot_tri):
        pygame.draw.polygon(frame, (125, 232, 255), tri)
        pygame.draw.polygon(frame, BLACK, tri, 2)
    pygame.draw.line(frame, (255, 214, 48), (cx - r * 0.85, cy - r * 0.88), (cx + r * 0.85, cy - r * 0.88), 3)
    pygame.draw.line(frame, (255, 214, 48), (cx - r * 0.85, cy + r * 0.88), (cx + r * 0.85, cy + r * 0.88), 3)


def _mini_hero_ball(frame: pygame.Surface, h_key: str, cx: float, cy: float, rad: float, reigning: str | None) -> None:
    h = HERO_BY_KEY.get(h_key)
    if h is None:
        return
    from src.rendering import balls
    balls.draw_ball(frame, h, None, (cx, cy), 0.0, 0.0, (0, 0), 0.0, "happy", "none", 0.0, rad / max(1.0, h.radius))
    if reigning == h_key:
        scenery.draw_gold_star(frame, cx + rad * 0.72, cy - rad * 0.68, max(7.0, rad * 0.38))


def draw_winner_card(frame: pygame.Surface, hero: Hero | None, name: str, colour: tuple[int, int, int], points: str,
                     prompt: str, t: float, bot=None, outcome: Any = None) -> None:
    """v4.0 IPL Season League Winner Card (y = 366..1364, zero overlap with header or captions)."""
    is_final = bool(outcome and getattr(outcome, "is_grand_final", False))
    effects.draw_confetti(frame, t + 0.4, 19, pygame.Rect(0, 260, W, H - 260), n=160 if is_final else 115)

    panel = pygame.Rect(64, 396, W - 128, 964)   # 952x964 -> ends at y = 1360 (120px clear of y = 1480 captions!)
    pygame.draw.rect(frame, (0, 0, 0, 160), panel.move(12, 16), border_radius=40)
    pygame.draw.rect(frame, BLACK, panel.inflate(14, 14), border_radius=42)

    card = pygame.Surface(panel.size, pygame.SRCALPHA)
    cw, ch = panel.size
    for row in range(0, ch, 4):
        kk = row / max(1, ch)
        if is_final:
            col_row = (int(56 + 34 * kk), int(26 + 18 * kk), int(42 + 28 * kk))
        else:
            col_row = (int(30 + 24 * kk), int(20 + 14 * kk), int(68 + 40 * kk))
        pygame.draw.rect(card, col_row, (0, row, cw, 4))

    # Spinning comic sunburst glow behind the champion
    scx, scy = cw / 2, 245
    n_rays = 16
    base_ang = t * 0.95
    ray_r = max(cw, ch) * 0.85
    burst = pygame.Surface(panel.size, pygame.SRCALPHA)
    for i in range(n_rays):
        a0 = base_ang + 2 * math.pi * i / n_rays
        a1 = base_ang + 2 * math.pi * (i + 0.52) / n_rays
        pts = [(scx, scy), (scx + math.cos(a0) * ray_r, scy + math.sin(a0) * ray_r),
               (scx + math.cos(a1) * ray_r, scy + math.sin(a1) * ray_r)]
        pygame.draw.polygon(burst, (255, 214, 40, 105 if i % 2 == 0 else 48), pts)
    pygame.draw.circle(burst, (255, 232, 96, 145), (scx, scy), 142)
    pygame.draw.circle(burst, (255, 255, 255, 110), (scx, scy), 100)
    card.blit(burst, (0, 0))

    mask = pygame.Surface(panel.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=36)
    card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(card, panel.topleft)
    pygame.draw.rect(frame, BLACK, panel, 7, border_radius=36)
    pygame.draw.rect(frame, (255, 214, 40), panel.inflate(-16, -16), 5, border_radius=28)

    # 1. Top Ribbon: `SEASON {S} • RACE {E} / 30` (or Play-In / Q1 / Q2 / GRAND FINAL)
    pop = 1.0 + 0.24 * math.exp(-t * 5) * math.cos(t * 18)
    rib_w, rib_h = 740, 88
    rx, ry = W / 2 - rib_w / 2, panel.top - 28
    rib_fill = (188, 32, 62) if not is_final else (218, 148, 12)
    rib_tail = (138, 18, 42) if not is_final else (158, 102, 8)
    for side in (-1, 1):
        tx = W / 2 + side * (rib_w / 2 - 12)
        tail = [
            (tx, ry + 20),
            (tx + side * 48, ry + 20),
            (tx + side * 30, ry + 50),
            (tx + side * 48, ry + 80),
            (tx, ry + 80),
        ]
        pygame.draw.polygon(frame, rib_tail, tail)
        pygame.draw.polygon(frame, BLACK, tail, 5)
    rib = pygame.Rect(int(rx), int(ry), rib_w, rib_h)
    pygame.draw.rect(frame, BLACK, rib.move(0, 6), border_radius=22)
    pygame.draw.rect(frame, rib_fill, rib, border_radius=22)
    pygame.draw.rect(frame, (255, 224, 68), rib.inflate(-10, -10), 4, border_radius=17)
    pygame.draw.rect(frame, BLACK, rib, 6, border_radius=22)
    ribbon_label = getattr(outcome, "ribbon_text", None) or "CHAMPION!"
    rib_txt = fit_width(pygame.transform.rotozoom(outlined(ribbon_label, 46, fill=(255, 244, 168) if is_final else (255, 228, 56), width=6), 0, pop), rib_w - 44)
    blit_text(frame, rib_txt, center=rib.center)

    # 2. Crowned Champion + Bouncing Trophy Celebration (on Ep 30 Grand Final)
    champ_y = panel.top + 245
    hop = abs(math.sin(t * 7.5)) * 20
    reigning = getattr(outcome, "reigning_champion", None)
    if hero is not None:
        from src.rendering import balls
        balls.draw_ball(frame, hero, None, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "celebrating",
                        "victory", t, 2.55 / max(0.6, hero.radius / 25) * pop, force_grin=True)
        _crown_badge(frame, W / 2, champ_y - hop - 102, 70)
        if reigning == hero.key:
            scenery.draw_gold_star(frame, W / 2 + 78, champ_y - hop - 64, 20)
        if is_final:
            _draw_trophy_cup(frame, W / 2 - 168, champ_y - hop * 0.5 + 8, scale=1.22)
            _draw_trophy_cup(frame, W / 2 + 168, champ_y - hop * 0.5 + 8, scale=1.22)
    elif bot is not None:
        from src.rendering import balls
        balls.draw_ball(frame, None, bot, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "neutral", "victory", t, 2.6)

    # Champion Name + Points / KO Bonus Pills
    name_col = colour if sum(colour) > 160 else (0, 245, 255)
    champ_title = f"{name.upper()} — CHAMPION!" if is_final else f"{name.upper()} WINS!"
    blit_text(frame, fit_width(outlined(champ_title, 66, fill=name_col, width=7), cw - 64), center=(W / 2, panel.top + 402))

    pts_str = getattr(outcome, "winner_points_pill", None) or points
    ko_key = getattr(outcome, "ko_bonus_key", None)
    if ko_key:
        ko_hero_name = HERO_BY_KEY[ko_key].name.upper() if ko_key in HERO_BY_KEY else ""
        ko_txt = "+2 KO BONUS!" if getattr(outcome, "winner_got_ko_bonus", False) else f"+2 KO: {ko_hero_name}"
        p_left = pygame.Rect(panel.left + 86, panel.top + 450, 360, 56)
        p_right = pygame.Rect(panel.right - 446, panel.top + 450, 360, 56)
        for rect_p, bd_c, fill_t, txt_c in (
            (p_left, (0, 229, 255), pts_str, WHITE),
            (p_right, (255, 196, 36), ko_txt, (255, 226, 72)),
        ):
            pygame.draw.rect(frame, BLACK, rect_p.move(0, 4), border_radius=18)
            pygame.draw.rect(frame, (20, 18, 42), rect_p, border_radius=18)
            pygame.draw.rect(frame, bd_c, rect_p, 3, border_radius=18)
            blit_text(frame, fit_width(outlined(fill_t, 33, fill=txt_c, width=4), rect_p.width - 28), center=rect_p.center)
    else:
        pts_pill = pygame.Rect(W // 2 - 250, panel.top + 450, 500, 56)
        pygame.draw.rect(frame, BLACK, pts_pill.move(0, 4), border_radius=18)
        pygame.draw.rect(frame, (20, 18, 42), pts_pill, border_radius=18)
        pygame.draw.rect(frame, (255, 214, 40) if is_final else (0, 229, 255), pts_pill, 3, border_radius=18)
        blit_text(frame, fit_width(outlined(pts_str, 34, fill=(255, 232, 88) if is_final else WHITE, width=4), 460), center=pts_pill.center)

    # 3. Season Standings Strip + Compact Top-3 Mini-Row
    if outcome is not None:
        strip = pygame.Rect(panel.left + 36, panel.top + 528, cw - 72, 86)
        pygame.draw.rect(frame, BLACK, strip.move(0, 4), border_radius=20)
        pygame.draw.rect(frame, (18, 16, 38, 242), strip, border_radius=20)
        pygame.draw.rect(frame, (255, 208, 44), strip, 3, border_radius=20)

        # Left side: [Crown] LEADER: [Icon] NAME (PTS) [+ NEW LEADER! badge]
        _crown_badge(frame, strip.left + 28, strip.centery - 2, 26)
        ld_lbl = outlined("CHAMP:" if is_final else "LEADER:", 24, fill=(255, 216, 56), width=3)
        blit_text(frame, ld_lbl, midleft=(strip.left + 48, strip.centery))
        icon_x = strip.left + 48 + ld_lbl.get_width() + 26
        _mini_hero_ball(frame, outcome.leader_key, icon_x, strip.centery, 21, reigning)
        ld_info = f"{outcome.leader_name.upper()} ({outcome.leader_pts} PTS)"
        ld_surf = fit_width(outlined(ld_info, 27, fill=WHITE, width=4), 295)
        blit_text(frame, ld_surf, midleft=(icon_x + 28, strip.centery))

        if outcome.lead_changed:
            nl_x = icon_x + 34 + ld_surf.get_width()
            if nl_x + 150 < strip.right - 220:
                _draw_flame_icon(frame, nl_x + 12, strip.centery, 12)
                nl_s = outlined("NEW LEADER!", 22, fill=(255, 132, 36), width=3)
                blit_text(frame, nl_s, midleft=(nl_x + 28, strip.centery))

        # Right side: [Hourglass] {30 - E} RACES LEFT (or stage status)
        rt_surf = fit_width(outlined(outcome.right_status_text, 25, fill=(138, 238, 255), width=3), 240)
        rt_rect = blit_text(frame, rt_surf, midright=(strip.right - 20, strip.centery))
        _draw_hourglass_icon(frame, rt_rect.left - 18, strip.centery, 11)

        # 4. Compact Top-3 Mini-Row (`#1 [Icon] 64 PTS   #2 [Icon] 58 PTS   #3 [Icon] 51 PTS`)
        row_rect = pygame.Rect(panel.left + 36, panel.top + 628, cw - 72, 74)
        pygame.draw.rect(frame, (14, 14, 30, 215), row_rect, border_radius=18)
        pygame.draw.rect(frame, (255, 255, 255, 70), row_rect, 2, border_radius=18)
        slot_w = row_rect.width / 3.0
        medal_cols = ((255, 216, 44), (214, 222, 236), (228, 148, 84))
        for idx, (hk, hpts) in enumerate(outcome.top3[:3]):
            sx0 = row_rect.left + idx * slot_w
            scx_slot = sx0 + slot_w * 0.5
            rk_s = outlined(f"#{idx + 1}", 28, fill=medal_cols[idx], width=4)
            pts_s = outlined(f"{hpts} PTS", 26, fill=WHITE, width=3)
            total_slot_w = rk_s.get_width() + 52 + pts_s.get_width()
            start_x = scx_slot - total_slot_w * 0.5
            blit_text(frame, rk_s, midleft=(start_x, row_rect.centery))
            _mini_hero_ball(frame, hk, start_x + rk_s.get_width() + 25, row_rect.centery, 19, reigning)
            blit_text(frame, pts_s, midleft=(start_x + rk_s.get_width() + 50, row_rect.centery))

        cta_top_y = panel.top + 720
    else:
        cta_top_y = panel.top + 545

    # 5. Verbatim Spoken CTA Box at Bottom of Card (matches MC Tuno's exact spoken words!)
    cta_box = pygame.Rect(panel.left + 36, cta_top_y, cw - 72, panel.bottom - cta_top_y - 26)
    pygame.draw.rect(frame, (26, 20, 54, 225), cta_box, border_radius=22)
    pygame.draw.rect(frame, (250, 204, 21), cta_box, 3, border_radius=22)

    words_cta = (prompt or "Drop your pick below!").strip().split()
    bob = 3.0 * math.sin(t * 6.5)
    if len(words_cta) <= 5:
        s1 = fit_width(outlined(" ".join(words_cta).upper(), 44, fill=(255, 226, 52), width=5), cta_box.width - 36)
        blit_text(frame, s1, center=(W / 2, cta_box.centery + bob))
    else:
        mid = (len(words_cta) + 1) // 2
        l1 = " ".join(words_cta[:mid]).upper()
        l2 = " ".join(words_cta[mid:]).upper()
        s1 = fit_width(outlined(l1, 40, fill=WHITE, width=5), cta_box.width - 36)
        s2 = fit_width(outlined(l2, 42, fill=(255, 224, 48), width=5), cta_box.width - 36)
        blit_text(frame, s1, center=(W / 2, cta_box.centery - 24 + bob * 0.5))
        blit_text(frame, s2, center=(W / 2, cta_box.centery + 26 + bob))

    effects.draw_confetti(frame, t, 73, panel.inflate(80, 60), n=42)


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
