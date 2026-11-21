"""ToonToonCastle v4.6 post-publish engagement boost (best-effort: NEVER raises, NEVER triggers a rollback).

- `post_launch_engagement(yt_id, ig_id, meta)`: right after Step D, posts the spoiler-free "Which ball did you pick?"
  first comment on the YouTube Short (pin it manually: the YouTube API cannot pin) and on the Instagram Reel.
- Retrofit CLI for an already-published episode (used by `.github/workflows/engage.yml`):
      python -m src.publish.engage --published-index -1 --update-youtube-metadata --comments
  Rebuilds the v4.6 metadata from `state/episode_history.json`, updates the YouTube title/description/tags/category
  (`videos.update`), posts the first comments, and prints the Instagram caption to paste manually (the Instagram
  Graph API cannot edit the caption of a published Reel).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from src.publish import instagram, metadata, youtube
from src.publish.alerts import redact

ROOT = Path(__file__).resolve().parents[2]


def _err(exc: BaseException) -> str:
    return redact(f"{type(exc).__name__}: {exc}")[:220]


def post_launch_engagement(
    yt_video_id: str | None,
    ig_media_id: str | None,
    meta: dict[str, Any],
    yt_comment_fn: Callable[[str, str], str] | None = None,
    ig_comment_fn: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Posts the first comments; returns {'yt_comment_id' | 'yt_comment_error', 'ig_comment_id' | 'ig_comment_error'}."""
    yt_fn = yt_comment_fn or youtube.post_comment
    ig_fn = ig_comment_fn or instagram.post_comment
    out: dict[str, Any] = {}
    meta = meta or {}
    if yt_video_id and meta.get("yt_comment"):
        try:
            out["yt_comment_id"] = yt_fn(str(yt_video_id), str(meta["yt_comment"]))
        except Exception as exc:  # noqa: BLE001 - engagement is best-effort by design
            out["yt_comment_error"] = _err(exc)
    if ig_media_id and meta.get("ig_comment"):
        try:
            out["ig_comment_id"] = ig_fn(str(ig_media_id), str(meta["ig_comment"]))
        except Exception as exc:  # noqa: BLE001 - engagement is best-effort by design
            out["ig_comment_error"] = _err(exc)
    return out


def metadata_for_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    stage = str(entry.get("stage") or "league")
    outcome = SimpleNamespace(
        season_number=int(entry.get("season") or 1),
        race_number=int(entry.get("race") or 1),
        stage=stage,
        winner_key=entry.get("winner"),
        is_grand_final=stage == "grand_final",
    )
    return metadata.build_upload_metadata(
        str(entry.get("arena") or ""),
        outcome,
        "",
        goal=entry.get("goal"),
        hazards=list(entry.get("hazards") or []),
        twist=entry.get("twist"),
        cast_keys=entry.get("cast") or None,
    )


def _published_entries(state_dir: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads((state_dir / "episode_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = raw.get("entries", []) if isinstance(raw, dict) else raw
    return [e for e in entries if isinstance(e, dict) and e.get("published") and
            (e.get("youtube_id") or e.get("instagram_id"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-apply v4.6 SEO metadata + first comments to a published episode")
    ap.add_argument("--published-index", type=int, default=-1, help="index into published episodes (-1 = latest)")
    ap.add_argument("--update-youtube-metadata", action="store_true")
    ap.add_argument("--comments", action="store_true")
    ap.add_argument("--comment-on", choices=["both", "youtube", "instagram"], default="both")
    ap.add_argument("--state-dir", default=str(ROOT / "state"))
    a = ap.parse_args(argv)

    published = _published_entries(Path(a.state_dir))
    if not published:
        print("[ENGAGE] no published episodes in episode_history.json")
        return 1
    try:
        entry = published[a.published_index]
    except IndexError:
        print(f"[ENGAGE] published index {a.published_index} out of range (have {len(published)})")
        return 1

    meta = metadata_for_history_entry(entry)
    yt_id, ig_id = entry.get("youtube_id"), entry.get("instagram_id")
    print(f"[ENGAGE] S{entry.get('season')} R{entry.get('race')} {entry.get('arena')} yt={yt_id} ig={ig_id}")
    for key in ("title", "description", "tags", "category_id", "ig_caption", "yt_comment", "ig_comment"):
        print(f"\n----- {key} -----\n{meta[key]}")
    print()

    failures = 0
    if a.update_youtube_metadata and yt_id:
        try:
            youtube.update_video_metadata(str(yt_id), meta["title"], meta["description"], meta["tags"],
                                          meta["category_id"])
            print(f"[ENGAGE OK] YouTube title/description/tags/category updated for {yt_id}")
        except Exception as exc:  # noqa: BLE001 - report and continue with comments
            failures += 1
            print(f"[ENGAGE FAIL] YouTube metadata update: {_err(exc)}")
    if a.comments:
        res = post_launch_engagement(yt_id if a.comment_on in ("both", "youtube") else None,
                                     ig_id if a.comment_on in ("both", "instagram") else None, meta)
        for k, v in res.items():
            print(f"[ENGAGE {'FAIL' if k.endswith('_error') else 'OK'}] {k}: {v}")
        failures += sum(1 for k in res if k.endswith("_error"))
    print("[ENGAGE] Instagram captions of published Reels cannot be edited via API: paste `ig_caption` above "
          "manually (Reel -> ... -> Edit).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
