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
    video_url: str | None = None,
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
    init_resp = requests.post(f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media", params=init_params, timeout=30)
    used_video_url = False
    if not init_resp.ok and video_url:
        print(f"[instagram] resumable init failed ({init_resp.status_code}: {init_resp.text[:250]}); trying video_url...")
        url_params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": full_caption,
            "access_token": token,
        }
        if cover_url:
            url_params["cover_url"] = cover_url
        init_resp = requests.post(f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media", params=url_params, timeout=30)
        used_video_url = True
    if not init_resp.ok:
        raise RuntimeError(f"Instagram media init failed ({init_resp.status_code}): {init_resp.text}")
    init_data = init_resp.json()
    container_id = init_data["id"]

    if not used_video_url:
        upload_uri = init_data["uri"]
        file_size = video_path.stat().st_size
        with open(video_path, "rb") as f:
            up_resp = requests.post(
                upload_uri,
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(file_size)},
                data=f,
                timeout=180,
            )
        if not up_resp.ok:
            raise RuntimeError(f"Instagram upload failed ({up_resp.status_code}): {up_resp.text}")

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
