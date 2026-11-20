"""v4.0 Seasonal Themes (`SeasonTheme`): 8 zero-asset procedural themes cycling automatically every 30-episode season
(`(season_number - 1) % 8`). Skins sky gradients, parallax spires, block masonry/caps, weather particles, abyss trenches,
and the 3-layer foreground Killer Wall + interior storm."""
from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class SeasonTheme:
    key: str
    name: str
    sky_top: RGB
    sky_bottom: RGB
    castle: RGB
    terrain: RGB              # platform top cap colour
    terrain_outline: RGB
    accent: RGB
    particles: str            # motes | snow | embers | cyber_glitch | monsoon | haunted_mist | sand_wind | sprinkles
    hazard: RGB
    rock: RGB = (148, 152, 168)
    block_style: str = "royal"   # royal | frost | obsidian | neon | moss | gothic | sandstone | wafer
    wall_outer: RGB = (185, 28, 28)
    wall_mid: RGB = (249, 115, 22)
    wall_core: RGB = (254, 240, 138)
    wall_back: RGB = (136, 20, 18)
    wall_glow: RGB = (11, 5, 1)  # 17-step BLEND_RGB_ADD increment ahead of the wall
    wall_style: str = "fire"


# Backwards-compatible alias
Theme = SeasonTheme

