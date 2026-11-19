"""Buffer + publish bookkeeping (pure): oldest story first, parts strictly in order, per-platform idempotency."""
from __future__ import annotations

from typing import Any

PLATFORMS = ("youtube", "instagram")


def next_episode(buffer: dict[str, Any], published: dict[str, Any]) -> tuple[dict, dict, list[str]] | None:
    """Return (story, episode, platforms_still_needed) for today's post, or None (skip day)."""
    eps_done = published.get("episodes", {})
    for story in buffer.get("stories", []):
        if story.get("approved") is False:  # waiting for human review of the draft release
            continue
        for ep in sorted(story["episodes"], key=lambda e: e["part"]):
            done = eps_done.get(ep["episode_id"], {})
            need = [p for p in PLATFORMS if not done.get(p, {}).get("id")]
            if need:
                return story, ep, need
    return None


def record(published: dict[str, Any], episode_id: str, platform: str, platform_id: str, at: float) -> None:
    published.setdefault("episodes", {}).setdefault(episode_id, {})[platform] = {"id": platform_id, "at": at}


def story_complete(story: dict[str, Any], published: dict[str, Any]) -> bool:
    eps = published.get("episodes", {})
    return all(all(eps.get(e["episode_id"], {}).get(p, {}).get("id") for p in PLATFORMS) for e in story["episodes"])


def prune_completed(buffer: dict[str, Any], published: dict[str, Any]) -> list[dict[str, Any]]:
    done = [s for s in buffer.get("stories", []) if story_complete(s, published)]
    buffer["stories"] = [s for s in buffer.get("stories", []) if not story_complete(s, published)]
    return done


def ready_episode_count(buffer: dict[str, Any], published: dict[str, Any]) -> int:
    eps = published.get("episodes", {})
    return sum(1 for s in buffer.get("stories", []) for e in s["episodes"]
               if not all(eps.get(e["episode_id"], {}).get(p, {}).get("id") for p in PLATFORMS))


def youtube_description(story: dict, ep: dict, prev_url: str | None, series: str) -> str:
    lines = [story["logline"], "", f"Part {ep['part']} of {ep['total']} — {series}"]
    if prev_url:
        lines.append(f"Previous part: {prev_url}")
    if ep.get("moral"):
        lines += ["", f"Moral: {ep['moral']}"]
    if ep.get("hashtags"):
        lines += ["", " ".join(h if h.startswith("#") else f"#{h}" for h in ep["hashtags"][:5])]
    return "\n".join(lines)


def instagram_caption(ep: dict) -> str:
    cap = ep.get("caption") or ""
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in ep.get("hashtags", [])[:5])
    return f"{cap}\n\n{tags}".strip()
