"""Tests for canonical IDs/tags (§7) and episode title validation (§6.2)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.common.ids import make_episode_id, make_release_tag, make_story_id, parse_episode_id
from src.story.title_validator import validate_title


def test_canonical_ids_never_double_prefix() -> None:
    dt = datetime(2026, 11, 16, tzinfo=timezone.utc)
    sid = make_story_id(now=dt, hex_id="a1b2c3")
    assert sid == "ep-20261116-a1b2c3"

    eid = make_episode_id(sid, 1, 5)
    assert eid == "ep-20261116-a1b2c3-pt1of5"
    assert not eid.startswith("ep-ep-")

    tag = make_release_tag(eid)
    assert tag == eid
    assert parse_episode_id(tag) == {"date": "20261116", "hash": "a1b2c3", "part_num": 1, "part_count": 5}

    with pytest.raises(ValueError):
        make_release_tag("bad-tag")


def test_title_validator_rules() -> None:
    assert not validate_title("Short title")[0]
    assert not validate_title("A pizza delivery goes wrong when")[0]
    assert not validate_title("The Giant Neon Pizza Tower")[0]
    ok, reasons = validate_title("Brewtan Chases the Runaway Pizza")
    assert ok, reasons
