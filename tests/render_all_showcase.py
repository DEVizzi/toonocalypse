"""Render (or pre-check with --no-render) all 17 arenas and all 7 gameplays across all 8 seasonal themes.

Usage:
    # Local physics & scorer pre-check (no ffmpeg/pygame required):
    python tests/render_all_showcase.py --no-render

    # Sharded GitHub Actions parallel render (e.g. 4 shards):
    python tests/render_all_showcase.py --shard 0 --num-shards 4
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import main as run_episode  # noqa: E402

# 18 showcase episodes covering:
# - ALL 17 arenas (12 SIDE_VIEW + 5 TOP_DOWN)
# - ALL 7 gameplays/goals (including BOTH SIDE_VIEW and TOP_DOWN variants for BOTH-mode goals)
# - ALL 8 procedural seasonal themes (S1..S8) + League / Play-In / Q1 / Q2 / Grand Final stages
SHOWCASE_JOBS: list[tuple[str, int, int, int, str, str]] = [
    # 12 SIDE_VIEW arenas
    ("show_01_ramp_descent_reach_finish",      301, 1, 28, "ramp_descent",     "reach_finish"),
    ("show_02_pachinko_drop_reach_finish",     302, 2,  8, "pachinko_drop",    "reach_finish"),
    ("show_03_crumbling_bridge_reach_finish",  303, 3, 12, "crumbling_bridge", "reach_finish"),
    ("show_04_collapse_tower_reach_finish",    304, 4, 16, "collapse_tower",   "reach_finish"),
    ("show_05_crusher_gauntlet_reach_finish",  305, 7, 20, "crusher_gauntlet", "reach_finish"),
    ("show_06_flat_track_reach_finish",        306, 5,  6, "flat_track",       "reach_finish"),
    ("show_07_pit_platforms_survive_timer",    307, 6, 10, "pit_platforms",    "survive_timer"),
    ("show_08_tiered_tower_last_standing",     308, 8, 14, "tiered_tower",     "last_one_standing"),
    ("show_09_narrow_bridge_hot_potato",       309, 1, 18, "narrow_bridge",    "hot_potato_bomb"),
    ("show_10_bouncy_pad_field_collect_items", 310, 8, 22, "bouncy_pad_field", "collect_items"),
    ("show_11_seesaw_gauntlet_reach_finish",   311, 2, 27, "seesaw_gauntlet",  "reach_finish"),
    ("show_12_conveyor_chaos_collect_items",   312, 4, 21, "conveyor_chaos",   "collect_items"),
    # 5 TOP_DOWN arenas + all TOP_DOWN gameplays
    ("show_13_rotating_disc_last_standing",    313, 5, 29, "rotating_disc",    "last_one_standing"),
    ("show_14_sumo_pool_pit_push_others_out",  314, 3, 30, "sumo_pool_pit",    "push_others_out"),
    ("show_15_maze_corridors_hold_a_zone",     315, 6, 15, "maze_corridors",   "hold_a_zone"),
    ("show_16_hex_tile_drop_survive_timer",    316, 7, 19, "hex_tile_drop",    "survive_timer"),
    ("show_17_bumper_ring_hot_potato",         317, 1, 24, "bumper_ring",      "hot_potato_bomb"),
    ("show_18_bumper_ring_collect_items",      318, 2, 11, "bumper_ring",      "collect_items"),
]


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch showcase renderer for all 17 arenas and 7 gameplays")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--stills", type=int, default=3)
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args(argv)

    if a.num_shards < 1 or not (0 <= a.shard < a.num_shards):
        raise SystemExit("Invalid --shard / --num-shards")

    out_dir = (ROOT / a.out_dir).resolve()
    if out_dir != ROOT and ROOT not in out_dir.parents:
        raise SystemExit("--out-dir must stay inside repository root")
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [j for idx, j in enumerate(SHOWCASE_JOBS) if idx % a.num_shards == a.shard]
    print(f"[SHOWCASE] running {len(jobs)}/{len(SHOWCASE_JOBS)} jobs (shard {a.shard}/{a.num_shards}) -> {out_dir}")
    failures = 0
    for slug, seed, s_num, r_num, arena, goal in jobs:
        out_mp4 = out_dir / f"{slug}.mp4"
        args = [
            "--dry-run",
            "--seed", str(seed),
            "--season", str(s_num),
            "--race", str(r_num),
            "--arena", arena,
            "--goal", goal,
            "--stills", str(0 if a.no_render else a.stills),
            "--out", str(out_mp4.relative_to(ROOT)),
        ]
        if a.no_render:
            args.append("--no-render")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_episode(args)
        else:
            print(f"\n=== [{slug}] S{s_num} R{r_num} | {arena} / {goal} (seed={seed}) ===", flush=True)
            rc = run_episode(args)
        meta_path = out_mp4.with_suffix(".json")
        d = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        valid = sum(1 for c in d.get("candidates", []) if not c.get("rejected"))
        total_c = len(d.get("candidates", []))
        negs = {k: v for k, v in (d.get("score_parts") or {}).items() if v < 0}
        win = str(d.get("winner") or "?")
        res_t = float(d.get("resolved_at") or 0.0)
        sc = float(d.get("score") or 0.0)
        print(
            f"{slug:40s} | rc={rc} | valid={valid:2d}/{total_c:2d} | "
            f"score={sc:+5.0f} | t={res_t:4.1f}s | win={win:10s} | neg={negs}",
            flush=True,
        )
        if rc != 0 or valid == 0 or win.startswith("extra"):
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(cli())
