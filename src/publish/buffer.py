"""Ordered episode buffer (state/buffer.json) with story-order enforcement (§6.3)."""
from __future__ import annotations

from typing import Any

from src.common.state import load_state, save_state


def load_buffer() -> dict[str, Any]:
    return load_state("buffer.json", {"episodes": []})


def buffer_size() -> int:
    return len(load_buffer().get("episodes", []))


def add_to_buffer(entry: dict[str, Any]) -> dict[str, Any]:
    """Append a publishable episode entry to state/buffer.json (idempotent by episode_id)."""
    if not entry.get("publishable", False):
        raise ValueError("Refusing to buffer a non-publishable episode")
    buf = load_buffer()
    eps = buf.setdefault("episodes", [])
    if not any(e.get("episode_id") == entry.get("episode_id") for e in eps):
        eps.append(entry)
    save_state("buffer.json", buf)
    return buf


def remove_from_buffer(episode_id: str) -> dict[str, Any]:
    buf = load_buffer()
    buf["episodes"] = [e for e in buf.get("episodes", []) if e.get("episode_id") != episode_id]
    save_state("buffer.json", buf)
    return buf


def pick_next_publishable(pub_state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Pick the next buffered episode respecting strict story part order (§6.3).

    If part N of a multi-part story is not yet published and missing from the buffer,
    never skip ahead to part N+1; pick a buffered One-Shot instead, or return None.
    """
    buf = load_buffer()
    episodes = buf.get("episodes", [])
    if not episodes:
        return None

    pub = pub_state if pub_state is not None else load_state("published.json", {"episodes": {}})
    pub_eps = pub.get("episodes", {})

    def _is_fully_published(ep_id: str) -> bool:
        rec = pub_eps.get(ep_id, {})
        return bool(rec.get("youtube", {}).get("id") and rec.get("instagram", {}).get("id"))

    # Group buffered episodes by story_id
    for entry in episodes:
        ep_id = entry["episode_id"]
        if _is_fully_published(ep_id):
            continue
        part_num = int(entry.get("part_num", 1))
        part_count = int(entry.get("part_count", 1))
        story_id = entry.get("story_id", "")

        if part_count <= 1 or part_num == 1:
            return entry

        # For part N > 1, ensure all earlier parts 1..N-1 are already published!
        prev_ok = True
        for prev_p in range(1, part_num):
            prev_id = f"{story_id}-pt{prev_p}of{part_count}"
            if not _is_fully_published(prev_id):
                prev_ok = False
                break
        if prev_ok:
            return entry

    # Fallback: pick any buffered One-Shot
    for entry in episodes:
        if int(entry.get("part_count", 1)) <= 1 and not _is_fully_published(entry["episode_id"]):
            return entry

    return None
