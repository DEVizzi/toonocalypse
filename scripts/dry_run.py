"""End-to-end dry-run proof script for Toonocalypse (runs in CI / GitHub Actions)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli import AbortPipeline, generate_episode_bundle


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return val in ("1", "true", "yes", "on") if val else default


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Toonocalypse dry-run proof episode.")
    parser.add_argument("--format", default=os.environ.get("TOON_FORMAT", "Mini-Arc"), choices=["One-Shot", "Mini-Arc", "Epic-Arc"])
    parser.add_argument("--heroes", default=os.environ.get("TOON_HEROES", "brewtan-the-yeti,detective-bubbles"))
    parser.add_argument("--villain", default=os.environ.get("TOON_VILLAIN", "") or None)
    parser.add_argument("--offline", action="store_true", default=_env_bool("TOON_OFFLINE", False))
    parser.add_argument("--draft-release", action="store_true", default=_env_bool("TOON_DRAFT_RELEASE", False))
    parser.add_argument("--fail-preflight", action="store_true", default=_env_bool("TOON_FAIL_PREFLIGHT", False))
    parser.add_argument("--out-dir", default="dry_run_output")
    args = parser.parse_args()

    out_dir = ROOT / args.out_dir / args.format.lower()
    heroes = [h.strip() for h in args.heroes.split(",") if h.strip()] if args.heroes else None
    try:
        result = generate_episode_bundle(
            work_dir=out_dir,
            forced_format=args.format,
            forced_heroes=heroes,
            forced_villain=args.villain,
            offline=args.offline,
            part_num=1,
            upload_release=args.draft_release,
            draft_release=args.draft_release,
            force_fail_preflight=args.fail_preflight,
        )
        print(json.dumps(result, indent=2))
        return 0
    except AbortPipeline as exc:
        print(f"ABORTED: {exc.reason}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
