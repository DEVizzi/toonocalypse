"""Canonical episode ID and GitHub Release tag builders (§7)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

EPISODE_ID_RE = re.compile(r"^ep-(\d{8})-([0-9a-f]{6})-pt(\d+)of(\d+)$")


def make_story_id(now: datetime | None = None, hex_id: str | None = None) -> str:
    """Return canonical story_id 'ep-YYYYMMDD-<6hex>'."""
    dt = now or datetime.now(timezone.utc)
    suffix = (hex_id or uuid.uuid4().hex)[:6].lower()
    return f"ep-{dt.strftime('%Y%m%d')}-{suffix}"


def make_episode_id(story_id: str, part_num: int, part_count: int) -> str:
    """Return canonical episode_id 'ep-YYYYMMDD-<hash>-ptXofN' without doubling 'ep-'."""
    clean = story_id.strip()
    if clean.startswith("ep-ep-"):
        clean = clean[3:]
    if not clean.startswith("ep-"):
        clean = f"ep-{clean}"
    return f"{clean}-pt{int(part_num)}of{int(part_count)}"


def make_release_tag(episode_id: str) -> str:
    """Return the GitHub Release tag for an episode (identical to canonical episode_id)."""
    clean = episode_id.strip()
    if clean.startswith("ep-ep-"):
        clean = clean[3:]
    if not EPISODE_ID_RE.match(clean):
        raise ValueError(f"Invalid canonical episode_id: {episode_id!r}")
    return clean


def parse_episode_id(episode_id: str) -> dict[str, int | str] | None:
    """Parse canonical episode_id into components, or None if invalid."""
    m = EPISODE_ID_RE.match(episode_id.strip())
    if not m:
        return None
    return {
        "date": m.group(1),
        "hash": m.group(2),
        "part_num": int(m.group(3)),
        "part_count": int(m.group(4)),
    }
