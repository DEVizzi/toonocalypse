"""ToonToonCastle v4.6 viral-SEO upload metadata for YouTube Shorts & Instagram Reels.

Rules (2025 Shorts/Reels ranking research):
- Title: spoiler-free "pick a ball" / curiosity hook first, niche keyword second, <= 60 chars. No `#shorts` (YouTube
  auto-detects vertical Shorts) and no channel name (already shown on the Shorts overlay). Rotates daily.
- Never reveal the race winner in the title, the description, the Instagram caption or the auto-comments: viewers
  must watch to the end to find out (watch time / swipe-away rate is the #1 ranking signal on both platforms).
- YouTube description: keyword sentences + one-word comment CTA + series line + 4 hashtags (comments drive Shorts).
- Instagram caption: keyword headline (IG search indexes captions) + comment CTA + DM-share prompt (sends per reach
  is a top Reels signal) + series line + 5 hashtags (Instagram's hard cap).
- Tags: truthful niche keywords only (<= 15 tags, <= 30 chars each).
- First-comment copy for YouTube (pin it manually; the API cannot pin) and Instagram.
"""
from __future__ import annotations

from typing import Any, Sequence

from src.characters.roster import HERO_BY_KEY, HEROES
from src.narration.script import ARENA_NAMES

METADATA_VERSION = "4.6"
TITLE_MAX = 60
IG_HEADLINE_MAX = 125
TAGS_MAX = 15
TAG_CHARS_BUDGET = 450
DEFAULT_CATEGORY_ID = "20"     # Gaming (matches config/settings.yaml `youtube_category_id`)
SCHEDULE_LINE = "new race every day at 8 PM IST"

YT_HASHTAGS = ("#marblerace", "#marblerun", "#satisfying", "#ToonToonCastle")
IG_HASHTAGS = ("#marblerace", "#marblerun", "#satisfyingvideos", "#ballrace", "#toontooncastle")

BASE_TAGS = (
    "marble race", "marble run", "ball race", "pick a ball", "guess the winner", "marble race elimination",
    "satisfying video", "physics simulation", "cartoon race", "marble league", "ToonToonCastle",
)
GOAL_TAGS: dict[str, tuple[str, ...]] = {
    "reach_finish": ("race to the finish",),
    "last_one_standing": ("last ball standing", "marble battle royale"),
    "survive_timer": ("survival challenge",),
    "collect_items": ("crown rush",),
    "hold_a_zone": ("king of the hill",),
    "push_others_out": ("marble battle royale", "knockout battle"),
    "hot_potato_bomb": ("hot potato",),
}

# Signature feature of every arena (keyword-rich, truthful description of what viewers will see)
ARENA_FEATURES: dict[str, str] = {
    "rotating_disc": "a shrinking spinning disc",
    "ramp_descent": "steep downhill ramps",
    "pachinko_drop": "a pachinko peg drop",
    "sumo_pool_pit": "a sumo pit",
    "crumbling_bridge": "a crumbling bridge",
    "collapse_tower": "a collapsing tower",
    "crusher_gauntlet": "giant crushers",
    "flat_track": "a flat-out sprint track",
    "pit_platforms": "platforms over bottomless pits",
    "tiered_tower": "a tiered tower drop",
    "narrow_bridge": "a razor-thin bridge",
    "bouncy_pad_field": "bouncy launch pads",
    "seesaw_gauntlet": "wobbly seesaws",
    "conveyor_chaos": "runaway conveyor belts",
    "maze_corridors": "a twisting maze",
    "hex_tile_drop": "hex tiles that drop away",
    "bumper_ring": "a ring of bumpers",
}
HAZARD_WORDS: dict[str, str] = {
    "spinning_bars": "spinning bars",
    "swinging_hammers": "swinging hammers",
    "falling_floor_tiles": "falling floor tiles",
    "rolling_boulders": "rolling boulders",
    "wind_gusts": "wind gusts",
    "lava_floor": "a lava floor",
    "moving_walls": "moving walls",
    "cannon_balls": "cannonballs",
    "slippery_ice": "slippery ice",
    "sticky_mud": "sticky mud",
}

