"""Instagram Graph API long-lived token refresh & secret rotation (§13)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.common.config import load_settings
from src.common.secrets_sync import update_github_secret
from src.common.state import load_state, save_state


def days_remaining(expires_at_iso: str | None, now: datetime | None = None) -> float | None:
    if not expires_at_iso:
        return None
    ref = now or datetime.now(timezone.utc)
    exp = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
    return (exp - ref).total_seconds() / 86400.0


def should_refresh_instagram(expires_at_iso: str | None, threshold_days: float = 20.0, now: datetime | None = None) -> bool:
    rem = days_remaining(expires_at_iso, now=now)
    if rem is None:
        return True
    return rem < threshold_days


def refresh_instagram_token(force: bool = False) -> dict[str, Any]:
    state = load_state("tokens.json", {"youtube": {}, "instagram": {}})
    ig_state = state.get("instagram", {})
    now = datetime.now(timezone.utc)

    if not force and not should_refresh_instagram(ig_state.get("expires_at"), threshold_days=20.0, now=now):
        return ig_state

    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("IG_ACCESS_TOKEN is not set")

    ver = load_settings().get("instagram_api_version", "v21.0")
    resp = requests.get(
        f"https://graph.instagram.com/{ver}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=20,
    )
    new_token = token
    expires_in = 60 * 86400
    if resp.ok:
        payload = resp.json()
        new_token = payload.get("access_token") or token
        expires_in = int(payload.get("expires_in", 60 * 86400))
    else:
        fb_id = os.environ.get("FB_APP_ID", "").strip()
        fb_sec = os.environ.get("FB_APP_SECRET", "").strip()
        if fb_id and fb_sec:
            fb_resp = requests.get(
                f"https://graph.facebook.com/{ver}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": fb_id,
                    "client_secret": fb_sec,
                    "fb_exchange_token": token,
                },
                timeout=20,
            )
            fb_resp.raise_for_status()
            payload = fb_resp.json()
            new_token = payload.get("access_token") or token
            expires_in = int(payload.get("expires_in", 60 * 86400))
        else:
            # Verify Facebook Page/Graph token is still valid (Page tokens from long-lived user tokens do not expire)
            checked = check_instagram_token()
            if checked.get("status") != "valid":
                resp.raise_for_status()
            return checked

    if os.environ.get("GH_PAT_SECRETS") and os.environ.get("GITHUB_REPOSITORY"):
        update_github_secret("IG_ACCESS_TOKEN", new_token)

    ig_state.update({
        "status": "valid",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
        "last_refreshed": now.isoformat(),
        "last_checked": now.isoformat(),
        "last_error": None,
    })
    state["instagram"] = ig_state
    save_state("tokens.json", state)
    return ig_state


def check_instagram_token() -> dict[str, Any]:
    state = load_state("tokens.json", {"youtube": {}, "instagram": {}})
    ig_state = state.get("instagram", {})
    now = datetime.now(timezone.utc).isoformat()
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    user_id = os.environ.get("IG_USER_ID", "")
    ver = load_settings().get("instagram_api_version", "v21.0")
    try:
        resp = requests.get(
            f"https://graph.facebook.com/{ver}/{user_id}",
            params={"fields": "id,username", "access_token": token},
            timeout=20,
        )
        resp.raise_for_status()
        ig_state["status"] = "valid"
        ig_state["last_checked"] = now
        ig_state["last_error"] = None
    except Exception as exc:
        ig_state["status"] = "invalid"
        ig_state["last_checked"] = now
        ig_state["last_error"] = type(exc).__name__
    state["instagram"] = ig_state
    save_state("tokens.json", state)
    return ig_state
