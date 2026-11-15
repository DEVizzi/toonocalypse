"""End-to-end dry-run proof script for Toonocalypse (runs in CI / GitHub Actions)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli import generate_episode_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Toonocalypse dry-run proof episode.")
    parser.add_argument("--format", default="Mini-Arc", choices=["One-Shot", "Mini-Arc", "Epic-Arc"])
    parser.add_argument("--heroes", default="brewtan-the-yeti,detective-bubbles")
    parser.add_argument("--villain", default=None)
    parser.add_argument("--offline", action="store_true", help="Use deterministic offline stubs (no API spend)")
    parser.add_argument("--draft-release", action="store_true", help="Upload output as a GitHub draft release")
    parser.add_argument("--out-dir", default="dry_run_output")
    args = parser.parse_args()

    out_dir = ROOT / args.out_dir / args.format.lower()
    heroes = [h.strip() for h in args.heroes.split(",") if h.strip()] if args.heroes else None
    result = generate_episode_bundle(
        work_dir=out_dir,
        forced_format=args.format,
        forced_heroes=heroes,
        forced_villain=args.villain,
        offline=args.offline,
        part_num=1,
        upload_release=args.draft_release,
        draft_release=args.draft_release,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
