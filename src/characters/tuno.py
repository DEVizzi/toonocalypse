"""MC Tuno (v3.2): High-energy Cartoon Commentator Host in the top-right 220x220 broadcast booth cam.
Features oversized cyan/gold studio headphones, boom microphone with foam pop-filter, tiny crooked gold crown perched
on his headset, thick black comic outlines, and 6 vivid reaction poses:
HYPED_TALKING, SHOCKED_JAWDROP, LAUGHING_TEARS, FACEPALM, SWEATING_INTENSE, TROPHY_CHEER.
"""
from __future__ import annotations

import math

import pygame

from src.characters.expressions import BLACK, WHITE

JACKET = (118, 32, 188)       # Vibrant Royal Purple broadcaster jacket
JACKET_HI = (168, 72, 238)
CYAN = (0, 229, 255)
CYAN_DARK = (0, 150, 190)
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


def _crown(s: pygame.Surface, cx: float, cy: float, w: float, tilt_deg: float = -14.0) -> None:
    """Tiny crooked gold crown perched jauntily on top of MC Tuno's headphone band."""
    cw, ch = int(w * 1.6), int(w * 1.2)
    cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
    ox, oy = cw / 2, ch * 0.74
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
    pygame.draw.polygon(cs, BLACK, pts, 4)
    pygame.draw.line(cs, (255, 244, 160), (ox - w * 0.38, oy - w * 0.08), (ox + w * 0.38, oy - w * 0.08), 3)
    for gx, col in ((ox - w * 0.24, CRIMSON), (ox, (40, 160, 255)), (ox + w * 0.24, (46, 214, 115))):
        pygame.draw.circle(cs, col, (gx, oy - w * 0.16), max(3, int(w * 0.085)))
        pygame.draw.circle(cs, BLACK, (gx, oy - w * 0.16), max(3, int(w * 0.085)), 1)
    rot = pygame.transform.rotozoom(cs, tilt_deg, 1.0)
    s.blit(rot, rot.get_rect(center=(cx, cy)))


def _sweat_drop(s: pygame.Surface, x: float, y: float, r: float) -> None:
    pts = [(x, y - r * 1.35), (x + r * 0.85, y + r * 0.2), (x, y + r * 0.95), (x - r * 0.85, y + r * 0.2)]
    pygame.draw.polygon(s, BLACK, [(px, py) for px, py in pts], 0)
    pygame.draw.circle(s, BLACK, (x, y + r * 0.28), r * 0.88)
    pygame.draw.polygon(s, (110, 225, 255), [(x, y - r * 1.05), (x + r * 0.62, y + r * 0.2), (x - r * 0.62, y + r * 0.2)])
    pygame.draw.circle(s, (110, 225, 255), (x, y + r * 0.28), r * 0.65)
    pygame.draw.circle(s, WHITE, (x - r * 0.22, y + r * 0.15), max(1, int(r * 0.22)))


def _star(s: pygame.Surface, cx: float, cy: float, rr: float, col=GOLD) -> None:
    pts = [
        (cx + math.cos(-math.pi / 2 + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.44),
         cy + math.sin(-math.pi / 2 + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.44))
        for i in range(10)
    ]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, BLACK, pts, 2)


