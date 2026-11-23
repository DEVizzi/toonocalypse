"""YouTube OAuth refresh-token keep-alive / health check (v4.3.1 production launch).

Exchanges the long-lived YOUTUBE_REFRESH_TOKEN for a short-lived access token and proves it works against the
YouTube Data API (`channels.list?mine=true`, 1 quota unit). Run on a schedule so the refresh token is exercised well
inside Google's inactivity window and so a revoked/expired token fails LOUDLY days before an upload would.

Security: credentials come ONLY from environment variables (GitHub Actions secrets); they are sent in the POST
body / Authorization header (never in URLs) and are never printed or logged. Any failure exits non-zero (fail closed).

Usage:  python -m src.publish.oauth          # exit 0 = healthy, 1 = broken (job fails, GitHub emails the owner)
"""
from __future__ import annotations

import os
import sys


def _requests():
    import requests
    return requests


TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
REQUIRED = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
TIMEOUT_S = 20


class OAuthError(RuntimeError):
    """Raised with a redacted, generic message (never contains secrets)."""


def _creds() -> dict[str, str]:
    aliases = {
        "YOUTUBE_CLIENT_ID": ("YOUTUBE_CLIENT_ID", "YT_CLIENT_ID"),
        "YOUTUBE_CLIENT_SECRET": ("YOUTUBE_CLIENT_SECRET", "YT_CLIENT_SECRET"),
        "YOUTUBE_REFRESH_TOKEN": ("YOUTUBE_REFRESH_TOKEN", "YT_REFRESH_TOKEN"),
    }
    out: dict[str, str] = {}
    missing: list[str] = []
    for canonical, keys in aliases.items():
        val = next(((os.environ.get(k) or "").strip() for k in keys if (os.environ.get(k) or "").strip()), "")
        if not val:
            missing.append(canonical)
        else:
            out[canonical] = val
    if missing:
        raise OAuthError(f"missing required secret(s): {', '.join(missing)}")
    return out


def access_token() -> tuple[str, int, str]:
    """Returns (access_token, expires_in_s, granted_scopes). Raises OAuthError on any failure."""
    c = _creds()
    req = _requests()
    try:
        resp = req.post(TOKEN_URL, data={
            "client_id": c["YOUTUBE_CLIENT_ID"],
            "client_secret": c["YOUTUBE_CLIENT_SECRET"],
            "refresh_token": c["YOUTUBE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }, timeout=TIMEOUT_S)
    except req.RequestException as exc:
        raise OAuthError(f"token endpoint unreachable ({type(exc).__name__})") from None
    if resp.status_code != 200:
        try:
            err = str(resp.json().get("error", "unknown"))[:40]
        except ValueError:
            err = "unparseable"
        hint = (" -> refresh token revoked/expired: re-run the OAuth consent flow and update YOUTUBE_REFRESH_TOKEN"
                if err == "invalid_grant" else "")
        raise OAuthError(f"token refresh failed: HTTP {resp.status_code} ({err}){hint}")
    body = resp.json()
    tok = body.get("access_token")
    if not tok:
        raise OAuthError("token refresh returned no access_token")
    return tok, int(body.get("expires_in", 0)), str(body.get("scope", ""))


def check_channel(token: str) -> int:
    """Proves the access token works for YouTube; returns the number of channels on the account."""
    req = _requests()
    try:
        resp = req.get(CHANNELS_URL, params={"part": "id", "mine": "true"},
                       headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_S)
    except req.RequestException as exc:
        raise OAuthError(f"YouTube API unreachable ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise OAuthError(f"YouTube channels.list failed: HTTP {resp.status_code}")
    return len(resp.json().get("items") or [])


def channel_identity(token: str) -> tuple[str, str]:
    """(channel_id, channel_title) the token is bound to (public info, safe to log)."""
    req = _requests()
    try:
        resp = req.get(CHANNELS_URL, params={"part": "snippet", "mine": "true"},
                       headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_S)
    except req.RequestException as exc:
        raise OAuthError(f"YouTube API unreachable ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise OAuthError(f"YouTube channels.list failed: HTTP {resp.status_code}")
    items = resp.json().get("items") or []
    if not items:
        return "", ""
    return str(items[0].get("id") or ""), str((items[0].get("snippet") or {}).get("title") or "")


def assert_expected_channel(token: str) -> str:
    """Fails closed if YOUTUBE_EXPECTED_CHANNEL_ID is set and the token belongs to another channel
    (the Google account owns several brand channels; a wrong pick at consent time must never upload elsewhere)."""
    expected = (os.environ.get("YOUTUBE_EXPECTED_CHANNEL_ID") or "").strip()
    cid, title = channel_identity(token)
    if expected and cid != expected:
        raise OAuthError(f"token is bound to channel {title or '?'} ({cid or 'none'}), expected {expected}")
    return cid


def main() -> int:
    try:
        tok, ttl, scopes = access_token()
        n = check_channel(tok)
        cid, title = channel_identity(tok)
        expected = (os.environ.get("YOUTUBE_EXPECTED_CHANNEL_ID") or "").strip()
    except OAuthError as exc:
        print(f"[OAUTH FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OAUTH OK] bound channel: {title or '?'} ({cid or 'none'})")
    try:   # the Google Cloud project NUMBER of the OAuth client (not a secret) - shows which consent screen applies
        print(f"[OAUTH OK] OAuth client project: {_creds()['YOUTUBE_CLIENT_ID'].split('-', 1)[0]}")
    except Exception:  # noqa: BLE001
        pass
    if expected and cid != expected:
        print(f"[OAUTH FAIL] token is bound to the wrong channel (expected {expected}); re-run "
              "scripts/youtube_reauth.py and pick the ToonToonCastle channel", file=sys.stderr)
        return 1
    granted = {s.rsplit("/", 1)[-1] for s in scopes.split()}
    upload_ok = bool(granted & {"youtube.upload", "youtube", "youtube.force-ssl", "youtubepartner"})
    manage_ok = bool(granted & {"youtube", "youtube.force-ssl", "youtubepartner"})
    print(f"[OAUTH OK] access token refreshed (ttl {ttl}s), channels visible: {n}, "
          f"upload scope: {'yes' if upload_ok else 'NO'}, scopes: {', '.join(sorted(granted)) or 'unknown'}")
    if not manage_ok:
        print("[OAUTH WARN] token lacks youtube.force-ssl: auto-comments, title/description updates and rollback "
              "deletes of partial uploads will fail. Re-run OAuth consent with youtube.upload + youtube.force-ssl.")
    if n < 1:
        print("[OAUTH FAIL] token is valid but sees no YouTube channel", file=sys.stderr)
        return 1
    if not upload_ok:
        print("[OAUTH FAIL] refresh token lacks the youtube.upload scope", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
