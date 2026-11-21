"""Stdlib-only scheduler for The Tuno Report (no pygame/numpy imports: the GitHub Actions due-check runs it in <1 s).

A season (30 races) is split into thirds. Part k covers races (10k-9)..(10k) and becomes due as soon as race 10k of
that season is published. At most ONE recap is published per run, oldest first, and a part is never published twice.

    python -m src.recap.schedule            # prints `due=true|false` (+ `recap_key=s1_part1` when due)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state"
SEASON_LEN = 30
PARTS = 3
PART_SIZE = SEASON_LEN // PARTS
RECAP_KINDS = ("part1", "part2", "part3", "preview")
_KEY_RE = re.compile(r"^s([1-9][0-9]{0,3})_(part[123]|preview)$")


def part_range(part: int) -> tuple[int, int]:
    """Races covered by Part 1/2/3 -> (1, 10), (11, 20), (21, 30)."""
    if part not in (1, 2, 3):
        raise ValueError("part must be 1, 2 or 3")
    return (part - 1) * PART_SIZE + 1, part * PART_SIZE


def recap_key(season: int, kind: str) -> str:
    key = f"s{int(season)}_{kind}"
    if not _KEY_RE.match(key):
        raise ValueError(f"invalid recap key {key!r}")
    return key


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def published_races(entries: list[dict]) -> dict[int, set[int]]:
    """{season: {race numbers that were published}} from `episode_history.json` entries."""
    out: dict[int, set[int]] = {}
    for e in entries or []:
        if not isinstance(e, dict) or e.get("published") is not True:
            continue
        try:
            s, r = int(e.get("season") or 0), int(e.get("race") or 0)
        except (TypeError, ValueError):
            continue
        if s >= 1 and 1 <= r <= SEASON_LEN:
            out.setdefault(s, set()).add(r)
    return out


def pick_next_due_recap(entries: list[dict], recaps: dict[str, Any]) -> dict[str, Any] | None:
    """Oldest not-yet-published part whose final race (10 / 20 / 30) is published; None on all other days."""
    done = set((recaps or {}).get("recaps", {}).keys()) if isinstance(recaps, dict) else set()
    for season, races in sorted(published_races(entries).items()):
        for part in range(1, PARTS + 1):
            start, end = part_range(part)
            key = recap_key(season, f"part{part}")
            if key in done or end not in races:
                continue
            return {"key": key, "season": season, "part": part, "kind": f"part{part}",
                    "start_race": start, "end_race": end}
    return None


def load_due(state_dir: Path = STATE_DIR) -> dict[str, Any] | None:
    hist = _load(state_dir / "episode_history.json", {"entries": []})
    entries = hist.get("entries", []) if isinstance(hist, dict) else (hist if isinstance(hist, list) else [])
    recaps = _load(state_dir / "recaps.json", {"recaps": {}})
    return pick_next_due_recap(entries, recaps if isinstance(recaps, dict) else {"recaps": {}})


def main(argv: list[str] | None = None) -> int:
    due = load_due()
    print("due=" + ("true" if due else "false"))
    if due:
        print(f"recap_key={due['key']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
