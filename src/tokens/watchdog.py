"""Daily token watchdog (§13)."""
from __future__ import annotations

from src.monitoring.alerts import open_alert_issue
from src.tokens.instagram_auth import check_instagram_token, refresh_instagram_token, should_refresh_instagram
from src.tokens.youtube_auth import check_youtube_token


def run_watchdog() -> dict[str, object]:
    yt = check_youtube_token()
    ig = check_instagram_token()
    if ig.get("status") == "valid" and should_refresh_instagram(ig.get("expires_at")):
        try:
            ig = refresh_instagram_token()
        except Exception as exc:
            ig["last_error"] = type(exc).__name__

    problems = []
    if yt.get("status") != "valid":
        problems.append(f"YouTube token invalid ({yt.get('last_error')})")
    if ig.get("status") != "valid":
        problems.append(f"Instagram token invalid ({ig.get('last_error')})")

    if problems:
        open_alert_issue(
            title="[Alert] Token Watchdog: Refresh Needed",
            body="Publishing paused safely until tokens are valid:\n- " + "\n- ".join(problems),
            dedup_key="token-watchdog",
        )
    return {"youtube": yt, "instagram": ig, "problems": problems}
