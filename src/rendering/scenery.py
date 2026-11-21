"""Polished scenery, 8 Procedural Seasonal Themes & Broadcast HUD Art (§8, §15, v4.0):
- 8 zero-asset Seasonal Themes (Royal Classic, Frostbite Siege, Volcanic Foundry, Cyber Neon Keep,
  Monsoon Storm, Haunted Castle, Desert Mirage, Candy Chaos) + Grand Final Championship Gold Trim.
- Architectural 2D stitched platforms (snow caps + icicles, obsidian lava seams, cyber neon grid,
  moss stone, cracked gothic stone, desert sandstone, wafer biscuit + frosting drips — ZERO paper triangles).
- Top-right 240x220 Commentator Booth Cam for MC Tuno with RMS lip-sync + LIVE indicator.
- Reigning Season Champion wears a persistent Gold Champion Star (★) badge in HUD."""
from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from src.characters.expressions import BLACK, WHITE
from src.characters.roster import Hero
from src.characters.tuno import draw_tuno
from src.config import H, LAYOUT, W, font_path

HEADER_BOTTOM = LAYOUT["header"][1]
PANEL = pygame.Rect(28, 120, 760, 104)          # Top-left dynamic-width Top-5 Heroes Bar
CAM_RECT = pygame.Rect(816, 20, 240, 220)       # 240x220 rounded-rectangle Broadcast Booth Window


def mix(a, b, k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(a[i] + (b[i] - a[i]) * k))) for i in range(3))  # type: ignore[return-value]


@lru_cache(maxsize=24)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


