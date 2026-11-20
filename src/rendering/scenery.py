"""Polished scenery & broadcast HUD art (§8, §15, v3.2):
- 3-layer parallax background (sky gradient + clouds, slow distant castle spires, mid-ground viaduct arches & pennants).
- Architectural 2D stitched platforms (thick beveled stone castle masonry slabs & riveted bridge beams + vertical stone
  support pillars — ZERO paper triangles).
- Top-right Commentator Booth Cam for MC Tuno with bottom-anchored speech callout tag (y ~ 235, zero overlap with Top-5).
- Proportional 3D rim on Rotating Disc (rim_h = max(14, 0.14 * current_radius)).
"""
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
PANEL = pygame.Rect(28, 108, 762, 114)          # Top-left Top-5 Heroes Bar (y=0..255 broadcast header)
CAM_RECT = pygame.Rect(815, 20, 230, 220)       # Top-right: MC Tuno Commentator Booth Cam


def mix(a, b, k: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))  # type: ignore[return-value]


@lru_cache(maxsize=16)
def font(size: int, face: str = "LuckiestGuy-Regular.ttf") -> pygame.font.Font:
    return pygame.font.Font(font_path(face), size)


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


def parallax_layers(theme) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    """v3.2: 3 distinct seamless horizontal depth layers:
    1) sky_bg (gradient + soft clouds), 2) far_spires (distant castle silhouettes), 3) mid_arches (viaduct arches & pennants).
    """
    # Layer 1: Sky gradient + high soft clouds
    sky_bg = pygame.Surface((W, H))
    top = mix(theme.sky_top, WHITE, 0.20)
    bot = mix(theme.sky_bottom, WHITE, 0.30)
    for y in range(H):
        pygame.draw.line(sky_bg, mix(top, bot, y / H), (0, y), (W, y))
    cloud, shade = mix(WHITE, theme.sky_bottom, 0.08), mix(WHITE, theme.sky_top, 0.28)
    rng = random.Random(11)
    for i in range(6):
        x, y = i * 190 + rng.randint(-25, 25), rng.randint(360, 920)
        cw = rng.randint(170, 250)
        for ox in (0, -W, W):
            _cloud(sky_bg, x + ox, y, cw, cloud, shade)

    # Layer 2: Distant castle spires & curtain wall (seamless wrap across W)
    spires = pygame.Surface((W, H), pygame.SRCALPHA)
    far = mix(theme.castle, bot, 0.54)
    far_d = mix(far, theme.sky_top, 0.22)
    win_col = mix(far_d, BLACK, 0.25)
    rng2 = random.Random(23)
    # Continuous distant curtain wall base
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
            pygame.draw.polygon(spires, far_d, roof)
            pygame.draw.rect(spires, win_col, (bx + tw / 2 - 8, top_y + 52, 16, 34), border_radius=8)

    # Layer 3: Mid-ground castle viaduct arches + colourful pennant flags (seamless wrap across W)
    mid = pygame.Surface((W, H), pygame.SRCALPHA)
    mid_stone = mix(theme.castle, bot, 0.34)
    mid_dark = mix(mid_stone, BLACK, 0.18)
    mid_hi = mix(mid_stone, WHITE, 0.18)
    span = W // 4  # 270 px exact integer divisor of 1080 -> 100% seamless wrap
    parapet_y = 1190
    # Viaduct parapet band + piers + arches
    pygame.draw.rect(mid, mid_stone, (0, parapet_y, W, 56))
    pygame.draw.line(mid, mid_hi, (0, parapet_y + 3), (W, parapet_y + 3), 4)
    pygame.draw.line(mid, mid_dark, (0, parapet_y + 52), (W, parapet_y + 52), 5)
    for x in range(0, W, 54):
        pygame.draw.rect(mid, mid_stone, (x + 6, parapet_y - 22, 34, 24), border_radius=4)
    pennant_cols = [(235, 58, 82), (255, 208, 40), (0, 205, 245), (155, 89, 210)]
    for i in range(4):
        px = i * span
        for ox in (0, -W, W):
            bx = px + ox
            # Heavy mid-ground pier descending into the abyss
            pygame.draw.rect(mid, mid_stone, (bx - 30, parapet_y + 52, 60, H - parapet_y))
            pygame.draw.rect(mid, mid_dark, (bx + 10, parapet_y + 52, 20, H - parapet_y))
            # Arch spandrel bridging to next pier
            arch_pts = [(bx + 28, parapet_y + 52), (bx + span - 28, parapet_y + 52)]
            for u in range(13):
                ang = math.pi * (1.0 - u / 12)
                arch_pts.append((bx + span / 2 + math.cos(ang) * (span / 2 - 28),
                                 parapet_y + 150 - math.sin(ang) * 92))
            pygame.draw.polygon(mid, mid_dark, arch_pts)
            # Hanging castle pennant flags along the arch line + tall lance pennant on pier
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


