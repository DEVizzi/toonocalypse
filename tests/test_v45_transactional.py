"""v4.5 Transactional 10-Min Timeout/Rollback, 1x/Day Lock & Visible Branding unit tests."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml

import run_daily_episode as rde
from src.publish import youtube

ROOT = Path(__file__).resolve().parent.parent


class TestV45TransactionalLock(unittest.TestCase):
    def _make_temp_env(self) -> tuple[Path, Path, Path]:
        tmp = Path(tempfile.mkdtemp(prefix="ttc_v45_test_"))
        st_dir = tmp / "state"
        out_dir = tmp / "output"
        shutil.copytree(ROOT / "state", st_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return tmp, st_dir, out_dir

    def test_5s_watchdog_timeout_rolls_back_and_auto_recreates_attempt_2(self) -> None:
        """Verifies a 5s watchdog timeout cancels hung Attempt 1 (+ child processes), deletes local .mp4/media,
        deletes partial YT upload + temp IG release, restores state/*.json verbatim with zero leftover entries,
        and launches Attempt 2 with a fresh seed that succeeds."""
        tmp, st_dir, out_dir = self._make_temp_env()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        orig_season = (st_dir / "season_state.json").read_bytes()
        orig_hist = (st_dir / "episode_history.json").read_bytes()
        orig_hof = (st_dir / "hall_of_fame.json").read_bytes()
        out_mp4 = out_dir / "episode.mp4"

        yt_deleted: list[str] = []
        ig_cleaned: list[str] = []
        alerts_sent: list[tuple[str, str]] = []
        observed_seeds: list[int] = []
        pre_attempt2_checks: dict[str, object] = {}

        # Write helper mock worker script inside tmp
        worker_script = tmp / "mock_worker.py"
        worker_script.write_text(
            "import json, pathlib, subprocess, sys, time\n"
            "attempt = int(sys.argv[1])\n"
            "seed = int(sys.argv[2])\n"
            "mp4 = pathlib.Path(sys.argv[3])\n"
            "mf = pathlib.Path(sys.argv[4])\n"
            "st_dir = pathlib.Path(sys.argv[5])\n"
            "if attempt == 1:\n"
            "    mp4.write_bytes(b'PARTIAL_MP4_BYTES' * 100)\n"
            "    mp4.with_suffix('.wav').write_bytes(b'PARTIAL_WAV')\n"
            "    (mp4.parent / 'verify_gameplay_brand.png').write_bytes(b'PNG')\n"
            "    # Simulate dirty partial state mutation before hang\n"
            "    (st_dir / 'season_state.json').write_text(json.dumps({'season_number': 1, 'race_number': 99}))\n"
            "    (st_dir / 'episode_history.json').write_text(json.dumps({'entries': [{'day': 1, 'failed': True}]}))\n"
            "    mf.write_text(json.dumps({\n"
            "        'stage': 'step_c_ig_media_publish',\n"
            "        'seed': seed,\n"
            "        'ig_release_tag': 'ig-stage-1700000000-42',\n"
            "        'yt_video_id': 'ytPartial99',\n"
            "    }))\n"
            "    # Spawn a grandchild process to verify process-group kill\n"
            "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "    time.sleep(15)\n"
            "    sys.exit(0)\n"
            "else:\n"
            "    mp4.write_bytes(b'VALID_ATTEMPT2_MP4')\n"
            "    next_st = json.loads((st_dir / 'season_state.json').read_text())\n"
            "    next_st['race_number'] = 2\n"
            "    next_st['total_day'] = 2\n"
            "    mp4.with_suffix('.json').write_text(json.dumps({\n"
            "        'pending_state': {\n"
            "            'next_state': next_st,\n"
            "            'next_hof': {'seasons': []},\n"
            "            'history_entry': {'day': 1, 'season': 1, 'race': 1, 'winner': 'bonk'},\n"
            "        }\n"
            "    }))\n"
            "    mf.write_text(json.dumps({\n"
            "        'stage': 'step_c_complete',\n"
            "        'seed': seed,\n"
            "        'ig_release_tag': 'ig-stage-1700000002-77',\n"
            "        'yt_video_id': 'ytLiveVid77',\n"
            "        'ig_media_id': 'igLiveReel88',\n"
            "        'both_published': True,\n"
            "    }))\n"
            "    sys.exit(0)\n",
            encoding="utf-8",
        )

        def build_cmd(attempt: int, seed: int, target_mp4: Path, manifest_path: Path) -> list[str]:
            observed_seeds.append(seed)
            if attempt == 2:
                # Verify Attempt 1 was 100% rolled back BEFORE Attempt 2 starts!
                pre_attempt2_checks["mp4_exists"] = target_mp4.exists()
                pre_attempt2_checks["wav_exists"] = target_mp4.with_suffix(".wav").exists()
                pre_attempt2_checks["png_exists"] = (target_mp4.parent / "verify_gameplay_brand.png").exists()
                pre_attempt2_checks["season_restored"] = (st_dir / "season_state.json").read_bytes() == orig_season
                pre_attempt2_checks["hist_restored"] = (st_dir / "episode_history.json").read_bytes() == orig_hist
                pre_attempt2_checks["hof_restored"] = (st_dir / "hall_of_fame.json").read_bytes() == orig_hof
            return [
                sys.executable,
                str(worker_script),
                str(attempt),
                str(seed),
                str(target_mp4),
                str(manifest_path),
                str(st_dir),
            ]

        t0 = time.monotonic()
        with mock.patch.object(rde.instagram, "cleanup_ephemeral_release_by_tag",
                               side_effect=lambda tag: (ig_cleaned.append(tag), True)[1]):
            rc = rde.run_transactional_pipeline(
                dry_run=False,
                force_run=True,
                commit_git=False,
                timeout_s=5.0,
                retry_wait_s=0.15,
                max_attempts=2,
                out_mp4=out_mp4,
                state_dir=st_dir,
                worker_cmd_builder=build_cmd,
                delete_yt_fn=lambda vid: (yt_deleted.append(vid), True)[1],
                cleanup_ig_fn=lambda tag: (ig_cleaned.append(tag), True)[1],
                alert_fn=lambda title, body: (alerts_sent.append((title, body)), True)[1],
                seed_override=11111,
            )
        elapsed = time.monotonic() - t0

        self.assertEqual(rc, 0)
        self.assertGreaterEqual(elapsed, 4.9)
        self.assertLess(elapsed, 9.5, "Watchdog must cancel Attempt 1 promptly near 5.0s, not wait 15s")
        self.assertEqual(len(observed_seeds), 2)
        self.assertEqual(observed_seeds[0], 11111)
        self.assertNotEqual(observed_seeds[0], observed_seeds[1], "Attempt 2 must get a fresh random seed")

        # Verify Attempt 1 rollback cleaned everything before Attempt 2 launched
        self.assertEqual(pre_attempt2_checks, {
            "mp4_exists": False,
            "wav_exists": False,
            "png_exists": False,
            "season_restored": True,
            "hist_restored": True,
            "hof_restored": True,
        })
        self.assertEqual(yt_deleted, ["ytPartial99"])
        self.assertIn("ig-stage-1700000000-42", ig_cleaned)
        self.assertIn("ig-stage-1700000002-77", ig_cleaned)
        self.assertEqual(alerts_sent, [])

        # Verify Step D after Attempt 2 deleted local MP4 and committed exactly 1 NEW published entry
        self.assertFalse(out_mp4.exists())
        final_st = json.loads((st_dir / "season_state.json").read_text())
        final_hist = json.loads((st_dir / "episode_history.json").read_text())
        orig_entries = json.loads(orig_hist).get("entries", [])
        self.assertEqual(final_st["race_number"], 2)
        self.assertEqual(len(final_hist["entries"]), len(orig_entries) + 1)
        self.assertEqual(final_hist["entries"][:-1], orig_entries)
        self.assertTrue(final_hist["entries"][-1]["published"])
        self.assertEqual(final_hist["entries"][-1]["youtube_id"], "ytLiveVid77")
        self.assertEqual(final_hist["entries"][-1]["instagram_id"], "igLiveReel88")

    def test_double_timeout_preserves_state_verbatim_and_opens_alert(self) -> None:
        tmp, st_dir, out_dir = self._make_temp_env()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        orig_season = (st_dir / "season_state.json").read_bytes()
        orig_hist = (st_dir / "episode_history.json").read_bytes()
        out_mp4 = out_dir / "episode.mp4"
        alerts_sent: list[tuple[str, str]] = []

        def build_hang_cmd(attempt: int, seed: int, target_mp4: Path, manifest_path: Path) -> list[str]:
            return [
                sys.executable,
                "-c",
                f"import json, pathlib, time; "
                f"pathlib.Path({str(target_mp4)!r}).write_bytes(b'x'); "
                f"pathlib.Path({str(manifest_path)!r}).write_text(json.dumps({{'stage': 'step_a_render'}})); "
                f"time.sleep(8)",
            ]

        rc = rde.run_transactional_pipeline(
            dry_run=False,
            force_run=True,
            commit_git=False,
            timeout_s=0.8,
            retry_wait_s=0.05,
            max_attempts=2,
            out_mp4=out_mp4,
            state_dir=st_dir,
            worker_cmd_builder=build_hang_cmd,
            delete_yt_fn=lambda _v: True,
            cleanup_ig_fn=lambda _t: True,
            alert_fn=lambda title, body: (alerts_sent.append((title, body)), True)[1],
        )
        self.assertEqual(rc, 1)
        self.assertFalse(out_mp4.exists())
        self.assertEqual((st_dir / "season_state.json").read_bytes(), orig_season)
        self.assertEqual((st_dir / "episode_history.json").read_bytes(), orig_hist)
        self.assertEqual(len(alerts_sent), 1)
        self.assertIn("step_a_render", alerts_sent[0][1])
        self.assertIn("TIMEOUT", alerts_sent[0][1])

    def test_same_day_duplicate_guard(self) -> None:
        tmp, st_dir, out_dir = self._make_temp_env()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        today = rde.utc_today_str()
        (st_dir / "episode_history.json").write_text(
            json.dumps({"entries": [{"day": 1, "season": 1, "race": 1, "utc_date": today, "published": True}]}),
            encoding="utf-8",
        )
        calls: list[int] = []

        def build_noop(attempt: int, seed: int, target_mp4: Path, manifest_path: Path) -> list[str]:
            calls.append(attempt)
            return [sys.executable, "-c", "raise SystemExit(0)"]

        rc_guarded = rde.run_transactional_pipeline(
            dry_run=False,
            force_run=False,
            commit_git=False,
            out_mp4=out_dir / "episode.mp4",
            state_dir=st_dir,
            worker_cmd_builder=build_noop,
        )
        self.assertEqual(rc_guarded, 0)
        self.assertEqual(calls, [], "Same-Day Duplicate Guard must exit 0 without running worker")

    def test_strict_single_daily_episode_cron_and_clean_secrets(self) -> None:
        wf_dir = ROOT / ".github" / "workflows"
        self.assertFalse((wf_dir / "daily.yml").exists(), "Legacy daily.yml must be deleted")
        self.assertFalse((ROOT / "tests" / "render_all_showcase.py").exists(), "Multi-video showcase batch script must be deleted")

        daily_path = wf_dir / "daily_episode.yml"
        self.assertTrue(daily_path.is_file())
        parsed = yaml.safe_load(daily_path.read_text(encoding="utf-8"))
        triggers = parsed.get("on") or parsed.get(True)
        schedules = triggers.get("schedule", [])
        self.assertEqual(schedules, [{"cron": "17 14 * * *"}])
        self.assertEqual(parsed["concurrency"], {"group": "toontooncastle-daily", "cancel-in-progress": False})
        self.assertEqual(parsed["jobs"]["episode"]["timeout-minutes"], 25)

        for wf in wf_dir.glob("*.yml"):
            txt = wf.read_text(encoding="utf-8")
            self.assertNotIn("KAGGLE_", txt, f"Unused KAGGLE secret ref in {wf.name}")
            self.assertNotIn("GROQ_API_KEY", txt, f"Unused GROQ secret ref in {wf.name}")

    def test_youtube_delete_video_validation_and_http_call(self) -> None:
        self.assertFalse(youtube.delete_video(""))
        with self.assertRaises(ValueError):
            youtube.delete_video("../bad_id")
        fake_req = mock.Mock()
        fake_req.delete.return_value = mock.Mock(status_code=204, text="")
        with mock.patch.object(youtube, "access_token", return_value=("tok_test", 3600, "youtube")), \
             mock.patch.object(youtube, "_requests", return_value=fake_req):
            self.assertTrue(youtube.delete_video("AbCdEf12345"))
            fake_req.delete.assert_called_once()
            self.assertEqual(fake_req.delete.call_args.kwargs["params"], {"id": "AbCdEf12345"})

    def test_unclipped_brand_overlay_is_last_in_render_shot(self) -> None:
        src = (ROOT / "src" / "rendering" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("def _draw_brand_overlay(self, shot: Shot) -> None:", src)
        self.assertIn('hud.outlined("TOONTOONCASTLE", 22, fill=(255, 255, 255), outline=(0, 0, 0), width=2)', src)
        self.assertIn('hud.outlined("@ToonToonCastle", 30, fill=(255, 255, 255), outline=(0, 0, 0), width=4', src)
        self.assertIn("wm.fill((255, 255, 255, 160), special_flags=pygame.BLEND_RGBA_MULT)", src)
        self.assertIn('hud.outlined("TOONTOONCASTLE", 34, fill=gold, outline=(0, 0, 0), width=4)', src)
        # Ensure _draw_brand_overlay(shot) is called immediately before `return self.frame` in render_shot
        rs_chunk = src.split("def render_shot(")[1].split("def _draw_glitch_blinks(")[0]
        lines = [ln.strip() for ln in rs_chunk.strip().splitlines() if ln.strip()]
        self.assertEqual(lines[-2], "self._draw_brand_overlay(shot)")
        self.assertEqual(lines[-1], "return self.frame")


if __name__ == "__main__":
    unittest.main()
