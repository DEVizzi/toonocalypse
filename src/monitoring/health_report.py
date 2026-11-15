"""Weekly pipeline health report generator."""
from __future__ import annotations

from datetime import datetime, timezone

from src.monitoring.alerts import open_alert_issue
from src.monitoring.metrics import collect_pipeline_metrics
from src.publish.releases import list_buffer_releases


def build_health_report_markdown() -> str:
    """Build a markdown summary of Toonocalypse pipeline health."""
    metrics = collect_pipeline_metrics()
    try:
        buffer_releases = list_buffer_releases()
    except Exception:
        buffer_releases = []

    quota = metrics.get("quota", {})
    tokens = metrics.get("tokens", {})
    lines = [
        "# Toonocalypse Weekly Health Report",
        f"- Generated: `{metrics['generated_at']}`",
        f"- Published episodes: **{metrics['published_total']}** (YT: {metrics['youtube_published']}, IG: {metrics['instagram_published']})",
        f"- Buffered releases ready: **{len(buffer_releases)}**",
        f"- Active arc: `{metrics.get('active_arc')}`",
        f"- Used story ideas: `{metrics['used_ideas_count']}`",
        f"- Recent QA pass rate: **{metrics['qa_recent_pass']}/{metrics['qa_recent_total']}**",
        f"- Daily Quota: `{quota}`",
        f"- Tokens: YT refreshed `{tokens.get('youtube_last_refresh')}`, IG refreshed `{tokens.get('instagram_last_refresh')}`, IG expires `{tokens.get('instagram_expires_at')}`",
    ]
    return "\n".join(lines)


def publish_weekly_health_report(dry_run: bool = False) -> str:
    """Create or update the weekly health report issue."""
    week_tag = datetime.now(timezone.utc).strftime("%G-W%V")
    body = build_health_report_markdown()
    if not dry_run:
        open_alert_issue(
            title=f"[Toonocalypse] Weekly Health Report ({week_tag})",
            body=body,
            dedup_key=f"weekly-health-{week_tag}",
            labels=["health-report"],
        )
    return body