# ---------------------------------------------------------------------------------------------- broadcast header (v3.2)
def castle_header(theme) -> pygame.Surface:
    """v3.2: Vibrant Commentator Booth Cam ring for MC Tuno in the top-right (260x260)."""
    s = pygame.Surface((260, 260), pygame.SRCALPHA)
    cx, cy, r = 130, 126, 106
    pygame.draw.circle(s, (0, 0, 0, 105), (cx + 4, cy + 7), r + 9)
    pygame.draw.circle(s, BLACK, (cx, cy), r + 8)
    pygame.draw.circle(s, (44, 48, 76), (cx, cy), r + 3)
    pygame.draw.circle(s, BLACK, (cx, cy), r - 7)
    # Studio booth backdrop with diagonal neon spotlight beams
    inner_r = r - 13
    booth = pygame.Surface((260, 260), pygame.SRCALPHA)
    pygame.draw.circle(booth, (34, 24, 68), (cx, cy), inner_r)
    pygame.draw.polygon(booth, (66, 42, 118), [(cx - 90, cy - 90), (cx - 20, cy - 95), (cx + 75, cy + 95), (cx + 5, cy + 95)])
    pygame.draw.circle(booth, (0, 229, 255, 55), (cx, cy + 16), inner_r * 0.76, 6)
    mask = pygame.Surface((260, 260), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), inner_r)
    booth.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(booth, (0, 0))
    pygame.draw.circle(s, (255, 208, 40), (cx, cy), r - 10, 5)
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


@lru_cache(maxsize=16)
def episode_ribbon(text: str) -> pygame.Surface:
    """Stylized cartoon episode ribbon with thick black outline."""
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
    """Top-left episode ribbon + Top-right MC Tuno Commentator Booth Cam with bottom-anchored speech tag (y ~ 235)."""
    rib = episode_ribbon(ep_label.replace(" - ", " • "))
    r = rib.get_rect(topleft=(28, 30))
    frame.blit(rib, r)
    text_boxes.append(r)

    # Top-right Commentator Booth Cam (220x220 inner clip)
    cx, cy = CAM_RECT.centerx, CAM_RECT.centery - 6
    frame.blit(portrait_bg, portrait_bg.get_rect(center=(cx, cy)))
    buf = pygame.Surface((220, 220), pygame.SRCALPHA)
    draw_tuno(buf, 110, 214, tuno_state, t, scale=1.62)
    mask = pygame.Surface((220, 220), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (110, 110), 92)
    buf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    frame.blit(buf, buf.get_rect(center=(cx, cy)))

    # Crisp bezel highlight + ON-AIR red pulse dot on top-right of bezel
    rim_col = (255, 65, 85) if tuno_state == "SWEATING_INTENSE" else (255, 208, 40)
    pygame.draw.circle(frame, BLACK, (cx, cy), 99, 4)
    pygame.draw.circle(frame, rim_col, (cx, cy), 95, 4)
    if int(t * 3) % 2 == 0 or tuno_state != "HYPED_TALKING":
        pygame.draw.circle(frame, BLACK, (cx + 76, cy - 68), 9)
        pygame.draw.circle(frame, (255, 50, 70), (cx + 76, cy - 68), 6)

    if speech:
        # v3.2 FIX: Anchor speech tag cleanly along the BOTTOM edge of the portrait circle (y ~ 235),
        # NEVER on the left edge where it collided with the dark Top-5 leaderboard bar!
        sp = _fit(_outlined_text(speech, 30, fill=WHITE, outline=BLACK, w=4), 196)
        bw, bh = sp.get_width() + 26, sp.get_height() + 10
        tag = pygame.Surface((bw, bh + 12), pygame.SRCALPHA)
        # Upward comic speech pointer pointing cleanly at MC Tuno's chin
        ptr = [(bw / 2 - 11, 13), (bw / 2, 1), (bw / 2 + 11, 13)]
        pygame.draw.polygon(tag, BLACK, [(px, py) for px, py in ptr])
        body_r = pygame.Rect(0, 10, bw, bh)
        pygame.draw.rect(tag, BLACK, body_r, border_radius=14)
        fill_col = (238, 52, 78) if speech in ("NO WAY!", "OOF!", "RIP!", "WIPEOUT!") else (0, 175, 235)
        pygame.draw.rect(tag, fill_col, body_r.inflate(-6, -6), border_radius=11)
        pygame.draw.polygon(tag, fill_col, [(bw / 2 - 7, 14), (bw / 2, 5), (bw / 2 + 7, 14)])
        tag.blit(sp, sp.get_rect(center=(bw / 2, 10 + bh / 2 + 1)))
        tr = tag.get_rect(center=(cx, 235))
        if tr.right > W - 14:
            tr.right = W - 14
        if tr.left < PANEL.right + 14:
            tr.left = PANEL.right + 14
        frame.blit(tag, tr)
        text_boxes.append(tr)


