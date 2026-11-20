"""v4.3.1 micro-polish + production launch checks (unittest; NEVER pytest locally on the Mac)."""
from __future__ import annotations

import unittest

from src.narration import script
from src.publish import validate
from src.state import league


class TestV431(unittest.TestCase):
    def test_no_ko_language_on_stun_beats(self) -> None:
        b = script.Beat(6.0, "squash", 5, {"B": "Bonk", "_gp": 6.0}, max_words=8)
        b.family = "squash"
        self.assertFalse(script._valid_llm_line(b, "Bonk just self-destructed. What a muppet."))
        self.assertFalse(script._valid_llm_line(b, "Bonk's binned it, folks!"))
        self.assertTrue(script._valid_llm_line(b, "Bonk just got pancaked flat!"))
        ko = script.Beat(6.0, "hero_fall", 4, {"B": "Bonk", "_gp": 6.0}, max_words=8)
        ko.family = "host"
        self.assertTrue(script._valid_llm_line(ko, "Bonk has binned it completely!"))   # confirmed KO: allowed

    def test_bank_fallback_is_clean(self) -> None:
        b = script.Beat(6.0, "squash", 5, {"B": "Bonk"}, max_words=8)
        b.family = "squash"
        fb = script._bank_fallback(b)
        self.assertIsNotNone(fb)
        self.assertIn("Bonk", fb)
        self.assertIsNone(script._ELIM_WORDS.search(fb))

    def test_bracket_ctas(self) -> None:
        st = league.fresh_season_state(1)
        st["playoff"].update(seeds=["bonk", "pip", "sly"], wildcard_winner="dash")
        self.assertEqual(league.cta_heroes(st, "play_in"), ["bonk", "pip"])          # Ep27 -> Q1 #1 vs #2
        st["playoff"].update(q1_winner="bonk", q1_loser="pip")
        self.assertEqual(league.cta_heroes(st, "qualifier_1"), ["pip", "sly"])       # Ep28 -> Q2 loser vs #3
        st["playoff"].update(finalists=["bonk", "sly", "dash"])
        self.assertEqual(league.cta_heroes(st, "qualifier_2"), ["bonk", "sly", "dash"])
        self.assertEqual(league.cta_heroes(st, "league"), [])
        self.assertEqual(league.cta_heroes(st, "grand_final"), [])

    def test_three_finalist_outro_validation(self) -> None:
        b = script.Beat(25.0, "outro", 10, {"a": "Bonk", "b": "Sly", "c": "Dash"}, max_words=10)
        b.family = "outro_q2"
        self.assertTrue(script._valid_llm_line(b, "Bonk, Sly, or Dash for the crown tomorrow?"))
        self.assertFalse(script._valid_llm_line(b, "Bonk or Sly for the crown tomorrow?"))

    def test_ffprobe_gate_path_restriction(self) -> None:
        for bad in ("/etc/passwd", "../README.md", "output/../src/main.py", "output/nope.mp4"):
            with self.assertRaises(ValueError):
                validate._safe_path(bad)

    def test_fresh_state_is_season1_race1(self) -> None:
        st = league.fresh_season_state(1)
        self.assertEqual((st["season_number"], st["race_number"], st["total_day"]), (1, 1, 1))
        self.assertTrue(all(not any(v.values()) for v in st["stats"].values()))

    def test_bumper_ring_camera_zoom_never_collapses(self) -> None:
        import random
        from src.characters.roster import HEROES, make_extras
        from src.games import recipe_generator
        from src.physics.camera import top_base_zoom, track
        from src.physics.engine import Sim

        rng = random.Random(318)
        r, _ = recipe_generator.generate([], 1, 318, mode="TOP_DOWN", arena="bumper_ring",
                                         goal="collect_items", season_theme="frostbite_siege")
        tr = Sim(r, list(HEROES), make_extras(4, rng), 318013).run()
        cams = track(tr)
        bz = top_base_zoom(tr.meta)
        self.assertGreaterEqual(min(c.zoom for c in cams), bz * 0.98)
        self.assertLessEqual(max(c.zoom for c in cams), bz * 2.15)


if __name__ == "__main__":
    unittest.main()
