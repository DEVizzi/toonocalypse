"""Alert Issue: one open issue labelled 'toonocalypse-alert', updated (not duplicated), closed after the next success."""
from __future__ import annotations

import json
import subprocess

LABEL = "toonocalypse-alert"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def open_or_update(title: str, body: str) -> None:
    _gh("label", "create", LABEL, "--color", "D93F0B", "--force")
    res = _gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1")
    issues = json.loads(res.stdout or "[]")
    if issues:
        _gh("issue", "edit", str(issues[0]["number"]), "--title", title, "--body", body)
    else:
        _gh("issue", "create", "--title", title, "--body", body, "--label", LABEL)
    print(f"[alert] {title}", flush=True)


def close_if_open(note: str = "Recovered: the next run succeeded.") -> None:
    res = _gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "5")
    for it in json.loads(res.stdout or "[]"):
        _gh("issue", "close", str(it["number"]), "--comment", note)