def _crown(frame, cx: float, cy: float, w: float) -> None:
    pts = [(cx - w / 2, cy + w * 0.35), (cx - w / 2, cy - w * 0.1), (cx - w / 4, cy + w * 0.12), (cx, cy - w * 0.25),
           (cx + w / 4, cy + w * 0.12), (cx + w / 2, cy - w * 0.1), (cx + w / 2, cy + w * 0.35)]
    pygame.draw.polygon(frame, (255, 205, 40), pts)
    pygame.draw.polygon(frame, BLACK, pts, 2)


def _icon(frame, h: Hero, c, rad: float, expr: str = "neutral") -> None:
    from src.rendering import balls
    balls.draw_ball(frame, h, None, c, 0.0, 0.0, (0, 0), 0.0, expr, "none", 0.0, rad / max(1.0, h.radius))


def draw_panel(frame: pygame.Surface, survivors: int, total: int, heroes: list[Hero], status: dict[str, str],
               ranks: dict[str, int], text_boxes: list, pulse: float = 0.0) -> None:
    """Top-left ALIVE pill beside the episode ribbon + Top 5 Heroes Bar (#1-#5 over alive heroes only)."""
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

    plate = pygame.Surface(PANEL.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 22, 36, 218), plate.get_rect(), border_radius=24)
    pygame.draw.rect(plate, (255, 255, 255, 80), plate.get_rect(), 3, border_radius=24)
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


# ---------------------------------------------------------------------------------------------- architectural 2D terrain (v3.2)
def rock_colours(theme) -> tuple:
    cap = theme.terrain
    rock = mix(mix(theme.castle, (148, 146, 162), 0.38), theme.terrain_outline, 0.20)
    return cap, rock, mix(rock, BLACK, 0.28), mix(rock, WHITE, 0.22)


