"""python -m src.render — render ALL parts of the READY_TO_RENDER story, QA them, then buffer the whole story."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

from src.audio import tts
from src.common.config import ROOT, categories, settings
from src.common.ids import make_episode_id, release_tag
from src.common.quota import Quota
from src.common.retry import Abort
from src.common.state import load_state, save_state
from src.kaggle_jobs import cli_tools
from src.kaggle_jobs.job import panel_id
from src.render import frames, timeline, video


def build_part_timeline(story: dict, part: dict, voices: dict[str, str]) -> timeline.Timeline:
    total = int(story["parts"])
    cap = settings()["story"]["part_seconds"]["hard_cap"]
    for speed in (1.0, 1.08, 1.15):
        tl = timeline.build(part, story, voices, tts.synth, speed=speed, final=part["part"] == total)
        if tl.duration <= cap:
            return tl
        print(f"[render] part {part['part']} is {tl.duration:.1f}s at speed {speed}; retrying faster", flush=True)
    raise Abort(f"Part {part['part']} exceeds {cap}s even at 1.15x speech")


def qa_report(story: dict) -> dict:
    art = story.get("art", {})
    return {"story_id": story["story_id"], "title": story["title"], "judge": story.get("judge"),
            "portraits": {n: {"approved": p.get("approved"), "qa": p.get("qa")} for n, p in art.get("portraits", {}).items()},
            "panels": {pid: {"approved": s.get("approved"), "qa": s.get("qa"), "prefilter": s.get("prefilter")}
                       for pid, s in art.get("panels", {}).items()},
            "log": art.get("log", [])}


def render_story(story: dict) -> dict:
    tag = release_tag(story["story_id"])
    work = ROOT / "work" / story["story_id"] / "render"
    work.mkdir(parents=True, exist_ok=True)
    art = story["art"]["panels"]
    names = [art[panel_id(p["part"], int(x["id"]))]["approved"] for p in story["parts"] for x in p["panels"]]
    files = cli_tools.download_assets(tag, names, ROOT / "work" / story["story_id"] / "assets")
    voices = tts.assign_voices(story["cast"]) | {"Narrator": tts.pick_voice(None)}
    mood = story.get("music_mood") or categories()["categories"][story["category"]]["music_mood"]
    total = int(story["parts"])
    episodes, uploads = [], []
    for part in story["parts"]:
        imgs = {str(x["id"]): Image.open(files[art[panel_id(part["part"], int(x["id"]))]["approved"]]) for x in part["panels"]}
        ep_id = make_episode_id(story["story_id"], part["part"], total)
        out = work / f"{ep_id}.mp4"
        errs = []
        for attempt in range(2):
            tl = build_part_timeline(story, part, voices)
            video.encode(tl, imgs, mood, out)
            errs = video.render_qa(out)
            print(f"[render] {ep_id} attempt {attempt + 1}: {tl.duration:.1f}s QA={errs or 'PASS'}", flush=True)
            if not errs:
                break
        if errs:
            raise Abort(f"Render QA failed twice for {ep_id}: {errs}")
        hook_img = imgs[str(part["panels"][0]["id"])]
        cover_words = part["title"].split("|")[0].strip().rstrip("…")
        cover = frames.cover(hook_img.convert("RGB").resize((1080, 1920)), cover_words, part["part"], total, work / f"{ep_id}_cover.jpg")
        uploads += [out, cover]
        episodes.append({"episode_id": ep_id, "part": part["part"], "total": total, "title": part["title"],
                         "description": part.get("description", ""), "caption": part.get("caption", ""),
                         "hashtags": part.get("hashtags", []), "video_asset": out.name, "cover_asset": cover.name,
                         "duration": round(tl.duration, 2), "moral": story["moral"] if part["part"] == total else None})
    script = work / "script.json"
    script.write_text(json.dumps({k: story[k] for k in ["story_id", "title", "category", "logline", "moral", "cast", "beats", "parts"]},
                                 indent=2, ensure_ascii=False))
    report = work / "qa_report.json"
    report.write_text(json.dumps(qa_report(story), indent=2, ensure_ascii=False))
    cli_tools.upload_assets(tag, uploads + [script, report])
    return {"story_id": story["story_id"], "title": story["title"], "category": story["category"], "logline": story["logline"],
            "moral": story["moral"], "release_tag": tag, "buffered_at": time.time(), "episodes": episodes}


def main() -> int:
    q = Quota()
    b = load_state("story_bible.json")
    story = b.get("current")
    if not story or story.get("status") != "READY_TO_RENDER":
        print("Nothing to render.")
        return 0
    try:
        entry = render_story(story)
    except Abort as e:
        from src.kaggle_jobs.__main__ import abort_story

        abort_story(b, story, str(e), q)
        save_state("story_bible.json", b)
        q.save()
        return 0
    buf = load_state("buffer.json", {"stories": []})
    buf["stories"].append(entry)
    save_state("buffer.json", buf)
    used = b.setdefault("used", {"categories": [], "settings": [], "morals": [], "premises": []})
    used["categories"].append(story["category"])
    used["settings"].append(story["setting"])
    used["morals"].append(story["moral"])
    used["premises"].append(story["logline"])
    b.setdefault("history", []).append({"story_id": story["story_id"], "title": story["title"], "category": story["category"],
                                        "status": "BUFFERED", "at": time.time(), "platform_ids": {}})
    story["status"] = "BUFFERED"
    b["archive"] = {story["story_id"]: story} | b.get("archive", {})
    b["current"] = None
    save_state("story_bible.json", b)
    q.record_success()
    q.save()
    print(f"BUFFERED: {entry['title']} ({len(entry['episodes'])} parts) -> draft release {entry['release_tag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
