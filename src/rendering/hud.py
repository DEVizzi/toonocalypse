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
    """Big slam-in banner for 1.2 s (SPEED UP!, OVERTIME CHAOS!), auto-fitted to <= 900 px.
    v4.3: exits with an alpha fade at full size (never shrinks into a tiny stray label over the slime/HUD)."""
    if age < 0 or age > 1.2:
        return
    k = 1.45 - 0.45 * min(1.0, age / 0.12) if age < 0.12 else 1.0
    alpha = 255 if age < 0.95 else int(255 * max(0.0, 1 - (age - 0.95) / 0.25))
    if alpha <= 8:
        return
    base = fit_width(outlined(text, 86, fill=colour, width=8), 780)
    s = fit_width(pygame.transform.rotozoom(base, -3, k), MAX_BANNER_W)
    if alpha < 255:
        s = s.convert_alpha() if pygame.display.get_init() and pygame.display.get_surface() else s.copy()
        s.set_alpha(alpha)
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


def _delta_tag(frame: pygame.Surface, x_right: float, cy: float, delta: int) -> float:
    """Bright green '+10 ▲' tag (triangle drawn as a polygon, never a font glyph). Returns its left x."""
    s = outlined(f"+{delta}", 26, fill=(74, 232, 120), width=3)
    tri_w = 16
    left = x_right - s.get_width() - tri_w - 4
    blit_text(frame, s, midleft=(left, cy))
    tx = left + s.get_width() + 4
    tri = [(tx, cy + 7), (tx + tri_w, cy + 7), (tx + tri_w / 2, cy - 8)]
    pygame.draw.polygon(frame, BLACK, [(px + 1, py + 2) for px, py in tri])
    pygame.draw.polygon(frame, (74, 232, 120), tri)
    pygame.draw.polygon(frame, BLACK, tri, 2)
    return left


def _down_arrow(frame: pygame.Surface, cx: float, cy: float, s: float) -> None:
    pts = [(cx - s * 0.32, cy - s * 0.55), (cx + s * 0.32, cy - s * 0.55), (cx + s * 0.32, cy),
           (cx + s * 0.62, cy), (cx, cy + s * 0.62), (cx - s * 0.62, cy), (cx - s * 0.32, cy)]
    pygame.draw.polygon(frame, (255, 214, 36), pts)
    pygame.draw.polygon(frame, BLACK, pts, 3)


