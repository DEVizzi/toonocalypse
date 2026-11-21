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

    def test_upload_refuses_wrong_channel(self) -> None:
        from src.publish import oauth

        with mock.patch.object(oauth, "channel_identity", return_value=("UCother000000000000000000", "Other")), \
                mock.patch.dict(os.environ, {"YOUTUBE_EXPECTED_CHANNEL_ID": "UCDFPguMeI582rA374rLa7ow"}):
            with self.assertRaisesRegex(oauth.OAuthError, "expected UCDFPguMeI582rA374rLa7ow"):
                oauth.assert_expected_channel("tok")
            tmp = Path(tempfile.mkdtemp(prefix="ttc_v46_up_"))
            self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
            mp4 = tmp / "e.mp4"
            mp4.write_bytes(b"x" * 10)
            req = self._fake_req()
            with mock.patch.object(youtube, "access_token", return_value=("tok", 3600, "s")), \
                    mock.patch.object(youtube, "_requests", return_value=req):
                with self.assertRaises(oauth.OAuthError):
                    youtube.upload_short(mp4, "T", "D", [], "public", "20")
            req.post.assert_not_called()
        with mock.patch.object(oauth, "channel_identity", return_value=("UCDFPguMeI582rA374rLa7ow", "ToonToonCastle")), \
                mock.patch.dict(os.environ, {"YOUTUBE_EXPECTED_CHANNEL_ID": "UCDFPguMeI582rA374rLa7ow"}):
            self.assertEqual(oauth.assert_expected_channel("tok"), "UCDFPguMeI582rA374rLa7ow")

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

    def test_retrofit_comment_on_youtube_skips_instagram(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ttc_v46_eng_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "episode_history.json").write_text(json.dumps({"entries": [{
            "season": 1, "race": 1, "stage": "league", "arena": "crusher_gauntlet", "goal": "reach_finish",
            "hazards": [], "published": True, "youtube_id": "21UG6Vz6Oz4", "instagram_id": "18181230226449454"}]}))
        with mock.patch.object(youtube, "post_comment", return_value="Ugz1") as yt_c, \
                mock.patch.object(instagram, "post_comment", return_value="c1") as ig_c:
            rc = engage.main(["--comments", "--comment-on", "youtube", "--state-dir", str(tmp)])
        self.assertEqual(rc, 0)
        yt_c.assert_called_once()
        ig_c.assert_not_called()


class TestV46YouTubeReauthHelper(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("youtube_reauth", ROOT / "scripts" / "youtube_reauth.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_auth_url_requests_force_ssl_with_pkce_on_loopback(self) -> None:
        from urllib.parse import parse_qs, urlparse

        verifier, challenge = self.mod.pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        q = parse_qs(urlparse(self.mod.build_auth_url("x.apps.googleusercontent.com", "http://127.0.0.1:5555/",
                                                      "st8", challenge)).query)
        self.assertIn("https://www.googleapis.com/auth/youtube.force-ssl", q["scope"][0].split())
        self.assertIn("https://www.googleapis.com/auth/youtube.upload", q["scope"][0].split())
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:5555/"])

    def test_callback_state_and_errors(self) -> None:
        self.assertEqual(self.mod.parse_callback("/?state=abc&code=4%2Fxyz", "abc"), "4/xyz")
        for bad in ("/?state=evil&code=1", "/?code=1", "/?state=abc&error=access_denied", "/?state=abc",
                    "/?state=%C3%A9&code=1"):
            with self.assertRaises(ValueError):
                self.mod.parse_callback(bad, "abc")

    def test_client_json_validation(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ttc_v46_cs_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        good, bad = tmp / "good.json", tmp / "bad.json"
        good.write_text(json.dumps({"installed": {"client_id": "1-a.apps.googleusercontent.com", "client_secret": "s"}}))
        bad.write_text(json.dumps({"installed": {"client_id": "nope", "client_secret": ""}}))
        self.assertEqual(self.mod.load_client(good), ("1-a.apps.googleusercontent.com", "s", []))
        with self.assertRaises(ValueError):
            self.mod.load_client(bad)
        web = tmp / "web.json"
        web.write_text(json.dumps({"web": {"client_id": "2-b.apps.googleusercontent.com", "client_secret": "w",
                                           "redirect_uris": ["https://developers.google.com/oauthplayground",
                                                             "http://localhost:8080/"]}}))
        cid, _sec, redirects = self.mod.load_client(web)
        self.assertEqual(cid, "2-b.apps.googleusercontent.com")
        self.assertEqual(self.mod.pick_redirect(redirects), ("http://localhost:8080/", 8080))
        self.assertIsNone(self.mod.pick_redirect(["https://example.com/cb", "http://evil.example:8080/"]))


if __name__ == "__main__":
    unittest.main()
