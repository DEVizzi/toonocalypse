"""python -m src.publish — post today's episode to YouTube Shorts + Instagram Reels (idempotent, parts in order)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from src.common import alerts
from src.common.config import ROOT, settings
from src.common.state import load_state, save_state
from src.kaggle_jobs import cli_tools
from src.publish import buffer as buf
from src.publish import instagram, youtube


def approve(story_id: str) -> int:
    b = load_state("buffer.json", {"stories": []})
    for s in b.get("stories", []):
        if s["story_id"] == story_id:
            s["approved"] = True
            save_state("buffer.json", b)
            print(f"approved {story_id} for publishing")
            return 0
    print(f"{story_id} not in buffer")
    return 1


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "approve":
        return approve(sys.argv[2])
    b = load_state("buffer.json", {"stories": []})
    pub = load_state("published.json", {"episodes": {}, "stories": {}})
    tokens = load_state("tokens.json", {})
    pick = buf.next_episode(b, pub)
    if pick is None:
        print("Buffer empty: skipping today (no-op).")
        return 0
    story, ep, need = pick
    if tokens.get("publishing_paused"):
        print(f"ABORTED: publishing paused ({tokens.get('pause_reason')})")
        return 0
    work = ROOT / "work" / "publish"
    files = cli_tools.download_assets(story["release_tag"], [ep["video_asset"], ep["cover_asset"]], work)
    video, cover = files[ep["video_asset"]], files[ep["cover_asset"]]
    sinfo = pub.setdefault("stories", {}).setdefault(story["story_id"], {})
    failures = []

    if "youtube" in need:
        try:
            tok = youtube.access_token()
            vid = youtube.find_existing(tok, ep["episode_id"])
            if not vid:
                prev = next((e for e in story["episodes"] if e["part"] == ep["part"] - 1), None)
                prev_id = pub["episodes"].get(prev["episode_id"], {}).get("youtube", {}).get("id") if prev else None
                desc = buf.youtube_description(story, ep, f"https://youtube.com/shorts/{prev_id}" if prev_id else None, settings()["series_name"])
                vid = youtube.upload(tok, video, ep["title"], desc, ep["episode_id"])
                youtube.set_thumbnail(tok, vid, cover)
                sinfo["playlist"] = youtube.ensure_playlist(tok, story["title"], story["logline"], sinfo.get("playlist"))
                youtube.add_to_playlist(tok, sinfo["playlist"], vid, ep["part"] - 1)
                if prev_id:
                    youtube.append_next_link(tok, prev_id, vid)
            buf.record(pub, ep["episode_id"], "youtube", vid, time.time())
            save_state("published.json", pub)
            print(f"[youtube] {ep['episode_id']} -> {vid}")
        except Exception as e:  # the other platform still posts; this one retries the same episode next run
            failures.append(f"YouTube: {e}")

    if "instagram" in need:
        try:
            ig_user = os.environ["IG_USER_ID"]
            caption = buf.instagram_caption(ep)
            mid = instagram.find_existing(ig_user, caption) or instagram.publish_reel(ig_user, video, caption)
            buf.record(pub, ep["episode_id"], "instagram", mid, time.time())
            save_state("published.json", pub)
            print(f"[instagram] {ep['episode_id']} -> {mid}")
        except Exception as e:
            failures.append(f"Instagram: {e}")

    done = buf.prune_completed(b, pub)
    save_state("buffer.json", b)
    if done:
        bible = load_state("story_bible.json")
        for s in done:
            for h in bible.get("history", []):
                if h["story_id"] == s["story_id"]:
                    h["status"] = "PUBLISHED"
                    h["platform_ids"] = {e["episode_id"]: pub["episodes"].get(e["episode_id"]) for e in s["episodes"]}
        save_state("story_bible.json", bible)
    if failures:
        alerts.open_or_update("Toonocalypse: publishing failed", "\n".join(failures) + f"\n\nEpisode: {ep['episode_id']} (retries next run)")
        print("PUBLISH FAILURES:", failures)
        return 1
    alerts.close_if_open()
    return 0


if __name__ == "__main__":
    sys.exit(main())
