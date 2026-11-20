"""60-Day Long-Lived Instagram Graph API Token Maintenance (v4.4).

Runs on cron `0 10 1,15 * *` (1st & 15th of each month) and supports manual `--force`:
- Checks repository variable `IG_TOKEN_REFRESHED_AT` (ISO-8601 UTC date) so it refreshes when token age >= 45 days
  (or immediately if `IG_TOKEN_REFRESHED_AT` has never been recorded or `--force` is passed).
- Supports BOTH Meta Business Graph (`META_APP_ID` + `META_APP_SECRET` -> `fb_exchange_token`) AND Instagram Login
  (`ig_refresh_token`) long-lived token endpoints.
- Writes the refreshed token directly into GitHub Actions Secret `IG_ACCESS_TOKEN` via stdin (`gh secret set`) and
  updates `IG_TOKEN_REFRESHED_AT` via `gh variable set`.
- Opens a GitHub Issue alert immediately if refresh or secret update fails.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys

import requests

from src.publish.alerts import open_alert_issue, redact

FB_TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
IG_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
MIN_AGE_DAYS = 45
TIMEOUT_S = 25
_SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class IGTokenError(RuntimeError):
    """Redacted token refresh failure."""


def _gh_context() -> tuple[str, str, dict[str, str]]:
    gh = shutil.which("gh")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    pat = (os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or "").strip()
    if not gh or not repo or not pat or not _SAFE_REPO.match(repo):
        raise IGTokenError("GH_PAT (with actions/secrets scope) and GITHUB_REPOSITORY are required")
    return gh, repo, {**os.environ, "GH_TOKEN": pat}


def last_refresh_age_days(gh: str, repo: str, env: dict[str, str]) -> float | None:
    res = subprocess.run(
        [gh, "variable", "get", "IG_TOKEN_REFRESHED_AT", "--repo", repo],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        stamp = dt.datetime.fromisoformat(res.stdout.strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds() / 86400.0
    except ValueError:
        return None


def refresh_long_lived_token() -> tuple[str, int]:
    """Exchanges current `IG_ACCESS_TOKEN` for a fresh 60-day token. Returns (new_token, expires_in_seconds)."""
    cur = (os.environ.get("IG_ACCESS_TOKEN") or "").strip()
    if not cur:
        raise IGTokenError("missing required secret: IG_ACCESS_TOKEN")
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()

    try:
        if app_id and app_secret and not cur.startswith("IGAA"):
            resp = requests.post(
                FB_TOKEN_URL,
                data={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": cur,
                },
                timeout=TIMEOUT_S,
            )
        else:
            resp = requests.get(
                IG_REFRESH_URL,
                headers={"Authorization": f"Bearer {cur}"},
                params={"grant_type": "ig_refresh_token"},
                timeout=TIMEOUT_S,
            )
    except requests.RequestException as exc:
        raise IGTokenError(f"Meta/Instagram token endpoint unreachable ({type(exc).__name__})") from None

    if resp.status_code != 200:
        msg = ""
        try:
            msg = str(((resp.json() or {}).get("error") or {}).get("message", ""))[:120]
        except ValueError:
            msg = "non-JSON response"
        hint = " (provide META_APP_ID and META_APP_SECRET if using a Facebook-Login EAA token)" if not app_id else ""
        raise IGTokenError(f"token refresh failed: HTTP {resp.status_code} ({redact(msg)}){hint}")

    body = resp.json() or {}
    new_tok = str(body.get("access_token") or "").strip()
    if not new_tok:
        raise IGTokenError("token refresh response contained no access_token")
    return new_tok, int(body.get("expires_in", 0))


def main(argv: list[str] | None = None) -> int:
    args = set(argv or [])
    force = "--force" in args
    try:
        gh, repo, env = _gh_context()
        age = last_refresh_age_days(gh, repo, env)
        if not force and age is not None and age < MIN_AGE_DAYS:
            print(f"[IG TOKEN OK] last refreshed {age:.1f} days ago (< {MIN_AGE_DAYS}d threshold); skipping refresh")
            return 0

        new_tok, ttl_s = refresh_long_lived_token()
        upd = subprocess.run(
            [gh, "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo],
            input=new_tok,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if upd.returncode != 0:
            raise IGTokenError(
                f"gh secret set IG_ACCESS_TOKEN failed (exit {upd.returncode}) — ensure GH_PAT has repo secrets:write"
            )
        now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        subprocess.run(
            [gh, "variable", "set", "IG_TOKEN_REFRESHED_AT", "--body", now_iso, "--repo", repo],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        print(f"[IG TOKEN REFRESHED] updated IG_ACCESS_TOKEN secret (ttl ~{ttl_s // 86400}d, stamped {now_iso})")
        return 0
    except IGTokenError as exc:
        msg = redact(str(exc))
        print(f"[IG TOKEN FAIL] {msg}", file=sys.stderr)
        open_alert_issue(
            "[ToonToonCastle Alert] Instagram 60-Day Token Refresh Failed",
            f"Automated 45-day refresh of `IG_ACCESS_TOKEN` failed:\n\n`{msg}`\n\n"
            "Action required: refresh the Instagram Graph API long-lived token and update `IG_ACCESS_TOKEN` "
            "(and verify `META_APP_ID`, `META_APP_SECRET`, and `GH_PAT`).",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
