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
