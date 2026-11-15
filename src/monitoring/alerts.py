"""GitHub Issue alerting with deduplication."""
from __future__ import annotations

import json
import subprocess
from typing import Optional


def open_alert_issue(
    title: str,
    body: str,
    dedup_key: str = "",
    labels: Optional[list[str]] = None,
) -> Optional[str]:
    """Open a GitHub issue for operational alerts if no open issue matches dedup_key/title."""
    marker = dedup_key or title
    try:
        listed = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--limit", "50", "--json", "number,title,body"],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode == 0 and listed.stdout.strip():
            issues = json.loads(listed.stdout)
            for issue in issues:
                if marker in (issue.get("title") or "") or (
                    dedup_key and dedup_key in (issue.get("body") or "")
                ):
                    return str(issue.get("number"))
    except Exception:
        return None

    full_body = body
    if dedup_key and dedup_key not in full_body:
        full_body = f"{body}\n\n<!-- dedup:{dedup_key} -->"

    cmd = ["gh", "issue", "create", "--title", title, "--body", full_body]
    for label in labels or ["automation-alert"]:
        cmd.extend(["--label", label])

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 and labels is None:
        # Retry without label in case the label doesn't exist yet on the repo
        res = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", full_body],
            capture_output=True,
            text=True,
            check=False,
        )
    if res.returncode == 0:
        return res.stdout.strip()
    return None