def draw_gold_star(surface: pygame.Surface, cx: float, cy: float, r_outer: float) -> None:
    """Draws a crisp 5-pointed Gold Champion Star (★) with comic black outline for the reigning Season Champion."""
    pts: list[tuple[float, float]] = []
    r_inner = r_outer * 0.44
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    pygame.draw.polygon(surface, BLACK, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(surface, (255, 214, 36), pts)
    pygame.draw.polygon(surface, BLACK, pts, max(2, int(r_outer * 0.18)))
    pygame.draw.circle(surface, (255, 250, 190), (int(cx - r_outer * 0.14), int(cy - r_outer * 0.16)), max(1, int(r_outer * 0.18)))


# ---------------------------------------------------------------------------------------------- 3-layer parallax sky
def _cloud(s: pygame.Surface, x: float, y: float, w: float, col, shade) -> None:
    rng = random.Random(int(x * 7 + y))
    puffs = [(x + w * k, y - rng.uniform(0.1, 0.45) * w * 0.5, w * rng.uniform(0.22, 0.34))
             for k in (0.0, 0.22, 0.45, 0.68, 0.9)]
    for px, py, r in puffs:
        pygame.draw.circle(s, shade, (px, py + r * 0.18), r)
    for px, py, r in puffs:
        pygame.draw.circle(s, col, (px, py), r)
    pygame.draw.rect(s, col, (x - w * 0.05, y - w * 0.12, w * 1.0, w * 0.2), border_radius=int(w * 0.1))


def parallax_layers(theme, finale: bool = False) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    """v4.0: 3 seamless depth layers skinned for all 8 Seasonal Themes (+ Grand Final gold trim)."""
    bstyle = getattr(theme, "block_style", "royal")
    dark_sky = bstyle in ("obsidian", "neon", "gothic", "moss", "frost")

    # Layer 1: Sky gradient + celestial features (Haunted crescent moon, Desert sun, Cyber horizon grid, clouds)
    sky_bg = pygame.Surface((W, H))
    top = theme.sky_top if dark_sky else mix(theme.sky_top, WHITE, 0.14)
    bot = theme.sky_bottom if dark_sky else mix(theme.sky_bottom, WHITE, 0.20)
    for y in range(H):
        pygame.draw.line(sky_bg, mix(top, bot, y / H), (0, y), (W, y))

    if bstyle == "gothic":
        # S6 Haunted Castle: Large pale crescent moon with eerie halo in midnight-purple sky
        mcx, mcy, mr = 780, 470, 96
        halo = pygame.Surface((mr * 4, mr * 4), pygame.SRCALPHA)
        for hr in range(int(mr * 1.8), mr, -8):
            pygame.draw.circle(halo, (220, 245, 195, 14), (mr * 2, mr * 2), hr)
        sky_bg.blit(halo, (mcx - mr * 2, mcy - mr * 2))
        moon = pygame.Surface((mr * 3, mr * 3), pygame.SRCALPHA)
        pygame.draw.circle(moon, (246, 248, 212, 245), (int(mr * 1.5), int(mr * 1.5)), mr)
        pygame.draw.circle(moon, (0, 0, 0, 0), (int(mr * 1.5 + 34), int(mr * 1.5 - 18)), int(mr * 0.86))
        sky_bg.blit(moon, (mcx - int(mr * 1.5), mcy - int(mr * 1.5)))
    elif bstyle == "sandstone":
        # S7 Desert Mirage: Blazing amber sunset sun disc
        scx, scy = 760, 560
        for sr, al in ((150, 35), (120, 55), (92, 220)):
            sun = pygame.Surface((sr * 2 + 8, sr * 2 + 8), pygame.SRCALPHA)
            pygame.draw.circle(sun, (255, 236, 156, al), (sr + 4, sr + 4), sr)
            sky_bg.blit(sun, (scx - sr - 4, scy - sr - 4))
    elif bstyle == "neon":
        # S4 Cyber Neon Keep: Synthwave neon perspective grid + glowing cyber sun
        scx, scy = 540, 620
        nsun = pygame.Surface((240, 240), pygame.SRCALPHA)
        pygame.draw.circle(nsun, (255, 42, 182, 165), (120, 120), 104)
        for yy in range(118, 228, 16):
            pygame.draw.rect(nsun, (0, 0, 0, 0), (0, yy, 240, 6))
        sky_bg.blit(nsun, (scx - 120, scy - 120))
        for gy in range(720, 1260, 68):
            pygame.draw.line(sky_bg, mix(bot, (0, 235, 255), 0.25), (0, gy), (W, gy), 2)

    cloud_col = (
        (255, 220, 242) if bstyle == "wafer"
        else (mix(theme.sky_bottom, (90, 95, 118), 0.45) if dark_sky else mix(WHITE, theme.sky_bottom, 0.10))
    )
    shade_col = mix(cloud_col, theme.sky_top, 0.34)
    if bstyle != "neon":
        rng = random.Random(11)
        for i in range(6):
            x, y = i * 190 + rng.randint(-25, 25), rng.randint(360, 880)
            cw = rng.randint(170, 250)
            for ox in (0, -W, W):
                _cloud(sky_bg, x + ox, y, cw, cloud_col, shade_col)

    # Layer 2: Distant castle spires & curtain wall (seamless wrap across W)
    spires = pygame.Surface((W, H), pygame.SRCALPHA)
    far = mix(theme.castle, bot, 0.38 if dark_sky else 0.50)
    far_d = mix(far, BLACK if dark_sky else theme.sky_top, 0.26)
    win_col = {
        "obsidian": (255, 126, 28),
        "neon": (0, 242, 255),
        "gothic": (148, 255, 112),
        "frost": (195, 246, 255),
    }.get(bstyle, mix(far_d, BLACK, 0.28))
    rng2 = random.Random(23)
    pygame.draw.rect(spires, far, (0, 1260, W, H - 1260))
    for i in range(6):
        x = i * 180 + rng2.randint(-20, 20)
        tw = rng2.randint(78, 118)
        th_h = rng2.randint(420, 680)
        top_y = 1360 - th_h
        for ox in (0, -W, W):
            bx = x + ox
            pygame.draw.rect(spires, far, (bx, top_y, tw, th_h + 420))
            pygame.draw.rect(spires, far_d, (bx + tw * 0.68, top_y, tw * 0.32, th_h + 420))
            for k in range(int(tw // 26) + 1):
                pygame.draw.rect(spires, far, (bx + k * 26 - 4, top_y - 20, 16, 22))
            roof = [(bx - 12, top_y - 18), (bx + tw + 12, top_y - 18), (bx + tw / 2, top_y - 125)]
            roof_c = (232, 246, 255) if bstyle == "frost" else ((255, 126, 186) if bstyle == "wafer" else far_d)
            pygame.draw.polygon(spires, roof_c, roof)
            if bstyle == "neon":
                pygame.draw.polygon(spires, (255, 48, 192), roof, 2)
            pygame.draw.rect(spires, win_col, (bx + tw / 2 - 8, top_y + 52, 16, 34), border_radius=8)

    # Layer 3: Mid-ground castle viaduct arches + themed/finale pennant flags (seamless wrap across W)
    mid = pygame.Surface((W, H), pygame.SRCALPHA)
    mid_stone = mix(theme.castle, bot, 0.28 if dark_sky else 0.34)
    mid_dark = mix(mid_stone, BLACK, 0.22)
    mid_hi = (255, 214, 48) if finale else (theme.accent if bstyle == "neon" else mix(mid_stone, WHITE, 0.20))
    span = W // 4
    parapet_y = 1190
    pygame.draw.rect(mid, mid_stone, (0, parapet_y, W, 56))
    pygame.draw.line(mid, mid_hi, (0, parapet_y + 3), (W, parapet_y + 3), 4)
    pygame.draw.line(mid, mid_dark, (0, parapet_y + 52), (W, parapet_y + 52), 5)
    for x in range(0, W, 54):
        pygame.draw.rect(mid, mid_stone, (x + 6, parapet_y - 22, 34, 24), border_radius=4)
    if finale:
        pennant_cols = [(255, 212, 38), (236, 48, 76), (255, 236, 120), (245, 158, 11)]
    elif bstyle == "neon":
        pennant_cols = [(0, 242, 255), (255, 48, 192), (168, 85, 247), (56, 189, 248)]
    elif bstyle == "wafer":
        pennant_cols = [(255, 108, 182), (112, 224, 255), (255, 220, 72), (168, 242, 148)]
    else:
        pennant_cols = [(235, 58, 82), (255, 208, 40), (0, 205, 245), (155, 89, 210)]
    for i in range(4):
        px = i * span
        for ox in (0, -W, W):
            bx = px + ox
            pygame.draw.rect(mid, mid_stone, (bx - 30, parapet_y + 52, 60, H - parapet_y))
            pygame.draw.rect(mid, mid_dark, (bx + 10, parapet_y + 52, 20, H - parapet_y))
            arch_pts = [(bx + 28, parapet_y + 52), (bx + span - 28, parapet_y + 52)]
            for u in range(13):
                ang = math.pi * (1.0 - u / 12)
                arch_pts.append((bx + span / 2 + math.cos(ang) * (span / 2 - 28),
                                 parapet_y + 150 - math.sin(ang) * 92))
            pygame.draw.polygon(mid, mid_dark, arch_pts)
            pole_x = bx
            pygame.draw.line(mid, mid_dark, (pole_x, parapet_y - 98), (pole_x, parapet_y - 18), 5)
            pcol = pennant_cols[i % len(pennant_cols)]
            pygame.draw.polygon(mid, pcol, [(pole_x + 2, parapet_y - 96), (pole_x + 56, parapet_y - 80),
                                            (pole_x + 2, parapet_y - 62)])
            for f_idx in range(3):
                fx = bx + 58 + f_idx * 56
                fy = parapet_y + 56
                fc = pennant_cols[(i + f_idx) % len(pennant_cols)]
                pygame.draw.polygon(mid, fc, [(fx - 14, fy), (fx + 14, fy), (fx, fy + 38)])
    return sky_bg, spires, mid


def sky(theme) -> pygame.Surface:
    """Single-surface composite fallback."""
    s, sp, md = parallax_layers(theme)
    out = s.copy()
    out.blit(sp, (0, 0))
    out.blit(md, (0, 0))
    return out


# ---------------------------------------------------------------------------------------------- broadcast header (v3.4/v4.0)
def castle_header(theme) -> pygame.Surface:
    """Sleek 240x220 rounded-rectangle Broadcast Booth Window backdrop (inside 256x236 shadow canvas)."""
    s = pygame.Surface((256, 236), pygame.SRCALPHA)
    win = pygame.Rect(8, 6, 240, 220)
    pygame.draw.rect(s, (0, 0, 0, 115), win.move(4, 7), border_radius=24)
    pygame.draw.rect(s, BLACK, win.inflate(8, 8), border_radius=26)
    pygame.draw.rect(s, (138, 96, 12), win, border_radius=22)

    inner = win.inflate(-16, -16)
    booth = pygame.Surface(inner.size, pygame.SRCALPHA)
    bw, bh = inner.size
    booth.fill((28, 20, 56))
    for x in range(12, bw, 22):
        pygame.draw.line(booth, (36, 26, 70), (x, 0), (x, bh), 4)
    pygame.draw.polygon(booth, (66, 42, 118), [(0, 0), (78, 0), (195, bh), (96, bh)])
    pygame.draw.polygon(booth, (0, 205, 245, 34), [(bw, 0), (bw - 65, 0), (50, bh), (130, bh)])
    pygame.draw.circle(booth, (0, 229, 255, 48), (int(bw * 0.56), int(bh * 0.48)), 74, 5)
    mask = pygame.Surface(inner.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=16)
    booth.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(booth, inner.topleft)
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


def _fit(surf: pygame.Surface, width: float) -> pygame.Surface:
    if surf.get_width() <= width:
        return surf
    return pygame.transform.smoothscale(surf, (int(width), max(1, int(surf.get_height() * width / surf.get_width()))))


@lru_cache(maxsize=24)
def episode_ribbon(text: str) -> pygame.Surface:
    """Stylized cartoon episode ribbon with thick black outline."""
    is_final = "GRAND FINAL" in text.upper()
    txt = _outlined_text(text.upper(), 28, fill=(255, 228, 72) if is_final else (255, 214, 0), outline=BLACK, w=4)
    w = min(516, txt.get_width() + 42)
    h = 52
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pts = [(10, 4), (w - 4, 4), (w - 16, h - 4), (2, h - 4)]
    pygame.draw.polygon(s, BLACK, [(x + 3, y + 4) for x, y in pts])
    pygame.draw.polygon(s, (124, 28, 52) if is_final else (46, 48, 78), pts)
    if is_final:
        pygame.draw.polygon(s, (255, 212, 44), pts, 6)
    pygame.draw.polygon(s, BLACK, pts, 4)
    fit = _fit(txt, w - 32)
    s.blit(fit, fit.get_rect(center=(w / 2, h / 2 + 1)))
    return s


def _draw_twist_icon(s: pygame.Surface, kind: str, cx: float, cy: float) -> None:
    if kind == "bolt":
        pts = [(cx + 2, cy - 12), (cx - 8, cy + 1), (cx - 1, cy + 1), (cx - 4, cy + 12), (cx + 8, cy - 2), (cx + 1, cy - 2)]
        pygame.draw.polygon(s, BLACK, [(x + 1, y + 1) for x, y in pts])
        pygame.draw.polygon(s, (250, 204, 21), pts)
        pygame.draw.polygon(s, BLACK, pts, 2)
    elif kind in ("down", "up"):
        sgn = 1 if kind == "down" else -1
        pts = [
            (cx - 4, cy - 10 * sgn), (cx + 4, cy - 10 * sgn),
            (cx + 4, cy + 1 * sgn), (cx + 10, cy + 1 * sgn),
            (cx, cy + 11 * sgn), (cx - 10, cy + 1 * sgn), (cx - 4, cy + 1 * sgn),
        ]
        col = (255, 118, 42) if kind == "down" else (0, 229, 255)
        pygame.draw.polygon(s, col, pts)
        pygame.draw.polygon(s, BLACK, pts, 2)
    elif kind == "ice":
        for k in range(3):
            a = k * math.pi / 3
            p0 = (cx - math.cos(a) * 10, cy - math.sin(a) * 10)
            p1 = (cx + math.cos(a) * 10, cy + math.sin(a) * 10)
            pygame.draw.line(s, BLACK, p0, p1, 5)
            pygame.draw.line(s, (165, 243, 252), p0, p1, 3)
    else:
        pygame.draw.circle(s, BLACK, (cx, cy), 10)
        pygame.draw.circle(s, (250, 204, 21), (cx, cy), 8)
        pygame.draw.circle(s, WHITE, (cx - 2, cy - 2), 3)


@lru_cache(maxsize=32)
def _twist_badge_surf(icon_kind: str, label: str, accent: tuple[int, int, int]) -> pygame.Surface:
    txt = _outlined_text(label.upper(), 22, fill=WHITE, outline=BLACK, w=3)
    w = min(310, txt.get_width() + 48)
    h = 36
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    r = pygame.Rect(0, 0, w, h)
    pygame.draw.rect(s, (0, 0, 0, 120), r.move(2, 3), border_radius=12)
    pygame.draw.rect(s, (26, 22, 48, 232), r, border_radius=12)
    pygame.draw.rect(s, accent, r, 3, border_radius=12)
    _draw_twist_icon(s, icon_kind, 20, h / 2)
    fit = _fit(txt, w - 42)
    s.blit(fit, fit.get_rect(midleft=(36, h / 2 + 1)))
    return s


def draw_header(frame: pygame.Surface, portrait_bg: pygame.Surface, ep_label: str, tuno_state: str, t: float,
                text_boxes: list, speech: str = "", talking: bool | None = None,
                voice_rms: float | None = None, twist_badge: tuple[str, str, tuple[int, int, int]] | None = None) -> None:
    """Top-left Episode Ribbon + Active Twist Badge + Top-right 240x220 Broadcast Booth Window with LIVE badge."""
    rib = episode_ribbon(ep_label.replace(" - ", " • "))
    r = rib.get_rect(topleft=(28, 20))
    frame.blit(rib, r)
    text_boxes.append(r)

    if twist_badge is not None:
        ik, lbl, acc = twist_badge
        tb = _twist_badge_surf(ik, lbl, acc)
        tr = tb.get_rect(topleft=(30, 76))
        frame.blit(tb, tr)
        text_boxes.append(tr)

    frame.blit(portrait_bg, (CAM_RECT.left - 8, CAM_RECT.top - 6))
    buf = pygame.Surface(CAM_RECT.size, pygame.SRCALPHA)
    draw_tuno(buf, 134, 216, tuno_state, t, scale=1.0, talking=talking, voice_rms=voice_rms)

    mask = pygame.Surface(CAM_RECT.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), pygame.Rect(8, 8, 224, 204), border_radius=16)
    buf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(buf, CAM_RECT.topleft)

    outer_gold = (156, 108, 14) if tuno_state != "SWEATING_INTENSE" else (196, 52, 48)
    inner_gold = (246, 198, 48) if tuno_state != "SWEATING_INTENSE" else (255, 126, 72)
    pygame.draw.rect(frame, BLACK, CAM_RECT.inflate(4, 4), 4, border_radius=24)
    pygame.draw.rect(frame, outer_gold, CAM_RECT, 8, border_radius=22)
    pygame.draw.rect(frame, inner_gold, CAM_RECT.inflate(-6, -6), 3, border_radius=19)
    pygame.draw.rect(frame, BLACK, CAM_RECT.inflate(-14, -14), 3, border_radius=16)

    live_box = pygame.Rect(CAM_RECT.left + 14, CAM_RECT.top + 13, 76, 25)
    live_plate = pygame.Surface(live_box.size, pygame.SRCALPHA)
    pygame.draw.rect(live_plate, (14, 14, 24, 222), live_plate.get_rect(), border_radius=8)
    pygame.draw.rect(live_plate, (246, 198, 48, 150), live_plate.get_rect(), 2, border_radius=8)
    blink_on = int(t * 2.6) % 2 == 0
    if blink_on:
        pygame.draw.circle(live_plate, (255, 48, 68, 95), (14, 12), 8)
        pygame.draw.circle(live_plate, (255, 42, 62), (14, 12), 5)
    else:
        pygame.draw.circle(live_plate, (120, 26, 36), (14, 12), 5)
    live_txt = font(18).render("LIVE", True, WHITE if blink_on else (205, 210, 224))
    live_plate.blit(live_txt, live_txt.get_rect(midleft=(25, 13)))
    frame.blit(live_plate, live_box.topleft)


def _crown(frame, cx: float, cy: float, w: float) -> None:
    pts = [(cx - w / 2, cy + w * 0.35), (cx - w / 2, cy - w * 0.1), (cx - w / 4, cy + w * 0.12), (cx, cy - w * 0.25),
           (cx + w / 4, cy + w * 0.12), (cx + w / 2, cy - w * 0.1), (cx + w / 2, cy + w * 0.35)]
    pygame.draw.polygon(frame, (255, 205, 40), pts)
    pygame.draw.polygon(frame, BLACK, pts, 2)


def _icon(frame, h: Hero, c, rad: float, expr: str = "neutral", star: bool = False) -> None:
    from src.rendering import balls
    balls.draw_ball(frame, h, None, c, 0.0, 0.0, (0, 0), 0.0, expr, "none", 0.0, rad / max(1.0, h.radius))
    if star:
        draw_gold_star(frame, c[0] + rad * 0.72, c[1] - rad * 0.68, max(8.0, rad * 0.36))


def draw_panel(frame: pygame.Surface, survivors: int, total: int, heroes: list[Hero], status: dict[str, str],
               ranks: dict[str, int], text_boxes: list, pulse: float = 0.0, t: float = 0.0,
               eff_slots: float | None = None, reigning_champion: str | None = None) -> None:
    """v4.0 Dynamic Top-Left HUD:
    - Snappy 1.22x red pulse + shake animation on ALIVE: X/Y pill synced to exact visual KO frame.
    - Auto-shrinking Top-5 Leaderboard pill + persistent Gold Champion Star (★) for reigning Season Champion."""
    p = max(0.0, min(1.0, pulse))
    k_scale = 1.0 + 0.22 * p
    shake_dx = math.sin(t * 68.0) * 6.0 * p
    shake_dy = math.cos(t * 54.0) * 3.5 * p

    base_w, base_h = 220, 52
    pill_surf = pygame.Surface((base_w + 10, base_h + 10), pygame.SRCALPHA)
    pr = pygame.Rect(4, 3, base_w, base_h)
    pygame.draw.rect(pill_surf, BLACK, pr.move(3, 4), border_radius=15)
    bg_col = mix((24, 26, 40), (168, 24, 44), min(1.0, p * 1.15))
    bd_col = mix(WHITE, (255, 72, 86), min(1.0, p * 1.3))
    pygame.draw.rect(pill_surf, bg_col, pr, border_radius=15)
    pygame.draw.rect(pill_surf, bd_col, pr, 3, border_radius=15)
    lab = font(25).render("ALIVE:", True, WHITE)
    num_col = (255, 224, 64) if (survivors <= 3 and p < 0.25) else ((255, 255, 255) if p > 0.35 else (255, 92, 92))
    num = font(32).render(f"{survivors}/{total}", True, num_col)
    pill_surf.blit(lab, lab.get_rect(midleft=(pr.left + 14, pr.centery + 2)))
    pill_surf.blit(num, num.get_rect(midright=(pr.right - 14, pr.centery + 2)))

    if k_scale > 1.005:
        pill_surf = pygame.transform.rotozoom(pill_surf, math.sin(t * 48.0) * 2.2 * p, k_scale)
    alive_anchor = (670 + shake_dx, 46 + shake_dy)
    ar = frame.blit(pill_surf, pill_surf.get_rect(center=(int(alive_anchor[0]), int(alive_anchor[1]))))
    text_boxes.append(ar)

    live = sorted((h for h in heroes if status.get(h.key) != "out"), key=lambda h: ranks.get(h.key, 99))[:5]
    if not live:
        return
    slot_w = 148.0
    slots = max(float(len(live)), min(5.0, eff_slots if eff_slots is not None else float(len(live))))
    dyn_w = max(168, int(round(20.0 + slot_w * slots)))
    dyn_panel = pygame.Rect(PANEL.x, PANEL.y, dyn_w, PANEL.height)

    plate = pygame.Surface(dyn_panel.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 22, 36, 220), plate.get_rect(), border_radius=22)
    pygame.draw.rect(plate, (255, 255, 255, 88), plate.get_rect(), 3, border_radius=22)
    frame.blit(plate, dyn_panel.topleft)

    f_rank = font(32)
    for i, h in enumerate(live):
        cx = dyn_panel.x + 12 + slot_w * i + 42
        cy = dyn_panel.centery + 2
        _icon(
            frame,
            h,
            (cx, cy),
            32,
            "celebrating" if status.get(h.key) == "crown" else "neutral",
            star=(reigning_champion == h.key),
        )
        rank = ranks.get(h.key, i + 1)
        rn = f_rank.render(f"#{rank}", True, (255, 214, 0) if rank == 1 else WHITE)
        rb = frame.blit(rn, rn.get_rect(midleft=(cx + 39, cy + 2)))
        if rank == 1:
            _crown(frame, cx, cy - 39, 22)
        text_boxes.append(rb)


def draw_pick_strip(frame: pygame.Surface, heroes: list[Hero], t: float, text_boxes: list,
                    reigning_champion: str | None = None, hook_text: str = "PICK YOUR FIGHTER!") -> None:
    """Cold-open single-row hook strip in the top-left bar slot (y=120..224, capped at <=6 named characters)."""
    plate = pygame.Surface(PANEL.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 22, 36, 225), plate.get_rect(), border_radius=22)
    pygame.draw.rect(plate, (255, 214, 0, 210), plate.get_rect(), 4, border_radius=22)
    frame.blit(plate, PANEL)
    lab = font(26).render(hook_text.upper(), True, (255, 214, 0))
    text_boxes.append(frame.blit(lab, lab.get_rect(midtop=(PANEL.centerx, PANEL.y + 6))))
    shown = list(heroes)[:6]
    n = len(shown)
    step = (PANEL.width - 36) / max(1, n)
    for i, h in enumerate(shown):
        cx = PANEL.x + 18 + step * (i + 0.5)
        bob = 3 * math.sin(t * 9 + i)
        _icon(frame, h, (cx, PANEL.y + 70 + bob), 24, "happy", star=(reigning_champion == h.key))


