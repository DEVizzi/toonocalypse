"""GitHub Issue alerting with deduplication, updates, and auto-close (§6.4)."""
from __future__ import annotations

import json
import subprocess
from typing import Optional


def _find_open_issue(marker: str) -> Optional[str]:
    try:
        listed = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--limit", "50", "--json", "number,title,body"],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode == 0 and listed.stdout.strip():
            for issue in json.loads(listed.stdout):
                if marker in (issue.get("title") or "") or marker in (issue.get("body") or ""):
                    return str(issue.get("number"))
    except Exception:
        pass
    return None


def open_alert_issue(
    title: str,
    body: str,
    dedup_key: str = "",
    labels: Optional[list[str]] = None,
) -> Optional[str]:
    """Create or update a single deduplicated GitHub Issue for operational alerts."""
    marker = dedup_key or title
    full_body = f"{body}\n\n<!-- dedup:{marker} -->" if marker not in body else body

    existing = _find_open_issue(marker)
    if existing:
        subprocess.run(
            ["gh", "issue", "edit", existing, "--title", title, "--body", full_body],
            capture_output=True,
            text=True,
            check=False,
        )
        return existing

    cmd = ["gh", "issue", "create", "--title", title, "--body", full_body]
    for label in labels or ["automation-alert"]:
        cmd.extend(["--label", label])
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 and labels is None:
        res = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", full_body],
            capture_output=True,
            text=True,
            check=False,
        )
    if res.returncode == 0:
        return res.stdout.strip()
    return None


def close_alert_issue(dedup_key: str, comment: str = "Resolved automatically.") -> None:
    """Close any open alert issue matching dedup_key."""
    existing = _find_open_issue(dedup_key)
    if existing:
        subprocess.run(
            ["gh", "issue", "close", existing, "--comment", comment],
            capture_output=True,
            text=True,
            check=False,
        )