def _trophy(s: pygame.Surface, cx: float, cy: float, r: float) -> None:
    """Mini golden champion cup held up on TROPHY_CHEER."""
    lw = max(3, int(r * 0.10))
    # handles
    pygame.draw.circle(s, BLACK, (cx - r * 0.52, cy - r * 0.12), r * 0.26, lw + 2)
    pygame.draw.circle(s, GOLD, (cx - r * 0.52, cy - r * 0.12), r * 0.24, lw - 1)
    pygame.draw.circle(s, BLACK, (cx + r * 0.52, cy - r * 0.12), r * 0.26, lw + 2)
    pygame.draw.circle(s, GOLD, (cx + r * 0.52, cy - r * 0.12), r * 0.24, lw - 1)
    # cup bowl
    cup = [(cx - r * 0.54, cy - r * 0.48), (cx + r * 0.54, cy - r * 0.48),
           (cx + r * 0.36, cy + r * 0.22), (cx - r * 0.36, cy + r * 0.22)]
    pygame.draw.polygon(s, GOLD, cup)
    pygame.draw.polygon(s, BLACK, cup, lw)
    pygame.draw.line(s, (255, 248, 190), (cx - r * 0.34, cy - r * 0.36), (cx - r * 0.22, cy + r * 0.10), lw)
    # stem + base
    pygame.draw.rect(s, GOLD, (cx - r * 0.12, cy + r * 0.20, r * 0.24, r * 0.28))
    pygame.draw.rect(s, BLACK, (cx - r * 0.12, cy + r * 0.20, r * 0.24, r * 0.28), lw - 1)
    base = pygame.Rect(cx - r * 0.38, cy + r * 0.44, r * 0.76, r * 0.22)
    pygame.draw.rect(s, (120, 75, 35), base, border_radius=4)
    pygame.draw.rect(s, BLACK, base, lw - 1, border_radius=4)


