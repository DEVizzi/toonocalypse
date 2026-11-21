"""v4.4 Rebrand, Repo Cleanup, Branding, Dual YT+IG Publishing & Launch Lock unit tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.publish import alerts, metadata, validate
from src.state import league

ROOT = Path(__file__).resolve().parent.parent


class TestV44LaunchLock(unittest.TestCase):
    def test_zero_legacy_brand_references_repo_wide(self) -> None:
        banned_words = ("toon" + "ocalypse", "tuno" + " clips")
        skip_dirs = {".git", "__pycache__", ".venv", ".pytest_cache", "output", "renders", "tmp", "cache", "work"}
        hits: list[str] = []
        for p in ROOT.rglob("*"):
            if any(part in skip_dirs for part in p.parts) or not p.is_file():
                continue
            if p.suffix.lower() in {".png", ".ttf", ".jpg", ".mp4", ".wav", ".mp3", ".pyc"}:
                continue
            txt = p.read_text(errors="ignore").lower()
            for bw in banned_words:
                if bw in txt:
                    hits.append(f"{p.relative_to(ROOT)} ({bw})")
        self.assertEqual(hits, [], f"Legacy brand references remain: {hits}")

    def test_standardized_toontooncastle_upload_metadata(self) -> None:
        outcome = SimpleNamespace(
            season_number=1,
            race_number=1,
            winner_key="bonk",
            ribbon_text="SEASON 1 • RACE 1 / 30",
            is_grand_final=False,
        )
        m = metadata.build_upload_metadata("rotating_disc", outcome, "Dash or Sly tomorrow? Drop your pick!",
                                           goal="last_one_standing")
        self.assertEqual(m["title"], "Only ONE Ball Survives the Rotating Disc 😱")   # v4.6 replaces the v4.4 title
        self.assertLessEqual(len(m["title"]), 100)
        self.assertNotIn("#shorts", m["title"])
        self.assertIn("#ToonToonCastle", m["description"])
        self.assertIn("#toontooncastle", m["ig_caption"])
        self.assertIn("ToonToonCastle", m["tags"])

    def test_gitignore_blocks_all_media_and_temp_dirs(self) -> None:
        gi = (ROOT / ".gitignore").read_text()
        for pat in ("*.mp4", "*.mov", "*.wav", "*.mp3", "output/", "renders/", "tmp/", "__pycache__/"):
            self.assertIn(pat, gi)

    def test_camera_zoom_sanity_gate(self) -> None:
        self.assertEqual(validate.validate_camera_meta({"cam_zoom_min": 0.94, "cam_zoom_max": 1.98}), [])
        self.assertTrue(validate.validate_camera_meta({"cam_zoom_min": 0.0022, "cam_zoom_max": 0.95}))
        self.assertTrue(validate.validate_camera_meta({"cam_zoom_min": 0.95, "cam_zoom_max": 4.2}))

    def test_alert_secret_redaction(self) -> None:
        raw = "Failed with AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz and EAA1234567890abcdefghijkl and ghp_1234567890abcdefghij"
        clean = alerts.redact(raw)
        self.assertNotIn("AIza", clean)
        self.assertNotIn("EAA123", clean)
        self.assertNotIn("ghp_", clean)
        self.assertIn("[REDACTED]", clean)

    def test_workflows_schedule_and_concurrency(self) -> None:
        daily = (ROOT / ".github" / "workflows" / "daily_episode.yml").read_text()
        self.assertIn('cron: "17 14 * * *"', daily)
        self.assertIn("group: toontooncastle-daily", daily)
        self.assertIn("cancel-in-progress: false", daily)
        ig_wf = (ROOT / ".github" / "workflows" / "ig-token-refresh.yml").read_text()
        self.assertIn('cron: "0 10 1,15 * *"', ig_wf)

    def test_season_state_invariants(self) -> None:
        st = json.loads((ROOT / "state" / "season_state.json").read_text())
        hof = json.loads((ROOT / "state" / "hall_of_fame.json").read_text())
        hist = json.loads((ROOT / "state" / "episode_history.json").read_text())
        self.assertGreaterEqual(int(st["season_number"]), 1)
        self.assertTrue(1 <= int(st["race_number"]) <= 30)
        self.assertEqual(len(st["stats"]), 10)
        self.assertIsInstance(hof.get("seasons"), list)
        entries = hist.get("entries") if isinstance(hist, dict) else hist
        self.assertIsInstance(entries, list)


if __name__ == "__main__":
    unittest.main()
