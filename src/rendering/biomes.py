"""Per-race time-of-day / biome colour grades for the parallax backdrop (never the balls, track or hazards).

Ten races in a row against the same blue sky looked like one long video. Each race now gets one of six looks
(day, sunset, night, storm, dawn, lava). The order is a per-season permutation indexed by race number, so two
consecutive races never share a look and re-renders are deterministic. Pure cosmetics: it never touches physics,
RNG streams or recipe fingerprints, and it works on any Renderer that exposes `sky_bg`/`far_spires`/`mid_arches`
(also archived code trees replayed by the Tuno Report clip worker).
"""
from __future__ import annotations

import random

import numpy as np
import pygame

# name -> (sky top RGB, sky horizon RGB, sky blend 0..1, layer multiply RGB, star density)
BIOMES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], float, tuple[float, float, float], int]] = {
    "day": ((0, 0, 0), (0, 0, 0), 0.0, (1.0, 1.0, 1.0), 0),
    "sunset": ((255, 120, 70), (255, 206, 120), 0.62, (1.0, 0.78, 0.66), 0),
    "night": ((10, 14, 44), (46, 44, 98), 0.86, (0.46, 0.50, 0.78), 140),
    "storm": ((58, 64, 80), (122, 128, 140), 0.74, (0.62, 0.64, 0.72), 0),
    "dawn": ((255, 160, 196), (255, 226, 190), 0.52, (0.98, 0.86, 0.92), 0),
    "lava": ((54, 8, 10), (214, 72, 22), 0.80, (0.86, 0.46, 0.36), 0),
}
LABELS = {"day": "", "sunset": "SUNSET RUN", "night": "NIGHT RACE", "storm": "STORM WARNING", "dawn": "DAWN RAID",
          "lava": "LAVA HOUR"}
ORDER = tuple(BIOMES)


def biome_for(season: int, race: int) -> str:
    """Deterministic per-season permutation; consecutive races always differ."""
    perm = list(ORDER)
    random.Random(7919 * int(season or 1) + 17).shuffle(perm)
    return perm[(max(1, int(race or 1)) - 1) % len(perm)]


def _grade_layer(surf: pygame.Surface, mul: tuple[float, float, float]) -> pygame.Surface:
    if mul == (1.0, 1.0, 1.0):
        return surf
    out = surf.copy()
    try:
        px = pygame.surfarray.pixels3d(out)
        px[...] = np.clip(px.astype(np.float32) * np.array(mul, dtype=np.float32), 0, 255).astype(np.uint8)
        del px
    except Exception:  # noqa: BLE001 - e.g. palette surfaces: fall back to a multiply blit
        tint = pygame.Surface(out.get_size())
        tint.fill(tuple(int(255 * m) for m in mul))
        out.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    return out


def _grade_sky(surf: pygame.Surface, top, hor, blend: float, stars: int, seed: int) -> pygame.Surface:
    if blend <= 0:
        return surf
    out = surf.copy()
    w, h = out.get_size()
    try:
        px = pygame.surfarray.pixels3d(out)
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[None, :, None]
        grad = np.array(top, np.float32)[None, None, :] * (1 - ys) + np.array(hor, np.float32)[None, None, :] * ys
        base = px.astype(np.float32)
        # keep a little of the original shading (clouds/hills) so the look stays "drawn", not flat
        lum = base.mean(axis=2, keepdims=True) / 255.0
        graded = grad * (0.72 + 0.5 * lum)
        px[...] = np.clip(base * (1 - blend) + graded * blend, 0, 255).astype(np.uint8)
        del px
    except Exception:  # noqa: BLE001
        return surf
    if stars:
        rng = random.Random(seed)
        for _ in range(stars):
            x, y = rng.randrange(w), rng.randrange(int(h * 0.55))
            c = 200 + rng.randrange(55)
            out.set_at((x, y), (c, c, min(255, c + 20)))
            if rng.random() < 0.12:
                pygame.draw.circle(out, (c, c, 255), (x, y), 2)
    return out


def apply(renderer, name: str) -> str:
    """Grades the renderer's backdrop layers in place (idempotent: only the first call has an effect)."""
    if getattr(renderer, "_biome_applied", None) or name not in BIOMES:
        return getattr(renderer, "_biome_applied", None) or "day"
    top, hor, blend, mul, stars = BIOMES[name]
    try:
        if getattr(renderer, "sky_bg", None) is not None:
            renderer.sky_bg = _grade_sky(renderer.sky_bg, top, hor, blend, stars, seed=sum(map(ord, name)))
        for attr in ("far_spires", "mid_arches"):
            if getattr(renderer, attr, None) is not None:
                setattr(renderer, attr, _grade_layer(getattr(renderer, attr), mul))
        if getattr(renderer, "_void", None) is not None:
            renderer._void = _grade_layer(renderer._void, tuple(0.55 + 0.45 * m for m in mul))
        if getattr(renderer, "castle", None) is not None and name in ("night", "storm", "lava"):
            renderer.castle = _grade_layer(renderer.castle, mul)
    except Exception:  # noqa: BLE001 - cosmetics must never break a render
        return "day"
    renderer._biome_applied = name
    return name
