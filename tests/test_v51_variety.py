"""v5.1 variety upgrade invariants: zero-repeat commentary, race formats, biomes, rosters, powers, smooth slow-mo."""
from __future__ import annotations

import os
import random
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


class TestZeroRepeat(unittest.TestCase):
    def test_skeleton_ignores_names_and_numbers(self) -> None:
        from src.recap.comedy import skeleton
        self.assertEqual(skeleton("Grumble with zero remorse! Bye, Pip!"), skeleton("Dash with zero remorse! Bye, Bonk!"))
        self.assertEqual(skeleton("Bonk leads on 12."), skeleton("Sly leads on 30."))
        self.assertNotEqual(skeleton("Bonk is out!"), skeleton("Down goes Bonk!"))

    def test_fresh_never_repeats_and_exhausts(self) -> None:
        from src.recap.comedy import Writer
        w = Writer.__new__(Writer)
        w.rng, w.used, w.said = random.Random(1), {}, set()
        opts = ("Alpha line.", "Bravo line.", "Charlie line.")
        got = [w._fresh("f", opts) for _ in range(4)]
        self.assertEqual(sorted(g for g in got if g), sorted(opts))
        self.assertIsNone(got[-1])

    def test_peek_does_not_claim(self) -> None:
        from src.recap.comedy import Line, Writer
        w = Writer.__new__(Writer)
        w.rng, w.used, w.said = random.Random(2), {}, set()
        a = w._peek("x", ("Alpha call.", "Bravo call."))
        b = w._peek("x", ("Alpha call.", "Bravo call."))
        self.assertEqual(a, b)
        self.assertTrue(w.claim(Line(a[0])))
        self.assertFalse(w.claim(Line(a[0])))
        self.assertNotEqual(w._peek("x", ("Alpha call.", "Bravo call."))[0], a[0])


class TestRaceFormats(unittest.TestCase):
    def _ri(self, race, lead=False, betray=0, winner="bonk"):
        elims = [{"hero": True, "by_hero": True, "actors": ["pip", "sly"]}] * betray
        return SimpleNamespace(race=race, lead_changed=lead, elims=elims, stats_before={}, winner=winner,
                               behind_dummy=[])

    def test_three_features_three_quicks_never_adjacent(self) -> None:
        from src.recap.run import race_formats
        races = [self._ri(i, lead=(i in (3, 6)), betray=(2 if i in (5, 8) else 0)) for i in range(1, 11)]
        f = race_formats(races)
        vals = [f[i] for i in range(1, 11)]
        self.assertEqual(vals.count("FEATURE"), 3)
        self.assertEqual(vals.count("QUICK"), 3)
        self.assertNotEqual(f[1], "QUICK")
        self.assertNotEqual(f[10], "QUICK")
        for a, b in zip(vals, vals[1:]):
            self.assertFalse(a == b == "QUICK")


class TestBiomes(unittest.TestCase):
    def test_consecutive_races_differ_and_deterministic(self) -> None:
        from src.rendering.biomes import BIOMES, biome_for
        for s in (1, 2, 3):
            seq = [biome_for(s, r) for r in range(1, 31)]
            self.assertTrue(all(b in BIOMES for b in seq))
            self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))
            self.assertEqual(seq, [biome_for(s, r) for r in range(1, 31)])

    def test_apply_grades_backdrop_only_once(self) -> None:
        import pygame
        from src.rendering import biomes
        pygame.init()
        r = SimpleNamespace(sky_bg=pygame.Surface((64, 64)), far_spires=pygame.Surface((64, 64), pygame.SRCALPHA),
                            mid_arches=pygame.Surface((64, 64), pygame.SRCALPHA), _void=None, castle=None)
        r.sky_bg.fill((120, 180, 255))
        self.assertEqual(biomes.apply(r, "night"), "night")
        c1 = r.sky_bg.get_at((10, 10))
        self.assertLess(c1[0] + c1[1] + c1[2], 120 + 180 + 255)
        biomes.apply(r, "lava")
        self.assertEqual(r.sky_bg.get_at((10, 10)), c1)


