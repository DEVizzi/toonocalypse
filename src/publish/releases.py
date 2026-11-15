"""GitHub Releases storage for buffered episodes and story releases (§12)."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def upload_episode_to_release(tag: str, files: list[Path], title: str, notes: str = "", draft: bool = False) -> None:
    view = subprocess.run(["gh", "release", "view", tag], capture_output=True, text=True)
    if view.returncode != 0:
        cmd = ["gh", "release", "create", tag, "--title", title, "--notes", notes or "Toonocalypse automated release"]
        if draft:
            cmd.append("--draft")
        subprocess.run(cmd, check=True)
    for f in files:
        if f.exists():
            subprocess.run(["gh", "release", "upload", tag, str(f), "--clobber"], check=True)


def download_release_assets(tag: str, dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", tag, "--dir", str(dest_dir), "--clobber"], check=True)
    return sorted(dest_dir.iterdir())


def list_buffer_releases() -> list[dict[str, Any]]:
    res = subprocess.run(
        ["gh", "release", "list", "--json", "tagName,name,createdAt,isDraft", "--limit", "50"],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return []
    releases = json.loads(res.stdout)
    return [r for r in releases if r.get("tagName", "").startswith("buffer-")]


def cleanup_old_releases(retention_days: int = 30) -> list[str]:
    res = subprocess.run(
        ["gh", "release", "list", "--json", "tagName,createdAt", "--limit", "100"],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted: list[str] = []
    for r in json.loads(res.stdout):
        tag = r.get("tagName", "")
        if not tag.startswith("story-"):
            continue
        created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        if created < cutoff:
            subprocess.run(["gh", "release", "delete", tag, "--yes"], check=False)
            deleted.append(tag)
    return deleted