# Spoiler-free hooks per goal (first template = strongest; rotated day by day). `{arena}` is optional.
TITLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "reach_finish": (
        "Only ONE Ball Can Win 😱 {arena} Marble Race",
        "Pick a Ball Before the Gate Drops! 🏁 {arena}",
        "Which Ball Wins the {arena}? 🏁 Marble Race",
        "Guess the Winner! 🏁 {arena} Marble Race",
    ),
    "last_one_standing": (
        "Only ONE Ball Survives the {arena} 😱",
        "Last Ball Standing Wins 👑 {arena} Marble Race",
        "Marble Battle Royale: Last Ball Standing Wins 👑",
    ),
    "survive_timer": (
        "Survive the Clock or You're OUT ⏱️ Pick a Ball!",
        "Can Your Ball Survive the {arena}? ⏱️",
    ),
    "collect_items": (
        "Crown Rush! Which Ball Grabs the Most? 👑",
        "Grab the Most Crowns to Win 👑 Pick a Ball!",
        "Pick a Ball! {arena} Crown Rush 👑",
    ),
    "hold_a_zone": (
        "King of the Hill: Which Ball Holds On? 👑",
        "Hold the Zone to Win! 👑 Pick a Ball",
    ),
    "push_others_out": (
        "Knock Everyone Out to Win 💥 Pick a Ball!",
        "Marble Battle Royale 💥 Who Wins the {arena}?",
    ),
    "hot_potato_bomb": (
        "Don't Get Caught With the Bomb! 💣 Pick a Ball",
        "Hot Potato Bomb Marble Race 💣 Which Ball Wins?",
    ),
}
STAGE_TITLES: dict[str, tuple[str, ...]] = {
    "play_in": ("Win or Go Home! 🏆 Playoff Marble Race", "Playoff Time! 🏆 Only the Winner Moves On"),
    "qualifier_1": ("Winner Goes Straight to the FINAL 🏆 Pick a Ball!",),
    "qualifier_2": ("2 Spots Left in the Grand Final 🏆 Pick a Ball!",),
    "grand_final": ("GRAND FINAL: One Ball Takes the Crown 👑", "3 Balls, 1 Crown 👑 Season {season} GRAND FINAL"),
}
WIN_CLAUSE: dict[str, str] = {
    "reach_finish": "Only ONE wins 👑",
    "last_one_standing": "Last ball standing wins 👑",
    "survive_timer": "Survive the clock or you're OUT ⏱️",
    "collect_items": "Most crowns wins 👑",
    "hold_a_zone": "Hold the hill to win 👑",
    "push_others_out": "Knock everyone out to win 💥",
    "hot_potato_bomb": "Don't get caught holding the bomb 💣",
}
STAGE_LABELS: dict[str, str] = {
    "play_in": "Play-In", "qualifier_1": "Qualifier 1", "qualifier_2": "Qualifier 2", "grand_final": "Grand Final",
}


def arena_display_name(arena_key: str) -> str:
    if arena_key in ARENA_NAMES:
        return ARENA_NAMES[arena_key]
    from src.games.arena_kit import v6_info
    return v6_info(str(arena_key)).get("name") or str(arena_key).replace("_", " ").title()


def _join_and(items: Sequence[str]) -> str:
    vals = [i for i in items if i]
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    return ", ".join(vals[:-1]) + " and " + vals[-1]


def _rotate(options: Sequence[str], season: int, race: int) -> list[str]:
    """Deterministic day-by-day rotation so consecutive episodes don't reuse the same hook."""
    if not options:
        return []
    start = ((race - 1) + (season - 1) * 3) % len(options)
    return list(options[start:]) + list(options[:start])


def _configured_category() -> str:
    try:
        from src.config import settings

        cat = str(settings().get("youtube_category_id") or DEFAULT_CATEGORY_ID).strip()
    except Exception:  # noqa: BLE001 - metadata must never fail because of config loading
        cat = DEFAULT_CATEGORY_ID
    return cat if cat.isdigit() else DEFAULT_CATEGORY_ID


