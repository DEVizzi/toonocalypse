"""The 23 v6 arenas, split by family. Importing this package registers every arena in `src.games.arena_kit`."""
from __future__ import annotations

import importlib

GROUP_MODULES = ("side_a", "side_b", "fixed", "top_a", "top_b")

for _m in GROUP_MODULES:
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except ModuleNotFoundError as exc:          # a group not written yet must not break the legacy 17 arenas
        if exc.name != f"{__name__}.{_m}":
            raise

# Pacing tune (lab-measured): a gentler LEFT-BEHIND wall stretches these side courses toward a 22 s+ Short.
_PACING = {"red_light": (0.55, 1.7), "knock_doors": (0.55, 1.7), "clockwork_cogs": (0.55, 1.7),
           "glass_bridge": (0.55, 1.7)}
from src.games.arena_kit import REGISTRY as _REG  # noqa: E402

for _k, (_cs, _ls) in _PACING.items():
    if _k in _REG:
        _REG[_k].chase_scale, _REG[_k].lag_scale = _cs, _ls
