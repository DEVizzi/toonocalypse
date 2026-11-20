"""Standardized ToonToonCastle v4.4 upload metadata for YouTube Shorts & Instagram Reels."""
from __future__ import annotations

from typing import Any

from src.characters.roster import HERO_BY_KEY
from src.narration.script import ARENA_NAMES

HASHTAGS = "#ToonToonCastle #physics #marblerace #shorts #reels"
DEFAULT_TAGS = [
    "ToonToonCastle",
    "marble race",
    "physics",
    "ball race",
    "shorts",
    "reels",
    "cartoon",
]


def arena_display_name(arena_key: str) -> str:
    return ARENA_NAMES.get(arena_key) or str(arena_key).replace("_", " ").title()


def build_upload_metadata(arena_key: str, outcome: Any, cta_prompt: str) -> dict[str, Any]:
    """Returns {'title', 'description', 'ig_caption', 'tags'} following the v4.4 ToonToonCastle spec:
    - YouTube Shorts Title: `{ARENA_NAME} Chaos! S{S} E{E} | ToonToonCastle #shorts`
    - Description/Caption (YT & IG): Concise hook + current season/race tag + CTA +
      `#ToonToonCastle #physics #marblerace #shorts #reels`
    """
    s_num = int(getattr(outcome, "season_number", 1))
    e_num = int(getattr(outcome, "race_number", 1))
    arena_name = arena_display_name(arena_key)
    w_key = str(getattr(outcome, "winner_key", "") or "")
    w_name = HERO_BY_KEY[w_key].name if w_key in HERO_BY_KEY else "A wildcard"
    ribbon = str(getattr(outcome, "ribbon_text", None) or f"SEASON {s_num} • RACE {e_num} / 30")
    is_final = bool(getattr(outcome, "is_grand_final", False))

    title = f"{arena_name} Chaos! S{s_num} E{e_num} | ToonToonCastle #shorts"
    if len(title) > 100:
        short_arena = arena_name[: max(8, 100 - len(f" Chaos! S{s_num} E{e_num} | ToonToonCastle #shorts"))].rstrip()
        title = f"{short_arena} Chaos! S{s_num} E{e_num} | ToonToonCastle #shorts"

    hook = (
        f"{w_name} claims the Season {s_num} Crown in {arena_name} Chaos!"
        if is_final
        else f"{w_name} survives {arena_name} Chaos! ({ribbon})"
    )
    cta = (cta_prompt or "Who takes the next race? Drop your pick below!").strip()
    body = (
        f"{hook}\n"
        f"Daily Season {s_num} League action on @ToonToonCastle!\n\n"
        f"{cta}\n\n"
        f"{HASHTAGS}"
    )
    return {
        "title": title,
        "description": body,
        "ig_caption": body,
        "tags": list(DEFAULT_TAGS),
    }
