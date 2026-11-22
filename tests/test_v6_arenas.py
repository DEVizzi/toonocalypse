"""v6 arenas: every registered arena builds, simulates to a hero-or-anyone winner, replays deterministically, and the
legacy recipe pool is untouched for days before `v6_from_day` (published races + seed backfill stay reproducible)."""
from __future__ import annotations

import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _cast(info, seed):
    from src.characters.roster import HEROES, make_extras
    n = {"qualifier_1": 2, "grand_final": 3}.get(info.get("playoff") or "", 10)
    rng = random.Random(seed)
    return list(HEROES)[:n], make_extras(6 if n < 10 else 4, rng, golden=info.get("playoff") == "grand_final")


class TestV6Arenas(unittest.TestCase):
    def test_registry_metadata(self) -> None:
        from src.games import arenas_v6  # noqa: F401
        from src.games.arena_kit import INFO
        from src.games.base import GOALS, HAZARDS, TWISTS, fits
        for key, info in INFO.items():
            self.assertTrue(info["name"] and info["feature"], key)
            self.assertGreaterEqual(len(info["quips"]), 2, key)
            self.assertTrue(info["goals"], key)
            for g in info["goals"]:
                self.assertIn(g, GOALS, key)
                self.assertTrue(fits(GOALS[g], info["mode"]), (key, g))
            for h in info["hazards"]:
                self.assertIn(h, HAZARDS, key)
            for t in info["twists"] or ():
                self.assertIn(t, TWISTS, key)

    def test_every_arena_simulates_and_replays(self) -> None:
        from src.games import arenas_v6  # noqa: F401
        from src.games import recipe_generator
        from src.games.arena_kit import INFO
        from src.physics.engine import Sim
        for key, info in sorted(INFO.items()):
            with self.subTest(arena=key):
                seed = 4242
                recipe, _ = recipe_generator.generate([], 400, seed, arena=key, goal=info["goals"][0],
                                                      season_theme="royal_classic")
                self.assertEqual(recipe.arena, key)
                heroes, extras = _cast(info, seed)
                tr = Sim(recipe, heroes, extras, seed).run()
                self.assertIsNotNone(tr.meta.get("winner"), key)
                self.assertLess(tr.meta.get("resolved_at") or 99, 40.0, key)
                tr2 = Sim(recipe, heroes, extras, seed).run()
                self.assertEqual(tr.meta.get("ranking"), tr2.meta.get("ranking"), f"{key} not deterministic")

    def test_legacy_pool_before_v6_day(self) -> None:
        from src.games import recipe_generator as g
        r, _ = g.generate([], 1, 22959, season_theme="royal_classic")
        self.assertEqual((r.arena, r.goal, sorted(r.hazards), r.twist),
                         ("crusher_gauntlet", "reach_finish", ["falling_floor_tiles", "slippery_ice"], None))
        self.assertEqual(r.fingerprint()[:16], "9930d202ca08d049")
        self.assertEqual(len(g.arena_pool(1)), 17)
        self.assertGreater(len(g.arena_pool(g.v6_from_day())), 17)
        self.assertTrue(all(not g._v6_info()[k].get("playoff") for k in g.arena_pool(999) if k in g._v6_info()))


if __name__ == "__main__":
    unittest.main()
