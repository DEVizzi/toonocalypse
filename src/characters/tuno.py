"""MC Tuno (v3.4): Full Upper-Body Cartoon Commentator Host in the top-right 240x220 Broadcast Booth Window.
- Zoomed out ~20% so his entire crooked mini crown, oversized studio headphones, royal-purple broadcaster shoulders,
  animated reacting hands, studio desk, boom-mic, and 5-bar mic EQ meter are 100% visible with zero clipping.
- Frame-accurate 3-state RMS lip-sync driven by the isolated voice stem (including throughout the Winner Card outro!):
  * rms < 0.02:        Closed mouth matching active emotion (smile / grin / gasp / grimace).
  * 0.02 <= rms < 0.08: Half-open talking mouth.
  * rms >= 0.08:        Wide-open hyped mouth + subtle 3px head bounce + pulsing 5-bar mic EQ meter.
"""
from __future__ import annotations

import math

import pygame

from src.characters.expressions import BLACK, WHITE

JACKET = (118, 32, 188)
JACKET_HI = (168, 72, 238)
CYAN = (0, 229, 255)
SKIN = (255, 214, 172)
SKIN_SHADE = (232, 178, 134)
GOLD = (255, 208, 36)
CRIMSON = (235, 48, 76)

STATES = (
    "HYPED_TALKING",
    "SHOCKED_JAWDROP",
    "LAUGHING_TEARS",
    "FACEPALM",
    "SWEATING_INTENSE",
    "TROPHY_CHEER",
)

_ALIASES = {
    "idle": "HYPED_TALKING",
    "lever": "HYPED_TALKING",
    "shocked": "SHOCKED_JAWDROP",
    "laughing": "LAUGHING_TEARS",
    "evil": "SWEATING_INTENSE",
    "crowning": "TROPHY_CHEER",
}


def _crown(s: pygame.Surface, cx: float, cy: float, w: float, tilt_deg: float = -12.0) -> None:
    """Crooked mini gold crown perched jauntily atop MC Tuno's headphone band."""
    cw, ch = max(16, int(w * 1.7)), max(14, int(w * 1.3))
    cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
    ox, oy = cw / 2, ch * 0.76
    pts = [
        (ox - w * 0.48, oy),
        (ox - w * 0.54, oy - w * 0.46),
        (ox - w * 0.22, oy - w * 0.18),
        (ox, oy - w * 0.62),
        (ox + w * 0.22, oy - w * 0.18),
        (ox + w * 0.54, oy - w * 0.46),
        (ox + w * 0.48, oy),
    ]
    pygame.draw.polygon(cs, GOLD, pts)
    pygame.draw.polygon(cs, BLACK, pts, 3)
    pygame.draw.line(cs, (255, 244, 160), (ox - w * 0.36, oy - w * 0.08), (ox + w * 0.36, oy - w * 0.08), 2)
    for gx, col in ((ox - w * 0.23, CRIMSON), (ox, (40, 160, 255)), (ox + w * 0.23, (46, 214, 115))):
        gr = max(2, int(w * 0.085))
        pygame.draw.circle(cs, col, (gx, oy - w * 0.16), gr)
        pygame.draw.circle(cs, BLACK, (gx, oy - w * 0.16), gr, 1)
    rot = pygame.transform.rotozoom(cs, tilt_deg, 1.0)
    s.blit(rot, rot.get_rect(center=(cx, cy)))


def _sweat_drop(s: pygame.Surface, x: float, y: float, r: float) -> None:
    pts = [(x, y - r * 1.35), (x + r * 0.85, y + r * 0.2), (x, y + r * 0.95), (x - r * 0.85, y + r * 0.2)]
    pygame.draw.polygon(s, BLACK, pts)
    pygame.draw.circle(s, BLACK, (x, y + r * 0.28), r * 0.88)
    pygame.draw.polygon(s, (110, 225, 255), [(x, y - r * 1.05), (x + r * 0.62, y + r * 0.2), (x - r * 0.62, y + r * 0.2)])
    pygame.draw.circle(s, (110, 225, 255), (x, y + r * 0.28), r * 0.65)
    pygame.draw.circle(s, WHITE, (x - r * 0.20, y + r * 0.15), max(1, int(r * 0.22)))


