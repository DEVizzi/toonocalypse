"""Instagram Reels Graph API publisher (v4.4).

Flow:
1. Stages the validated MP4 to an ephemeral GitHub Release asset (`ig-stage-<ts>`) to obtain a short-lived HTTPS
   `video_url` reachable by Meta's Reels crawler (or uses `IG_VIDEO_URL` if provided).
2. Creates a `REELS` media container (`POST /{ig_user_id}/media`, `media_type=REELS`).
3. Polls `GET /{creation_id}?fields=status_code` until `FINISHED` (bounded timeout).
4. Publishes via `POST /{ig_user_id}/media_publish`.
5. `finally:` ALWAYS deletes the temporary GitHub Release & tag immediately so zero media artifacts linger.

Security:
- `IG_ACCESS_TOKEN` and `IG_USER_ID` are read strictly from `os.environ` and sent via `Authorization: Bearer` header
  (never in URLs, never logged).
- All `gh` subprocess calls use `shell=False` with strict regex-validated repo/tag identifiers.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from src.publish.alerts import redact

FB_GRAPH = "https://graph.facebook.com/v21.0"
IG_GRAPH = "https://graph.instagram.com/v21.0"
MAX_BYTES = 256 * 1024 * 1024
POLL_INTERVAL_S = 10
MAX_POLLS = 30
TIMEOUT_S = 30
_SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SAFE_ID = re.compile(r"^[0-9]{5,30}$")


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


def _stage_ephemeral_release(mp4: Path) -> tuple[str, str, str, dict[str, str]]:
    """Uploads `mp4` to an ephemeral GitHub pre-release and returns (gh_bin, repo, tag, env) + public download URL."""
    gh = shutil.which("gh")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    pat = (os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or "").strip()
    if not gh or not repo or not pat or not _SAFE_REPO.match(repo):
        raise InstagramError("GH_PAT/GH_TOKEN and GITHUB_REPOSITORY are required to stage ephemeral Reels video_url")
    tag = f"ig-stage-{int(time.time())}-{os.getpid()}"
    env = {**os.environ, "GH_TOKEN": pat}
    res = subprocess.run(
        [gh, "release", "create", tag, str(mp4), "--repo", repo, "--prerelease",
         "--title", tag, "--notes", "Ephemeral Instagram Reels staging asset (auto-deleted immediately)."],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if res.returncode != 0:
        raise InstagramError(f"ephemeral release staging failed (exit {res.returncode})")
    return gh, repo, tag, env


def _cleanup_ephemeral_release(gh: str, repo: str, tag: str, env: dict[str, str]) -> None:
    try:
        subprocess.run(
            [gh, "release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def upload_reel(mp4: Path, caption: str, video_url: str | None = None) -> str:
    """Publishes `mp4` as an Instagram Reel and returns the published `media_id`."""
    size = mp4.stat().st_size
    if not (0 < size <= MAX_BYTES):
        raise InstagramError("video size out of bounds")
    uid, token, base = _ig_creds()
    headers = {"Authorization": f"Bearer {token}"}
    staged: tuple[str, str, str, dict[str, str]] | None = None

    try:
        if not video_url:
            gh, repo, tag, env = _stage_ephemeral_release(mp4)
            staged = (gh, repo, tag, env)
            video_url = f"https://github.com/{repo}/releases/download/{tag}/{mp4.name}"

        # 1. Create REELS media container
        try:
            init = requests.post(
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
        except requests.RequestException as exc:
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

        # 2. Poll container status until FINISHED
        status_code = "IN_PROGRESS"
        for _ in range(MAX_POLLS):
            time.sleep(POLL_INTERVAL_S)
            try:
                poll = requests.get(
                    f"{base}/{creation_id}",
                    headers=headers,
                    params={"fields": "status_code,status"},
                    timeout=TIMEOUT_S,
                )
            except requests.RequestException as exc:
                raise InstagramError(f"container status poll failed ({type(exc).__name__})") from None
            if poll.status_code != 200:
                raise InstagramError(f"container status HTTP {poll.status_code}")
            body = poll.json() or {}
            status_code = str(body.get("status_code") or "").upper()
            if status_code == "FINISHED":
                break
            if status_code in ("ERROR", "EXPIRED"):
                detail = redact(str(body.get("status") or status_code))[:140]
                raise InstagramError(f"container processing failed ({detail})")
        if status_code != "FINISHED":
            raise InstagramError(f"container timed out in state {status_code or 'UNKNOWN'}")

        # 3. Publish Reel
        try:
            pub = requests.post(
                f"{base}/{uid}/media_publish",
                headers=headers,
                data={"creation_id": creation_id},
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise InstagramError(f"media_publish request failed ({type(exc).__name__})") from None
        if pub.status_code != 200:
            raise InstagramError(f"media_publish HTTP {pub.status_code}")
        media_id = str((pub.json() or {}).get("id") or "").strip()
        if not media_id:
            raise InstagramError("media_publish returned no media id")
        return media_id
    finally:
        if staged is not None:
            _cleanup_ephemeral_release(*staged)


__all__ = ["InstagramError", "upload_reel"]
