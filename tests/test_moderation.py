"""Tests for deterministic family-safety & studio-name moderation gate."""
from __future__ import annotations

from src.moderation.gate import check_metadata, check_script, check_text


def test_check_text_blocks_profanity_violence_and_studio_names() -> None:
    assert check_text("Brewtan and Detective Bubbles share cocoa in the treehouse.").passed
    assert not check_text("This looks like a Pixar movie.").passed
    assert not check_text("A bloody sword fight with murder.").passed


def test_check_script_and_metadata() -> None:
    script = {
        "title": "The Great Cocoa Caper",
        "on_screen_hook": "WHO STOLE THE COCOA?",
        "panels": [
            {"action": "Brewtan sniffs the empty mug.", "dialogue": [{"speaker": "Brewtan", "line": "Oh no, my cocoa!"}]}
        ],
    }
    assert check_script(script).passed
    assert check_metadata("Cocoa Caper", "A fun mystery!", "Watch now! #Toonocalypse", ["comedy", "cartoon"]).passed
    assert not check_metadata("Ghibli Cocoa", "desc", "cap", []).passed