def draw_winner_card(frame: pygame.Surface, hero: Hero | None, name: str, colour: tuple[int, int, int], points: str,
                     prompt: str, t: float, bot=None, outcome: Any = None) -> None:
    """v4.2 Broadcast IPL Winner Card (panel y = 396..1360; captions zone stays clear):
    - Top 42%: spinning sunburst + bouncing crowned winner + `{WINNER} WINS!` + `+10 PTS` / `+2 KO: {HERO}` pills.
    - Middle 46%: `SEASON {S} STANDINGS` header + RACES LEFT pill + 4 stacked scoreboard rows (rank, 42px icon, name,
      animated fill bar vs #1, points, green `+N ▲` delta). Grand Final: points-free champion podium instead.
    - Bottom 12%: single-line verbatim spoken CTA pill."""
    is_final = bool(outcome and getattr(outcome, "is_grand_final", False))
    effects.draw_confetti(frame, t + 0.4, 19, pygame.Rect(0, 260, W, H - 260), n=150 if is_final else 90)

    panel = pygame.Rect(64, 396, W - 128, 964)
    cw, ch = panel.size
    top_h, mid_h = int(ch * 0.42), int(ch * 0.46)
    mid_top = panel.top + top_h
    bot_top = mid_top + mid_h

    pygame.draw.rect(frame, (0, 0, 0, 160), panel.move(12, 16), border_radius=40)
    pygame.draw.rect(frame, BLACK, panel.inflate(14, 14), border_radius=42)
    card = pygame.Surface(panel.size, pygame.SRCALPHA)
    for row in range(0, ch, 4):
        kk = row / max(1, ch)
        col_row = (int(58 + 30 * kk), int(26 + 16 * kk), int(40 + 26 * kk)) if is_final else \
                  (int(30 + 20 * kk), int(22 + 12 * kk), int(70 + 34 * kk))
        pygame.draw.rect(card, col_row, (0, row, cw, 4))
    scx, scy = cw / 2, top_h * 0.44
    burst = pygame.Surface(panel.size, pygame.SRCALPHA)
    ray_r = cw * 0.9
    for i in range(16):
        a0 = t * 0.95 + 2 * math.pi * i / 16
        a1 = t * 0.95 + 2 * math.pi * (i + 0.52) / 16
        pygame.draw.polygon(burst, (255, 214, 40, 100 if i % 2 == 0 else 44),
                            [(scx, scy), (scx + math.cos(a0) * ray_r, scy + math.sin(a0) * ray_r),
                             (scx + math.cos(a1) * ray_r, scy + math.sin(a1) * ray_r)])
    pygame.draw.circle(burst, (255, 232, 96, 140), (scx, scy), 122)
    pygame.draw.circle(burst, (255, 255, 255, 105), (scx, scy), 86)
    # sunburst stays inside the top section only
    pygame.draw.rect(burst, (0, 0, 0, 0), (0, top_h, cw, ch - top_h))
    card.blit(burst, (0, 0))
    mask = pygame.Surface(panel.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=36)
    card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(card, panel.topleft)
    pygame.draw.rect(frame, BLACK, panel, 7, border_radius=36)
    pygame.draw.rect(frame, (255, 214, 40), panel.inflate(-16, -16), 5, border_radius=28)

    # Ribbon on the card's top edge
    pop = 1.0 + 0.24 * math.exp(-t * 5) * math.cos(t * 18)
    rib = pygame.Rect(int(W / 2 - 360), panel.top - 30, 720, 78)
    pygame.draw.rect(frame, BLACK, rib.move(0, 6), border_radius=22)
    pygame.draw.rect(frame, (218, 148, 12) if is_final else (188, 32, 62), rib, border_radius=22)
    pygame.draw.rect(frame, (255, 224, 68), rib.inflate(-10, -10), 4, border_radius=17)
    pygame.draw.rect(frame, BLACK, rib, 6, border_radius=22)
    ribbon_label = getattr(outcome, "ribbon_text", None) or "WINNER!"
    blit_text(frame, fit_width(outlined(ribbon_label, 42, fill=(255, 236, 120), width=6), rib.width - 44), center=rib.center)

    # ---- TOP 42%: bouncing crowned winner + WINS! + pills
    champ_y = panel.top + scy + 6
    hop = abs(math.sin(t * 7.5)) * 16
    reigning = getattr(outcome, "reigning_champion", None)
    if hero is not None:
        from src.rendering import balls
        balls.draw_ball(frame, hero, None, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "celebrating",
                        "victory", t, 2.15 / max(0.6, hero.radius / 25) * pop, force_grin=True)
        _crown_badge(frame, W / 2, champ_y - hop - 88, 62)
        if reigning == hero.key:
            scenery.draw_gold_star(frame, W / 2 + 66, champ_y - hop - 54, 18)
        if is_final:
            _draw_trophy_cup(frame, W / 2 - 170, champ_y + 4, scale=1.1)
            _draw_trophy_cup(frame, W / 2 + 170, champ_y + 4, scale=1.1)
    elif bot is not None:
        from src.rendering import balls
        balls.draw_ball(frame, None, bot, (W / 2, champ_y - hop), 0.0, 0.0, (0, 0), 0.0, "neutral", "victory", t, 2.3)
    name_col = colour if sum(colour) > 160 else (0, 245, 255)
    blit_text(frame, fit_width(outlined(f"{name.upper()} WINS!", 64, fill=name_col, width=7), cw - 80),
              center=(W / 2, panel.top + top_h - 98))

    pills: list[tuple[str, tuple[int, int, int], tuple[int, int, int]]] = []
    pts_str = getattr(outcome, "winner_points_pill", None) or points
    if pts_str:
        pills.append((pts_str, (0, 229, 255), WHITE))
    ko_txt = getattr(outcome, "ko_pill_text", None)
    if ko_txt:
        pills.append((ko_txt, (255, 196, 36), (255, 228, 80)))
    if pills:
        pill_w = 400 if len(pills) == 2 else 480
        gap = 24
        total = pill_w * len(pills) + gap * (len(pills) - 1)
        x0 = W / 2 - total / 2
        for k, (txt, bd, fc) in enumerate(pills):
            r = pygame.Rect(int(x0 + k * (pill_w + gap)), panel.top + top_h - 54, pill_w, 46)
            pygame.draw.rect(frame, BLACK, r.move(0, 4), border_radius=16)
            pygame.draw.rect(frame, (20, 18, 42), r, border_radius=16)
            pygame.draw.rect(frame, bd, r, 3, border_radius=16)
            blit_text(frame, fit_width(outlined(txt, 30, fill=fc, width=4), r.width - 24), center=r.center)

    # ---- MIDDLE 46%: vertical IPL Top-4 points table (or Grand Final podium)
    inner = pygame.Rect(panel.left + 24, mid_top + 6, cw - 48, mid_h - 12)
    pygame.draw.rect(frame, (14, 14, 30), inner, border_radius=22)
    pygame.draw.rect(frame, (255, 255, 255, 60), inner, 2, border_radius=22)
    head = pygame.Rect(inner.left, inner.top, inner.width, 62)
    pygame.draw.rect(frame, (36, 30, 74), head, border_top_left_radius=22, border_top_right_radius=22)
    pygame.draw.line(frame, (255, 208, 44), head.bottomleft, head.bottomright, 3)
    snum = getattr(outcome, "season_number", 1) if outcome else 1
    if outcome is not None and is_final:
        _draw_trophy_cup(frame, head.left + 34, head.centery + 4, scale=0.55)
        blit_text(frame, fit_width(outlined(f"SEASON {snum} CHAMPION: {name.upper()}", 32, fill=(255, 226, 72), width=4),
                                   head.width - 90), midleft=(head.left + 66, head.centery))
    else:
        blit_text(frame, outlined(f"SEASON {snum} STANDINGS", 30, fill=WHITE, width=4), midleft=(head.left + 22, head.centery))
        if outcome is not None:
            rt = outcome.right_status_text
            rs = outlined(rt, 26, fill=(28, 20, 8), outline=(255, 236, 140), width=2)
            pr = pygame.Rect(0, 0, rs.get_width() + 30, 42)
            pr.midright = (head.right - 16, head.centery)
            pygame.draw.rect(frame, BLACK, pr.move(0, 3), border_radius=21)
            pygame.draw.rect(frame, (255, 212, 36), pr, border_radius=21)
            pygame.draw.rect(frame, BLACK, pr, 3, border_radius=21)
            blit_text(frame, rs, center=pr.center)

    rows_top = head.bottom + 8
    row_h = (inner.bottom - 8 - rows_top) / 4.0
    medal = [(255, 214, 44), (214, 222, 236), (226, 146, 82), (148, 158, 184)]
    grow = min(1.0, max(0.0, (t - 0.15) / 0.7))
    grow = 1.0 - (1.0 - grow) ** 3
    if outcome is not None and is_final:
        podium = list(getattr(outcome, "podium", None) or [outcome.winner_key])
        labels = ["CHAMPION", "RUNNER-UP", "THIRD"]
        for idx, hk in enumerate(podium[:3]):
            cy = rows_top + row_h * (idx + 0.5) + row_h * 0.25
            rect = pygame.Rect(inner.left + 12, int(cy - row_h * 0.62), inner.width - 24, int(row_h * 1.15))
            pygame.draw.rect(frame, (30, 26, 54) if idx else (78, 58, 18), rect, border_radius=16)
            blit_text(frame, outlined(f"#{idx + 1}", 44, fill=medal[idx], width=5), midleft=(rect.left + 14, rect.centery))
            _mini_hero_ball(frame, hk, rect.left + 128, rect.centery, 26, reigning)
            hn = HERO_BY_KEY[hk].name.upper() if hk in HERO_BY_KEY else hk.upper()
            blit_text(frame, outlined(hn, 38, fill=WHITE, width=4), midleft=(rect.left + 168, rect.centery))
            blit_text(frame, outlined(labels[idx], 30, fill=medal[idx], width=4), midright=(rect.right - 18, rect.centery))
    elif outcome is not None:
        rows = list(getattr(outcome, "top4", None) or [(k, p, 0) for k, p in outcome.top3])
        rows.sort(key=lambda r_: -int(r_[1]))              # v4.3 P0: strictly points DESC (stable tie order)
        assert all(rows[i][1] >= rows[i + 1][1] for i in range(len(rows) - 1)), rows
        top_pts = max(1, rows[0][1]) if rows else 1
        for idx, (hk, hpts, delta) in enumerate(rows[:4]):
            cy = rows_top + row_h * (idx + 0.5)
            rect = pygame.Rect(inner.left + 10, int(cy - row_h / 2 + 4), inner.width - 20, int(row_h - 8))
            pygame.draw.rect(frame, (28, 26, 52) if idx % 2 == 0 else (22, 20, 42), rect, border_radius=14)
            if hk == outcome.winner_key:
                pygame.draw.rect(frame, (0, 229, 255), rect, 3, border_radius=14)
            rk = outlined(f"#{idx + 1}", 40, fill=medal[idx], width=5)
            blit_text(frame, rk, midleft=(rect.left + 12, rect.centery))
            if idx == 0:
                _crown_badge(frame, rect.left + 12 + rk.get_width() / 2, rect.centery - 30, 22)
            _mini_hero_ball(frame, hk, rect.left + 112, rect.centery, 21, reigning)
            hn = HERO_BY_KEY[hk].name.upper() if hk in HERO_BY_KEY else hk.upper()
            blit_text(frame, fit_width(outlined(hn, 32, fill=WHITE, width=4), 176), midleft=(rect.left + 142, rect.centery))
            if idx == 0 and getattr(outcome, "lead_changed", False):
                nl = outlined("NEW LEADER!", 20, fill=WHITE, outline=BLACK, width=3)
                nr = pygame.Rect(0, 0, nl.get_width() + 22, 28)
                nr.midleft = (rect.left + 136, rect.top + 1)
                flash = 0.5 + 0.5 * math.sin(t * 9)
                pygame.draw.rect(frame, BLACK, nr.move(0, 3), border_radius=14)
                pygame.draw.rect(frame, (int(205 + 45 * flash), 30, 60), nr, border_radius=14)
                pygame.draw.rect(frame, (255, 226, 72), nr, 2, border_radius=14)
                blit_text(frame, nl, center=nr.center)
            pts_s = outlined(f"{hpts} PTS", 34, fill=(255, 236, 140) if idx == 0 else WHITE, width=4)
            pts_r = blit_text(frame, pts_s, midright=(rect.right - 14, rect.centery))
            right_edge = pts_r.left - 10
            if delta > 0:
                right_edge = _delta_tag(frame, right_edge, rect.centery, delta) - 12
            bar_l = rect.left + 330
            bar_w = max(40, right_edge - bar_l)
            track = pygame.Rect(bar_l, int(rect.centery - 9), int(bar_w), 18)
            pygame.draw.rect(frame, (10, 10, 22), track, border_radius=9)
            fill_w = int(track.width * grow * max(0.04, hpts / top_pts))
            if fill_w > 4:
                pygame.draw.rect(frame, medal[idx] if idx < 3 else (120, 190, 255),
                                 (track.left, track.top, fill_w, track.height), border_radius=9)
                pygame.draw.rect(frame, (255, 255, 255), (track.left + 4, track.top + 3, max(0, fill_w - 8), 4), border_radius=2)
            pygame.draw.rect(frame, BLACK, track, 2, border_radius=9)

    # ---- BOTTOM 12%: Ep 1-29 single-line verbatim spoken CTA pill | Ep 30 golden championship banner (zero CTA)
    cta = pygame.Rect(panel.left + 30, bot_top + 14, cw - 60, ch - (bot_top - panel.top) - 32)
    bob = 2.5 * math.sin(t * 6.5)
    if is_final:
        shine = 0.5 + 0.5 * math.sin(t * 5.0)
        pygame.draw.rect(frame, BLACK, cta.move(0, 5), border_radius=cta.height // 2)
        pygame.draw.rect(frame, (int(222 + 30 * shine), int(160 + 40 * shine), 18), cta, border_radius=cta.height // 2)
        pygame.draw.rect(frame, (255, 246, 170), cta.inflate(-12, -12), 3, border_radius=cta.height // 2 - 6)
        pygame.draw.rect(frame, BLACK, cta, 5, border_radius=cta.height // 2)
        txt = f"ALL HAIL SEASON {snum} CHAMPION: {name.upper()}!"
        cs = fit_width(outlined(txt, 36, fill=(255, 252, 230), outline=(92, 52, 6), width=4), cta.width - 150)
        r_txt = blit_text(frame, cs, center=(cta.centerx, cta.centery + bob))
        _draw_trophy_cup(frame, r_txt.left - 34, cta.centery + 4 + bob, scale=0.42)
        _crown_badge(frame, r_txt.right + 36, cta.centery + bob, 40)
        gold = pygame.Rect(0, 200, W, H - 200)
        effects.draw_confetti(frame, t + 0.2, 97, gold, n=170)     # denser championship confetti
        effects.draw_confetti(frame, t, 73, panel.inflate(120, 80), n=70)
        return
    pygame.draw.rect(frame, BLACK, cta.move(0, 4), border_radius=cta.height // 2)
    pygame.draw.rect(frame, (250, 204, 21), cta, border_radius=cta.height // 2)
    pygame.draw.rect(frame, BLACK, cta, 4, border_radius=cta.height // 2)
    txt = (prompt or "Drop your pick below!").strip().upper()
    cs = fit_width(outlined(txt, 38, fill=(26, 18, 40), outline=(255, 250, 220), width=3), cta.width - 110)
    r_txt = blit_text(frame, cs, center=(cta.centerx - 24, cta.centery + bob))
    _down_arrow(frame, r_txt.right + 34, cta.centery + bob * 1.6, 30)

    effects.draw_confetti(frame, t, 73, panel.inflate(80, 60), n=30)


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
