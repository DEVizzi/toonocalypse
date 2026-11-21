"""v4.0 verification suite (unittest + CI compatible):
- 180-episode (6-season / 6+ month) autonomous IPL Season League state machine, Playoffs, Golden Dummies & Day-31 rollover.
- All 8 procedural SeasonThemes & seasonal rotation `(season_number - 1) % 8`.
- Zero `_time_fit` resampling in `src/audio/mix.py` (100% native pitch).
- Natural Broadcast Voice validator (bans 'I see', 'I am', stiff double-adjective phrasing, wrong contestant counts).
- TOP_DOWN `(0, 0)` camera center lock on `rotating_disc` and `sumo_pool_pit` + all 7 showcase arenas build & run cleanly."""
from __future__ import annotations

import random
import unittest

from src.audio import mix
from src.characters.roster import HEROES, make_extras
from src.games import recipe_generator
from src.games.base import SHOWCASE_ARENAS
from src.games.themes import SEASON_THEMES, for_season
from src.narration import script
from src.physics.camera import track
from src.physics.engine import Sim
from src.physics.trace import Event, Trace
from src.state import league


class TestV40LeagueAndOverhaul(unittest.TestCase):
    def test_eight_seasonal_themes_rotation(self) -> None:
        self.assertEqual(len(SEASON_THEMES), 8)
        keys = [for_season(s).key for s in range(1, 10)]
        self.assertEqual(keys[:8], [t.key for t in SEASON_THEMES])
        self.assertEqual(keys[8], SEASON_THEMES[0].key)  # Season 9 wraps cleanly to S1

    def test_180_episodes_six_seasons_autonomous_rollover(self) -> None:
        st = league.fresh_season_state(1, None, 1)
        hof = {"seasons": []}
        rng = random.Random(400)

        for ep_idx in range(180):
            s_before = st["season_number"]
            r_before = st["race_number"]
            heroes, extras, is_final = league.select_cast_for_race(st, rng)
            stage = league.stage_for_race(r_before)

            if stage == "league":
                self.assertEqual((len(heroes), len(extras), is_final), (10, 4, False))
            elif stage == "play_in":
                self.assertEqual((len(heroes), len(extras), is_final), (7, 4, False))
            elif stage == "qualifier_1":
                self.assertEqual((len(heroes), len(extras), is_final), (2, 6, False))
            elif stage == "qualifier_2":
                self.assertEqual((len(heroes), len(extras), is_final), (3, 6, False))
            elif stage == "grand_final":
                self.assertEqual((len(heroes), len(extras), is_final), (3, 6, True))
                self.assertTrue(all(ex.golden for ex in extras))

            # Construct synthetic trace outcome from real cast keys
            order = [h.key for h in heroes]
            rng.shuffle(order)
            winner = order[0]
            tr = Trace(30, "SIDE_VIEW", order + [f"extra{i+1}" for i in range(len(extras))])
            tr.meta["heroes"] = [h.key for h in heroes]
            tr.meta["ranking"] = order
            tr.meta["winner"] = winner
            if len(order) >= 2:
                tr.events.append(Event(4.0, "elimination", [order[-1], order[0]], {"hero": True, "by_hero": True}))

            outcome, st, hof = league.evaluate_and_advance(st, tr, hall_of_fame=hof, mutate=True)
            self.assertEqual(outcome.season_number, s_before)
            self.assertEqual(outcome.race_number, r_before)
            if r_before == 30:
                self.assertEqual(st["season_number"], s_before + 1)
                self.assertEqual(st["race_number"], 1)
                self.assertEqual(st["reigning_champion"], winner)
                self.assertTrue(all(v["points"] == 0 for v in st["stats"].values()))

        self.assertEqual(len(hof["seasons"]), 6)
        self.assertEqual(st["season_number"], 7)
        self.assertEqual(st["race_number"], 1)
        self.assertEqual(st["theme"], "desert_mirage")

    def test_no_time_fit_resampling_and_voice_rules(self) -> None:
        self.assertFalse(hasattr(mix, "_time_fit"), "_time_fit must be completely deleted in v4.0")

        b_intro = script.Beat(0.04, "intro", 10, {"arena": "Rotating Disc", "count": 14, "count_word": "Fourteen"}, max_words=7)
        self.assertFalse(script._valid_llm_line(b_intro, "Fifteen balls drop into Rotating Disc!"))
        self.assertTrue(script._valid_llm_line(b_intro, "Fourteen drop into Rotating Disc!"))

        b_bet = script.Beat(4.0, "betrayal", 8, {"killer": "Juggernaut", "victim": "Pip"}, max_words=7)
        self.assertFalse(script._valid_llm_line(b_bet, "I see Juggernaut hitting Pip!"))
        self.assertFalse(script._valid_llm_line(b_bet, "I am watching Juggernaut wreck Pip!"))
        self.assertFalse(script._valid_llm_line(b_bet, "Massive Juggernaut flattens tiny Pip!"))
        self.assertTrue(script._valid_llm_line(b_bet, "Juggernaut just deleted Pip!"))

        b_win = script.Beat(18.0, "winner", 10, {"winner": "Magneto"}, max_words=8)
        self.assertFalse(script._valid_llm_line(b_win, "Double wipeout! Magneto steals it!"))   # v4.2 banned
        self.assertTrue(script._valid_llm_line(b_win, "Last-second carnage—Magneto walks away!"))

    def test_top_down_camera_locked_at_origin_and_all_7_arenas_run(self) -> None:
        for arena in SHOWCASE_ARENAS:
            goal = "last_one_standing" if arena in ("rotating_disc", "sumo_pool_pit") else "reach_finish"
            rec, _ = recipe_generator.generate([], 1, 88, arena=arena, goal=goal, season_theme="royal_classic")
            tr = Sim(rec, list(HEROES), make_extras(4, random.Random(88)), 88).run()
            cams = track(tr)
            self.assertGreater(len(cams), 60)
            if arena in ("rotating_disc", "sumo_pool_pit"):
                f3_started = False
                for fi, c in enumerate(cams):
                    alive_n = sum(1 for k in range(len(tr.keys)) if tr.flags[fi][k] & 1)
                    if alive_n <= 3:
                        f3_started = True
                    if not f3_started:
                        self.assertEqual((c.x, c.y), (0.0, 0.0), f"{arena} camera drifted off (0,0): {(c.x, c.y)}")
                    else:
                        self.assertLessEqual(abs(c.x), 145.0)
                        self.assertLessEqual(abs(c.y), 145.0)


if __name__ == "__main__":
    unittest.main()
