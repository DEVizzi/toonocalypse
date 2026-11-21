"""The Tuno Report (season recap) tests — pure Python (no ffmpeg / network): safe for `python -m unittest` locally
and `pytest` in CI. Never mutates the live `state/` directory."""
from __future__ import annotations

import copy
import json
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.characters.roster import HERO_BY_KEY  # noqa: E402
from src.recap import schedule  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _entries(season: int, races: range, published: bool = True) -> list[dict]:
    return [{"season": season, "race": r, "published": published, "winner": "bonk"} for r in races]


class ScheduleTest(unittest.TestCase):
    def test_thirds_lifecycle_one_per_run_never_duplicated(self) -> None:
        self.assertIsNone(schedule.pick_next_due_recap(_entries(1, range(1, 10)), {"recaps": {}}))
        due = schedule.pick_next_due_recap(_entries(1, range(1, 11)), {"recaps": {}})
        self.assertEqual(due["key"], "s1_part1")
        self.assertEqual((due["start_race"], due["end_race"]), (1, 10))
        done = {"recaps": {"s1_part1": {}}}
        self.assertIsNone(schedule.pick_next_due_recap(_entries(1, range(1, 20)), done))
        due = schedule.pick_next_due_recap(_entries(1, range(1, 21)), done)
        self.assertEqual((due["key"], due["start_race"], due["end_race"]), ("s1_part2", 11, 20))
        done["recaps"]["s1_part2"] = {}
        ents = _entries(1, range(1, 31)) + _entries(2, range(1, 4))
        due = schedule.pick_next_due_recap(ents, done)
        self.assertEqual((due["key"], due["start_race"], due["end_race"]), ("s1_part3", 21, 30))
        done["recaps"]["s1_part3"] = {}
        self.assertIsNone(schedule.pick_next_due_recap(ents, done))
        ents = _entries(1, range(1, 31)) + _entries(2, range(1, 11))
        self.assertEqual(schedule.pick_next_due_recap(ents, done)["key"], "s2_part1")

    def test_unpublished_races_never_trigger_a_recap(self) -> None:
        ents = _entries(1, range(1, 10)) + _entries(1, range(10, 11), published=False)
        self.assertIsNone(schedule.pick_next_due_recap(ents, {"recaps": {}}))

    def test_recap_key_validation(self) -> None:
        self.assertEqual(schedule.recap_key(3, "part2"), "s3_part2")
        with self.assertRaises(ValueError):
            schedule.recap_key(1, "part9")


