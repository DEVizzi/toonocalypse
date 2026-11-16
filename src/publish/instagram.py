"""Instagram Graph API Reels publishing: resumable upload -> wait for FINISHED -> media_publish.
Idempotency: recent media captions are checked for this episode's exact caption first line before posting."""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from src.common.config import settings

GRAPH = "https://graph.facebook.com"


def _v() -> str:
    return settings()["publish"]["instagram_graph_version"]


def _tok() -> str:
    return os.environ["IG_ACCESS_TOKEN"]


def find_existing(ig_user: str, caption: str) -> str | None:
    first = caption.strip().splitlines()[0][:80] if caption.strip() else ""
    r = requests.get(f"{GRAPH}/{_v()}/{ig_user}/media", params={"fields": "id,caption", "limit": 25, "access_token": _tok()}, timeout=30)
    r.raise_for_status()
    for m in r.json().get("data", []):
        if first and (m.get("caption") or "").strip().startswith(first):
            return m["id"]
    return None


def publish_reel(ig_user: str, video: Path, caption: str, timeout_s: int = 600) -> str:
    r = requests.post(f"{GRAPH}/{_v()}/{ig_user}/media", data={"media_type": "REELS", "upload_type": "resumable",
                                                              "caption": caption, "share_to_feed": "true", "access_token": _tok()}, timeout=60)
    r.raise_for_status()
    container = r.json()["id"]
    size = video.stat().st_size
    with open(video, "rb") as f:
        up = requests.post(f"https://rupload.facebook.com/ig-api-upload/{_v()}/{container}", data=f, timeout=900,
                           headers={"Authorization": f"OAuth {_tok()}", "offset": "0", "file_size": str(size)})
    up.raise_for_status()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = requests.get(f"{GRAPH}/{_v()}/{container}", params={"fields": "status_code,status", "access_token": _tok()}, timeout=30).json()
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    pub = requests.post(f"{GRAPH}/{_v()}/{ig_user}/media_publish", data={"creation_id": container, "access_token": _tok()}, timeout=60)
    pub.raise_for_status()
    return pub.json()["id"]