class TestRoster(unittest.TestCase):
    def test_season_rosters(self) -> None:
        from src.characters.roster import HEROES
        from src.state import league
        base = [h.key for h in HEROES]
        self.assertEqual(league.next_season_roster(1), base)
        s1 = league.fresh_season_state(1)
        self.assertNotIn("roster", s1)                       # Season 1 state unchanged
        self.assertEqual(sorted(s1["stats"]), sorted(base))
        s2 = league.next_season_roster(2, base)
        self.assertEqual(len(s2), 12)
        self.assertTrue({"zap", "goo"} <= set(s2))
        table = list(reversed(s2))                            # pretend zap/goo... finished top, bonk/pip bottom
        s3 = league.next_season_roster(3, s2, table)
        self.assertEqual(len(s3), 12)
        self.assertNotIn(table[-1], s3)
        self.assertNotIn(table[-2], s3)
        st2 = league.fresh_season_state(2, roster=s2)
        heroes, extras, _ = league.select_cast_for_race(st2, random.Random(1))
        self.assertEqual(len(heroes), 12)
        self.assertEqual(len(heroes) + len(extras), 14)

    def test_grumble_always_grumpy(self) -> None:
        from src.characters.personality import expression_for
        for e in ("happy", "neutral", "celebrating", "scared"):
            self.assertEqual(expression_for("grumble", e), "angry")
        self.assertEqual(expression_for("grumble", "dizzy"), "dizzy")
        self.assertEqual(expression_for("juggernaut", "scared"), "angry")


class TestPowers(unittest.TestCase):
    def test_every_hero_and_rookie_has_a_power(self) -> None:
        from src.characters.roster import ALL_HEROES
        from src.physics.powers import POWERS
        for h in ALL_HEROES:
            self.assertIn(h.key, POWERS)

    def test_powers_fire_in_a_real_sim(self) -> None:
        from src.characters.roster import HEROES, make_extras
        from src.games import recipe_generator
        from src.physics.engine import Sim
        fired = set()
        for seed in (101, 202):
            recipe, _ = recipe_generator.generate([], 1, seed, season_theme="royal_classic")
            tr = Sim(recipe, list(HEROES), make_extras(4, random.Random(seed)), seed).run()
            fired |= {e.actors[0] for e in tr.events if e.kind == "trait" and e.data.get("power")}
        self.assertGreaterEqual(len(fired), 2, fired)


class TestSmoothSlowMo(unittest.TestCase):
    def test_cam_and_props_interpolate_at_fractional_frames(self) -> None:
        import numpy as np
        from src.physics.camera import Cam
        from src.recap.clip_worker import _SmoothSeq
        cams = _SmoothSeq([Cam(0, 0, 1.0), Cam(10, 20, 2.0)], "cam")
        cams.tf = 0.25
        c = cams[0]
        self.assertAlmostEqual(c.x, 2.5)
        self.assertAlmostEqual(c.zoom, 1.25)
        cams.tf = None
        self.assertEqual(cams[1].x, 10)
        props = _SmoothSeq([np.array([[0, 0, 179.0]], np.float32), np.array([[10, 0, -179.0]], np.float32)], "props")
        props.tf = 0.5
        row = props[0] if round(0.5) == 0 else props[1]
        self.assertAlmostEqual(float(row[0, 0]), 5.0, places=3)
        self.assertGreater(abs(float(row[0, 2])), 178.0)     # shortest-arc blend across the +-180 deg seam

    def test_quick_format_has_no_replay(self) -> None:
        from src.recap.clip_worker import FORMATS
        self.assertFalse(FORMATS["QUICK"]["replay"])
        self.assertLessEqual(FORMATS["FEATURE"]["chaos"], 2)


if __name__ == "__main__":
    unittest.main()
