"""python -m src.story plan [--seed TITLE] — plan + script + judge one story and print a sample."""
from __future__ import annotations

import argparse
import json
import sys

from src.common.quota import Quota
from src.common.retry import Abort
from src.story.pipeline import create_story


def print_sample(story: dict) -> None:
    print("=" * 70)
    print(f"{story['title']}  [{story['category']}]  {story['parts']} parts  id={story['story_id']}")
    print(f"Logline: {story['logline']}\nMoral:   {story['moral']}\nSetting: {story['setting']}")
    print("Cast:")
    for c in story["cast"]:
        print(f"  - {c['name']} ({c['age']}, {c['gender']}, {c['region']}): {c['visual_prompt']}")
    print(f"Judge: avg={story['judge']['avg']} {story['judge']['scores']}")
    for p in story["parts"]:
        print(f"\n--- {p['title']} ({len(p['panels'])} panels, {sum(float(x['duration']) for x in p['panels']):.0f}s)")
        print(f"Hook: {p['hook_text']}")
        for x in p["panels"][:3]:
            lines = " / ".join(f"{d.get('speaker')}: {d.get('line')}" for d in x.get("dialogue", []))
            print(f"  [{x.get('id')}] {str(x.get('image_prompt', ''))[:110]}… | {lines or x.get('narration', '')}")
    print("=" * 70, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--seed", default=None)
    args = ap.parse_args(argv)

    q = Quota()
    if q.is_paused():
        print(f"ABORTED: paused until {q.data['aborts']['paused_until']}")
        return 0
    try:
        story = create_story(seed_title=args.seed, quota=q)
    except Abort as e:
        q.record_abort(str(e))
        q.save()
        print(f"ABORTED: {e}")
        return 0
    q.record_success()
    q.save()
    print_sample(story)
    with open("story_sample.json", "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
