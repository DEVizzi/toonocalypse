"""Renderers for the v6 arenas (one module per arena family, mirroring src/games/arenas_v6).

Group modules register drawing functions with the decorators below; `pipeline.Renderer` calls the dispatchers:
  UNDER[arena_key](r, cam, fi, zone, t_anim, play_t)       before tracks/platforms (water, pits, backdrops, floors)
  STATIC[static_type](r, cam, s, zone, t_anim, play_t)      any static dict whose "type" is not a legacy type
  PROP[style](r, cam, st, i, x, y, ang, fi)                 a whole prop (all its shapes) by style
  OVER[arena_key](r, cam, fi, zone, t_anim, play_t)        after props (beams, eyes, banners, glows)
`r` is the Renderer (r.frame surface, r.theme, r.tr trace, r.meta), `cam.to_screen(x, y)` maps world -> screen and
`cam.zoom` scales sizes. Draw cartoon-style: flat fills + thick BLACK outlines, theme colours where sensible.
"""
from __future__ import annotations

import importlib
from typing import Callable

UNDER: dict[str, Callable] = {}
STATIC: dict[str, Callable] = {}
PROP: dict[str, Callable] = {}
OVER: dict[str, Callable] = {}


def under(key: str):
    def deco(fn):
        UNDER[key] = fn
        return fn
    return deco


def static(kind: str):
    def deco(fn):
        STATIC[kind] = fn
        return fn
    return deco


def prop(style: str):
    def deco(fn):
        PROP[style] = fn
        return fn
    return deco


def over(key: str):
    def deco(fn):
        OVER[key] = fn
        return fn
    return deco


for _m in ("side_a", "side_b", "fixed", "top_a", "top_b"):
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.{_m}":
            raise
