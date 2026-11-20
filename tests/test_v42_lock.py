"""v4.2 production-lock checks (unittest; never pytest locally)."""
from __future__ import annotations

import random
import unittest

from src.audio import mix, music
from src.narration import script, tts


class TestV42Lock(unittest.TestCase):
    def test_comedy_bank_size_bans_and_lengths(self) -> None:
        self.assertGreaterEqual(script.bank_size(), 80)
        for fam, lines in script.BANK.items():
            for ln in lines:
                low = f" {ln.lower()} "
                self.assertFalse(any(p in low for p in script.BANNED_PHRASES), f"{fam}: {ln}")
                self.assertLessEqual(len(ln.split()), 9, f"{fam}: {ln}")

    def test_family_dedup_and_cooldown(self) -> None:
        pk = script.Picker(random.Random(3), recent_ids={"drama:0", "drama:1"})
        first = pk.pick(["drama"], {"A": "Bonk", "B": "Pip"})
        self.assertIsNotNone(first)
        self.assertNotIn(first[1], {"drama:0", "drama:1"})
        self.assertIsNone(pk.pick(["drama"], {"A": "Bonk", "B": "Pip"}))   # family never reused in an episode

    def test_metadata_and_cliche_bans(self) -> None:
        b = script.Beat(3.0, "betrayal", 8, {"A": "Bonk", "B": "Pip"}, max_words=8)
        for bad in ("Heavy orange bowling ball Bonk wins!", "Down to three, who blinks first?",
                    "Zero room for error here!", "Pure chaos in the pack!"):
            self.assertFalse(script._valid_llm_line(b, bad), bad)

    def test_winner_line_lead_fact_lock(self) -> None:
        lead = script.Beat(20.0, "winner", 10, {"winner": "Floater", "leader": "Bonk"}, max_words=8)
        lead.family = "winner_lead_other"
        self.assertFalse(script._valid_llm_line(lead, "Floater wins! Bonk keeps his lead."))
        self.assertTrue(script._valid_llm_line(lead, "Floater wins! Bonk grabs the lead!"))
        plain = script.Beat(20.0, "winner", 10, {"winner": "Glitch", "leader": "Grumble"}, max_words=8)
        plain.family = "winner"
        self.assertFalse(script._valid_llm_line(plain, "Glitch wins and takes the lead!"))
        self.assertTrue(script._valid_llm_line(plain, "Glitch steals it, Grumble stays king."))

    def test_prosody_voice_and_card_hold(self) -> None:
        self.assertEqual(tts.PROSODY["hype"], ("+24%", "+7Hz"))
        self.assertEqual(tts.PROSODY["deadpan"], ("+11%", "-2Hz"))
        self.assertIn("acompressor=threshold=-16dB", tts.BOOTH_MIC_AF)
        self.assertFalse(hasattr(mix, "CARD_MAX_S"))
        self.assertAlmostEqual(mix.CARD_TAIL_S, 0.65)
        self.assertEqual(script.family_style("kill.bonk"), "hype")
        self.assertEqual(script.family_style("dummy"), "deadpan")

    def test_theme_bgm_tracks(self) -> None:
        self.assertGreaterEqual(len(set(music.THEME_TRACK.values())), 6)
        for tr in set(music.THEME_TRACK.values()):
            a = music.theme_bgm(3.0, tr, seed=1)
            self.assertEqual(a.size, int(3.0 * 44100))
            self.assertGreater(float(abs(a).max()), 0.5)       # normalised, audible, no NaNs


if __name__ == "__main__":
    unittest.main()