# Ordered S1..S8 seasonal rotation (season_index % 8)
SEASON_THEMES: tuple[SeasonTheme, ...] = (
    # S1 — Royal Classic
    SeasonTheme(
        key="royal_classic",
        name="Royal Classic",
        sky_top=(74, 158, 248),
        sky_bottom=(198, 234, 255),
        castle=(168, 174, 204),
        terrain=(92, 188, 76),
        terrain_outline=(36, 86, 30),
        accent=(255, 224, 92),
        particles="motes",
        hazard=(232, 64, 58),
        rock=(148, 154, 172),
        block_style="royal",
        wall_outer=(185, 28, 28),
        wall_mid=(249, 115, 22),
        wall_core=(254, 240, 138),
        wall_back=(128, 18, 18),
        wall_glow=(11, 5, 1),
        wall_style="fire",
    ),
    # S2 — Frostbite Siege
    SeasonTheme(
        key="frostbite_siege",
        name="Frostbite Siege",
        sky_top=(24, 48, 108),
        sky_bottom=(112, 166, 226),
        castle=(136, 168, 212),
        terrain=(238, 248, 255),
        terrain_outline=(58, 104, 162),
        accent=(125, 238, 255),
        particles="snow",
        hazard=(244, 68, 108),
        rock=(118, 148, 188),
        block_style="frost",
        wall_outer=(20, 68, 188),
        wall_mid=(0, 178, 255),
        wall_core=(222, 252, 255),
        wall_back=(14, 38, 116),
        wall_glow=(1, 6, 12),
        wall_style="frost",
    ),
    # S3 — Volcanic Foundry
    SeasonTheme(
        key="volcanic_foundry",
        name="Volcanic Foundry",
        sky_top=(42, 12, 22),
        sky_bottom=(148, 44, 22),
        castle=(76, 50, 58),
        terrain=(92, 74, 72),
        terrain_outline=(24, 14, 14),
        accent=(255, 148, 36),
        particles="embers",
        hazard=(255, 206, 48),
        rock=(52, 44, 50),
        block_style="obsidian",
        wall_outer=(148, 18, 10),
        wall_mid=(255, 88, 12),
        wall_core=(255, 236, 112),
        wall_back=(96, 14, 10),
        wall_glow=(12, 4, 1),
        wall_style="magma",
    ),
    # S4 — Cyber Neon Keep
    SeasonTheme(
        key="cyber_neon_keep",
        name="Cyber Neon Keep",
        sky_top=(14, 8, 42),
        sky_bottom=(62, 18, 104),
        castle=(58, 44, 102),
        terrain=(0, 218, 242),
        terrain_outline=(18, 24, 52),
        accent=(255, 48, 192),
        particles="cyber_glitch",
        hazard=(255, 52, 168),
        rock=(32, 36, 62),
        block_style="neon",
        wall_outer=(156, 14, 188),
        wall_mid=(255, 36, 168),
        wall_core=(148, 252, 255),
        wall_back=(78, 8, 112),
        wall_glow=(9, 2, 11),
        wall_style="neon",
    ),
    # S5 — Monsoon Storm
    SeasonTheme(
        key="monsoon_storm",
        name="Monsoon Storm",
        sky_top=(30, 42, 66),
        sky_bottom=(84, 104, 132),
        castle=(78, 90, 114),
        terrain=(68, 148, 88),
        terrain_outline=(24, 46, 34),
        accent=(168, 236, 255),
        particles="monsoon",
        hazard=(255, 178, 38),
        rock=(78, 88, 106),
        block_style="moss",
        wall_outer=(26, 54, 158),
        wall_mid=(56, 152, 255),
        wall_core=(232, 248, 255),
        wall_back=(18, 32, 92),
        wall_glow=(2, 6, 12),
        wall_style="storm",
    ),
    # S6 — Haunted Castle
    SeasonTheme(
        key="haunted_castle",
        name="Haunted Castle",
        sky_top=(22, 14, 48),
        sky_bottom=(76, 52, 118),
        castle=(78, 66, 108),
        terrain=(108, 94, 132),
        terrain_outline=(28, 20, 44),
        accent=(142, 255, 118),
        particles="haunted_mist",
        hazard=(132, 248, 96),
        rock=(68, 60, 88),
        block_style="gothic",
        wall_outer=(16, 112, 48),
        wall_mid=(48, 214, 88),
        wall_core=(220, 255, 164),
        wall_back=(12, 64, 30),
        wall_glow=(2, 10, 3),
        wall_style="ghost",
    ),
    # S7 — Desert Mirage
    SeasonTheme(
        key="desert_mirage",
        name="Desert Mirage",
        sky_top=(198, 88, 34),
        sky_bottom=(248, 198, 118),
        castle=(198, 152, 96),
        terrain=(234, 192, 112),
        terrain_outline=(112, 72, 32),
        accent=(255, 232, 96),
        particles="sand_wind",
        hazard=(188, 42, 72),
        rock=(204, 162, 96),
        block_style="sandstone",
        wall_outer=(188, 52, 10),
        wall_mid=(252, 152, 16),
        wall_core=(255, 250, 188),
        wall_back=(132, 34, 8),
        wall_glow=(11, 7, 1),
        wall_style="solar",
    ),
    # S8 — Candy Chaos
    SeasonTheme(
        key="candy_chaos",
        name="Candy Chaos",
        sky_top=(118, 186, 248),
        sky_bottom=(252, 192, 224),
        castle=(232, 168, 208),
        terrain=(255, 118, 182),
        terrain_outline=(132, 46, 88),
        accent=(255, 232, 92),
        particles="sprinkles",
        hazard=(124, 58, 232),
        rock=(208, 152, 96),
        block_style="wafer",
        wall_outer=(156, 16, 88),
        wall_mid=(248, 56, 154),
        wall_core=(255, 226, 246),
        wall_back=(104, 12, 62),
        wall_glow=(10, 2, 7),
        wall_style="berry",
    ),
)

THEMES: tuple[SeasonTheme, ...] = SEASON_THEMES

_LEGACY_ALIASES: dict[str, SeasonTheme] = {
    "meadow": SEASON_THEMES[0],
    "sky": SEASON_THEMES[0],
    "ice": SEASON_THEMES[1],
    "volcano": SEASON_THEMES[2],
    "clockwork": SEASON_THEMES[2],
    "space": SEASON_THEMES[3],
    "storm": SEASON_THEMES[4],
    "underwater": SEASON_THEMES[4],
    "haunted": SEASON_THEMES[5],
    "jungle": SEASON_THEMES[5],
    "desert": SEASON_THEMES[6],
    "candy": SEASON_THEMES[7],
}

THEME_BY_KEY: dict[str, SeasonTheme] = {t.key: t for t in SEASON_THEMES} | _LEGACY_ALIASES


def for_season(season_number: int) -> SeasonTheme:
    """Returns the procedural SeasonTheme for 1-indexed season_number (cycles every 8 seasons)."""
    return SEASON_THEMES[(max(1, int(season_number)) - 1) % len(SEASON_THEMES)]
