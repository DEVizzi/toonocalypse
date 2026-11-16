"""Story / episode / release identifiers. One builder so prefixes are never doubled."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

STORY_RE = re.compile(r"^st-(\d{8})-([0-9a-f]{6})$")
EPISODE_RE = re.compile(r"^(st-\d{8}-[0-9a-f]{6})-pt(\d+)of(\d+)$")


def make_story_id(seed_text: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    digest = hashlib.sha1(f"{seed_text}|{now.isoformat()}".encode()).hexdigest()[:6]
    return f"st-{now:%Y%m%d}-{digest}"


def make_episode_id(story_id: str, part: int, total: int) -> str:
    m = EPISODE_RE.match(story_id)
    base = m.group(1) if m else story_id
    if not STORY_RE.match(base):
        raise ValueError(f"Invalid story id: {story_id!r}")
    if not 1 <= part <= total:
        raise ValueError(f"part {part} out of range 1..{total}")
    return f"{base}-pt{part}of{total}"


def parse_episode_id(episode_id: str) -> tuple[str, int, int]:
    m = EPISODE_RE.match(episode_id)
    if not m:
        raise ValueError(f"Invalid episode id: {episode_id!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def release_tag(story_id: str) -> str:
    """One draft Release per story (holds every part)."""
    base = EPISODE_RE.match(story_id).group(1) if EPISODE_RE.match(story_id) else story_id
    if not STORY_RE.match(base):
        raise ValueError(f"Invalid story id: {story_id!r}")
    return base
