"""Tests for story planner format selection, cast pairing, and cliffhangers."""
from __future__ import annotations

import random

from src.story.ideas import pick_unused_seed_idea, sanitize_legacy_idea
from src.story.planner import choose_format, rotate_cliffhangers, select_cast


def test_choose_format_and_cast_respect_forced_and_bounds() -> None:
    bible = {"used_ideas": [], "episodes": [], "active_arc": None}
    rng = random.Random(42)
    fmt, parts = choose_format(bible, forced_format="Mini-Arc", rng=rng)
    assert fmt == "Mini-Arc"
    assert 3 <= parts <= 4

    heroes, villain = select_cast(bible, fmt, forced_heroes=["brewtan-the-yeti", "detective-bubbles"], rng=rng)
    assert heroes == ["brewtan-the-yeti", "detective-bubbles"]
    assert villain is None or isinstance(villain, str)


def test_rotate_cliffhangers_no_adjacent_repeats() -> None:
    cliffs = rotate_cliffhangers(5, rng=random.Random(7))
    assert len(cliffs) == 5
    for a, b in zip(cliffs, cliffs[1:]):
        assert a != b


def test_sanitize_and_pick_unused_idea() -> None:
    cleaned = sanitize_legacy_idea("A bloody Pixar battle in the kitchen")
    assert "Pixar" not in cleaned
    assert "bloody" not in cleaned.lower()
    idea = pick_unused_seed_idea({"used_ideas": []}, rng=random.Random(1))
    assert "id" in idea and "premise" in idea
