"""v4.3 final production-lock checks (unittest; NEVER pytest locally on the Mac)."""
from __future__ import annotations

import random
import unittest

from src.narration import script
from src.physics.camera import duel_zoom
from src.state import league


class TestV43Lock(unittest.TestCase):
    def test_standings_assertion(self) -> None:
        league.assert_standings_sorted([98, 95, 85, 63])
        with self.assertRaises(AssertionError):
            league.assert_standings_sorted([90, 95, 85])

    def test_copy_guards(self) -> None:
        b = script.Beat(1.0, "intro", 10, {"L": "Pip", "R": "Sly", "count": 14}, max_words=8)
        b.family = "intro"
        self.assertFalse(script._valid_llm_line(b, "Pip leads league twelve, Sly's hungry!"))
        self.assertTrue(script._valid_llm_line(b, "Pip leads race twelve, Sly's hungry!"))
        o = script.Beat(20.0, "outro", 10, {"a": "Boing", "b": "Floater"}, max_words=9)
        o.family = "outro"
        self.assertFalse(script._valid_llm_line(o, "Boing or Floater for next season? Comment!"))
        self.assertTrue(script._valid_llm_line(o, "Boing or Floater next race? Comment!"))

    def test_grand_final_intro_names_all_three(self) -> None:
        b = script.Beat(0.04, "intro", 10, {"a": "Magneto", "b": "Pip", "c": "Bonk", "count": 9}, max_words=10)
        b.family = "intro_final"
        self.assertFalse(script._valid_llm_line(b, "Grand Final! Magneto and Bonk, prepare yourselves!"))
        self.assertTrue(script._valid_llm_line(b, "Grand Final! Magneto, Pip, Bonk—only one wears the crown!"))

    def test_grand_final_outro_winner_only_no_cta(self) -> None:
        b = script.Beat(25.0, "outro_final", 10, {"winner": "Bonk", "season": 7, "next_season": 8}, max_words=12)
        b.family = "outro_final"
        self.assertFalse(script._valid_llm_line(b, "Pip or Magneto? Tell me in comments."))
        self.assertFalse(script._valid_llm_line(b, "Bonk wins it all! Comment your pick below!"))
        self.assertTrue(script._valid_llm_line(b, "Bow to your Season 7 king—Bonk owns the castle!"))
        for tpl in script.BANK["outro_final"]:
            txt = tpl.format(winner="Bonk", season=7, next_season=8)
            self.assertTrue(script._valid_llm_line(b, txt), txt)
            self.assertTrue(8 <= len(txt.split()) <= 12, txt)

    def test_grand_final_winner_line_is_champion_only(self) -> None:
        b = script.Beat(24.0, "winner", 10, {"winner": "Pip", "leader": "Magneto", "season": 7}, max_words=8)
        b.family = "winner_champion"
        self.assertFalse(script._valid_llm_line(b, "Pip steals the win, Magneto keeps the lead."))
        self.assertTrue(script._valid_llm_line(b, "Pip is your Season 7 Champion!"))

    def test_cliche_cooldown(self) -> None:
        self.assertEqual(script.cliches_in(["This is getting properly spicy!"]), ["properly_spicy"])
        self.assertIn("hunting_blood", script.cliches_in(["Bonk's hunting Magneto for blood!"]))
        b = script.Beat(5.0, "filler", 3, {}, max_words=8)
        self.assertFalse(script._valid_llm_line(b, "Big ball incoming, total carnage!", blocked_cliches={"total_carnage"}))
        pk = script.Picker(random.Random(1), recent_cliches={"properly_spicy"})
        for _ in range(20):
            got = pk.pick(["filler"], {}, 9)
            if got is None:
                break
            self.assertNotIn("properly spicy", got[2].lower())
            pk.used_families.discard("filler")

    def test_duel_zoom_bands(self) -> None:
        z, edge = duel_zoom(100.0)
        self.assertTrue(1.12 <= z <= 1.30 and not edge)
        z, edge = duel_zoom(900.0)
        self.assertTrue(0.76 <= z <= 1.12 and not edge)
        z, edge = duel_zoom(1099.0)
        self.assertGreaterEqual(z, 0.76)
        z, edge = duel_zoom(1800.0)
        self.assertTrue(z >= 0.86 and edge)


if __name__ == "__main__":
    unittest.main()
