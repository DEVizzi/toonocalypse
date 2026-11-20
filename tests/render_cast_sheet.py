"""Render the M2 cast sheet: 10 heroes x 7 faces, squash/stretch + limb states, name pills, Lord Tuno's 5 states,
an extras sample and the impact popups.  Usage: python tests/render_cast_sheet.py [out.png]"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame  # noqa: E402

from src.characters import renderer  # noqa: E402
from src.characters.expressions import EXPRESSIONS  # noqa: E402
from src.characters.roster import HEROES, make_extras  # noqa: E402
from src.characters.tuno import STATES, draw_tuno  # noqa: E402
from src.config import font_path  # noqa: E402
from src.rendering import effects  # noqa: E402

CELL_W, CELL_H = 170, 190
LABEL_W = 210
COLS = list(EXPRESSIONS) + ["stretch", "squash", "airborne", "victory"]


def main(out: str = "docs/cast_sheet.png") -> str:
    pygame.init()
    title_f = pygame.font.Font(font_path("LuckiestGuy-Regular.ttf"), 44)
    lab_f = pygame.font.Font(font_path("Fredoka.ttf"), 24)
    rows_h = len(HEROES) * CELL_H
    width = LABEL_W + len(COLS) * CELL_W + 40
    height = 120 + 50 + rows_h + 330 + 260 + 470
    sheet = pygame.Surface((width, height))
    sheet.fill((246, 241, 230))
    sheet.blit(title_f.render("TOONTOONCASTLE  —  CAST SHEET", True, (40, 30, 60)), (30, 30))
    y0 = 120
    for c, name in enumerate(COLS):
        t = lab_f.render(name, True, (80, 70, 90))
        sheet.blit(t, t.get_rect(center=(LABEL_W + c * CELL_W + CELL_W // 2, y0 + 20)))
    y0 += 50
    for r, hero in enumerate(HEROES):
        cy = y0 + r * CELL_H + CELL_H // 2 - 10
        pill = renderer.name_pill(hero, crown=(r == 4))
        sheet.blit(pill, pill.get_rect(midleft=(20, cy - 22)))
        sheet.blit(lab_f.render(f"{hero.emoji} {hero.archetype}"[2:], True, (90, 80, 100)), (20, cy + 14))
        for c, col in enumerate(COLS):
            cx = LABEL_W + c * CELL_W + CELL_W // 2
            if col in EXPRESSIONS:
                renderer.draw_hero(sheet, hero, (cx, cy), 0, (0, 0), col, "idle", 0.3)
            elif col == "stretch":
                renderer.draw_hero(sheet, hero, (cx, cy), 0, (700, -60), "happy", "running", 0.25)
            elif col == "squash":
                renderer.draw_hero(sheet, hero, (cx, cy + 10), 0, (0, 0), "dizzy", "stunned", 0.4, squash=1.0)
            elif col == "airborne":
                renderer.draw_hero(sheet, hero, (cx, cy - 8), 18, (120, -200), "scared", "airborne", 0.2)
            elif col == "victory":
                renderer.draw_hero(sheet, hero, (cx, cy), 0, (0, 0), "celebrating", "victory", 0.1)
    # Lord Tuno
    ty = y0 + rows_h + 20
    sheet.blit(title_f.render("LORD TUNO", True, (40, 30, 60)), (30, ty))
    for i, st in enumerate(STATES):
        cx = 180 + i * 360
        draw_tuno(sheet, cx, ty + 250, st, 0.37)
        t = lab_f.render(st, True, (80, 70, 90))
        sheet.blit(t, t.get_rect(center=(cx, ty + 310)))
    # extras
    ey = ty + 330
    sheet.blit(title_f.render("EXTRAS", True, (40, 30, 60)), (30, ey))
    rng = random.Random(7)
    extras = make_extras(16, rng, cult_numbers={27 % 16 + 1})
    for i, e in enumerate(extras):
        expr = ["neutral", "scared", "eliminated"][i % 3]
        renderer.draw_extra(sheet, e, (90 + i * 110, ey + 150), 0, expr, zoom=1.6)
    # popups
    py = ey + 260
    sheet.blit(title_f.render("POPUPS", True, (40, 30, 60)), (30, py))
    words = list(effects.POPUP_WORDS) + ["SPITE!", "NO BRAKES!"]
    for i, w in enumerate(words):
        row, col = divmod(i, 4)
        effects.draw_popup(sheet, w, (230 + col * 440, py + 150 + row * 200), 0.2, seed=i)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, out)
    small = pygame.transform.smoothscale(sheet, (width // 3, height // 3))   # phone-size check
    pygame.image.save(small, out.replace(".png", "_phone.png"))
    return out


if __name__ == "__main__":
    print(main(*sys.argv[1:]))
