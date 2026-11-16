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
    b["current"] = None
    q.record_abort(reason)
    print(f"ABORTED: {reason}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["start", "collect"])
    args = ap.parse_args(argv)
    q = Quota()
    b = load_state("story_bible.json")
    story = b.get("current")
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