def _star(s: pygame.Surface, cx: float, cy: float, rr: float, col=GOLD) -> None:
    pts = [
        (cx + math.cos(-math.pi / 2 + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.44),
         cy + math.sin(-math.pi / 2 + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.44))
        for i in range(10)
    ]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, BLACK, pts, 2)


def _glove_hand(s: pygame.Surface, cx: float, cy: float, r: float, lw: int, open_palm: bool = False, side: int = 1) -> None:
    """Expressive white cartoon broadcaster glove hand with cuff."""
    cuff = pygame.Rect(int(cx - r * 0.62), int(cy + r * 0.35), int(r * 1.24), max(5, int(r * 0.48)))
    pygame.draw.rect(s, BLACK, cuff.inflate(lw * 2, lw * 2), border_radius=5)
    pygame.draw.rect(s, JACKET, cuff, border_radius=4)
    pygame.draw.circle(s, BLACK, (cx, cy), r + lw)
    pygame.draw.circle(s, WHITE, (cx, cy), r)
    if open_palm:
        for k, ang in enumerate((-1.15, -0.65, -0.15)):
            fx = cx + math.sin(ang * side) * r * 0.95
            fy = cy - math.cos(ang) * r * 1.02
            pygame.draw.circle(s, BLACK, (fx, fy), r * 0.36 + lw - 1)
            pygame.draw.circle(s, WHITE, (fx, fy), r * 0.36)
    else:
        for dx in (-0.32, 0.0, 0.32):
            pygame.draw.line(s, BLACK, (cx + dx * r, cy - r * 0.48), (cx + dx * r, cy + r * 0.12), max(2, lw - 1))


def _trophy(s: pygame.Surface, cx: float, cy: float, r: float) -> None:
    """Compact golden champion cup held cleanly inside the right side of the booth window."""
    lw = max(2, int(r * 0.12))
    pygame.draw.circle(s, BLACK, (cx - r * 0.50, cy - r * 0.12), r * 0.25, lw + 2)
    pygame.draw.circle(s, GOLD, (cx - r * 0.50, cy - r * 0.12), r * 0.23, max(1, lw - 1))
    pygame.draw.circle(s, BLACK, (cx + r * 0.50, cy - r * 0.12), r * 0.25, lw + 2)
    pygame.draw.circle(s, GOLD, (cx + r * 0.50, cy - r * 0.12), r * 0.23, max(1, lw - 1))
    cup = [(cx - r * 0.52, cy - r * 0.48), (cx + r * 0.52, cy - r * 0.48),
           (cx + r * 0.35, cy + r * 0.22), (cx - r * 0.35, cy + r * 0.22)]
    pygame.draw.polygon(s, GOLD, cup)
    pygame.draw.polygon(s, BLACK, cup, lw)
    pygame.draw.line(s, (255, 248, 190), (cx - r * 0.32, cy - r * 0.36), (cx - r * 0.20, cy + r * 0.10), lw)
    pygame.draw.rect(s, GOLD, (cx - r * 0.12, cy + r * 0.20, r * 0.24, r * 0.26))
    pygame.draw.rect(s, BLACK, (cx - r * 0.12, cy + r * 0.20, r * 0.24, r * 0.26), max(1, lw - 1))
    base = pygame.Rect(int(cx - r * 0.38), int(cy + r * 0.44), int(r * 0.76), int(r * 0.22))
    pygame.draw.rect(s, (120, 75, 35), base, border_radius=3)
    pygame.draw.rect(s, BLACK, base, max(1, lw - 1), border_radius=3)


