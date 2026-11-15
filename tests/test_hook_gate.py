"""Tests for Hook & Retention Score gate."""
from __future__ import annotations

from src.story.hook_gate import evaluate_scores, judge_script, parse_judge_json


def test_parse_and_evaluate_hook_scores() -> None:
    raw = '{"hook":9,"stakes":8,"escalation":8,"surprises":8,"voice_accuracy":8,"warmth":9,"ending":8,"shareability":8,"safety":10,"feedback":"Great!"}'
    parsed = parse_judge_json(raw)
    res = evaluate_scores(parsed["scores"], parsed["feedback"])
    assert res.passed
    assert res.avg_score >= 7.5


def test_evaluate_fails_if_safety_below_10_or_hook_below_8() -> None:
    low_safety = {k: 9.0 for k in ("hook", "stakes", "escalation", "surprises", "voice_accuracy", "warmth", "ending", "shareability", "safety")}
    assert not evaluate_scores(low_safety).passed


def test_offline_judge_script() -> None:
    script = {
        "on_screen_hook": "WAIT FOR THIS!",
        "panels": [{"dialogue": [{"speaker": "Brewtan", "line": "Watch closely!"}], "narrator": ""} for _ in range(6)],
    }
    res = judge_script(script, offline=True)
    assert res.passed