def build_title(arena_key: str, goal: str, stage: str, season: int, race: int) -> str:
    arena = arena_display_name(arena_key)
    pool = STAGE_TITLES.get(stage) or TITLE_TEMPLATES.get(goal) or TITLE_TEMPLATES["reach_finish"]
    for tpl in _rotate(pool, season, race):
        title = tpl.format(arena=arena, season=season)
        if len(title) <= TITLE_MAX:
            return title
    return pool[0].format(arena=arena, season=season)[:100].rstrip()


def build_tags(arena_key: str, goal: str, stage: str) -> list[str]:
    raw = list(BASE_TAGS) + list(GOAL_TAGS.get(goal, ())) + [arena_display_name(arena_key).lower()]
    if stage == "grand_final":
        raw.append("grand final")
    elif stage in STAGE_LABELS:
        raw.append("playoffs")
    out: list[str] = []
    seen: set[str] = set()
    used = 0
    for tag in raw:
        clean = " ".join(str(tag).replace("<", "").replace(">", "").replace(",", " ").split())[:30]
        cost = len(clean) + (2 if " " in clean else 0) + 1
        if not clean or clean.lower() in seen or used + cost > TAG_CHARS_BUDGET:
            continue
        seen.add(clean.lower())
        out.append(clean)
        used += cost
        if len(out) >= TAGS_MAX:
            break
    return out


def _features(arena_key: str, hazards: Sequence[str] | None, twist: str | None) -> str:
    parts: list[str] = []
    feat = ARENA_FEATURES.get(arena_key)
    if feat is None:
        from src.games.arena_kit import v6_info
        feat = v6_info(str(arena_key)).get("feature")
    if feat:
        parts.append(feat)
    for hz in hazards or []:
        word = HAZARD_WORDS.get(str(hz)) or str(hz).replace("_", " ")
        if word and word not in parts:
            parts.append(word)
    txt = _join_and(parts[:4])
    if twist:
        txt = f"{txt}, plus a surprise twist" if txt else "a surprise twist"
    return txt


def _cast_line(cast_keys: Sequence[str], sep: str) -> str:
    return sep.join(f"{HERO_BY_KEY[k].emoji} {HERO_BY_KEY[k].name}" for k in cast_keys if k in HERO_BY_KEY)


def _series_label(season: int, race: int, stage: str) -> str:
    if stage in STAGE_LABELS:
        return f"Season {season} • {STAGE_LABELS[stage]}"
    return f"Season {season} • Race {race}/30"


def _standings_line(season: int, race: int, stage: str, pre_standings: Sequence[tuple[str, int]] | None,
                    cast_keys: Sequence[str]) -> str:
    """Pre-race context only (never today's result)."""
    names = [HERO_BY_KEY[k].name for k in cast_keys if k in HERO_BY_KEY]
    if stage == "grand_final":
        return f"👑 Season {season} Grand Final: {_join_and(names[:3])} fight for the crown!" if names else ""
    if stage == "qualifier_2":
        return f"🔥 Season {season} Qualifier 2: {_join_and(names[:3])}. Two spots left in the Grand Final!" if names else ""
    if stage == "qualifier_1":
        return (f"🔥 Season {season} Qualifier 1: {_join_and(names[:2])}. "
                f"The winner goes straight to the Grand Final!") if names else ""
    if stage == "play_in":
        return f"🔥 Season {season} Play-In: {len(names)} balls, only the winner moves on!"
    leader = pre_standings[0] if pre_standings else None
    if leader and int(leader[1]) > 0 and leader[0] in HERO_BY_KEY:
        lname = HERO_BY_KEY[leader[0]].name
        return f"📊 Before this race: {lname} leads Season {season} with {int(leader[1])} pts. Can anyone catch {lname}?"
    if race <= 1:
        return f"👑 Season {season} starts NOW: 10 balls, 30 races, 1 crown!"
    return ""


