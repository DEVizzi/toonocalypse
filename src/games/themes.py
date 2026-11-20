"""Visual themes (§11.5): sky gradient, castle tint, terrain fill/outline, accent glow, ambient particles."""
from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    sky_top: RGB
    sky_bottom: RGB
    castle: RGB
    terrain: RGB
    terrain_outline: RGB
    accent: RGB
    particles: str        # pollen | snow | embers | sand | fireflies | stars | bubbles | sprinkles | wisps | sparks | clouds | rain
    hazard: RGB           # hazard/obstacle colour that reads against this theme


THEMES: tuple[Theme, ...] = (
    Theme("meadow", "Meadow", (120, 200, 255), (210, 240, 255), (196, 186, 220), (110, 190, 80), (40, 90, 30),
          (255, 236, 120), "pollen", (230, 80, 60)),
    Theme("ice", "Ice Kingdom", (90, 150, 230), (215, 235, 255), (190, 215, 245), (220, 240, 255), (70, 120, 180),
          (140, 230, 255), "snow", (255, 90, 120)),
    Theme("volcano", "Volcano", (60, 20, 40), (230, 90, 40), (90, 60, 70), (80, 60, 60), (25, 15, 15),
          (255, 140, 40), "embers", (255, 210, 60)),
    Theme("desert", "Desert Ruins", (250, 170, 90), (255, 230, 170), (220, 180, 130), (230, 190, 120), (130, 90, 50),
          (255, 220, 100), "sand", (90, 70, 200)),
    Theme("jungle", "Jungle Temple", (60, 140, 110), (180, 230, 170), (140, 160, 120), (70, 140, 60), (25, 60, 25),
          (255, 220, 80), "fireflies", (240, 90, 40)),
    Theme("space", "Outer Space", (10, 10, 40), (60, 30, 110), (110, 100, 160), (120, 120, 150), (40, 40, 70),
          (120, 255, 220), "stars", (255, 90, 200)),
    Theme("underwater", "Deep Underwater", (10, 60, 120), (40, 160, 200), (90, 140, 170), (200, 180, 120),
          (80, 70, 40), (130, 255, 230), "bubbles", (255, 120, 80)),
    Theme("candy", "Candy Land", (255, 170, 220), (255, 235, 245), (255, 200, 230), (255, 140, 190), (160, 50, 110),
          (130, 230, 255), "sprinkles", (110, 70, 220)),
    Theme("haunted", "Haunted Castle", (50, 40, 90), (140, 110, 170), (110, 100, 140), (90, 80, 110), (35, 25, 55),
          (180, 255, 140), "wisps", (255, 160, 60)),
    Theme("clockwork", "Clockwork Factory", (120, 90, 60), (220, 190, 140), (160, 130, 100), (150, 110, 70),
          (60, 40, 20), (255, 200, 80), "sparks", (60, 160, 230)),
    Theme("sky", "Sky Clouds", (100, 170, 255), (230, 245, 255), (220, 220, 245), (255, 255, 255), (120, 150, 200),
          (255, 220, 120), "clouds", (255, 100, 90)),
    Theme("storm", "Thunder Storm", (40, 50, 80), (110, 120, 150), (100, 105, 130), (90, 100, 110), (30, 35, 45),
          (255, 240, 120), "rain", (255, 170, 40)),
)
THEME_BY_KEY = {t.key: t for t in THEMES}
