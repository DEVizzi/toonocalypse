import base64
import json
from pathlib import Path

import pytest
from PIL import Image

import src.common.state as state_mod
from src.common.quota import Quota
from src.common.retry import Abort
from src.kaggle_jobs import job as jobs
from src.kaggle_jobs import machine


def make_story():
    cast = [{"name": "Jin", "visual_prompt": "Jin look"}, {"name": "Madam Wong", "visual_prompt": "Wong look"}]
    panels = [{"id": 1, "image_prompt": "street at dawn", "characters": []},
              {"id": 2, "image_prompt": "Jin finds gold", "characters": [{"name": "Jin", "position": "center"}]},
              {"id": 3, "image_prompt": "they argue", "characters": [{"name": "Jin", "position": "left"},
                                                                    {"name": "Madam Wong", "position": "right"}]}]
    return {"story_id": "st-20261117-abcdef", "title": "The Golden Rickshaw", "category": "moral_fable",
            "status": "SCRIPTED", "cast": cast, "parts": [{"part": 1, "panels": panels}]}


class FakeTools:
    def __init__(self, tmp: Path):
        self.tmp, self.pushed, self.state, self.manifest = tmp, [], "running", None

    def preflight(self): pass
    def ensure_release(self, tag, title): pass
    def upload_assets(self, tag, files): pass

    def push(self, kdir):
        code = (kdir / "art_kernel.py").read_text()
        payload = code.split('base64.b64decode("')[1].split('")')[0]
        self.pushed.append(json.loads(base64.b64decode(payload)))
        return str(len(self.pushed))

    def status(self): return self.state

    def download_output(self, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "manifest.json").write_text(json.dumps(self.manifest))
        return dest

    def download_assets(self, tag, names, dest):
        dest.mkdir(parents=True, exist_ok=True)
        out = {}
        for n in names:
            p = dest / n
            if not p.exists():
                Image.new("RGB", (64, 112), "gray").save(p, format="JPEG")
            out[n] = p
        return out


def manifest_for(job, keep=1, skip=()):
    items = {}
    for it in job["items"]:
        if it["id"] in skip:
            continue
        items[it["id"]] = {"kept": [{"file": f"{it['id']}__s{i}.jpg", "clip": 0.3} for i in range(keep)], "rejected": []}
    return {"items": items, "gpu_seconds": 600, "errors": []}


class FakeQA:
    def __init__(self, fail_panels=()):
        self.fail = set(fail_panels)

    def portrait_qa(self, char, paths, quota=None):
        return {"best": 0, "results": []}

    def panel_qa(self, panel, cast, image, portraits, quota=None):
        pid = image.name.split("__")[0]
        ok = pid not in self.fail
        return {"passed": ok, "avg": 9 if ok else 5, "scores": {}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(machine, "workdir", lambda s: tmp_path / "work")
    (tmp_path / "work").mkdir()
    return FakeTools(tmp_path), Quota()


def test_job_items_inject_visual_prompt_and_masks():
    s = make_story()
    items = {i["id"]: i for i in jobs.panel_items(s)}
    assert items["p1-1"]["refs"] == []
    assert items["p1-2"]["refs"] == [{"char": "Jin", "where": "full"}]
    assert items["p1-3"]["refs"] == [{"char": "Jin", "where": "left"}, {"char": "Madam Wong", "where": "right"}]
    assert "Jin on the left: Jin look" in items["p1-3"]["prompt"]
    assert "upper quarter" in items["p1-3"]["prompt"]
    # fixed seed per character per story
    assert jobs.char_seed(s["story_id"], "Jin") == jobs.char_seed(s["story_id"], "Jin")
    assert jobs.portrait_items(s)[1]["id"] == "portrait-madam-wong"


def test_full_happy_path_with_one_repair(env):
    tools, q = env
    s = make_story()
    machine.start(s, tools, q)
    assert tools.pushed[-1]["phase"] == "PORTRAITS" and len(tools.pushed[-1]["items"]) == 2
    assert machine.collect(s, tools, FakeQA(), q).startswith("WAITING")

    tools.state, tools.manifest = "complete", manifest_for(tools.pushed[-1])
    assert machine.collect(s, tools, FakeQA(), q) == "PANELS_PUSHED"
    panels_job = tools.pushed[-1]
    assert panels_job["phase"] == "PANELS" and set(panels_job["refs"]) == {"Jin", "Madam Wong"}

    tools.manifest = manifest_for(panels_job)
    assert machine.collect(s, tools, FakeQA(fail_panels={"p1-3"}), q) == "REPAIR_1_PUSHED"
    repair = tools.pushed[-1]
    assert [i["id"] for i in repair["items"]] == ["p1-3"] and repair["items"][0]["ip_scale"] == 0.55

    tools.manifest = manifest_for(repair)
    assert machine.collect(s, tools, FakeQA(), q) == "READY_TO_RENDER"
    assert s["status"] == "READY_TO_RENDER"
    assert q.data["kaggle"]["gpu_hours_used"] > 0


def test_killed_session_repushes_only_missing(env):
    tools, q = env
    s = make_story()
    machine.start(s, tools, q)
    tools.state, tools.manifest = "complete", manifest_for(tools.pushed[-1])
    machine.collect(s, tools, FakeQA(), q)
    tools.state, tools.manifest = "error", manifest_for(tools.pushed[-1], skip={"p1-2", "p1-3"})
    assert machine.collect(s, tools, FakeQA(), q) == "REPUSHED_MISSING"
    assert sorted(i["id"] for i in tools.pushed[-1]["items"]) == ["p1-2", "p1-3"]


def test_abort_after_repair_rounds_exhausted(env):
    tools, q = env
    s = make_story()
    machine.start(s, tools, q)
    tools.state, tools.manifest = "complete", manifest_for(tools.pushed[-1])
    machine.collect(s, tools, FakeQA(), q)
    with pytest.raises(Abort):
        for _ in range(4):
            tools.manifest = manifest_for(tools.pushed[-1])
            machine.collect(s, tools, FakeQA(fail_panels={"p1-1"}), q)


def test_quota_blocks_push(env, monkeypatch):
    tools, q = env
    q.kaggle_record(25.4)
    with pytest.raises(machine.QuotaWait):
        machine.start(make_story(), tools, q)
