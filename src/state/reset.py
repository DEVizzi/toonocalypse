"""Production reset: Season 1 • Race 1 / 30, empty Hall of Fame, empty episode history (v4.3.1 launch prep).

Usage:  python -m src.state.reset --yes      (refuses to run without --yes)
"""
from __future__ import annotations

import sys

from src.state import league


def main(argv: list[str]) -> int:
    if "--yes" not in argv:
        print("refusing to wipe league state without --yes", file=sys.stderr)
        return 2
    st = league.fresh_season_state(season_number=1, reigning_champion=None, total_day=1)
    league.save_all_state(st, {"seasons": []}, [], state_dir=league.STATE_DIR)
    print(f"state reset -> Season {st['season_number']} • Race {st['race_number']} / {league.SEASON_LEN}, "
          f"theme={st['theme']}, heroes={len(st['stats'])}, hall_of_fame=0, history=0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
