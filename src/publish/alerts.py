"""GitHub Issue alerting helper for autonomous publishing & token maintenance (v4.4).

Security:
- Never interpolates or logs tokens/secrets; scrubs any accidental credential-like substrings before posting.
- Invokes `gh` directly via argument list (`shell=False`) with a strict timeout; fails gracefully if `gh` or
  repository context is unavailable so alerting itself never crashes state persistence.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

_REDACT_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{12,}"),
    re.compile(r"EAA[0-9A-Za-z_\-]{16,}"),
    re.compile(r"IGAA[0-9A-Za-z_\-]{16,}"),
    re.compile(r"IGQV[0-9A-Za-z_\-]{16,}"),
    re.compile(r"gh[pousr]_[0-9A-Za-z_]{16,}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-.]{16,}"),
    re.compile(r"1//[0-9A-Za-z_\-]{16,}"),
)


def redact(text: str) -> str:
    out = str(text or "")
    for rx in _REDACT_PATTERNS:
        out = rx.sub("[REDACTED]", out)
    return out[:1200]


def open_alert_issue(title: str, body: str) -> bool:
    """Opens a GitHub Issue on GITHUB_REPOSITORY via `gh issue create`. Returns True if created."""
    gh = shutil.which("gh")
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = (os.environ.get("GITHUB_ISSUE_TOKEN") or os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or "").strip()
    if not gh or not repo or not token or not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
        print(f"[ALERT] (local/no-gh) {redact(title)}: {redact(body)}")
        return False
    env = {**os.environ, "GH_TOKEN": token}
    run_url = ""
    run_id = (os.environ.get("GITHUB_RUN_ID") or "").strip()
    server = (os.environ.get("GITHUB_SERVER_URL") or "https://github.com").strip()
    if run_id.isdigit():
        run_url = f"\n\nWorkflow Run: {server}/{repo}/actions/runs/{run_id}"
    safe_title = redact(title).replace("\n", " ")[:180]
    safe_body = redact(body) + run_url
    try:
        res = subprocess.run(
            [gh, "issue", "create", "--repo", repo, "--title", safe_title, "--body", safe_body],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if res.returncode == 0:
            print(f"[ALERT ISSUE OPENED] {res.stdout.strip()}")
            return True
        print(f"[ALERT ISSUE WARN] gh issue create exited {res.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[ALERT ISSUE WARN] {type(exc).__name__}")
    return False