class RecapPipelineTest(unittest.TestCase):
    """Builds a small demo season with the real pipeline steps in a temp dir (3 races, ~10 s)."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.recap import run

        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = Path(cls.tmp.name) / "state"
        cls.state.mkdir()
        run.build_demo_state(3, cls.state, log=lambda *_: None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_rebuilt_table_matches_live_state_and_detects_tampering(self) -> None:
        from src.recap import data

        recap = data.build_recap(1, "preview", state_dir=self.state)
        self.assertTrue(recap.verified, recap.verify_note)
        self.assertEqual([r.race for r in recap.part_races], [1, 2, 3])
        live = json.loads((self.state / "season_state.json").read_text())
        for k, v in live["stats"].items():
            self.assertEqual(recap.final_stats[k], {s: int(v[s]) for s in data.STAT_KEYS})
        for r in recap.races:
            self.assertEqual(r.hero_ranking[0], r.winner)
            self.assertIn(r.winner, HERO_BY_KEY)
        live["stats"]["bonk"]["points"] += 1
        tampered = Path(self.tmp.name) / "tampered"
        tampered.mkdir()
        for f in self.state.iterdir():
            (tampered / f.name).write_text(f.read_text())
        (tampered / "season_state.json").write_text(json.dumps(live))
        with self.assertRaises(data.RecapDataError):
            data.build_recap(1, "preview", state_dir=tampered, strict=True)

    def test_mini_trace_reproduces_league_engine_exactly(self) -> None:
        from src import main as ep_main
        from src.games import recipe_generator
        from src.recap import data
        from src.recap.record import build_record
        from src.state import league

        st = league.fresh_season_state(1, None, 1)
        recipe, _ = recipe_generator.generate([], 1, 4242, season_theme="royal_classic")
        heroes, extras, _ = league.select_cast_for_race(copy.deepcopy(st), random.Random(4242))
        trace, _, _ = ep_main.simulate_best(recipe, heroes, extras, 4242, history={}, log=lambda *_: None)
        rec = build_record(4242, recipe, heroes, extras, trace, code_sha="0123456789abcdef0123456789abcdef01234567")
        json.dumps(rec)                                            # JSON-only (no pickles)
        self.assertEqual(rec["code_sha"][:7], "0123456")
        self.assertEqual(len(rec["extras"]), len(extras))
        _, real, _ = league.evaluate_and_advance(st, trace, mutate=True)
        _, mini, _ = league.evaluate_and_advance(st, data.mini_trace(json.loads(json.dumps(rec))), mutate=True)
        self.assertEqual(real["stats"], mini["stats"])

    def test_comedy_lines_are_factual_short_and_varied(self) -> None:
        from src.recap import data
        from src.recap.comedy import Writer

        recap = data.build_recap(1, "preview", state_dir=self.state)
        w = Writer(recap)
        names = {h.name for h in HERO_BY_KEY.values()}
        lines = [w.title(), w.roster(), w.standings(), w.teaser(), w.outro()]
        prev = None
        for r in recap.part_races:
            rl = w.race_lines(r, prev, has_footage=False)
            lines += [rl.intro, rl.lost] + rl.verdict
            self.assertIn(HERO_BY_KEY[r.winner].name, rl.verdict[0].text)
            prev = r
        lines += [a.line for a in w.awards()]
        for ln in lines:
            self.assertLessEqual(len(ln.text.split()), 26, ln.text)
            self.assertNotIn("{", ln.text)
            for word in ln.text.replace("'s", " ").replace(".", " ").replace(",", " ").replace("!", " ").split():
                if word in {"Glitch", "Bonk", "Pip", "Boing", "Sly", "Grumble", "Dash", "Magneto", "Floater",
                            "Juggernaut"}:
                    self.assertIn(word, names)
        self.assertTrue(w.awards(), "every part has at least one Tuno award")

    def test_video_plan_frames_and_metadata_without_ffmpeg(self) -> None:
        from src.recap import data, run
        from src.recap.video import Ctx, RecapVideo, render_thumbnail

        recap = data.build_recap(1, "preview", state_dir=self.state)
        out = Path(self.tmp.name) / "out"
        out.mkdir()
        v = RecapVideo(recap, {}, None, out, use_tts=False, log=lambda *_: None)
        segs = v.plan()
        names = [s.name for s in segs]
        self.assertEqual(names[0], "title")
        self.assertEqual(names[-1], "end")
        self.assertTrue(any(n.startswith("race_") for n in names))
        self.assertGreater(sum(s.duration for s in segs), 60.0)
        for s in segs:
            if s.name.startswith(("race_", "award_", "chart", "standings")):
                ln = s.voice[0][1] if s.voice else None
                v.frame.blit(v.bg, (0, 0))
                s.draw(v.frame, s.duration * 0.8, Ctx(0, 0.05, ln, 0.3))
                self.assertEqual(v.frame.get_size(), (1920, 1080))
        thumb = render_thumbnail(recap, v.awards, out / "t.jpg")
        self.assertTrue(thumb.is_file())
        meta = run.build_metadata(recap, {"chapters": [(0.0, "Intro"), (12.0, "Race 1: X"), (30.0, "End")]}, v.awards)
        self.assertLessEqual(len(meta["title"]), 100)
        self.assertIn("0:00 Intro", meta["description"])
        self.assertNotIn("<", meta["description"])


class BackfillTest(unittest.TestCase):
    def test_race1_supervisor_seed_found_by_layout_fingerprint(self) -> None:
        from src.recap import backfill

        hist = json.loads((ROOT / "state" / "episode_history.json").read_text())["entries"]
        r1 = next((e for e in hist if e.get("season") == 1 and e.get("race") == 1), None)
        if not r1 or r1.get("fingerprint") != "99fbce337dc34bc48c463a9e50a440a1245fcfe7a17eeb1d9957d1b6e5a5b06d":
            self.skipTest("live S1 R1 entry not present")
        self.assertEqual(backfill.search_seed(1, 1, lo=22950, hi=22970), [22959])


if __name__ == "__main__":
    unittest.main()
