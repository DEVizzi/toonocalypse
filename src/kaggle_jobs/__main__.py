"""python -m src.kaggle_jobs start|collect — drive the Kaggle art state machine for the current story."""
from __future__ import annotations

import argparse
import sys
import time

from src.common.quota import Quota
from src.common.retry import Abort
from src.common.state import load_state, save_state
from src.kaggle_jobs import cli_tools, machine
from src.qa import vision


def abort_story(b: dict, story: dict, reason: str, q: Quota) -> None:
    story["status"] = "ABORTED"
    story["abort_reason"] = reason
    b.setdefault("history", []).append({"story_id": story["story_id"], "title": story["title"], "category": story["category"],
                                        "status": "ABORTED", "reason": reason, "at": time.time()})
    b["archive"] = {story["story_id"]: story} | b.get("archive", {})
    b["current"] = None
    q.record_abort(reason)
    print(f"ABORTED: {reason}")


def smoke(cmd: str, story: dict) -> None:
    """Kernel smoke test: 2 portrait candidates per character from the saved plan; outputs go to a 'smoke-test' draft release."""
    from pathlib import Path

    from src.kaggle_jobs import job as jobs

    work = Path("work/smoke")
    if cmd == "smoke":
        cli_tools.preflight()
        items = jobs.portrait_items(story)
        for it in items:
            it.update(n=2, keep=2)
        job = jobs.build_job(story, "PORTRAITS", items, {}, f"smoke-{int(time.time())}")
        print(f"pushed smoke job, kernel v{cli_tools.push(jobs.render_kernel(job, work / 'kernel', __import__('os').environ['KAGGLE_USERNAME']))}")
        return
    st = cli_tools.status()
    print(f"kernel status: {st}")
    if st in ("queued", "running", "unknown"):
        return
    out = cli_tools.download_output(work / "out")
    if not out:
        print("no output found")
        return
    manifest = (out / "manifest.json").read_text()
    print(manifest[:4000])
    cli_tools.ensure_release("smoke-test", "[draft] kernel smoke test")
    cli_tools.upload_assets("smoke-test", sorted(out.glob("*.jpg")) + [out / "manifest.json"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["start", "collect", "smoke", "smoke-collect", "restart-portraits", "restart-panels"])
    args = ap.parse_args(argv)
    q = Quota()
    b = load_state("story_bible.json")
    story = b.get("current")
    if args.cmd.startswith("smoke"):
        smoke(args.cmd, story)
        return 0
    if args.cmd == "restart-portraits":
        from src.kaggle_jobs import job as jobs

        if cli_tools.status() in ("queued", "running"):
            print("A Kaggle job is still running; try again after it finishes.")
            return 0
        art = story["art"]
        art.update(phase="PORTRAITS", job=None, portrait_repair=0, repair_round=0, session_retries=0, panels={})
        art["portraits"] = {c["name"]: {"candidates": [], "approved": None, "qa": None, "failed": False} for c in story["cast"]}
        machine.push_job(story, "PORTRAITS", jobs.portrait_items(story, salt=7), cli_tools, q)
        save_state("story_bible.json", b)
        q.save()
        return 0
    if args.cmd == "restart-panels":  # operator tool after a prompt fix: keep approved panels, redo the rest
        from src.kaggle_jobs import job as jobs

        if cli_tools.status() in ("queued", "running"):
            print("A Kaggle job is still running; try again after it finishes.")
            return 0
        art = story["art"]
        if art.get("job"):
            print(f"discarding uncollected job {art['job']['id']} (made with the old prompts)")
            art["job"] = None
        todo = {pid for pid, s in art["panels"].items() if s["status"] != "approved"}
        art.update(phase="PANELS", repair_round=0, session_retries=0)
        for pid in todo:
            art["panels"][pid].update(status="pending", candidates=[], qa=[], approved=None)
        machine.push_job(story, "PANELS", jobs.panel_items(story, todo, salt=13), cli_tools, q)
        save_state("story_bible.json", b)
        q.save()
        return 0
    cli_tools.checkpoint = lambda: (save_state("story_bible.json", b), q.save())  # per-panel QA progress
    try:
        if args.cmd == "start":
            if not story or story.get("status") != "SCRIPTED":
                print("Nothing to start (no SCRIPTED story).")
                return 0
            machine.start(story, cli_tools, q)
        else:
            if not story or story.get("status") != "ART_IN_PROGRESS":
                print("Nothing to collect.")
                return 0
            result = machine.collect(story, cli_tools, vision, q)
            print(f"collect: {result}")
            if result == "READY_TO_RENDER":
                q.record_success()
                import subprocess

                subprocess.run(["gh", "workflow", "run", "render.yml"], check=False)
    except machine.QuotaWait as e:
        print(f"WAITING: {e}")
    except Abort as e:
        abort_story(b, story, str(e), q)
    finally:
        save_state("story_bible.json", b)
        q.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
