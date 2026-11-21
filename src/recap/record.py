"""Per-race replay record (`entry["recap"]` in `state/episode_history.json`).

Everything The Tuno Report needs to (a) recompute the league table with the exact league rules and (b) re-simulate the
race bit-for-bit later — at the exact code version that produced it (`code_sha`, see `src/recap/timemachine.py`):

    {"v": 1, "code_sha": "...", "seed": 22959, "sim_seed": 22959006, "recipe": {...}, "heroes": [...],
     "extras": [{...}], "ranking": [...], "winner": "glitch", "resolved_at": 18.7,
     "elims": [{"t": 4.2, "actors": ["pip", "juggernaut"], "cause": "fell", "hero": true, "by_hero": true}]}

Kept compact (~2 KB/race) and JSON-only (no pickles). Building it can never break the daily episode: callers wrap it.
"""
from __future__ import annotations

import dataclasses
import os
import re
from typing import Any

RECORD_VERSION = 1
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _extra_dict(x: Any) -> dict[str, Any]:
    d = dataclasses.asdict(x)
    beh = d.get("behaviour")
    if isinstance(beh, dict):
        d["behaviour"] = [beh.get("aggression"), beh.get("caution"), beh.get("jumpiness"), beh.get("edge_awareness")]
    return d


def current_code_sha() -> str | None:
    sha = (os.environ.get("GITHUB_SHA") or "").strip().lower()
    return sha if _SHA_RE.match(sha) else None


def build_record(seed: int, recipe: Any, heroes: list, extras: list, trace: Any,
                 code_sha: str | None = None) -> dict[str, Any]:
    meta = trace.meta
    elims = []
    for e in sorted((e for e in trace.events if e.kind == "elimination"), key=lambda e: e.t):
        elims.append({
            "t": round(float(e.t), 3),
            "actors": [str(a) for a in e.actors[:2]],
            "cause": str(e.data.get("cause") or ""),
            "hero": bool(e.data.get("hero")),
            "by_hero": bool(e.data.get("by_hero")),
        })
    sha = code_sha if (code_sha and _SHA_RE.match(code_sha)) else current_code_sha()
    return {
        "v": RECORD_VERSION,
        "code_sha": sha,
        "seed": int(seed),
        "sim_seed": int(meta.get("seed")),
        "recipe": recipe.to_dict(),
        "heroes": [h.key for h in heroes],
        "extras": [_extra_dict(x) for x in extras],
        "ranking": [str(k) for k in (meta.get("ranking") or [])],
        "winner": meta.get("winner"),
        "resolved_at": round(float(meta.get("resolved_at") or 0.0), 3),
        "elims": elims,
    }