def _draw_eq_meter(s: pygame.Surface, x0: float, y_bot: float, rms: float, t: float, scale: float) -> None:
    """5-bar studio mic EQ meter beside MC Tuno's microphone; pulses vibrantly when rms >= 0.08."""
    bw = max(4, int(5 * scale))
    gap = max(2, int(3 * scale))
    max_h = 30.0 * scale
    total_w = 5 * bw + 4 * gap + int(10 * scale)
    box = pygame.Rect(int(x0), int(y_bot - max_h - 8 * scale), total_w, int(max_h + 12 * scale))
    plate = pygame.Surface(box.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (12, 16, 30, 200 if rms >= 0.08 else 135), plate.get_rect(), border_radius=6)
    border_col = (250, 204, 21, 235) if rms >= 0.08 else (90, 110, 150, 120)
    pygame.draw.rect(plate, border_col, plate.get_rect(), 2, border_radius=6)
    s.blit(plate, box.topleft)

    norm = min(1.0, rms / 0.20)
    freqs = (19.0, 27.0, 33.0, 23.0, 31.0)
    phases = (0.0, 1.1, 2.3, 0.7, 1.9)
    for i in range(5):
        if rms >= 0.08:
            lvl = min(1.0, 0.42 + 0.58 * norm * (0.62 + 0.38 * abs(math.sin(t * freqs[i] + phases[i]))))
        elif rms >= 0.02:
            lvl = 0.16 + 0.24 * (rms / 0.08) * (0.6 + 0.4 * abs(math.sin(t * freqs[i] + phases[i])))
        else:
            lvl = 0.09
        bh = max(3, int(max_h * lvl))
        bx = box.left + int(5 * scale) + i * (bw + gap)
        by = int(y_bot - 2 * scale) - bh
        col = (34, 215, 110) if lvl < 0.45 else ((250, 204, 21) if lvl < 0.76 else (255, 72, 88))
        if rms < 0.02:
            col = (58, 76, 98)
        pygame.draw.rect(s, col, (bx, by, bw, bh), border_radius=2)


