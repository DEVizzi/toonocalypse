from datetime import datetime, timezone

import pytest

from src.common.ids import make_episode_id, make_story_id, parse_episode_id, release_tag

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def test_story_id_format():
    sid = make_story_id("The Golden Rickshaw", NOW)
    assert sid.startswith("st-20261117-") and len(sid) == len("st-20261117-abcdef")


def test_episode_id_never_doubles_prefix():
    sid = make_story_id("x", NOW)
    ep = make_episode_id(sid, 1, 3)
    assert ep == f"{sid}-pt1of3"
    # Feeding an episode id back in must not produce st-...-pt1of3-pt2of3
    assert make_episode_id(ep, 2, 3) == f"{sid}-pt2of3"
    assert release_tag(ep) == sid


def test_parse_roundtrip():
    sid = make_story_id("y", NOW)
    assert parse_episode_id(make_episode_id(sid, 3, 5)) == (sid, 3, 5)


@pytest.mark.parametrize("bad", ["ep-ep-20261116-75a5d2", "st-2026-abc", ""])
def test_rejects_bad_ids(bad):
    with pytest.raises(ValueError):
        make_episode_id(bad, 1, 3)


def test_part_out_of_range():
    with pytest.raises(ValueError):
        make_episode_id(make_story_id("z", NOW), 4, 3)