# ---------------------------------------------------------------------------------------------- 8-Theme 2D Architecture
def rock_colours(theme) -> tuple:
    cap = theme.terrain
    rock = getattr(theme, "rock", None) or mix(mix(theme.castle, (148, 146, 162), 0.38), theme.terrain_outline, 0.20)
    return cap, rock, mix(rock, BLACK, 0.30), mix(rock, WHITE, 0.24)


def draw_support_pillar(frame: pygame.Surface, sx: float, sy_top: float, sy_bot: float, zoom: float, theme,
                        chain: bool = False) -> None:
    """Vertical masonry support pillar or heavy iron hanger chain."""
    if sy_bot <= sy_top + 12 or sx < -80 or sx > W + 80:
        return
    lw = max(2, int(4 * zoom))
    bstyle = getattr(theme, "block_style", "royal")
    if chain:
        link_h = max(12, int(22 * zoom))
        link_w = max(8, int(14 * zoom))
        y = sy_top
        idx = 0
        c_col = (0, 218, 242) if bstyle == "neon" else (125, 132, 148)
        while y > sy_bot:
            if idx % 2 == 0:
                r = pygame.Rect(int(sx - link_w / 2), int(y - link_h), link_w, link_h)
                pygame.draw.ellipse(frame, BLACK, r.inflate(4, 4), max(2, lw))
                pygame.draw.ellipse(frame, c_col, r, max(2, lw - 1))
            else:
                pygame.draw.line(frame, BLACK, (sx, y), (sx, y - link_h), lw + 3)
                pygame.draw.line(frame, mix(c_col, WHITE, 0.25), (sx, y - 2), (sx, y - link_h + 2), max(2, lw - 1))
            y -= int(link_h * 0.75)
            idx += 1
        return

    _, rock, dark, light = rock_colours(theme)
    col_base = mix(rock, BLACK, 0.14)
    col_sh = mix(dark, BLACK, 0.18)
    pw = max(18, int(46 * zoom))
    shaft = pygame.Rect(int(sx - pw / 2), int(sy_top), pw, int(sy_bot - sy_top))
    pygame.draw.rect(frame, col_base, shaft)
    pygame.draw.rect(frame, col_sh, (shaft.right - int(pw * 0.34), shaft.top, int(pw * 0.34), shaft.height))
    seam_col = (255, 92, 18) if bstyle == "obsidian" else ((0, 228, 248) if bstyle == "neon" else col_sh)
    pygame.draw.line(frame, mix(light, WHITE, 0.1), (shaft.left + 4, shaft.top), (shaft.left + 4, shaft.bottom), max(2, lw - 1))
    step_y = max(22, int(52 * zoom))
    for yy in range(int(sy_top) + step_y, int(sy_bot), step_y):
        pygame.draw.line(frame, seam_col, (shaft.left + 2, yy), (shaft.right - 2, yy), max(2, lw - 1))
    pygame.draw.line(frame, BLACK, shaft.topleft, shaft.bottomleft, lw)
    pygame.draw.line(frame, BLACK, shaft.topright, shaft.bottomright, lw)
    cap_w, cap_h = int(pw * 1.48), max(10, int(22 * zoom))
    corbel = [
        (sx - cap_w / 2, sy_top - 2),
        (sx + cap_w / 2, sy_top - 2),
        (sx + pw / 2 + 2, sy_top + cap_h),
        (sx - pw / 2 - 2, sy_top + cap_h),
    ]
    pygame.draw.polygon(frame, col_base, corbel)
    pygame.draw.polygon(frame, BLACK, corbel, lw)