def draw_support_pillar(frame: pygame.Surface, sx: float, sy_top: float, sy_bot: float, zoom: float, theme,
                        chain: bool = False) -> None:
    """v3.2: Vertical stone masonry support pillar (extending cleanly down into the pit) or heavy iron hanger chain."""
    if sy_bot <= sy_top + 12 or sx < -80 or sx > W + 80:
        return
    lw = max(2, int(4 * zoom))
    if chain:
        # Heavy dark-iron castle chain ascending from upper shelf
        link_h = max(12, int(22 * zoom))
        link_w = max(8, int(14 * zoom))
        y = sy_top
        idx = 0
        while y > sy_bot:
            if idx % 2 == 0:
                r = pygame.Rect(int(sx - link_w / 2), int(y - link_h), link_w, link_h)
                pygame.draw.ellipse(frame, BLACK, r.inflate(4, 4), max(2, lw))
                pygame.draw.ellipse(frame, (125, 132, 148), r, max(2, lw - 1))
            else:
                pygame.draw.line(frame, BLACK, (sx, y), (sx, y - link_h), lw + 3)
                pygame.draw.line(frame, (165, 172, 188), (sx, y - 2), (sx, y - link_h + 2), max(2, lw - 1))
            y -= int(link_h * 0.75)
            idx += 1
        return

    _, rock, dark, light = rock_colours(theme)
    col_base = mix(rock, BLACK, 0.14)
    col_sh = mix(dark, BLACK, 0.18)
    pw = max(18, int(46 * zoom))
    # Main vertical stone shaft
    shaft = pygame.Rect(int(sx - pw / 2), int(sy_top), pw, int(sy_bot - sy_top))
    pygame.draw.rect(frame, col_base, shaft)
    pygame.draw.rect(frame, col_sh, (shaft.right - int(pw * 0.34), shaft.top, int(pw * 0.34), shaft.height))
    pygame.draw.line(frame, mix(light, WHITE, 0.1), (shaft.left + 4, shaft.top), (shaft.left + 4, shaft.bottom), max(2, lw - 1))
    # Subtle ashlar stone course lines
    step_y = max(22, int(52 * zoom))
    for yy in range(int(sy_top) + step_y, int(sy_bot), step_y):
        pygame.draw.line(frame, col_sh, (shaft.left + 2, yy), (shaft.right - 2, yy), max(2, lw - 1))
    pygame.draw.line(frame, BLACK, shaft.topleft, shaft.bottomleft, lw)
    pygame.draw.line(frame, BLACK, shaft.topright, shaft.bottomright, lw)
    # Flared stone corbel capital directly under the slab
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
                     zoom: float, theme, t_anim: float = 0.0) -> None:
    """v3.2 Architectural 2D Platform Renderer (NO jagged inverted triangles!).
    Stitches consecutive slope segments seamlessly with shared vertices, beveled stone castle masonry blocks
    (or riveted timber/steel bridge beams), highlight top lip, shaded underside, and rounded corner joints.
    """
    if len(pts) < 2:
        return
    _, rock, dark, light = rock_colours(theme)
    lw = max(3, int(4.5 * zoom))
    is_beam = all(m in ("plank", "conveyor") for m in mats) or theme.key == "clockwork"
    slab_d = max(22.0, (58.0 if is_beam else 66.0) * zoom)
    chamfer = min(12.0 * zoom, slab_d * 0.25)

    # Build seamless shared-vertex beveled slab polygon
    n_pts = len(pts)
    bot_pts: list[tuple[float, float]] = []
    for i, (px, py) in enumerate(pts):
        if i == 0 and n_pts >= 2 and pts[-1][0] - pts[0][0] > 40 * zoom:
            bot_pts.append((px + chamfer, py + slab_d))
        elif i == n_pts - 1 and n_pts >= 2 and pts[-1][0] - pts[0][0] > 40 * zoom:
            bot_pts.append((px - chamfer, py + slab_d))
        else:
            bot_pts.append((px, py + slab_d))

    poly = list(pts) + bot_pts[::-1]
    if is_beam:
        # Riveted Timber / Steel Bridge Girder
        core_col = (84, 90, 108) if "conveyor" in mats else (158, 106, 58)
        flange_col = (52, 56, 72)
        pygame.draw.polygon(frame, core_col, poly)
        # Shaded lower steel flange band
        flange_top = [(px, py + slab_d * 0.68) for px, py in pts]
        pygame.draw.polygon(frame, flange_col, flange_top + bot_pts[::-1])
        # Diagonal truss ribs + silver rivets per segment
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
    else:
        # Stone Castle Masonry Block Slab
        pygame.draw.polygon(frame, rock, poly)
        # Shaded underside bevel band (bottom 32%)
        shade_top = [(px, py + slab_d * 0.68) for px, py in pts]
        pygame.draw.polygon(frame, dark, shade_top + bot_pts[::-1])
        # Mid-depth mortar course line + subtle highlight bevel
        mid_line = [(px, py + slab_d * 0.50) for px, py in pts]
        hi_line = [(px, py + slab_d * 0.54) for px, py in pts]
        pygame.draw.lines(frame, dark, False, mid_line, max(2, int(3 * zoom)))
        pygame.draw.lines(frame, light, False, hi_line, max(1, int(2 * zoom)))
        # Staggered vertical stone masonry joints (upper course & lower course)
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
                pygame.draw.line(frame, dark, (jx, jy + slab_d * 0.18), (jx, jy + slab_d * 0.50), max(2, int(2.8 * zoom)))
            for k in range(nb):
                u = (k + 0.5) / nb
                jx, jy = ax + dx * u, ay + dy * u
                pygame.draw.line(frame, mix(dark, BLACK, 0.2), (jx, jy + slab_d * 0.50), (jx, jy + slab_d * 0.94), max(2, int(2.8 * zoom)))
        # Rounded interior underside corner joints + crisp outer outline
        for i in range(1, n_pts - 1):
            pygame.draw.circle(frame, dark, bot_pts[i], max(3, int(5 * zoom)))
            pygame.draw.circle(frame, BLACK, bot_pts[i], max(3, int(5 * zoom)), max(2, lw - 1))
        pygame.draw.polygon(frame, BLACK, poly, lw)

    # Seamless Top Bevel Lip & Surface Cap across all segments in the chain
    cap_w = max(8, int(20 * zoom))
    # Pass 1: Continuous black outer cap casing with rounded corner joints
    for seg_i in range(n_pts - 1):
        a, b = pts[seg_i], pts[seg_i + 1]
        pygame.draw.line(frame, BLACK, a, b, cap_w + 8)
    for p in pts:
        pygame.draw.circle(frame, BLACK, p, (cap_w + 8) / 2)
    # Pass 2: Material fill + specular top lip + bouncy/conveyor surface details
    for seg_i, mat in enumerate(mats):
        a, b = pts[seg_i], pts[seg_i + 1]
        cap_col = {
            "ice": (195, 240, 255),
            "mud": (118, 80, 46),
            "bouncy": (255, 88, 176),
            "conveyor": (62, 66, 82),
            "plank": (192, 136, 78),
        }.get(mat, theme.terrain)
        pygame.draw.line(frame, cap_col, a, b, cap_w)
        pygame.draw.circle(frame, cap_col, a, cap_w / 2)
        pygame.draw.circle(frame, cap_col, b, cap_w / 2)
        hi = mix(cap_col, WHITE, 0.48)
        pygame.draw.line(frame, hi, (a[0] + 2, a[1] - cap_w * 0.24), (b[0] - 2, b[1] - cap_w * 0.24), max(2, cap_w // 4))
        if mat == "bouncy":
            # Crisp yellow/white spring stripes embedded in bouncy pad
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
    """Single-segment fallback wrapper."""
    draw_track_chain(frame, [a, b], [mat], [0.0], zoom, theme)


def draw_floating_platform(frame: pygame.Surface, centre, radius: float, zoom: float, theme, shape: str = "disc",
                           half: float = 0.0, spin_deg: float | None = None) -> None:
    """v3.2 TOP_DOWN arena floor: proportional 3D underside rim (rim_h = max(14, 0.14 * current_radius)) so shrinking
    discs always maintain crisp flat-disc proportions instead of turning into a tall floating coffee mug."""
    _, rock, dark, _ = rock_colours(theme)
    cx, cy = centre
    if shape == "square":
        rim_h = max(14.0, 0.14 * half)
        r = pygame.Rect(cx - half, cy - half, 2 * half, 2 * half)
        pygame.draw.rect(frame, BLACK, r.move(0, rim_h).inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, dark, r.move(0, rim_h), border_radius=20)
        pygame.draw.rect(frame, BLACK, r.inflate(10, 10), border_radius=22)
        pygame.draw.rect(frame, theme.terrain, r, border_radius=20)
        pygame.draw.rect(frame, mix(theme.terrain, WHITE, 0.35), r.inflate(-24, -24), 4, border_radius=16)
        return

    rim_h = max(14.0, 0.14 * radius)
    # 3D stone underside cylinder scaled proportionally with radius
    pygame.draw.circle(frame, BLACK, (cx, cy + rim_h), radius + 5)
    pygame.draw.circle(frame, dark, (cx, cy + rim_h), radius)
    pygame.draw.rect(frame, dark, (cx - radius, cy, 2 * radius, rim_h))
    # Subtle vertical stone block seams on the 3D rim that rotate with the disc
    a_rim = math.radians(spin_deg or 0.0)
    seam_col = mix(dark, BLACK, 0.32)
    for k in range(12):
        ca = math.cos(a_rim + k * math.pi / 6)
        sa = math.sin(a_rim + k * math.pi / 6)
        if sa > 0.05:  # front-facing half of cylinder
            sx = cx + ca * radius
            sy0 = cy + sa * radius * 0.12
            pygame.draw.line(frame, seam_col, (sx, sy0), (sx, sy0 + rim_h * 0.92), max(2, int(3 * zoom)))
    pygame.draw.line(frame, BLACK, (cx - radius - 3, cy), (cx - radius - 3, cy + rim_h), 5)
    pygame.draw.line(frame, BLACK, (cx + radius + 3, cy), (cx + radius + 3, cy + rim_h), 5)

    # Top disc surface + high-contrast radial pie stripes + metallic centre hub
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
    pygame.draw.circle(frame, mix(theme.terrain, WHITE, 0.34), (cx, cy), radius * 0.93, max(2, int(4 * zoom)))


def shadow(frame: pygame.Surface, pos, r: float) -> None:
    s = pygame.Surface((max(4, int(r * 2.4)), max(4, int(r * 0.9))), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 72), s.get_rect())
    frame.blit(s, s.get_rect(center=(pos[0], pos[1] + r * 0.95)))
