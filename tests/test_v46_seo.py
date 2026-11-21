"""v4.6 viral SEO metadata + best-effort engagement tests (unittest only; never pytest locally)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import run_daily_episode as rde
from src.characters.roster import HERO_BY_KEY, HEROES
from src.narration.script import ARENA_NAMES
from src.publish import engage, instagram, metadata, youtube

ROOT = Path(__file__).resolve().parent.parent
STAGES = ("league", "play_in", "qualifier_1", "qualifier_2", "grand_final")


def _outcome(race: int = 1, stage: str = "league", winner: str = "glitch", season: int = 1) -> SimpleNamespace:
    return SimpleNamespace(season_number=season, race_number=race, stage=stage, winner_key=winner,
                           is_grand_final=stage == "grand_final")


def _meta(arena: str = "crusher_gauntlet", goal: str = "reach_finish", race: int = 1, stage: str = "league",
          winner: str = "glitch", cast=None, pre=None, cta: str = "") -> dict:
    return metadata.build_upload_metadata(arena, _outcome(race, stage, winner), cta, goal=goal,
                                          hazards=["falling_floor_tiles", "slippery_ice"], twist=None,
                                          cast_keys=cast, pre_standings=pre)


class TestV46ViralMetadata(unittest.TestCase):
    def test_titles_short_spoiler_free_keyworded_for_every_combo(self) -> None:
        for arena in ARENA_NAMES:
            for goal in metadata.TITLE_TEMPLATES:
                for stage in STAGES:
                    for race in (1, 2, 3, 4, 27, 30):
                        t = metadata.build_title(arena, goal, stage, 2, race)
                        self.assertLessEqual(len(t), metadata.TITLE_MAX, t)
                        self.assertNotIn("#shorts", t.lower())
                        self.assertNotIn("toontooncastle", t.lower())
                        self.assertRegex(t, r"(?i)ball|marble|crown|final|playoff", t)
                        for hero in HEROES:
                            self.assertNotIn(hero.name, t)

    def test_first_episode_copy(self) -> None:
        m = _meta()
        self.assertEqual(m["title"], "Only ONE Ball Can Win 😱 Crusher Gauntlet Marble Race")
        self.assertEqual(m["category_id"], "20")
        self.assertEqual(m["metadata_version"], "4.6")
        self.assertIn("Season 1 starts NOW", m["description"])

    def test_no_winner_spoiler_anywhere(self) -> None:
        for winner in HERO_BY_KEY:
            m = _meta(winner=winner)
            for field in ("title", "description", "ig_caption"):
                self.assertNotIn(HERO_BY_KEY[winner].name, m[field], f"{winner} spoiled in {field}")

    def test_hashtag_caps_and_ig_share_prompt(self) -> None:
        m = _meta()
        ig_tags = [w for w in m["ig_caption"].split() if w.startswith("#")]
        yt_tags = [w for w in m["description"].split() if w.startswith("#")]
        self.assertLessEqual(len(ig_tags), 5)
        self.assertTrue(3 <= len(yt_tags) <= 5, yt_tags)
        self.assertNotIn("#shorts", m["description"] + m["ig_caption"])
        first = m["ig_caption"].splitlines()[0]
        self.assertTrue(first.startswith("Marble race"))
        self.assertLessEqual(len(first), metadata.IG_HEADLINE_MAX)
        self.assertIn("Send this to", m["ig_caption"])
        self.assertIn("Comment it below", m["description"])
        self.assertNotIn("<", m["description"] + m["ig_caption"])
        self.assertIn("\n", m["description"])

    def test_tags_limits(self) -> None:
        for goal in metadata.TITLE_TEMPLATES:
            tags = _meta(goal=goal, arena="bouncy_pad_field", stage="grand_final")["tags"]
            self.assertLessEqual(len(tags), 15)
            self.assertTrue(all(0 < len(t) <= 30 and "," not in t for t in tags))
            self.assertLessEqual(sum(len(t) + 3 for t in tags), 500)
            self.assertIn("marble race", tags)

    def test_daily_title_rotation(self) -> None:
        titles = {metadata.build_title("crusher_gauntlet", "reach_finish", "league", 1, r) for r in range(1, 5)}
        self.assertEqual(len(titles), 4)

    def test_comments_list_cast_and_playoff_cta_is_not_spoiled(self) -> None:
        cta = "Dash or Floater tomorrow? Comment your picks!"
        league = _meta(cta=cta)
        for hero in HEROES:
            self.assertIn(hero.name, league["yt_comment"])
            self.assertIn(hero.name, league["ig_comment"])
        self.assertIn(cta, league["yt_comment"])
        q1 = _meta(stage="qualifier_1", race=28, cast=["bonk", "sly"], cta="Glitch or Pip tomorrow? Comment!")
        self.assertNotIn("Glitch or Pip", q1["yt_comment"])
        self.assertIn("Bonk and Sly", q1["description"])

    def test_pre_race_standings_line(self) -> None:
        m = _meta(race=2, pre=[("glitch", 10), ("bonk", 5)])
        self.assertIn("Before this race: Glitch leads Season 1 with 10 pts", m["description"])
        self.assertIn("Grand Final", _meta(stage="grand_final", race=30, cast=["bonk", "sly", "pip"])["description"])


class TestV46Clients(unittest.TestCase):
    def _fake_req(self) -> mock.Mock:
        req = mock.Mock()
        req.RequestException = Exception
        return req

    def test_youtube_update_metadata_keeps_newlines_and_category(self) -> None:
        req = self._fake_req()
        req.put.return_value = mock.Mock(status_code=200)
        with mock.patch.object(youtube, "access_token", return_value=("tok", 3600, "youtube.force-ssl")), \
                mock.patch.object(youtube, "_requests", return_value=req):
            self.assertTrue(youtube.update_video_metadata("21UG6Vz6Oz4", "T", "line1\n\nline2 <x>", ["a", "b,c"], "20"))
        body = req.put.call_args.kwargs["json"]
        self.assertEqual(req.put.call_args.kwargs["params"], {"part": "snippet"})
        self.assertEqual(body["id"], "21UG6Vz6Oz4")
        self.assertEqual(body["snippet"]["description"], "line1\n\nline2 x")
        self.assertEqual(body["snippet"]["categoryId"], "20")
        self.assertEqual(body["snippet"]["tags"], ["a", "b c"])
        with self.assertRaises(ValueError):
            youtube.update_video_metadata("../bad", "T", "D", [], "20")

    def test_youtube_post_comment_includes_channel_and_reports_reason(self) -> None:
        req = self._fake_req()
        req.get.return_value = mock.Mock(status_code=200, json=lambda: {"items": [{"id": "UC" + "a" * 22}]})
        req.post.return_value = mock.Mock(status_code=200, json=lambda: {"id": "Ugz123"})
        with mock.patch.object(youtube, "access_token", return_value=("tok", 3600, "youtube.force-ssl")), \
                mock.patch.object(youtube, "_requests", return_value=req):
            self.assertEqual(youtube.post_comment("21UG6Vz6Oz4", "Which ball?\nBonk"), "Ugz123")
            snippet = req.post.call_args.kwargs["json"]["snippet"]
            self.assertEqual(snippet["videoId"], "21UG6Vz6Oz4")
            self.assertEqual(snippet["channelId"], "UC" + "a" * 22)
            self.assertEqual(snippet["topLevelComment"]["snippet"]["textOriginal"], "Which ball?\nBonk")
            req.post.return_value = mock.Mock(
                status_code=403, json=lambda: {"error": {"errors": [{"reason": "insufficientPermissions"}]}})
            with self.assertRaisesRegex(RuntimeError, "insufficientPermissions"):
                youtube.post_comment("21UG6Vz6Oz4", "hi")

    def test_instagram_post_comment_request(self) -> None:
        req = self._fake_req()
        req.post.return_value = mock.Mock(status_code=200, json=lambda: {"id": "1789"})
        env = {"IG_USER_ID": "17841400000000000", "IG_ACCESS_TOKEN": "IGAAtesttoken"}
        with mock.patch.dict(os.environ, env), mock.patch.object(instagram, "_requests", return_value=req):
            self.assertEqual(instagram.post_comment("18181230226449454", "Which ball? 👇"), "1789")
        url = req.post.call_args.args[0]
        self.assertEqual(url, f"{instagram.IG_GRAPH}/18181230226449454/comments")
        self.assertEqual(req.post.call_args.kwargs["data"], {"message": "Which ball? 👇"})
        with self.assertRaises(instagram.InstagramError):
            instagram.post_comment("not-a-number", "x")


class TestV46Engagement(unittest.TestCase):
    def test_engagement_is_best_effort(self) -> None:
        def boom(*_a):
            raise RuntimeError("HTTP 403 insufficientPermissions")

        res = engage.post_launch_engagement("21UG6Vz6Oz4", "18181230226449454",
                                            {"yt_comment": "a", "ig_comment": "b"}, yt_comment_fn=boom,
                                            ig_comment_fn=lambda mid, txt: "c1")
        self.assertIn("insufficientPermissions", res["yt_comment_error"])
        self.assertEqual(res["ig_comment_id"], "c1")
        self.assertEqual(engage.post_launch_engagement(None, None, {}), {})

    def test_history_entry_metadata_matches_first_episode(self) -> None:
        entry = {"season": 1, "race": 1, "stage": "league", "arena": "crusher_gauntlet", "goal": "reach_finish",
                 "hazards": ["falling_floor_tiles", "slippery_ice"], "twist": None, "winner": "glitch"}
        self.assertEqual(engage.metadata_for_history_entry(entry), _meta())

    def test_supervisor_engagement_failure_never_fails_published_run(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ttc_v46_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        st_dir = tmp / "state"
        shutil.copytree(ROOT / "state", st_dir)
        out_mp4 = tmp / "output" / "episode.mp4"
        out_mp4.parent.mkdir(parents=True)
        worker = tmp / "worker.py"
        worker.write_text(
            "import json, pathlib, sys\n"
            "mp4, mf, st = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])\n"
            "mp4.write_bytes(b'MP4')\n"
            "nxt = json.loads((st / 'season_state.json').read_text())\n"
            "nxt['race_number'] = int(nxt['race_number']) + 1\n"
            "mp4.with_suffix('.json').write_text(json.dumps({\n"
            "    'upload_metadata': {'yt_comment': 'Which ball?', 'ig_comment': 'Which ball?'},\n"
            "    'pending_state': {'next_state': nxt, 'next_hof': {'seasons': []},\n"
            "                      'history_entry': {'day': 99, 'season': 1, 'race': 2, 'winner': 'bonk'}}}))\n"
            "mf.write_text(json.dumps({'stage': 'step_c_complete', 'yt_video_id': 'ytLive0001',\n"
            "                          'ig_media_id': '18000000000000001', 'both_published': True}))\n",
            encoding="utf-8",
        )
        calls: list[tuple] = []

        def failing_engage(yt_id, ig_id, meta):
            calls.append((yt_id, ig_id, meta.get("yt_comment")))
            raise RuntimeError("network down")

        race_before = json.loads((st_dir / "season_state.json").read_text())["race_number"]
        rc = rde.run_transactional_pipeline(
            force_run=True, commit_git=False, timeout_s=30.0, retry_wait_s=0.05, out_mp4=out_mp4, state_dir=st_dir,
            worker_cmd_builder=lambda att, seed, mp4, mf: [sys.executable, str(worker), str(mp4), str(mf), str(st_dir)],
            cleanup_ig_fn=lambda _t: True, delete_yt_fn=lambda _v: True, alert_fn=lambda _t, _b: True,
            engage_fn=failing_engage,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("ytLive0001", "18000000000000001", "Which ball?")])
        self.assertEqual(json.loads((st_dir / "season_state.json").read_text())["race_number"], race_before + 1)


if __name__ == "__main__":
    unittest.main()
