"""v5.0 Pipeline Upgrade Specification lock tests (Parts 1-6: Shorts + 16:9 Long-Form + Widescreen Finale).

Pure Python (no ffmpeg / network), compatible with both `python -m unittest` and `pytest`.
"""
from __future__ import annotations

import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from src.characters.roster import HEROES, make_extras  # noqa: E402
from src.characters.tuno import draw_tuno  # noqa: E402
from src.config import TIMELINE, W, settings  # noqa: E402
from src.games import recipe_generator  # noqa: E402
from src.games.base import WIDESCREEN  # noqa: E402
from src.physics import trace as T  # noqa: E402
from src.physics.camera import final3_zoom_target, track  # noqa: E402
from src.physics.engine import Sim  # noqa: E402
from src.recap.video import (  # noqa: E402
    CHART_MARGIN_Y,
    CHART_ROW_H,
    SIDE_W,
    VIEWPORT,
    compute_chart_row_ys,
)
from src.rendering import effects, hud, pipeline  # noqa: E402
from src.rendering import widescreen_finale as wf  # noqa: E402
from src.state import league  # noqa: E402


class TestV50PipelineUpgrade(unittest.TestCase):
    def test_part1_instant_finish_camera_clamp_and_monotonic_survivors(self) -> None:
        # Find a deterministic flat_track seed that crosses the finish line
        tr = None
        for seed in range(100, 220):
            rec, _ = recipe_generator.generate([], 10, seed, arena="flat_track", goal="reach_finish", season_theme="royal_classic")
            cand = Sim(rec, list(HEROES), make_extras(4, random.Random(seed)), seed).run()
            if cand.meta.get("finish_won"):
                tr = cand
                break
        self.assertIsNotNone(tr, "Expected a finish-line crossing run on flat_track")
        assert tr is not None

        ep = pipeline.Episode(
            tr,
            "",
            season_line="SEASON 1 • EP. 28/30",
            prompt="Bonk or Sly tomorrow?",
            league_ctx={"season_number": 1, "episode_number": 28, "stage": "league"},
        )
        shots = pipeline.plan_shots(ep)
        ep.shots = shots
        r = pipeline.Renderer(ep)
        # Dynamic EP counter (Part 4.1)
        self.assertIn("EP. 28", r.ep.ep_label)

        # P0.1: Zero post-finish dead-air bounce frames before slow-mo replay
        res_f = r.pre + int(round((tr.meta["resolved_at"] or 0.0) * 30))
        max_play_f = max(int(round(s.tf)) for s in shots if s.segment == "play")
        self.assertLessEqual(max_play_f, res_f + 1)

        # P0.2: At least 1 living character stays inside the middle 50% horizontal frame [270, 810] on every frame
        for fi, c in enumerate(r.cams):
            alive = [k for k in range(len(tr.keys)) if tr.flags[fi][k] & T.ALIVE]
            if alive:
                in_mid50 = [k for k in alive if W * 0.25 <= c.to_screen(*tr.frames[fi][k][:2])[0] <= W * 0.75]
                self.assertGreaterEqual(len(in_mid50), 1, f"Empty middle-50% on frame {fi}")

        # P0.5: Monotonically non-increasing survivor count across cold -> play -> replay
        alive_counts = [r._alive_at(int(round(s.tf)), s.segment) for s in shots if s.segment in ("cold", "play", "replay")]
        for i in range(1, len(alive_counts)):
            self.assertLessEqual(alive_counts[i], alive_counts[i - 1])

        # P2.1 + Part 4.2: Bottom 15% safe zone (y < 1632) clear & Winner Card held 2.5s-3.0s
        self.assertGreaterEqual(TIMELINE.winner_card_s, 2.5)
        self.assertLessEqual(TIMELINE.winner_card_s, 3.0)
        self.assertLessEqual(TIMELINE.cold_open_s, 1.5)
        for idx in (10, len(shots) // 2, len(shots) - 10):
            r.render_shot(shots[idx], idx)
            for tb in hud.TEXT_BOXES:
                self.assertLessEqual(tb.bottom, 1632, f"HUD box violated bottom 15% safe zone: {tb}")

    def test_part1_and_part2_early_shrink_early_ko_and_final3_zoom(self) -> None:
        z_tight, edge = final3_zoom_target(120.0)
        self.assertFalse(edge)
        self.assertGreaterEqual(z_tight, 1.40)
        self.assertLessEqual(z_tight, 1.60)

        rec, _ = recipe_generator.generate([], 5, 2042, arena="rotating_disc", goal="last_one_standing", season_theme="royal_classic")
        tr = Sim(rec, list(HEROES), make_extras(4, random.Random(2042)), 2042).run()
        shrink_evs = [e for e in tr.events if e.kind == "escalation" and "SHRINKING" in str(e.data.get("banner", ""))]
        self.assertTrue(shrink_evs and abs(shrink_evs[0].t - 3.0) <= 0.15)
        first_ko = min((e.t for e in tr.events if e.kind == "elimination"), default=99.0)
        self.assertLessEqual(first_ko, 4.0)

    def test_part3_king_lever_pull_and_popup_z_bounds(self) -> None:
        pygame.init()
        surf = pygame.Surface((260, 260), pygame.SRCALPHA)
        draw_tuno(surf, 130, 250, "LEVER_PULL", 0.3, scale=1.1, voice_rms=0.15)
        # Popup clamping on 9:16 frame stays inside [264, 1390]
        fr = pygame.Surface((1080, 1920), pygame.SRCALPHA)
        r_hi = effects.draw_popup(fr, "BETRAYAL!", (540, 50), 0.1, seed=3)
        r_lo = effects.draw_popup(fr, "YEET!", (540, 1850), 0.1, seed=4)
        self.assertIsNotNone(r_hi)
        self.assertIsNotNone(r_lo)
        assert r_hi is not None and r_lo is not None
        self.assertGreaterEqual(r_hi.top, 264)
        self.assertLessEqual(r_lo.bottom, 1390)

    def test_part5_recap_ratio_and_title_race_non_overlap(self) -> None:
        # Left 4:3 viewport is 55-60% of 1920px; Right sidebar is 37-45%
        self.assertAlmostEqual(VIEWPORT.w / VIEWPORT.h, 4.0 / 3.0, places=3)
        self.assertGreaterEqual(VIEWPORT.w / 1920.0, 0.55)
        self.assertLessEqual(VIEWPORT.w / 1920.0, 0.66)   # v5.1: ticker removed, viewport enlarged
        self.assertGreaterEqual(SIDE_W / 1920.0, 0.30)   # v5.1 compact sidebar

        # Title Race horizontal bars never collide even on rapid rank swaps (e.g. Sly 19 vs Grumble 18)
        ys: dict[str, float] = {}
        keys = [h.key for h in HEROES]
        for f in range(90):
            order = list(keys)
            if f % 2 == 1:
                order[0], order[1] = order[1], order[0]
                order[2], order[3] = order[3], order[2]
            out_y = compute_chart_row_ys(order, ys)
            vals = sorted(out_y.values())
            for i in range(1, len(vals)):
                self.assertGreaterEqual(vals[i] - vals[i - 1], CHART_ROW_H + CHART_MARGIN_Y - 1e-4)

    def test_part6_widescreen_finale_recipe_and_cross_promo_flag(self) -> None:
        rec, _ = recipe_generator.generate([], 30, 3030, mode=WIDESCREEN, season_theme="royal_classic")
        self.assertEqual(rec.mode, WIDESCREEN)
        self.assertEqual(rec.params["resolution"], [1920, 1080])
        self.assertEqual(rec.params["participant_count"], 20)
        self.assertEqual(len(rec.params["rounds"]), 3)

        tourney = wf.simulate_widescreen_finale(season=1, seed=3030)
        self.assertEqual(len(tourney.rounds), 3)
        self.assertEqual(len(tourney.rounds[0].trace.keys), 20)
        self.assertEqual(len(tourney.rounds[0].qualified), 6)
        self.assertEqual(len(tourney.rounds[1].qualified), 3)
        self.assertEqual(len(tourney.rounds[2].qualified), 1)
        self.assertIn(tourney.champion, {h.key for h in HEROES})

        scfg = settings().get("season") or {}
        self.assertTrue(scfg.get("finale_cross_promo_enabled"))
        self.assertEqual(list(scfg.get("finale_cross_promo_races")), [28, 29, 30])
        lbl = league.header_label(1, 29, "ROTATING DISC")
        self.assertIn("EP. 29", lbl)


if __name__ == "__main__":
    unittest.main()