def build_upload_metadata(arena_key: str, outcome: Any, cta_prompt: str = "", *, goal: str | None = None,
                          hazards: Sequence[str] | None = None, twist: str | None = None,
                          cast_keys: Sequence[str] | None = None,
                          pre_standings: Sequence[tuple[str, int]] | None = None,
                          category_id: str | None = None) -> dict[str, Any]:
    """Returns {'title', 'description', 'ig_caption', 'tags', 'category_id', 'yt_comment', 'ig_comment',
    'metadata_version'} following the v4.6 spoiler-free viral SEO rules (see module docstring)."""
    s_num = int(getattr(outcome, "season_number", 1) or 1)
    e_num = int(getattr(outcome, "race_number", 1) or 1)
    is_final = bool(getattr(outcome, "is_grand_final", False))
    stage = "grand_final" if is_final else str(getattr(outcome, "stage", "") or "league")
    goal_key = str(goal or "reach_finish")
    arena = arena_display_name(arena_key)
    cast = [k for k in (cast_keys or [h.key for h in HEROES]) if k in HERO_BY_KEY]
    win_clause = f"One ball takes the Season {s_num} crown 👑" if is_final else WIN_CLAUSE.get(goal_key, "Only ONE wins 👑")

    n = len(cast)
    if n >= 4:
        who = f"{n} cartoon balls"
        verb = "race through" if goal_key == "reach_finish" else "battle it out in"
    else:
        who = _join_and([HERO_BY_KEY[k].name for k in cast]) or "The finalists"
        verb = "go head-to-head in" if n == 2 else "battle it out in"
    feats = _features(arena_key, hazards, twist)
    scene = f"{who} {verb} the {arena}: {feats}." if feats else f"{who} {verb} the {arena}."
    series = _series_label(s_num, e_num, stage)
    standings = _standings_line(s_num, e_num, stage, pre_standings, cast)

    desc_lines = [
        f"Pick your ball before it starts! 🏁 {scene} {win_clause}",
        "",
        "Which ball did you pick? Comment it below 👇",
        "",
        f"🏆 {series} of the ToonToonCastle Marble League • {SCHEDULE_LINE}",
    ]
    if standings:
        desc_lines.append(standings)
    desc_lines += ["", " ".join(YT_HASHTAGS)]

    headline = f"Marble race: pick your ball before it starts! 🏁 {win_clause}"
    if len(headline) > IG_HEADLINE_MAX:
        headline = "Marble race: pick your ball before it starts! 🏁"
    ig_lines = [
        headline,
        "Comment your pick before it ends 👇",
        "",
        "📤 Send this to the friend who always picks the wrong ball 😂",
        "",
        f"{arena}: {feats}" if feats else arena,
        f"🏆 {series} • {SCHEDULE_LINE}",
    ]
    if standings:
        ig_lines.append(standings)
    ig_lines += ["", " ".join(IG_HASHTAGS)]

    cta = (cta_prompt or "").strip()
    yt_comment_lines = ["Be honest 👇 Which ball did you pick?", _cast_line(cast, " • ")]
    if cta and stage == "league":   # playoff CTAs name tomorrow's bracket, which would spoil today's result
        yt_comment_lines.append(f"🎙️ {cta}")
    yt_comment_lines.append(f"🔔 {SCHEDULE_LINE[0].upper()}{SCHEDULE_LINE[1:]}!")
    ig_comment = "Which ball did you pick? 👇\n" + _cast_line(cast, " ")

    return {
        "title": build_title(arena_key, goal_key, stage, s_num, e_num),
        "description": "\n".join(desc_lines),
        "ig_caption": "\n".join(ig_lines),
        "tags": build_tags(arena_key, goal_key, stage),
        "category_id": category_id if (category_id and str(category_id).isdigit()) else _configured_category(),
        "yt_comment": "\n".join(yt_comment_lines),
        "ig_comment": ig_comment,
        "metadata_version": METADATA_VERSION,
    }
