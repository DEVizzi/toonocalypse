"""Instagram Graph API (current version) resumable Reels publisher with idempotency (§11)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from src.common.config import load_settings
from src.moderation.gate import check_metadata


def find_existing_instagram_reel(episode_id: str, ig_user_id: str, token: str, api_ver: str) -> str | None:
    marker = f"[ep:{episode_id}]"
    resp = requests.get(
        f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media",
        params={"fields": "id,caption", "limit": 25, "access_token": token},
        timeout=20,
    )
    if not resp.ok:
        return None
    for item in resp.json().get("data", []):
        if marker in (item.get("caption") or ""):
            return str(item["id"])
    return None


def publish_to_instagram(
    video_path: Path,
    episode_id: str,
    caption: str,
    cover_url: str | None = None,
) -> str:
    cfg = load_settings()
    api_ver = cfg.get("instagram_api_version", "v21.0")
    ig_user_id = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]

    full_caption = f"{caption.strip()}\n\n[ep:{episode_id}]"
    mod = check_metadata("", "", full_caption, [])
    if not mod.passed:
        raise ValueError(f"Instagram caption blocked by moderation: {mod.reasons}")

    existing = find_existing_instagram_reel(episode_id, ig_user_id, token, api_ver)
    if existing:
        return existing

    init_params = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": full_caption,
        "access_token": token,
    }
    if cover_url:
        init_params["cover_url"] = cover_url
    init_resp = requests.post(f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media", data=init_params, timeout=30)
    init_resp.raise_for_status()
    init_data = init_resp.json()
    container_id = init_data["id"]
    upload_uri = init_data["uri"]

    file_size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        up_resp = requests.post(
            upload_uri,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(file_size)},
            data=f,
            timeout=180,
        )
    up_resp.raise_for_status()

    # Wait briefly for container processing before publishing
    for _ in range(12):
        st_resp = requests.get(
            f"https://graph.facebook.com/{api_ver}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=20,
        )
        if st_resp.ok and st_resp.json().get("status_code") == "FINISHED":
            break
        time.sleep(5)

    pub_resp = requests.post(
        f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    pub_resp.raise_for_status()
    return str(pub_resp.json()["id"])