def _draw_mouth_rms(s: pygame.Surface, bx: float, my: float, r: float, lw: int, st: str, rms: float) -> None:
    """3-state frame-accurate RMS mouth across ALL commentator emotions (including TROPHY_CHEER on Winner Card)."""
    if rms >= 0.08:
        # State 3: Wide-open hyped broadcaster shout mouth (teeth + tongue)
        w_top = r * (0.38 if st in ("LAUGHING_TEARS", "TROPHY_CHEER") else 0.34)
        w_bot = r * 0.24
        h_open = r * min(0.42, 0.30 + (rms - 0.08) * 0.55)
        pts = [(bx - w_top, my - r * 0.06), (bx + w_top, my - r * 0.06),
               (bx + w_bot, my + h_open), (bx - w_bot, my + h_open)]
        pygame.draw.polygon(s, (98, 16, 34), pts)
        teeth_h = max(3, int(r * 0.10))
        pygame.draw.rect(s, WHITE, (int(bx - w_top * 0.84), int(my - r * 0.05), int(w_top * 1.68), teeth_h))
        pygame.draw.ellipse(s, (244, 92, 112), (bx - w_bot * 0.78, my + h_open * 0.44, w_bot * 1.56, h_open * 0.54))
        pygame.draw.polygon(s, BLACK, pts, lw)
        return

    if rms >= 0.02:
        # State 2: Half-open talking mouth
        mw, mh = r * 0.46, r * 0.24
        om = pygame.Rect(int(bx - mw / 2), int(my - r * 0.04), int(mw), int(mh))
        pygame.draw.rect(s, BLACK, om.inflate(lw * 2, lw * 2), border_radius=max(4, int(r * 0.10)))
        pygame.draw.rect(s, (102, 18, 36), om, border_radius=max(3, int(r * 0.09)))
        pygame.draw.rect(s, WHITE, (om.left + 3, om.top + 2, om.width - 6, max(2, int(mh * 0.34))), border_radius=2)
        pygame.draw.ellipse(s, (242, 90, 110), (bx - mw * 0.28, om.bottom - mh * 0.46, mw * 0.56, mh * 0.42))
        return

    # State 1 (rms < 0.02): Closed mouth matching active emotion (smile / smirk / shock / grin)
    if st == "SHOCKED_JAWDROP":
        # Tight closed/pursed shocked gasp ring
        gasp = pygame.Rect(int(bx - r * 0.10), int(my + r * 0.02), int(r * 0.20), int(r * 0.14))
        pygame.draw.ellipse(s, BLACK, gasp.inflate(lw * 2, lw * 2))
        pygame.draw.ellipse(s, SKIN_SHADE, gasp)
        pygame.draw.line(s, BLACK, (bx - r * 0.07, gasp.centery), (bx + r * 0.07, gasp.centery), max(2, lw - 1))
    elif st == "SWEATING_INTENSE":
        # Closed clenched grin
        grin = pygame.Rect(int(bx - r * 0.28), int(my - r * 0.02), int(r * 0.56), int(r * 0.17))
        pygame.draw.rect(s, BLACK, grin.inflate(lw * 2, lw * 2), border_radius=max(3, int(r * 0.07)))
        pygame.draw.rect(s, WHITE, grin, border_radius=max(2, int(r * 0.06)))
        pygame.draw.line(s, BLACK, (grin.left + 2, grin.centery), (grin.right - 2, grin.centery), max(2, lw - 1))
    elif st == "FACEPALM":
        # Exasperated closed wavy grimace
        pygame.draw.lines(s, BLACK, False, [(bx - r * 0.22, my + r * 0.08), (bx - r * 0.04, my + r * 0.01),
                                            (bx + r * 0.18, my + r * 0.09)], lw)
    elif st in ("LAUGHING_TEARS", "TROPHY_CHEER"):
        # Big closed celebratory smile arc with cheek dimples
        arc_r = pygame.Rect(int(bx - r * 0.30), int(my - r * 0.10), int(r * 0.60), int(r * 0.28))
        pygame.draw.arc(s, BLACK, arc_r, math.pi + 0.22, 2 * math.pi - 0.22, lw + 1)
        for sgn in (-1, 1):
            pygame.draw.arc(s, BLACK, (bx + sgn * r * 0.30 - r * 0.06, my - r * 0.02, r * 0.12, r * 0.12),
                            0.4 if sgn > 0 else math.pi + 0.4, 1.9 if sgn > 0 else math.pi + 1.9, max(2, lw - 1))
    else:
        # Confident broadcaster closed smirk/smile
        arc_r = pygame.Rect(int(bx - r * 0.26), int(my - r * 0.08), int(r * 0.52), int(r * 0.24))
        pygame.draw.arc(s, BLACK, arc_r, math.pi + 0.25, 2 * math.pi - 0.18, lw + 1)