def draw_tuno(s: pygame.Surface, cx: float, base_y: float, state: str, t: float, scale: float = 1.0) -> None:
    """Draws Commentator Host MC Tuno inside his portrait frame (clipped by caller if needed)."""
    st = _ALIASES.get(state, state)
    r = 54 * scale
    lw = max(3, int(3.8 * scale))
    bob = math.sin(t * 5.5) * 2.5 * scale if st == "HYPED_TALKING" else math.sin(t * 2.8) * 1.8 * scale
    shake = math.sin(t * 44) * 3.2 * scale if st == "LAUGHING_TEARS" else (
        math.sin(t * 55) * 1.6 * scale if st == "SWEATING_INTENSE" else 0.0
    )
    bx, by = cx + shake, base_y - r * 0.44 + bob

    # 1. Sporty Broadcaster Jacket & Gold Lapels
    pygame.draw.circle(s, BLACK, (bx, by + r * 0.36), r * 1.06 + lw + 1)
    pygame.draw.circle(s, JACKET, (bx, by + r * 0.36), r * 1.06)
    pygame.draw.arc(s, JACKET_HI, (bx - r * 0.96, by - r * 0.56, r * 1.92, r * 1.7), 1.7, 2.85, max(3, int(5 * scale)))
    # Crisp white shirt V-neck + gold collar lapels
    shirt = [(bx - r * 0.34, by + r * 0.06), (bx + r * 0.34, by + r * 0.06), (bx, by + r * 0.62)]
    pygame.draw.polygon(s, WHITE, shirt)
    pygame.draw.polygon(s, BLACK, shirt, lw - 1)
    for side in (-1, 1):
        lapel = [
            (bx + side * r * 0.22, by + r * 0.06),
            (bx + side * r * 0.56, by + r * 0.14),
            (bx + side * r * 0.40, by + r * 0.54),
            (bx, by + r * 0.60),
        ]
        pygame.draw.polygon(s, GOLD, lapel)
        pygame.draw.polygon(s, BLACK, lapel, lw - 1)

    # 2. Headphone Arched Band (behind head top)
    hb_rect = pygame.Rect(bx - r * 0.88, by - r * 1.04, r * 1.76, r * 1.32)
    pygame.draw.arc(s, BLACK, hb_rect.inflate(lw * 2 + 4, lw * 2 + 4), 0.22, math.pi - 0.22, int(r * 0.22) + lw * 2)
    pygame.draw.arc(s, (42, 46, 66), hb_rect.inflate(4, 4), 0.25, math.pi - 0.25, int(r * 0.20))
    pygame.draw.arc(s, CYAN, hb_rect, 0.42, math.pi - 0.42, max(3, int(r * 0.09)))

    # 3. Head Base
    head_rect = pygame.Rect(bx - r * 0.68, by - r * 0.84, r * 1.36, r * 1.08)
    pygame.draw.ellipse(s, BLACK, head_rect.inflate(lw * 2 + 2, lw * 2 + 2))
    pygame.draw.ellipse(s, SKIN, head_rect)
    # Subtle warm cheek shade
    for side in (-1, 1):
        pygame.draw.ellipse(s, (255, 168, 152), (bx + side * r * 0.36 - r * 0.13, by - r * 0.20, r * 0.26, r * 0.14))

    # 4. Oversized Cushioned Studio Earcups (Left & Right)
    for side in (-1, 1):
        ecx, ecy = bx + side * r * 0.76, by - r * 0.28
        pad = pygame.Rect(ecx - side * r * 0.10 - r * 0.13, ecy - r * 0.30, r * 0.26, r * 0.60)
        pygame.draw.rect(s, BLACK, pad.inflate(lw * 2, lw * 2), border_radius=int(r * 0.12))
        pygame.draw.rect(s, (38, 40, 56), pad, border_radius=int(r * 0.10))
        cup = pygame.Rect(ecx + side * r * 0.04 - r * 0.18, ecy - r * 0.27, r * 0.36, r * 0.54)
        pygame.draw.rect(s, BLACK, cup.inflate(lw * 2, lw * 2), border_radius=int(r * 0.16))
        pygame.draw.rect(s, CYAN, cup, border_radius=int(r * 0.15))
        pygame.draw.rect(s, GOLD, cup.inflate(-int(r * 0.12), -int(r * 0.14)), max(2, int(3 * scale)), border_radius=int(r * 0.09))

    # 5. Eyes, Brows & Expressions
    fy = by - r * 0.36
    if st == "SHOCKED_JAWDROP":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.24
            pygame.draw.circle(s, BLACK, (ex, fy - r * 0.02), er + lw)
            pygame.draw.circle(s, WHITE, (ex, fy - r * 0.02), er)
            pygame.draw.circle(s, BLACK, (ex, fy - r * 0.02), r * 0.055)
            # High shocked arch brows
            pygame.draw.arc(s, BLACK, (ex - r * 0.20, fy - r * 0.46, r * 0.40, r * 0.22), 0.2, math.pi - 0.2, lw + 1)
    elif st == "LAUGHING_TEARS":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            # Tight happy > < chevrons
            p0 = (ex - side * r * 0.16, fy - r * 0.10)
            p1 = (ex + side * r * 0.10, fy)
            p2 = (ex - side * r * 0.16, fy + r * 0.10)
            pygame.draw.lines(s, BLACK, False, [p0, p1, p2], lw + 1)
            # Flying cyan cartoon joy tears
            tx, ty = ex + side * r * 0.26, fy + r * 0.08 + math.sin(t * 22 + side) * r * 0.04
            tear = [(tx - side * r * 0.12, ty - r * 0.04), (tx + side * r * 0.16, ty - r * 0.02),
                    (tx + side * r * 0.14, ty + r * 0.13), (tx - side * r * 0.06, ty + r * 0.08)]
            pygame.draw.polygon(s, (90, 230, 255), tear)
            pygame.draw.polygon(s, BLACK, tear, max(2, lw - 1))
    elif st == "SWEATING_INTENSE":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.17
            pygame.draw.circle(s, BLACK, (ex, fy), er + lw - 1)
            pygame.draw.circle(s, WHITE, (ex, fy), er)
            pygame.draw.circle(s, BLACK, (ex + math.sin(t * 35) * 1.5, fy + r * 0.02), r * 0.065)
            # Deep furrowed V-brows
            pygame.draw.line(s, BLACK, (ex - side * r * 0.22, fy - r * 0.26), (ex + side * r * 0.16, fy - r * 0.09), lw + 2)
        _sweat_drop(s, bx - r * 0.46, fy - r * 0.22 + (t * 22) % (r * 0.18), r * 0.10)
        _sweat_drop(s, bx + r * 0.48, fy + r * 0.06 + (t * 18) % (r * 0.16), r * 0.09)
    elif st == "TROPHY_CHEER":
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            _star(s, ex, fy, r * 0.20, GOLD)
            pygame.draw.arc(s, BLACK, (ex - r * 0.18, fy - r * 0.34, r * 0.36, r * 0.18), 0.2, math.pi - 0.2, lw)
    elif st == "FACEPALM":
        # Left eye peeking out exasperated; right side covered by palm
        ex = bx - r * 0.28
        er = r * 0.16
        pygame.draw.circle(s, BLACK, (ex, fy + r * 0.02), er + lw - 1)
        pygame.draw.circle(s, WHITE, (ex, fy + r * 0.02), er)
        pygame.draw.circle(s, BLACK, (ex - r * 0.03, fy + r * 0.04), r * 0.06)
        pygame.draw.rect(s, SKIN_SHADE, (ex - er, fy - er, er * 2, er * 0.95))
        pygame.draw.line(s, BLACK, (ex - er - 2, fy - r * 0.02), (ex + er + 2, fy + r * 0.02), lw)
        _sweat_drop(s, bx - r * 0.50, fy - r * 0.16, r * 0.10)
    else:  # HYPED_TALKING
        look_x = math.sin(t * 2.2) * r * 0.03
        for side in (-1, 1):
            ex = bx + side * r * 0.27
            er = r * 0.18
            pygame.draw.circle(s, BLACK, (ex, fy), er + lw - 1)
            pygame.draw.circle(s, WHITE, (ex, fy), er)
            pygame.draw.circle(s, BLACK, (ex - r * 0.03 + look_x, fy + r * 0.01), r * 0.085)
            pygame.draw.circle(s, WHITE, (ex - r * 0.07 + look_x, fy - r * 0.04), max(2, int(r * 0.035)))
            # Energetic raised broadcaster brows
            pygame.draw.line(s, BLACK, (ex - side * r * 0.18, fy - r * 0.28), (ex + side * r * 0.16, fy - r * 0.22), lw + 1)

    # Nose
    pygame.draw.circle(s, BLACK, (bx, fy + r * 0.15), r * 0.095 + 2)
    pygame.draw.circle(s, (255, 168, 138), (bx, fy + r * 0.15), r * 0.095)

    # 6. Mouths (per expression)
    my = fy + r * 0.39
    if st == "SHOCKED_JAWDROP":
        jaw = pygame.Rect(bx - r * 0.20, my - r * 0.08, r * 0.40, r * 0.48)
        pygame.draw.ellipse(s, BLACK, jaw.inflate(lw * 2, lw * 2))
        pygame.draw.ellipse(s, (95, 18, 34), jaw)
        pygame.draw.ellipse(s, (240, 88, 108), (bx - r * 0.13, my + r * 0.18, r * 0.26, r * 0.18))
    elif st in ("LAUGHING_TEARS", "TROPHY_CHEER"):
        pts = [(bx - r * 0.36, my - r * 0.08), (bx + r * 0.36, my - r * 0.08),
               (bx + r * 0.24, my + r * 0.26), (bx - r * 0.24, my + r * 0.26)]
        pygame.draw.polygon(s, (105, 18, 36), pts)
        pygame.draw.polygon(s, WHITE, [(bx - r * 0.32, my - r * 0.06), (bx + r * 0.32, my - r * 0.06),
                                       (bx + r * 0.28, my + r * 0.05), (bx - r * 0.28, my + r * 0.05)])
        pygame.draw.ellipse(s, (240, 90, 110), (bx - r * 0.18, my + r * 0.10, r * 0.36, r * 0.15))
        pygame.draw.polygon(s, BLACK, pts, lw)
    elif st == "SWEATING_INTENSE":
        grin = pygame.Rect(bx - r * 0.32, my - r * 0.04, r * 0.64, r * 0.22)
        pygame.draw.rect(s, BLACK, grin.inflate(lw * 2, lw * 2), border_radius=int(r * 0.08))
        pygame.draw.rect(s, WHITE, grin, border_radius=int(r * 0.07))
        pygame.draw.line(s, BLACK, (grin.left + 3, grin.centery), (grin.right - 3, grin.centery), max(2, lw - 1))
        for k in range(1, 5):
            gx = grin.left + grin.width * k / 5
            pygame.draw.line(s, BLACK, (gx, grin.top + 2), (gx, grin.bottom - 2), max(2, lw - 1))
    elif st == "FACEPALM":
        pygame.draw.lines(s, BLACK, False, [(bx - r * 0.24, my + r * 0.08), (bx - r * 0.06, my), (bx + r * 0.16, my + r * 0.10)], lw)
    else:  # HYPED_TALKING: 2-frame animated mouth movement (ready for TTS lip-sync)
        talk_open = int(t * 7.5) % 2 == 0
        if talk_open:
            pts = [(bx - r * 0.30, my - r * 0.06), (bx + r * 0.30, my - r * 0.06),
                   (bx + r * 0.18, my + r * 0.22), (bx - r * 0.18, my + r * 0.22)]
            pygame.draw.polygon(s, (105, 18, 36), pts)
            pygame.draw.rect(s, WHITE, (bx - r * 0.24, my - r * 0.05, r * 0.48, r * 0.09))
            pygame.draw.ellipse(s, (240, 90, 110), (bx - r * 0.14, my + r * 0.09, r * 0.28, r * 0.12))
            pygame.draw.polygon(s, BLACK, pts, lw)
        else:
            om = pygame.Rect(bx - r * 0.15, my - r * 0.04, r * 0.30, r * 0.22)
            pygame.draw.ellipse(s, BLACK, om.inflate(lw * 2, lw * 2))
            pygame.draw.ellipse(s, (105, 18, 36), om)
            pygame.draw.ellipse(s, (240, 90, 110), (bx - r * 0.09, my + r * 0.07, r * 0.18, r * 0.09))

    # 7. Curved Boom Microphone + Foam Pop Filter
    m_start = (bx - r * 0.80, by - r * 0.18)
    m_mid = (bx - r * 0.62, by + r * 0.22)
    m_tip = (bx - r * 0.24, by + r * 0.18)
    pygame.draw.lines(s, BLACK, False, [m_start, m_mid, m_tip], lw + 5)
    pygame.draw.lines(s, (185, 195, 210), False, [m_start, m_mid, m_tip], max(2, lw))
    mic = pygame.Rect(m_tip[0] - r * 0.06, m_tip[1] - r * 0.13, r * 0.28, r * 0.22)
    pygame.draw.ellipse(s, BLACK, mic.inflate(lw * 2, lw * 2))
    pygame.draw.ellipse(s, (45, 48, 60), mic)
    pygame.draw.line(s, GOLD, (mic.left + 3, mic.top + 3), (mic.left + 3, mic.bottom - 3), max(2, lw - 1))
    if st == "HYPED_TALKING" and int(t * 7.5) % 2 == 0:
        # subtle comic sound ticks at the mic
        pygame.draw.line(s, GOLD, (mic.right + 6, mic.centery - 6), (mic.right + 14, mic.centery - 11), max(2, lw - 1))
        pygame.draw.line(s, GOLD, (mic.right + 7, mic.centery + 4), (mic.right + 15, mic.centery + 8), max(2, lw - 1))

    # 8. Foreground Props (Facepalm Hand / Golden Trophy)
    if st == "FACEPALM":
        palm = [
            (bx - r * 0.04, fy - r * 0.34),
            (bx + r * 0.48, fy - r * 0.28),
            (bx + r * 0.54, fy + r * 0.26),
            (bx + r * 0.24, fy + r * 0.56),
            (bx - r * 0.08, fy + r * 0.22),
        ]
        pygame.draw.polygon(s, WHITE, palm)
        pygame.draw.polygon(s, BLACK, palm, lw)
        for fk in (0.28, 0.56, 0.80):
            fx0 = bx + r * (-0.02 + 0.46 * fk)
            pygame.draw.line(s, BLACK, (fx0, fy - r * 0.30), (fx0 + r * 0.03, fy + r * 0.02), max(2, lw - 1))
    elif st == "TROPHY_CHEER":
        _trophy(s, bx + r * 0.72, by + r * 0.02, r * 0.42)
        _star(s, bx + r * 0.92, by - r * 0.34, r * 0.11, WHITE)

    # 9. Tiny Crooked Gold Crown perched on top of the headset
    lift = r * 0.24 * abs(math.sin(t * 12)) if st == "SHOCKED_JAWDROP" else 0.0
    _crown(s, bx - r * 0.10, by - r * 1.14 - lift, r * 0.56, tilt_deg=-14.0)