def draw_track_chain(frame: pygame.Surface, pts: list[tuple[float, float]], mats: list[str], belts: list[float],
                     zoom: float, theme, t_anim: float = 0.0, finale: bool = False) -> None:
    """v4.0 Architectural 2D Platform Renderer with bespoke procedural textures for all 8 Seasonal Themes."""
    if len(pts) < 2:
        return
    _, rock, dark, light = rock_colours(theme)
    bstyle = getattr(theme, "block_style", "royal")
    lw = max(3, int(4.5 * zoom))
    is_beam = all(m in ("plank", "conveyor") for m in mats)
    slab_d = max(22.0, (58.0 if is_beam else 66.0) * zoom)
    chamfer = min(12.0 * zoom, slab_d * 0.25)

    n_pts = len(pts)
    bot_pts: list[tuple[float, float]] = []
    for i, (px, py) in enumerate(pts):
        if i == 0 and n_pts >= 2 and abs(pts[-1][0] - pts[0][0]) > 40 * zoom:
            sgn = 1.0 if pts[-1][0] >= pts[0][0] else -1.0
            bot_pts.append((px + sgn * chamfer, py + slab_d))
        elif i == n_pts - 1 and n_pts >= 2 and abs(pts[-1][0] - pts[0][0]) > 40 * zoom:
            sgn = -1.0 if pts[-1][0] >= pts[0][0] else 1.0
            bot_pts.append((px + sgn * chamfer, py + slab_d))
        else:
            bot_pts.append((px, py + slab_d))

    poly = list(pts) + bot_pts[::-1]
    if is_beam:
        core_col = (84, 90, 108) if "conveyor" in mats else (158, 106, 58)
        flange_col = (52, 56, 72)
        pygame.draw.polygon(frame, core_col, poly)
        flange_top = [(px, py + slab_d * 0.68) for px, py in pts]
        pygame.draw.polygon(frame, flange_col, flange_top + bot_pts[::-1])
        step_r = max(28.0, 66.0 * zoom)
        riv_r = max(2, int(3.4 * zoom))
        for seg_i in range(n_pts - 1):
            (ax, ay), (bx, by) = pts[seg_i], pts[seg_i + 1]
            dx = bx - ax
            if abs(dx) < 6:
                continue
            steps = max(1, int(abs(dx) / step_r))
            for k in range(steps):
                u0, u1 = k / steps, (k + 1) / steps
                x0, y0 = ax + dx * u0, ay + (by - ay) * u0
                x1, y1 = ax + dx * u1, ay + (by - ay) * u1
                if k % 2 == 0:
                    pygame.draw.line(frame, flange_col, (x0, y0 + slab_d * 0.22), (x1, y1 + slab_d * 0.68), max(2, lw - 1))
                else:
                    pygame.draw.line(frame, flange_col, (x0, y0 + slab_d * 0.68), (x1, y1 + slab_d * 0.22), max(2, lw - 1))
                pygame.draw.circle(frame, (205, 212, 226), (x0 + (x1 - x0) * 0.5, y0 + (y1 - y0) * 0.5 + slab_d * 0.82), riv_r)
        pygame.draw.polygon(frame, BLACK, poly, lw)
    elif bstyle == "wafer":
        # S8 Candy Chaos: Golden wafer biscuit slab with crisscrossed diagonal wafer grid
        biscuit = (226, 174, 98)
        biscuit_d = (182, 128, 58)
        pygame.draw.polygon(frame, biscuit, poly)
        shade_top = [(px, py + slab_d * 0.70) for px, py in pts]
        pygame.draw.polygon(frame, biscuit_d, shade_top + bot_pts[::-1])
        step_w = max(20.0, 38.0 * zoom)
        for seg_i in range(n_pts - 1):
            (ax, ay), (bx, by) = pts[seg_i], pts[seg_i + 1]
            dx, dy = bx - ax, by - ay
            slen = math.hypot(dx, dy)
            if slen < 14:
                continue
            nw = max(1, int(slen / step_w))
            for k in range(nw):
                u0, u1 = k / nw, (k + 1) / nw
                x0, y0 = ax + dx * u0, ay + dy * u0
                x1, y1 = ax + dx * u1, ay + dy * u1
                pygame.draw.line(frame, biscuit_d, (x0, y0 + slab_d * 0.16), (x1, y1 + slab_d * 0.88), max(2, int(2.5 * zoom)))
                pygame.draw.line(frame, biscuit_d, (x0, y0 + slab_d * 0.88), (x1, y1 + slab_d * 0.16), max(2, int(2.5 * zoom)))
        pygame.draw.polygon(frame, BLACK, poly, lw)
    else:
        # Stone / Obsidian / Cyber-Neon / Frost / Gothic / Sandstone Block Slab
        pygame.draw.polygon(frame, rock, poly)
        shade_top = [(px, py + slab_d * 0.68) for px, py in pts]
        pygame.draw.polygon(frame, dark, shade_top + bot_pts[::-1])

        seam_col = (
            (255, 98, 18) if bstyle == "obsidian"
            else ((0, 236, 255) if bstyle == "neon" else dark)
        )
        hi_col = (
            (255, 206, 68) if bstyle == "obsidian"
            else ((255, 48, 192) if bstyle == "neon" else light)
        )
        mid_line = [(px, py + slab_d * 0.50) for px, py in pts]
        hi_line = [(px, py + slab_d * 0.54) for px, py in pts]
        pygame.draw.lines(frame, seam_col, False, mid_line, max(2, int(3 * zoom)))
        pygame.draw.lines(frame, hi_col, False, hi_line, max(1, int(2 * zoom)))

        block_w = max(32.0, 76.0 * zoom)
        for seg_i in range(n_pts - 1):
            (ax, ay), (bx, by) = pts[seg_i], pts[seg_i + 1]
            dx, dy = bx - ax, by - ay
            seg_len = math.hypot(dx, dy)
            if seg_len < 16:
                continue
            nb = max(1, int(seg_len / block_w))
            for k in range(1, nb):
                u = k / nb
                jx, jy = ax + dx * u, ay + dy * u
                pygame.draw.line(frame, seam_col, (jx, jy + slab_d * 0.18), (jx, jy + slab_d * 0.50), max(2, int(2.8 * zoom)))
            for k in range(nb):
                u = (k + 0.5) / nb
                jx, jy = ax + dx * u, ay + dy * u
                pygame.draw.line(frame, seam_col, (jx, jy + slab_d * 0.50), (jx, jy + slab_d * 0.94), max(2, int(2.8 * zoom)))
                if bstyle == "gothic" and k % 2 == 0:
                    # Weathered gothic crack line
                    pygame.draw.lines(
                        frame,
                        BLACK,
                        False,
                        [(jx - 8 * zoom, jy + slab_d * 0.28), (jx - 2 * zoom, jy + slab_d * 0.44), (jx - 6 * zoom, jy + slab_d * 0.62)],
                        max(1, int(2 * zoom)),
                    )

        for i in range(1, n_pts - 1):
            pygame.draw.circle(frame, dark, bot_pts[i], max(3, int(5 * zoom)))
            pygame.draw.circle(frame, BLACK, bot_pts[i], max(3, int(5 * zoom)), max(2, lw - 1))
        pygame.draw.polygon(frame, (0, 236, 255) if bstyle == "neon" else BLACK, poly, lw)
        if finale:
            gold_line = [(px, py + slab_d * 0.84) for px, py in pts]
            pygame.draw.lines(frame, (255, 214, 42), False, gold_line, max(2, int(3.5 * zoom)))

        # S2 Frostbite Siege: Hanging sharp blue-white icicles along the underside of stone slabs!
        if bstyle == "frost":
            ic_step = max(24.0, 48.0 * zoom)
            for seg_i in range(n_pts - 1):
                (ax, ay), (bx, by) = bot_pts[seg_i], bot_pts[seg_i + 1]
                dx, dy = bx - ax, by - ay
                slen = math.hypot(dx, dy)
                nic = int(slen / ic_step)
                for k in range(1, nic):
                    u = k / max(1, nic)
                    ix, iy = ax + dx * u, ay + dy * u
                    ih = (16.0 + (k * 13 % 15)) * zoom
                    iw = 6.5 * zoom
                    tri = [(ix - iw, iy - 2), (ix + iw, iy - 2), (ix, iy + ih)]
                    pygame.draw.polygon(frame, (198, 242, 255), tri)
                    pygame.draw.polygon(frame, (38, 82, 138), tri, max(2, lw - 2))

    # Seamless Top Bevel Lip & Surface Cap
    cap_w = max(8, int(20 * zoom))
    for seg_i in range(n_pts - 1):
        a, b = pts[seg_i], pts[seg_i + 1]
        pygame.draw.line(frame, BLACK, a, b, cap_w + 8)
    for p in pts:
        pygame.draw.circle(frame, BLACK, p, (cap_w + 8) / 2)

    sprinkle_cols = ((255, 72, 128), (72, 220, 255), (255, 224, 52), (138, 245, 118))
    for seg_i, mat in enumerate(mats):
        a, b = pts[seg_i], pts[seg_i + 1]
        default_cap = (255, 212, 48) if (finale and mat == "ground" and bstyle == "sandstone") else theme.terrain
        cap_col = {
            "ice": (195, 240, 255),
            "mud": (118, 80, 46),
            "bouncy": (255, 88, 176),
            "conveyor": (62, 66, 82),
            "plank": (192, 136, 78),
        }.get(mat, default_cap)
        pygame.draw.line(frame, cap_col, a, b, cap_w)
        pygame.draw.circle(frame, cap_col, a, cap_w / 2)
        pygame.draw.circle(frame, cap_col, b, cap_w / 2)
        hi = (255, 248, 195) if finale else mix(cap_col, WHITE, 0.48)
        pygame.draw.line(frame, hi, (a[0] + 2, a[1] - cap_w * 0.24), (b[0] - 2, b[1] - cap_w * 0.24), max(2, cap_w // 4))

        if bstyle == "wafer" and mat == "ground":
            # S8 Candy Chaos: Pink frosting drips + rainbow sprinkles embedded in cap
            slen = math.hypot(b[0] - a[0], b[1] - a[1])
            ns = max(2, int(slen / max(18, 34 * zoom)))
            for kk in range(1, ns):
                u = kk / ns
                sx, sy = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
                if kk % 2 == 0:
                    pygame.draw.circle(frame, cap_col, (int(sx), int(sy + cap_w * 0.55)), max(3, int(5 * zoom)))
                sc = sprinkle_cols[kk % len(sprinkle_cols)]
                pygame.draw.circle(frame, sc, (int(sx), int(sy)), max(2, int(2.8 * zoom)))

        if mat == "bouncy":
            slen = math.hypot(b[0] - a[0], b[1] - a[1])
            ns = max(2, int(slen / max(14, 26 * zoom)))
            for kk in range(1, ns):
                u = kk / ns
                sx, sy = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
                pygame.draw.circle(frame, (255, 232, 90), (sx, sy), max(2, int(cap_w * 0.24)))
        belt = belts[seg_i] if seg_i < len(belts) else 0.0
        if belt:
            slen = math.hypot(b[0] - a[0], b[1] - a[1])
            ux, uy = (b[0] - a[0]) / max(1.0, slen), (b[1] - a[1]) / max(1.0, slen)
            nx, ny = -uy, ux
            step_c = max(20.0, 38.0 * zoom)
            off = (t_anim * abs(belt) * 0.25) % step_c
            sgn = 1.0 if belt > 0 else -1.0
            for kk in range(int(slen / step_c)):
                dist = kk * step_c + (off if sgn > 0 else step_c - off)
                if dist > slen - 8:
                    continue
                cx_b, cy_b = a[0] + ux * dist, a[1] + uy * dist
                d = 7 * zoom * sgn
                h_c = 5 * zoom
                chev = [
                    (cx_b - ux * d + nx * h_c, cy_b - uy * d + ny * h_c),
                    (cx_b + ux * d * 0.4, cy_b + uy * d * 0.4),
                    (cx_b - ux * d - nx * h_c, cy_b - uy * d - ny * h_c),
                ]
                pygame.draw.lines(frame, (255, 214, 0), False, chev, max(2, int(3 * zoom)))


def draw_cap(frame: pygame.Surface, a, b, zoom: float, theme, mat: str) -> None:
    draw_track_chain(frame, [a, b], [mat], [0.0], zoom, theme)


def _octagon_pts(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    # Matches SumoPoolPit._walkable: |x|<=0.88R, |y|<=0.88R, |x|+|y|<=1.26R -> vertices at (±0.88R, ±0.38R) and (±0.38R, ±0.88R)
    a, b = 0.88 * r, 0.38 * r
    return [
        (cx + a, cy - b), (cx + a, cy + b),
        (cx + b, cy + a), (cx - b, cy + a),
        (cx - a, cy + b), (cx - a, cy - b),
        (cx - b, cy - a), (cx + b, cy - a),
    ]


def draw_floating_platform(frame: pygame.Surface, centre, radius: float, zoom: float, theme, shape: str = "disc",
                           half: float = 0.0, spin_deg: float | None = None, pocket_r: float = 0.0,
                           finale: bool = False) -> None:
    """v4.0 TOP_DOWN arena floor: supports Rotating Disc, Square, Ring, and Octagonal Sumo Pool Pit with 4 corner pockets."""
    _, _rock, dark, _ = rock_colours(theme)
    bstyle = getattr(theme, "block_style", "royal")
    cx, cy = centre
    trim_col = (255, 214, 44) if finale else ((0, 236, 255) if bstyle == "neon" else mix(theme.terrain, WHITE, 0.34))

    if shape == "square":
        rim_h = max(14.0, 0.14 * half)
        r = pygame.Rect(cx - half, cy - half, 2 * half, 2 * half)
        pygame.draw.rect(frame, BLACK, r.move(0, rim_h).inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, dark, r.move(0, rim_h), border_radius=20)
        pygame.draw.rect(frame, BLACK, r.inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, theme.terrain, r, border_radius=20)
        pygame.draw.rect(frame, trim_col, r.inflate(-24, -24), 4, border_radius=16)
        return

    if shape == "octagon_pool":
        if radius < 4.0:
            return
        rim_h = max(8.0, 0.13 * radius)
        top_pts = _octagon_pts(cx, cy, radius)
        bot_pts = [(px, py + rim_h) for px, py in top_pts]
        # 3D underside skirt
        pygame.draw.polygon(frame, BLACK, [(px + (4 if px > cx else -4), py + 4) for px, py in bot_pts])
        for k in range(len(top_pts)):
            nk = (k + 1) % len(top_pts)
            quad = [top_pts[k], top_pts[nk], bot_pts[nk], bot_pts[k]]
            pygame.draw.polygon(frame, dark, quad)
            pygame.draw.polygon(frame, BLACK, quad, max(2, int(3 * zoom)))
        # Render octagonal deck + 4 corner hazard pockets onto an alpha surface clipped strictly to top_pts!
        pad = int(radius + 24)
        deck_s = pygame.Surface((2 * pad, 2 * pad), pygame.SRCALPHA)
        ox, oy = cx - pad, cy - pad
        loc_pts = [(px - ox, py - oy) for px, py in top_pts]
        deck_col = mix(theme.terrain, (28, 128, 92) if bstyle == "royal" else theme.rock, 0.35)
        pygame.draw.polygon(deck_s, deck_col, loc_pts)
        inner_pts = [(px - ox, py - oy) for px, py in _octagon_pts(cx, cy, radius * 0.90)]
        pygame.draw.polygon(deck_s, trim_col, inner_pts, max(2, int(4 * zoom)))
        pygame.draw.circle(deck_s, trim_col, (pad, pad), max(6, int(radius * 0.24)), max(2, int(3 * zoom)))
        if bstyle == "obsidian":
            for ang in (0.0, math.pi / 2):
                pygame.draw.line(
                    deck_s,
                    (255, 106, 22),
                    (pad - math.cos(ang) * radius * 0.78, pad - math.sin(ang) * radius * 0.78),
                    (pad + math.cos(ang) * radius * 0.78, pad + math.sin(ang) * radius * 0.78),
                    max(2, int(4 * zoom)),
                )
        # P0.3: Scale pocket radius strictly proportionally with active radius AND mask inside octagon boundary!
        pk = radius * 0.67
        pr = max(2.0, min(pocket_r, radius * 0.30))
        if pr >= 3.0:
            for sx_sgn in (-1, 1):
                for sy_sgn in (-1, 1):
                    px, py = pad + sx_sgn * pk, pad + sy_sgn * pk
                    pygame.draw.circle(deck_s, (255, 92, 36) if bstyle == "obsidian" else theme.hazard,
                                       (int(px), int(py)), int(pr + 4 * zoom))
                    pygame.draw.circle(deck_s, BLACK, (int(px), int(py)), int(pr + 1.5 * zoom))
                    pygame.draw.circle(deck_s, (10, 8, 22), (int(px), int(py)), max(1, int(pr - 1.5 * zoom)))
                    if pr * 0.64 >= 3.0:
                        pygame.draw.circle(deck_s, (28, 22, 48), (int(px), int(py)), int(pr * 0.64), max(1, int(2 * zoom)))
        mask = pygame.Surface((2 * pad, 2 * pad), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), loc_pts)
        deck_s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        frame.blit(deck_s, (ox, oy))
        pygame.draw.polygon(frame, BLACK, top_pts, max(4, int(6 * zoom)))
        return

    rim_h = max(14.0, 0.14 * radius)
    pygame.draw.circle(frame, BLACK, (cx, cy + rim_h), radius + 5)
    pygame.draw.circle(frame, dark, (cx, cy + rim_h), radius)
    pygame.draw.rect(frame, dark, (cx - radius, cy, 2 * radius, rim_h))
    a_rim = math.radians(spin_deg or 0.0)
    seam_col = (255, 96, 18) if bstyle == "obsidian" else ((0, 232, 255) if bstyle == "neon" else mix(dark, BLACK, 0.32))
    for k in range(12):
        ca = math.cos(a_rim + k * math.pi / 6)
        sa = math.sin(a_rim + k * math.pi / 6)
        if sa > 0.05:
            sx = cx + ca * radius
            sy0 = cy + sa * radius * 0.12
            pygame.draw.line(frame, seam_col, (sx, sy0), (sx, sy0 + rim_h * 0.92), max(2, int(3 * zoom)))
    pygame.draw.line(frame, BLACK, (cx - radius - 3, cy), (cx - radius - 3, cy + rim_h), 5)
    pygame.draw.line(frame, BLACK, (cx + radius + 3, cy), (cx + radius + 3, cy + rim_h), 5)

    pygame.draw.circle(frame, BLACK, (cx, cy), radius + 5)
    pygame.draw.circle(frame, theme.terrain, (cx, cy), radius)
    if spin_deg is not None and radius > 8:
        a0 = math.radians(spin_deg)
        wedge_col = mix(theme.terrain, BLACK, 0.24)
        for k in range(0, 12, 2):
            pts = [(cx, cy)] + [(cx + math.cos(a0 + (k + u / 4) * math.pi / 6) * radius,
                                 cy + math.sin(a0 + (k + u / 4) * math.pi / 6) * radius) for u in range(5)]
            pygame.draw.polygon(frame, wedge_col, pts)
        hub_r = max(10.0, radius * 0.15)
        pygame.draw.circle(frame, BLACK, (cx, cy), hub_r + 4)
        pygame.draw.circle(frame, (255, 208, 40), (cx, cy), hub_r)
        pygame.draw.circle(frame, (255, 245, 175), (cx - hub_r * 0.25, cy - hub_r * 0.25), hub_r * 0.32)
    pygame.draw.circle(frame, trim_col, (cx, cy), radius * 0.93, max(2, int(4 * zoom)))


def shadow(frame: pygame.Surface, pos, r: float) -> None:
    s = pygame.Surface((max(4, int(r * 2.4)), max(4, int(r * 0.9))), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 72), s.get_rect())
    frame.blit(s, s.get_rect(center=(pos[0], pos[1] + r * 0.95)))
