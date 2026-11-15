"""Tests for strict prompt builder and panel-text color/outfit linter."""
from __future__ import annotations

from src.art.prompt_builder import build_page_prompt, build_scale_line, lint_panel_action


def test_lint_panel_action_rejects_colors_and_outfits() -> None:
    assert lint_panel_action("Brewtan slides across the icy counter to catch the runaway mug.") == []
    hits_color = lint_panel_action("Brewtan puts on a red scarf and jumps.")
    assert hits_color
    hits_long = lint_panel_action("a" * 205)
    assert hits_long


def test_build_scale_line_mentions_ratio_and_xs_xl_rules() -> None:
    line = build_scale_line(["brewtan-the-yeti", "detective-bubbles"])
    assert "Brewtan" in line
    assert "Detective Bubbles" in line


def test_build_page_prompt_includes_grid_anchors_and_no_text_rule() -> None:
    script = {
        "heroes": ["brewtan-the-yeti", "detective-bubbles"],
        "villain": None,
        "setting": "Frosty Espresso Bar",
        "panels": [{"action": "Brewtan waves hello."} for _ in range(6)],
    }
    prompt, _refs = build_page_prompt(script)
    assert "2-column x 3-row" in prompt
    assert "STRICTLY NO text" in prompt
    assert "FORBIDDEN:" in prompt
    assert "MUST HAVE:" in prompt
