"""Kaggle job state machine: PORTRAITS -> PANELS -> REPAIR -> READY_TO_RENDER (§7.2-7.4).

Resume: whatever a (possibly killed) session produced is collected; only missing items are re-pushed.
All external calls go through `tools` (Kaggle/gh) and `qa` (Gemini vision) so the logic is testable.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from src.common.config import ROOT, settings
from src.common.ids import release_tag
from src.common.quota import Quota
from src.common.retry import Abort
from src.kaggle_jobs import job as jobs

MAX_SESSION_RETRIES = 2
QA_BUDGET_S = 40 * 60  # leave room in the 60-min collect job to save state


class QuotaWait(Exception):
    """Gemini/Kaggle quota is exhausted for now; progress is saved and the next collect resumes."""


def _art(story: dict[str, Any]) -> dict[str, Any]:
    return story.setdefault("art", {"phase": None, "job": None, "session_retries": 0, "portrait_repair": 0,
                                    "repair_round": 0, "portraits": {}, "panels": {}, "log": []})


def _log(story: dict[str, Any], msg: str) -> None:
    print(f"[art] {msg}", flush=True)
    _art(story)["log"].append(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}")


def workdir(story: dict[str, Any]) -> Path:
    p = ROOT / "work" / story["story_id"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def push_job(story: dict[str, Any], phase: str, items: list[dict[str, Any]], tools, quota: Quota) -> None:
    art = _art(story)
    tag = release_tag(story["story_id"])
    portrait_files: dict[str, Path] = {}
    if phase != "PORTRAITS":
        names = {c["name"]: art["portraits"][c["name"]]["approved"] for c in story["cast"]}
        got = tools.download_assets(tag, list(names.values()), workdir(story) / "assets")
        portrait_files = {n: got[f] for n, f in names.items()}
    job_id = f"{story['story_id']}-{phase.lower()}-{int(time.time())}"
    job = jobs.build_job(story, phase, items, portrait_files, job_id)
    hours = jobs.estimate_gpu_hours(job)
    if not quota.kaggle_can_spend(hours):
        raise QuotaWait(f"Kaggle weekly GPU budget would exceed {quota.kaggle_limit_hours():.1f}h (need ~{hours}h)")
    kdir = jobs.render_kernel(job, workdir(story) / "kernel", os.environ.get("KAGGLE_USERNAME", "user"))
    version = tools.push(kdir)
    art["job"] = {"id": job_id, "phase": phase, "items": [it["id"] for it in items], "pushed_at": time.time(),
                  "est_hours": hours, "version": version}
    _log(story, f"pushed {phase} job {job_id} ({len(items)} items, ~{hours} GPU-h, kernel v{version})")


def start(story: dict[str, Any], tools, quota: Quota) -> None:
    art = _art(story)
    tools.preflight()
    tools.ensure_release(release_tag(story["story_id"]), f"[draft] {story['title']} ({story['story_id']})")
    art["phase"] = "PORTRAITS"
    art["portraits"] = {c["name"]: {"candidates": [], "approved": None, "qa": None, "failed": False} for c in story["cast"]}
    story["status"] = "ART_IN_PROGRESS"
    push_job(story, "PORTRAITS", jobs.portrait_items(story), tools, quota)


def _ingest(story: dict[str, Any], manifest: dict[str, Any], out_dir: Path, tools, quota: Quota) -> list[str]:
    """Upload kept candidates, attach them to state. Returns item ids that produced nothing (session died)."""
    art, job = _art(story), _art(story)["job"]
    quota.kaggle_record(round(float(manifest.get("gpu_seconds", 0)) / 3600, 3))
    files, missing = [], []
    name_by_pid = {jobs.portrait_id(c["name"]): c["name"] for c in story["cast"]}
    for item_id in job["items"]:
        rec = manifest.get("items", {}).get(item_id)
        generated = rec is not None and (rec.get("kept") or rec.get("rejected"))
        if not generated:
            missing.append(item_id)
            continue
        kept = [k["file"] for k in rec.get("kept", [])]
        files += [out_dir / f for f in kept]
        if item_id in name_by_pid:
            art["portraits"][name_by_pid[item_id]].update(candidates=kept, approved=None, qa=None, failed=not kept)
        else:
            art["panels"][item_id] = {"candidates": kept, "qa": [], "approved": None,
                                      "status": "candidates" if kept else "failed",
                                      "prefilter": {"kept": rec.get("kept", []), "rejected": rec.get("rejected", [])}}
    if files:
        tools.upload_assets(release_tag(story["story_id"]), files)
    if manifest.get("errors"):
        _log(story, f"kernel errors: {manifest['errors'][0][:300]}")
    return missing


def _panel_lookup(story: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {jobs.panel_id(p["part"], int(x["id"])): x for p in story["parts"] for x in p["panels"]}


def _run_qa(story: dict[str, Any], tools, qa, quota: Quota) -> None:
    art, tag = _art(story), release_tag(story["story_id"])
    assets = workdir(story) / "assets"
    cast = {c["name"]: c for c in story["cast"]}
    for name, p in art["portraits"].items():
        if p["candidates"] and not p["approved"] and p["qa"] is None and not p["failed"]:
            got = tools.download_assets(tag, p["candidates"], assets)
            res = qa.portrait_qa(cast[name], [got[f] for f in p["candidates"]], quota=quota)
            p["qa"] = res
            if res["best"] is None:
                p["failed"] = True
                _log(story, f"portrait {name}: no candidate passed QA")
            else:
                p["approved"] = p["candidates"][res["best"]]
                _log(story, f"portrait {name}: approved {p['approved']}")
    if art["phase"] in ("PANELS", "REPAIR"):
        lookup = _panel_lookup(story)
        portraits = None
        deadline = time.time() + QA_BUDGET_S
        for pid, st in art["panels"].items():
            if st["status"] != "candidates":
                continue
            if time.time() > deadline:
                _log(story, "QA time budget reached; the next collect resumes")
                return
            if portraits is None:
                names = {n: v["approved"] for n, v in art["portraits"].items()}
                got = tools.download_assets(tag, list(names.values()), assets)
                portraits = {n: got[f] for n, f in names.items()}
            for f in st["candidates"]:
                if any(q["file"] == f for q in st["qa"]):
                    continue
                img = tools.download_assets(tag, [f], assets)[f]
                res = qa.panel_qa(lookup[pid], cast, img, portraits, quota=quota)
                st["qa"].append({"file": f} | res)
                if res["passed"]:
                    st["approved"], st["status"] = f, "approved"
                    _log(story, f"panel {pid}: approved (avg {res['avg']})")
                    break
            else:
                st["status"] = "failed"
                _log(story, f"panel {pid}: all candidates failed QA")
            getattr(tools, "checkpoint", lambda: None)()


def _best_effort(story: dict[str, Any], failed: list[str]) -> list[str]:
    """Human-review mode: approve the best safe candidate (safety=10, no text) and flag it. Returns still-failed ids."""
    art, left = _art(story), []
    for pid in failed:
        st = art["panels"][pid]
        safe = [q for q in st["qa"] if q["scores"].get("safety", 0) >= 10 and q["scores"].get("no_text", 0) >= 5]
        if not safe:
            left.append(pid)
            continue
        best = max(safe, key=lambda q: q["avg"])
        st.update(approved=best["file"], status="approved", needs_review=True)
        _log(story, f"panel {pid}: best-effort {best['file']} (avg {best['avg']}) -> needs human review")
    return left


def collect(story: dict[str, Any], tools, qa, quota: Quota) -> str:
    """Advance one step. Returns a short status string. Raises Abort to kill the story, QuotaWait to pause."""
    art = _art(story)
    job = art.get("job")
    if job:
        st = tools.status()
        if st in ("queued", "running", "unknown"):
            return f"WAITING ({st})"
        out_dir = tools.download_output(workdir(story) / f"kout-{job['id']}")
        manifest = json.loads((out_dir / "manifest.json").read_text()) if out_dir else {"items": {}, "errors": [f"no output ({st})"]}
        missing = _ingest(story, manifest, out_dir or Path("."), tools, quota)
        phase = job["phase"]
        art["job"] = None
        if missing:
            if art["session_retries"] >= MAX_SESSION_RETRIES:
                raise Abort(f"Kaggle session failed {MAX_SESSION_RETRIES + 1}x; missing {len(missing)} items")
            art["session_retries"] += 1
            _log(story, f"session ended ({st}); re-pushing {len(missing)} missing items")
            items = (jobs.portrait_items(story, [n for n in art["portraits"] if jobs.portrait_id(n) in missing])
                     if phase == "PORTRAITS" else
                     jobs.panel_items(story, set(missing), salt=art["repair_round"], repair=phase == "REPAIR"))
            push_job(story, phase, items, tools, quota)
            return "REPUSHED_MISSING"
        art["session_retries"] = 0

    try:
        _run_qa(story, tools, qa, quota)
    except Abort as e:  # Gemini temporarily unavailable: keep progress, resume next collect
        raise QuotaWait(str(e)) from e

    if art["phase"] == "PORTRAITS":
        ps = art["portraits"]
        if any(p["candidates"] and not p["approved"] and p["qa"] is None and not p["failed"] for p in ps.values()):
            return "QA_PENDING"
        failed = [n for n, p in ps.items() if p["failed"]]
        if failed:
            if art["portrait_repair"] >= settings()["panel_qa"].get("max_portrait_repairs", 1):
                raise Abort(f"Cast portraits failed QA after repair: {failed}")
            art["portrait_repair"] += 1
            for n in failed:
                ps[n].update(candidates=[], qa=None, failed=False)
            push_job(story, "PORTRAITS", jobs.portrait_items(story, failed, salt=art["portrait_repair"]), tools, quota)
            return "PORTRAIT_REPAIR"
        art["phase"] = "PANELS"
        art["panels"] = {}
        push_job(story, "PANELS", jobs.panel_items(story), tools, quota)
        return "PANELS_PUSHED"

    if art["phase"] in ("PANELS", "REPAIR"):
        panels = art["panels"]
        if any(s["status"] == "candidates" for s in panels.values()):
            return "QA_PENDING"
        failed = [pid for pid, s in panels.items() if s["status"] == "failed"]
        if failed and art["repair_round"] >= settings()["panel_qa"].get("best_effort_after_round", 99):
            failed = _best_effort(story, failed)
        if failed:
            if art["repair_round"] >= settings()["panel_qa"]["max_repair_rounds"]:
                raise Abort(f"{len(failed)} panels failed QA after {art['repair_round']} repair rounds: {failed[:6]}")
            art["repair_round"] += 1
            art["phase"] = "REPAIR"
            for pid in failed:
                panels[pid]["status"] = "pending"
            push_job(story, "REPAIR", jobs.panel_items(story, set(failed), salt=art["repair_round"], repair=True), tools, quota)
            return f"REPAIR_{art['repair_round']}_PUSHED"
        art["phase"] = "DONE"
        story["status"] = "READY_TO_RENDER"
        _log(story, "all portraits and panels approved -> READY_TO_RENDER")
        return "READY_TO_RENDER"
    return f"IDLE ({art['phase']})"
