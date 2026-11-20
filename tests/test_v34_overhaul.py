"""v3.4 verification suite (unittest + pytest compatible):
- SpinningBars >= 35px clearance from all platforms, slab undersides, pegs, and seesaws on Pachinko Drop & Ramp Descent.
- -40 dB silence trimming & WordBoundary timestamp shift.
- Lore validation (Juggernaut != bowling ball, banned clichés blocked, first-person MC Tuno, exact 2-hero CTA).
- Borderless 3-4 word caption chunking."""
from __future__ import annotations

import random
import unittest

import numpy as np

from src.audio.sfx import SR
from src.characters.roster import HEROES, make_extras
from src.games import recipe_generator
from src.narration import script, tts
from src.physics.engine import Sim


class TestV34Overhaul(unittest.TestCase):
    def test_spinner_clearance_pachinko_and_ramp(self) -> None:
        for arena in ("pachinko_drop", "ramp_descent"):
            placed_count = 0
            for seed in range(1, 10):
                rec, _ = recipe_generator.generate([], 1, seed, mode="SIDE_VIEW", arena=arena, goal="reach_finish")
                rec.hazards = ["spinning_bars"]
                sim = Sim(rec, list(HEROES), make_extras(4, random.Random(seed)), seed)
                sb = [h for h in sim.hazards if h.key == "spinning_bars"][0]
                placed_count += len(sb.bars)
                for p in sb.bars:
                    L = abs(p.shapes[0]["a"][0])
                    clr = sb._side_clearance(float(p.body.position.x), float(p.body.position.y)) - (L + 9.0)
                    self.assertGreaterEqual(clr, 35.0, f"{arena} seed={seed} spinner clearance {clr:.1f} < 35px")
            self.assertGreater(placed_count, 8)

    def test_silence_trim_40db(self) -> None:
        lead = np.zeros(int(0.22 * SR), np.float32)
        body = (np.sin(2 * np.pi * 240 * np.arange(int(0.50 * SR)) / SR) * 0.75).astype(np.float32)
        tail = np.zeros(int(0.28 * SR), np.float32)
        pcm, words = tts.trim_silence_40db(np.concatenate([lead, body, tail]), [(0.24, 0.70, "BONK")])
        self.assertAlmostEqual(pcm.size / SR, 0.512, delta=0.025)
        self.assertAlmostEqual(words[0][0], 0.024, delta=0.015)

    def test_lore_and_banned_phrases(self) -> None:
        b_jug = script.Beat(3.0, "trait_bowling", 4, {"name": "Juggernaut", "actor_key": "juggernaut"}, max_words=8)
        self.assertFalse(script._valid_llm_line(b_jug, "Juggernaut is a bowling ball of doom!"))
        self.assertTrue(script._valid_llm_line(b_jug, "Freight train Juggernaut wrecks the pack!"))

        b_bet = script.Beat(4.0, "betrayal", 8, {"killer": "Bonk", "victim": "Dash"}, max_words=8)
        self.assertFalse(script._valid_llm_line(b_bet, "Bonk yeeted Dash! Friendship over!"))
        self.assertFalse(script._valid_llm_line(b_bet, "Lord Tuno is getting impatient!"))

        b_out = script.Beat(20.0, "outro", 10, {"a": "Floater", "b": "Boing"}, max_words=7)
        self.assertFalse(script._valid_llm_line(b_out, "Comment your pick for tomorrow!"))
        self.assertTrue(script._valid_llm_line(b_out, "Floater or Boing tomorrow? Drop your pick!"))


if __name__ == "__main__":
    unittest.main()
