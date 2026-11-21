"""Instagram Reels Graph API staged publisher & rollback cleanup (v4.5).

Supports two-phase transactional publishing for `run_daily_episode.py`:
- Phase 1 (`stage_and_prepare_reel`): uploads temporary MP4 asset to an ephemeral GitHub Release (`ig-stage-<ts>`),
  creates the `REELS` container, and polls until `status_code == 'FINISHED'` (WITHOUT calling `media_publish` yet!).
- Phase 2 (`publish_prepared_reel`): calls `media_publish` immediately after YouTube upload succeeds.
- Cleanup (`cleanup_ephemeral_release_by_tag`): deletes the temporary GitHub Release & tag on success OR rollback.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from src.publish.alerts import redact


def _requests():
    import requests
    return requests


FB_GRAPH = "https://graph.facebook.com/v21.0"
IG_GRAPH = "https://graph.instagram.com/v21.0"
MAX_BYTES = 256 * 1024 * 1024
POLL_INTERVAL_S = 10
MAX_POLLS = 28
TIMEOUT_S = 30
_SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SAFE_ID = re.compile(r"^[0-9]{5,30}$")
_SAFE_TAG = re.compile(r"^ig-stage-[0-9]+-[0-9]+$")


class InstagramError(RuntimeError):
    """Redacted Instagram Graph API error."""


def _ig_creds() -> tuple[str, str, str]:
    uid = (os.environ.get("IG_USER_ID") or "").strip()
    tok = (os.environ.get("IG_ACCESS_TOKEN") or "").strip()
    missing = [name for name, val in (("IG_USER_ID", uid), ("IG_ACCESS_TOKEN", tok)) if not val]
    if missing:
        raise InstagramError(f"missing required secret(s): {', '.join(missing)}")
    if not _SAFE_ID.match(uid):
        raise InstagramError("IG_USER_ID must be a numeric Instagram Business/Creator account ID")
    base = IG_GRAPH if tok.startswith("IGAA") else FB_GRAPH
    return uid, tok, base


def make_stage_tag() -> str:
    return f"ig-stage-{int(time.time())}-{os.getpid()}"


def stage_ephemeral_release(mp4: Path, tag: str | None = None) -> tuple[str, str]:
    """Uploads `mp4` to an ephemeral GitHub pre-release `tag` and returns `(tag, public_video_url)`."""
    gh = shutil.which("gh")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    pat = (os.environ.get("GH_TOKEN") or os.environ.get("GH_PAT") or "").strip()
    if not gh or not repo or not pat or not _SAFE_REPO.match(repo):
        raise InstagramError("GH_TOKEN and GITHUB_REPOSITORY are required to stage ephemeral Reels video_url")
    use_tag = tag or make_stage_tag()
    if not _SAFE_TAG.match(use_tag):
        raise InstagramError("invalid ephemeral release tag")
    env = {**os.environ, "GH_TOKEN": pat}
    res = subprocess.run(
        [gh, "release", "create", use_tag, str(mp4), "--repo", repo, "--prerelease",
         "--title", use_tag, "--notes", "Ephemeral Instagram Reels staging asset (auto-deleted immediately)."],
        env=env,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    if res.returncode != 0:
        detail = redact(" ".join((res.stderr or res.stdout or "").split()))[:160]
        raise InstagramError(f"ephemeral release staging failed (exit {res.returncode}: {detail})")
    return use_tag, f"https://github.com/{repo}/releases/download/{use_tag}/{mp4.name}"


def cleanup_ephemeral_release_by_tag(tag: str) -> bool:
    """Deletes ephemeral GitHub Release `tag` and its git tag (idempotent; safe during rollback)."""
    if not tag or not _SAFE_TAG.match(tag):
        return False
    gh = shutil.which("gh")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    pat = (os.environ.get("GH_TOKEN") or os.environ.get("GH_PAT") or "").strip()
    if not gh or not repo or not pat or not _SAFE_REPO.match(repo):
        return False
    env = {**os.environ, "GH_TOKEN": pat}
    try:
        res = subprocess.run(
            [gh, "release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag"],
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def prepare_reel_container(video_url: str, caption: str) -> str:
    """Creates an Instagram `REELS` container and polls until `FINISHED` (does NOT publish yet). Returns `creation_id`."""
    req = _requests()
    uid, token, base = _ig_creds()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        init = req.post(
            f"{base}/{uid}/media",
            headers=headers,
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": str(caption or "")[:2150],
                "share_to_feed": "true",
            },
            timeout=TIMEOUT_S,
        )
    except req.RequestException as exc:
        raise InstagramError(f"Graph API container request failed ({type(exc).__name__})") from None
    if init.status_code != 200:
        err_msg = ""
        try:
            err_msg = str(((init.json() or {}).get("error") or {}).get("message", ""))[:120]
        except ValueError:
            err_msg = "non-JSON error"
        raise InstagramError(f"container init HTTP {init.status_code}: {redact(err_msg)}")
    creation_id = str((init.json() or {}).get("id") or "").strip()
    if not _SAFE_ID.match(creation_id):
        raise InstagramError("Graph API returned invalid creation_id")

    status_code = "IN_PROGRESS"
    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL_S)
        try:
            poll = req.get(
                f"{base}/{creation_id}",
                headers=headers,
                params={"fields": "status_code,status"},
                timeout=TIMEOUT_S,
            )
        except req.RequestException as exc:
            raise InstagramError(f"container status poll failed ({type(exc).__name__})") from None
        if poll.status_code != 200:
            raise InstagramError(f"container status HTTP {poll.status_code}")
        body = poll.json() or {}
        status_code = str(body.get("status_code") or "").upper()
        if status_code == "FINISHED":
            return creation_id
        if status_code in ("ERROR", "EXPIRED"):
            detail = redact(str(body.get("status") or status_code))[:140]
            raise InstagramError(f"container processing failed ({detail})")
    raise InstagramError(f"container timed out in state {status_code or 'UNKNOWN'}")


def publish_prepared_reel(creation_id: str) -> str:
    """Publishes an already-`FINISHED` Instagram Reels container (`media_publish`) and returns `media_id`."""
    if not _SAFE_ID.match(str(creation_id or "").strip()):
        raise InstagramError("invalid creation_id for media_publish")
    req = _requests()
    uid, token, base = _ig_creds()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        pub = req.post(
            f"{base}/{uid}/media_publish",
            headers=headers,
            data={"creation_id": str(creation_id).strip()},
            timeout=TIMEOUT_S,
        )
    except req.RequestException as exc:
        raise InstagramError(f"media_publish request failed ({type(exc).__name__})") from None
    if pub.status_code != 200:
        raise InstagramError(f"media_publish HTTP {pub.status_code}")
    media_id = str((pub.json() or {}).get("id") or "").strip()
    if not media_id:
        raise InstagramError("media_publish returned no media id")
    return media_id


def upload_reel(mp4: Path, caption: str, video_url: str | None = None) -> str:
    """Single-call convenience wrapper (stages -> waits for FINISHED -> publishes -> cleans up)."""
    size = mp4.stat().st_size
    if not (0 < size <= MAX_BYTES):
        raise InstagramError("video size out of bounds")
    tag = None
    try:
        if not video_url:
            tag, video_url = stage_ephemeral_release(mp4)
        cid = prepare_reel_container(video_url, caption)
        return publish_prepared_reel(cid)
    finally:
        if tag:
            cleanup_ephemeral_release_by_tag(tag)


__all__ = [
    "InstagramError",
    "cleanup_ephemeral_release_by_tag",
    "make_stage_tag",
    "prepare_reel_container",
    "publish_prepared_reel",
    "stage_ephemeral_release",
    "upload_reel",
]
