from src.publish import buffer as buf
from src.tokens.__main__ import days_left, needs_refresh


def story(sid, parts):
    return {"story_id": sid, "logline": "x", "episodes": [{"episode_id": f"{sid}-pt{i}of{parts}", "part": i, "total": parts}
                                                          for i in range(parts, 0, -1)]}  # deliberately out of order


def test_skip_day_when_empty():
    assert buf.next_episode({"stories": []}, {"episodes": {}}) is None


def test_oldest_story_first_and_parts_in_order():
    b = {"stories": [story("st-20261101-aaaaaa", 3), story("st-20261102-bbbbbb", 3)]}
    pub = {"episodes": {}}
    s, ep, need = buf.next_episode(b, pub)
    assert s["story_id"] == "st-20261101-aaaaaa" and ep["part"] == 1 and need == ["youtube", "instagram"]


def test_failed_platform_retries_same_episode_only():
    b = {"stories": [story("st-20261101-aaaaaa", 3)]}
    pub = {"episodes": {}}
    buf.record(pub, "st-20261101-aaaaaa-pt1of3", "youtube", "yt1", 0)
    s, ep, need = buf.next_episode(b, pub)
    assert ep["part"] == 1 and need == ["instagram"]
    buf.record(pub, "st-20261101-aaaaaa-pt1of3", "instagram", "ig1", 0)
    assert buf.next_episode(b, pub)[1]["part"] == 2


def test_whole_story_pruned_only_when_every_part_posted():
    b = {"stories": [story("st-20261101-aaaaaa", 2)]}
    pub = {"episodes": {}}
    for p in ("youtube", "instagram"):
        buf.record(pub, "st-20261101-aaaaaa-pt1of2", p, "x", 0)
    assert buf.prune_completed(b, pub) == [] and len(b["stories"]) == 1
    assert buf.ready_episode_count(b, pub) == 1
    for p in ("youtube", "instagram"):
        buf.record(pub, "st-20261101-aaaaaa-pt2of2", p, "y", 0)
    assert len(buf.prune_completed(b, pub)) == 1 and b["stories"] == []


def test_descriptions():
    ep = {"part": 3, "total": 3, "moral": "Honesty is the richest fare.", "hashtags": ["comics", "#moral"], "caption": "Hook. Part 3/3"}
    d = buf.youtube_description({"logline": "A driver finds gold."}, ep, "https://youtube.com/shorts/abc", "Toonocalypse")
    assert "Part 3 of 3" in d and "Previous part" in d and "Moral: Honesty" in d and "#comics #moral" in d
    assert buf.instagram_caption(ep).endswith("#comics #moral")


def test_token_expiry_math():
    now = 1_000_000.0
    assert days_left(None, now) is None and not needs_refresh(None, 20)
    left = days_left(now + 19.5 * 86400, now)
    assert left == 19.5 and needs_refresh(left, 20)
    assert not needs_refresh(days_left(now + 40 * 86400, now), 20)


def test_unapproved_story_is_held_back():
    from src.publish.buffer import next_episode
    ep = {"episode_id": "e1", "part": 1}
    held = {"stories": [{"story_id": "s1", "approved": False, "episodes": [ep]}]}
    assert next_episode(held, {"episodes": {}}) is None
    held["stories"][0]["approved"] = True
    assert next_episode(held, {"episodes": {}})[1] is ep
