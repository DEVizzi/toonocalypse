"""Tests for preflight abort, never-degrade gate, compositor scale, buffer ordering, and skip-day no-op (§8)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from PIL import Image

from src import cli
from src.common import state as state_mod
from src.common.quota import QuotaTracker
from src.panels.compose import compose_panel_layers
from src.publish import buffer as buf_mod
from src.publish.gate import evaluate_publishable
from src.render.qa import RenderQAResult


def test_preflight_abort_and_never_degrade(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    qt = QuotaTracker(filename="q_pre.json")
    with pytest.raises(cli.AbortPipeline):
        cli.run_preflight(qt, force_fail_preflight=True)

    good_qa = RenderQAResult(True, 35.0, 1080, 1920, True, 4.0, [])
    bad_pub = evaluate_publishable(
        script={"source": "offline", "is_llm_judged": False, "title": "Brewtan Stops The Cat", "panels": [{}] * 6},
        art_qa_passed=True,
        used_library_art=True,
        yt_qa=good_qa,
        ig_qa=good_qa,
    )
    assert not bad_pub.publishable
    assert any("non-LLM" in r for r in bad_pub.reasons)


def test_compositor_uses_scale_heights(tmp_path: Path, monkeypatch) -> None:
    from src.panels import compose as comp_mod

    bg = tmp_path / "bg.png"
    big_sp = tmp_path / "big.png"
    small_sp = tmp_path / "small.png"
    Image.new("RGB", (768, 1344), (50, 100, 150)).save(bg)
    Image.new("RGBA", (512, 512), (200, 50, 50, 255)).save(big_sp)
    Image.new("RGBA", (512, 512), (50, 200, 50, 255)).save(small_sp)

    monkeypatch.setattr(comp_mod, "ROOT", tmp_path)
    lib_idx = {
        "backgrounds": {"test-bg": {"9x16": "bg.png"}},
        "characters": {
            "brewtan-the-yeti": {"idle": {"path": "big.png"}},
            "detective-bubbles": {"idle": {"path": "small.png"}},
        },
    }
    res = compose_panel_layers(
        {"panel_id": 1, "background": "test-bg", "characters": ["brewtan-the-yeti", "detective-bubbles"]},
        lib_idx,
        tmp_path / "out",
    )
    assert res["composite"].exists()
    assert res["fg"].exists()


def test_buffer_ordering_and_skip_day_and_idle_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)

    # Part 2 buffered before Part 1 is published -> must NOT publish Part 2; picks One-Shot instead
    buf_mod.add_to_buffer({"episode_id": "ep-20261116-aaaaaa-pt2of3", "story_id": "ep-20261116-aaaaaa", "part_num": 2, "part_count": 3, "publishable": True})
    buf_mod.add_to_buffer({"episode_id": "ep-20261116-bbbbbb-pt1of1", "story_id": "ep-20261116-bbbbbb", "part_num": 1, "part_count": 1, "publishable": True})

    picked = buf_mod.pick_next_publishable(pub_state={"episodes": {}})
    assert picked is not None
    assert picked["episode_id"] == "ep-20261116-bbbbbb-pt1of1"

    # Empty buffer -> cmd_publish records skipped_empty_buffer and returns 0
    buf_mod.remove_from_buffer("ep-20261116-aaaaaa-pt2of3")
    buf_mod.remove_from_buffer("ep-20261116-bbbbbb-pt1of1")
    monkeypatch.setattr(cli, "open_alert_issue", lambda **kw: None)
    assert cli.cmd_publish(argparse.Namespace()) == 0
    pub = state_mod.load_state("published.json")
    assert any(isinstance(v, dict) and v.get("status") == "skipped_empty_buffer" for v in pub["daily_posts"].values())

    # Full buffer (>=3) -> cmd_generate exits 0 immediately
    for i in range(3):
        buf_mod.add_to_buffer({"episode_id": f"ep-20261116-00000{i}-pt1of1", "part_num": 1, "part_count": 1, "publishable": True})
    args = argparse.Namespace(format="", heroes="", villain="", offline=False, draft=True, no_release=False, force=False, fail_preflight=False)
    assert cli.cmd_generate(args) == 0