def draw_tuno(s: pygame.Surface, cx: float, base_y: float, state: str, t: float, scale: float = 1.0,
              talking: bool | None = None, voice_rms: float | None = None) -> None:
    """Draws full upper-body MC Tuno + studio desk + boom-mic + reacting hands + 5-bar mic EQ inside 240x220 booth."""
    st = _ALIASES.get(state, state)
    # Resolve effective RMS (supports explicit voice_rms float as well as legacy silent/talking bool fallback)
    if voice_rms is not None:
        rms = float(voice_rms)
    elif talking:
        rms = 0.11 if int(t * 10) % 3 != 2 else 0.045
    else:
        rms = 0.0

    r = 44.0 * scale
    lw = max(2, int(3.2 * scale))
    desk_y = base_y - 24.0 * scale

    idle_bob = math.sin(t * 3.4) * 1.4 * scale
    hyped_bounce = -3.0 * scale * (0.65 + 0.35 * abs(math.sin(t * 20.0))) if rms >= 0.08 else (
        -1.2 * scale if rms >= 0.02 else 0.0
    )
    shake = math.sin(t * 42) * 2.2 * scale if st == "LAUGHING_TEARS" else (
        math.sin(t * 52) * 1.3 * scale if st == "SWEATING_INTENSE" else 0.0
    )
    bx = cx + shake
    torso_y = desk_y - r * 0.42 + idle_bob * 0.5
    head_y = desk_y - r * 1.56 + idle_bob + hyped_bounce

    # 1. Broadcaster Upper Torso, Shoulders & Gold Lapels (fully visible above desk_y)
    sh_rect = pygame.Rect(int(bx - r * 1.24), int(torso_y - r * 0.38), int(r * 2.48), int(r * 1.42))
    pygame.draw.rect(s, BLACK, sh_rect.inflate(lw * 2 + 2, lw * 2 + 2), border_top_left_radius=int(r * 0.72),
                     border_top_right_radius=int(r * 0.72), border_radius=int(r * 0.25))
    pygame.draw.rect(s, JACKET, sh_rect, border_top_left_radius=int(r * 0.68),
                     border_top_right_radius=int(r * 0.68), border_radius=int(r * 0.22))
    pygame.draw.line(s, JACKET_HI, (sh_rect.left + r * 0.22, sh_rect.top + r * 0.14),
                     (sh_rect.left + r * 0.65, sh_rect.top + r * 0.08), max(2, int(4 * scale)))
    shirt = [(bx - r * 0.36, torso_y - r * 0.34), (bx + r * 0.36, torso_y - r * 0.34), (bx, torso_y + r * 0.38)]
    pygame.draw.polygon(s, WHITE, shirt)
    pygame.draw.polygon(s, BLACK, shirt, max(2, lw - 1))
    # Red comic tie + gold lapels
    tie = [(bx - r * 0.09, torso_y - r * 0.22), (bx + r * 0.09, torso_y - r * 0.22),
           (bx + r * 0.13, torso_y + r * 0.26), (bx, torso_y + r * 0.40), (bx - r * 0.13, torso_y + r * 0.26)]
    pygame.draw.polygon(s, CRIMSON, tie)
    pygame.draw.polygon(s, BLACK, tie, max(1, lw - 1))
    for side in (-1, 1):
        lapel = [
            (bx + side * r * 0.24, torso_y - r * 0.34),
            (bx + side * r * 0.60, torso_y - r * 0.24),
            (bx + side * r * 0.44, torso_y + r * 0.28),
            (bx + side * r * 0.06, torso_y + r * 0.36),
        ]
        pygame.draw.polygon(s, GOLD, lapel)
        pygame.draw.polygon(s, BLACK, lapel, max(2, lw - 1))

    # 2. Headphone Arched Band (behind head top)
    hb_rect = pygame.Rect(int(bx - r * 0.90), int(head_y - r * 0.78), int(r * 1.80), int(r * 1.30))
    pygame.draw.arc(s, BLACK, hb_rect.inflate(lw * 2 + 4, lw * 2 + 4), 0.20, math.pi - 0.20, int(r * 0.22) + lw * 2)
    pygame.draw.arc(s, (42, 46, 66), hb_rect.inflate(4, 4), 0.24, math.pi - 0.24, int(r * 0.19))
    pygame.draw.arc(s, CYAN, hb_rect, 0.40, math.pi - 0.40, max(2, int(r * 0.09)))

    # 3. Neck & Head Base
    pygame.draw.rect(s, SKIN_SHADE, (int(bx - r * 0.20), int(head_y + r * 0.40), int(r * 0.40), int(r * 0.34)))
    head_rect = pygame.Rect(int(bx - r * 0.70), int(head_y - r * 0.56), int(r * 1.40), int(r * 1.12))
    pygame.draw.ellipse(s, BLACK, head_rect.inflate(lw * 2 + 2, lw * 2 + 2))
    pygame.draw.ellipse(s, SKIN, head_rect)
    for side in (-1, 1):
        pygame.draw.ellipse(s, (255, 168, 152),
                            (bx + side * r * 0.38 - r * 0.13, head_y + r * 0.06, r * 0.26, r * 0.14))

    # 4. Oversized Cushioned Studio Earcups (100% inside frame!)
    for side in (-1, 1):
        ecx, ecy = bx + side * r * 0.78, head_y + r * 0.02
        pad = pygame.Rect(int(ecx - side * r * 0.08 - r * 0.13), int(ecy - r * 0.30), int(r * 0.26), int(r * 0.60))
        pygame.draw.rect(s, BLACK, pad.inflate(lw * 2, lw * 2), border_radius=max(3, int(r * 0.12)))
        pygame.draw.rect(s, (38, 40, 56), pad, border_radius=max(2, int(r * 0.10)))
        cup = pygame.Rect(int(ecx + side * r * 0.05 - r * 0.18), int(ecy - r * 0.26), int(r * 0.36), int(r * 0.52))
        pygame.draw.rect(s, BLACK, cup.inflate(lw * 2, lw * 2), border_radius=max(4, int(r * 0.16)))
        pygame.draw.rect(s, CYAN, cup, border_radius=max(3, int(r * 0.15)))
        pygame.draw.rect(s, GOLD, cup.inflate(-max(2, int(r * 0.11)), -max(2, int(r * 0.13))),
                         max(2, int(2.5 * scale)), border_radius=max(2, int(r * 0.08)))

    # 5. Eyes & Brows per emotion
    fy = head_y - r * 0.08
    if st == "SHOCKED_JAWDROP":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.23
            pygame.draw.circle(s, BLACK, (ex, fy), er + lw)
            pygame.draw.circle(s, WHITE, (ex, fy), er)
            pygame.draw.circle(s, BLACK, (ex, fy), max(2, int(r * 0.06)))
            pygame.draw.arc(s, BLACK, (ex - r * 0.20, fy - r * 0.44, r * 0.40, r * 0.22), 0.2, math.pi - 0.2, lw + 1)
    elif st == "LAUGHING_TEARS":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            p0 = (ex - side * r * 0.16, fy - r * 0.10)
            p1 = (ex + side * r * 0.10, fy)
            p2 = (ex - side * r * 0.16, fy + r * 0.10)
            pygame.draw.lines(s, BLACK, False, [p0, p1, p2], lw + 1)
            tx, ty = ex + side * r * 0.26, fy + r * 0.08 + math.sin(t * 22 + side) * r * 0.04
            tear = [(tx - side * r * 0.11, ty - r * 0.04), (tx + side * r * 0.15, ty - r * 0.02),
                    (tx + side * r * 0.13, ty + r * 0.12), (tx - side * r * 0.05, ty + r * 0.08)]
            pygame.draw.polygon(s, (90, 230, 255), tear)
            pygame.draw.polygon(s, BLACK, tear, max(1, lw - 1))
    elif st == "SWEATING_INTENSE":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.17
            pygame.draw.circle(s, BLACK, (ex, fy), er + lw - 1)
            pygame.draw.circle(s, WHITE, (ex, fy), er)
            pygame.draw.circle(s, BLACK, (ex + math.sin(t * 35) * 1.2, fy + r * 0.02), max(2, int(r * 0.065)))
            pygame.draw.line(s, BLACK, (ex - side * r * 0.22, fy - r * 0.25), (ex + side * r * 0.16, fy - r * 0.09), lw + 1)
        _sweat_drop(s, bx - r * 0.48, fy - r * 0.20 + (t * 20) % (r * 0.16), r * 0.09)
        _sweat_drop(s, bx + r * 0.50, fy + r * 0.04 + (t * 16) % (r * 0.14), r * 0.08)
    elif st == "TROPHY_CHEER":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            _star(s, ex, fy, r * 0.19, GOLD)
            pygame.draw.arc(s, BLACK, (ex - r * 0.18, fy - r * 0.34, r * 0.36, r * 0.18), 0.2, math.pi - 0.2, lw)
    elif st == "FACEPALM":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.16
            pygame.draw.circle(s, BLACK, (ex, fy + r * 0.02), er + lw - 1)
            pygame.draw.circle(s, WHITE, (ex, fy + r * 0.02), er)
            pygame.draw.circle(s, BLACK, (ex - r * 0.02, fy + r * 0.04), max(2, int(r * 0.06)))
            pygame.draw.rect(s, SKIN_SHADE, (int(ex - er), int(fy - er), int(er * 2), int(er * 0.9)))
            pygame.draw.line(s, BLACK, (ex - er - 2, fy - r * 0.01), (ex + er + 2, fy + r * 0.02), lw)
        _sweat_drop(s, bx - r * 0.50, fy - r * 0.16, r * 0.09)
    else:  # HYPED_TALKING
        look_x = math.sin(t * 2.2) * r * 0.03
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.18
            pygame.draw.circle(s, BLACK, (ex, fy), er + lw - 1)
            pygame.draw.circle(s, WHITE, (ex, fy), er)
            pygame.draw.circle(s, BLACK, (ex - r * 0.02 + look_x, fy + r * 0.01), max(2, int(r * 0.085)))
            pygame.draw.circle(s, WHITE, (ex - r * 0.06 + look_x, fy - r * 0.04), max(1, int(r * 0.035)))
            pygame.draw.line(s, BLACK, (ex - side * r * 0.18, fy - r * 0.27), (ex + side * r * 0.16, fy - r * 0.21), lw + 1)

    # Nose
    pygame.draw.circle(s, BLACK, (bx, fy + r * 0.14), max(2, int(r * 0.09)) + 2)
    pygame.draw.circle(s, (255, 168, 138), (bx, fy + r * 0.14), max(2, int(r * 0.09)))

    # 6. Frame-Accurate 3-State RMS Lip-Sync Mouth (unobstructed!)
    my = fy + r * 0.36
    _draw_mouth_rms(s, bx, my, r, lw, st, rms)

    # 7. Crooked Gold Crown atop headphone band (100% inside top border!)
    lift = r * 0.14 * abs(math.sin(t * 12)) if st == "SHOCKED_JAWDROP" else 0.0
    _crown(s, bx - r * 0.06, head_y - r * 0.90 - lift, r * 0.52, tilt_deg=-12.0)

    # 8. Broadcast Studio Desk Surface (spans bottom of booth window cleanly)
    desk_rect = pygame.Rect(int(8 * scale), int(desk_y), int(s.get_width() - 16 * scale), int(base_y - desk_y + 8 * scale))
    pygame.draw.rect(s, (48, 34, 76), desk_rect)
    pygame.draw.line(s, (198, 152, 42), (desk_rect.left, desk_rect.top + 3), (desk_rect.right, desk_rect.top + 3), max(2, lw))
    pygame.draw.line(s, BLACK, (desk_rect.left, desk_rect.top), (desk_rect.right, desk_rect.top), lw)

    # 9. Animated Reacting Hands (100% visible above/on desk, zero clipping)
    hr = r * 0.24
    talk_jab = (4.5 * scale * abs(math.sin(t * 16.0))) if rms >= 0.08 else (1.8 * scale * abs(math.sin(t * 9.0)) if rms >= 0.02 else 0.0)
    if st == "SHOCKED_JAWDROP":
        _glove_hand(s, bx - r * 1.12, head_y + r * 0.28, hr, lw, open_palm=True, side=-1)
        _glove_hand(s, bx + r * 1.12, head_y + r * 0.28, hr, lw, open_palm=True, side=1)
    elif st == "LAUGHING_TEARS":
        slap = abs(math.sin(t * 22.0)) * 7.0 * scale
        _glove_hand(s, bx - r * 0.88, desk_y - r * 0.10, hr, lw)
        _glove_hand(s, bx + r * 0.98, desk_y - r * 0.04 - slap, hr, lw, open_palm=True, side=1)
    elif st == "FACEPALM":
        _glove_hand(s, bx - r * 0.92, desk_y - r * 0.06, hr, lw)
        # Temple-palm so mouth lip-sync remains 100% unobstructed!
        _glove_hand(s, bx + r * 0.66, head_y - r * 0.02, hr * 1.08, lw, open_palm=True, side=1)
    elif st == "SWEATING_INTENSE":
        _glove_hand(s, bx - r * 0.92, desk_y - r * 0.02, hr, lw)
        _glove_hand(s, bx + r * 0.92, desk_y - r * 0.02, hr, lw)
    elif st == "TROPHY_CHEER":
        _glove_hand(s, bx - r * 0.98, desk_y - r * 0.36 - talk_jab, hr, lw)
        tx_cup, ty_cup = bx + r * 1.30, head_y + r * 0.44 - talk_jab * 0.6
        _trophy(s, tx_cup, ty_cup, r * 0.44)
        _glove_hand(s, tx_cup, ty_cup + r * 0.34, hr * 0.88, lw)
        _star(s, tx_cup + r * 0.22, ty_cup - r * 0.36, r * 0.10, WHITE)
    else:  # HYPED_TALKING
        _glove_hand(s, bx - r * 0.96, desk_y - r * 0.14 - talk_jab, hr, lw, open_palm=(rms >= 0.08), side=-1)
        _glove_hand(s, bx + r * 1.04, desk_y - r * 0.18 - talk_jab * 1.2, hr, lw, open_palm=(rms >= 0.02), side=1)

    # 10. Studio Desk Boom-Mic (left desk mount -> articulated arm -> foam pop-filter beside cheek, never blocking mouth!)
    stand_x = cx - r * 2.18
    base_stand = pygame.Rect(int(stand_x - 12 * scale), int(desk_y - 5 * scale), int(24 * scale), int(8 * scale))
    pygame.draw.rect(s, BLACK, base_stand.inflate(4, 4), border_radius=3)
    pygame.draw.rect(s, (92, 98, 118), base_stand, border_radius=2)
    elbow = (stand_x - 6 * scale, desk_y - r * 1.02)
    boom_tip = (bx - r * 0.72, my + r * 0.04)
    pygame.draw.lines(s, BLACK, False, [(stand_x, desk_y - 4 * scale), elbow, boom_tip], lw + 4)
    pygame.draw.lines(s, (190, 198, 214), False, [(stand_x, desk_y - 4 * scale), elbow, boom_tip], max(2, lw))
    pygame.draw.circle(s, GOLD, elbow, max(3, int(4.5 * scale)))
    pygame.draw.circle(s, BLACK, elbow, max(3, int(4.5 * scale)), 1)
    mic = pygame.Rect(int(boom_tip[0] - r * 0.10), int(boom_tip[1] - r * 0.15), int(r * 0.30), int(r * 0.24))
    pygame.draw.ellipse(s, BLACK, mic.inflate(lw * 2, lw * 2))
    pygame.draw.ellipse(s, (42, 46, 58), mic)
    pygame.draw.line(s, GOLD, (mic.left + 3, mic.top + 3), (mic.left + 3, mic.bottom - 3), max(2, lw - 1))

    # 11. Animated 5-Bar Mic EQ Meter pulsing right beside his microphone
    _draw_eq_meter(s, stand_x - 14 * scale, elbow[1] - 8 * scale, rms, t, scale)
