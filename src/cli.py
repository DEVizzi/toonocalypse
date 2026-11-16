"""Unified CLI entrypoint for Toonocalypse GitHub Actions workflows."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analytics.learning_loop import run_learning_loop
from src.art.image_gen import generate_comic_page
from src.art.qa import check_page_qa
from src.art.ref_builder import build_ref_sheet
from src.audio.sfx import ensure_sfx_library
from src.common.config import ROOT, load_all_characters, load_settings
from src.common.quota import QuotaTracker
from src.common.state import load_state, save_state
from src.moderation.gate import check_metadata, check_script
from src.monitoring.alerts import open_alert_issue
from src.monitoring.health_report import publish_weekly_health_report
from src.panels.cover import build_cover_image
from src.panels.slicer import slice_page
from src.publish.coordinator import can_publish_episode_today, record_platform_publish
from src.publish.instagram import publish_to_instagram
from src.publish.releases import (
    cleanup_old_releases,
    download_release_assets,
    list_buffer_releases,
    upload_episode_to_release,
)
from src.publish.youtube import publish_to_youtube
from src.render.compiler import compile_wide_film
from src.render.qa import check_render_qa
from src.render.vertical import render_episode_formats
from src.story.generator import generate_part_script
from src.story.hook_gate import judge_script
from src.story.ideas import check_holiday_trigger, pick_unused_seed_idea
from src.story.planner import choose_format, pick_setting, rotate_cliffhangers, select_cast
from src.tokens.instagram_auth import refresh_instagram_token
from src.tokens.watchdog import run_watchdog


def generate_episode_bundle(
    work_dir: Path,
    forced_format: str | None = None,
    forced_heroes: list[str] | None = None,
    forced_villain: str | None = None,
    offline: bool = False,
    part_num: int = 1,
    part_count_override: int | None = None,
    story_id_override: str | None = None,
    title_override: str | None = None,
    upload_release: bool = True,
    draft_release: bool = False,
) -> dict[str, Any]:
    """Generate one complete episode bundle (script, art, panels, videos, metadata)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    bible = load_state("story_bible.json", default={"used_ideas": [], "episodes": [], "active_arc": None})
    quota = QuotaTracker()
    ensure_sfx_library()

    holiday = check_holiday_trigger()
    fmt, part_count = choose_format(bible, holiday=holiday, forced_format=forced_format)
    if part_count_override is not None:
        part_count = part_count_override
    heroes, villain = select_cast(
        bible, fmt, forced_heroes=forced_heroes, forced_villain=forced_villain
    )
    setting = pick_setting(bible)
    idea = pick_unused_seed_idea(bible)
    cliffhangers = rotate_cliffhangers(part_count)
    cliff = cliffhangers[min(part_num - 1, len(cliffhangers) - 1)]

    story_id = story_id_override or f"ep-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    title = title_override or " ".join(idea.split()[:6]).rstrip(".,!?")
    episode_id = f"{story_id}-pt{part_num}of{part_count}"

    script = generate_part_script(
        story_id=story_id,
        title=title,
        part_num=part_num,
        part_count=part_count,
        heroes=heroes,
        villain=villain,
        setting=setting,
        idea=idea,
        cliffhanger_type=cliff,
        offline=offline,
        quota=quota,
    )

    mod = check_script(script, use_llm=not offline)
    if not mod.passed:
        raise RuntimeError(f"Script moderation failed: {mod.reasons}")

    hook_res = judge_script(script, offline=offline, quota=quota)
    if not hook_res.passed:
        raise RuntimeError(f"Hook gate failed ({hook_res.avg_score}): {hook_res.feedback}")

    page_path = work_dir / f"{episode_id}_page.png"
    generate_comic_page(script, page_path, offline=offline, quota=quota)
    art_qa = check_page_qa(page_path, script, offline=offline, quota=quota)
    if not art_qa.passed:
        raise RuntimeError(f"Art QA failed: {art_qa.reasons}")

    panels_dir = work_dir / "panels"
    panel_paths = slice_page(page_path, panels_dir)
    if len(panel_paths) != 6:
        raise RuntimeError(f"Expected 6 sliced panels, got {len(panel_paths)}")

    cover_path = work_dir / f"{episode_id}_cover.jpg"
    build_cover_image(
        panel_paths[0],
        cover_path,
        hook_words=script.get("on_screen_hook", "WAIT FOR IT!"),
        part_num=part_num,
        part_count=part_count,
    )

    videos = render_episode_formats(script, panel_paths, work_dir / "render")
    yt_qa = check_render_qa(videos["youtube"], is_vertical=True)
    ig_qa = check_render_qa(videos["instagram"], is_vertical=True)
    wide_qa = check_render_qa(videos["wide"], is_vertical=False)
    for name, q in (("youtube", yt_qa), ("instagram", ig_qa), ("wide", wide_qa)):
        if not q.passed:
            raise RuntimeError(f"Render QA failed for {name}: {q.reasons}")

    meta = {
        "episode_id": episode_id,
        "story_id": story_id,
        "format": fmt,
        "title": script.get("title", title),
        "part_num": part_num,
        "part_count": part_count,
        "heroes": heroes,
        "villain": villain,
        "setting": setting,
        "cliffhanger_type": cliff,
        "description": script.get("description", f"{title} - Toonocalypse motion comic!"),
        "caption": script.get("caption", f"{title} #Toonocalypse #MotionComic #Shorts"),
        "tags": script.get("tags", ["Toonocalypse", "MotionComic", "Animation", "FamilyFriendly"]),
        "hook_score": hook_res.avg_score,
        "art_anchor_score": art_qa.anchor_score,
        "youtube_duration": yt_qa.duration,
        "instagram_duration": ig_qa.duration,
        "wide_duration": wide_qa.duration,
    }
    meta_mod = check_metadata(meta["title"], meta["description"], meta["caption"], meta["tags"])
    if not meta_mod.passed:
        raise RuntimeError(f"Metadata moderation failed: {meta_mod.reasons}")

    script_path = work_dir / "script.json"
    meta_path = work_dir / "metadata.json"
    script_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    yt_final = work_dir / f"{episode_id}_youtube.mp4"
    ig_final = work_dir / f"{episode_id}_instagram.mp4"
    wide_final = work_dir / f"{episode_id}_wide.mp4"
    videos["youtube"].replace(yt_final)
    videos["instagram"].replace(ig_final)
    videos["wide"].replace(wide_final)

    if upload_release:
        tag = f"ep-{episode_id}"
        upload_episode_to_release(
            tag=tag,
            files=[yt_final, ig_final, wide_final, cover_path, page_path, script_path, meta_path],
            title=f"Episode {episode_id}: {meta['title']}",
            notes=f"Format: {fmt} | Heroes: {', '.join(heroes)} | Hook: {hook_res.avg_score}",
            draft=draft_release,
        )

    if not draft_release:
        used = set(bible.get("used_ideas", []))
        if idea:
            used.add(idea)
        bible["used_ideas"] = sorted(used)
        save_state("story_bible.json", bible)

    return {
        "episode_id": episode_id,
        "files": {
            "youtube": str(yt_final),
            "instagram": str(ig_final),
            "wide": str(wide_final),
            "cover": str(cover_path),
            "page": str(page_path),
            "script": str(script_path),
            "metadata": str(meta_path),
        },
        "meta": meta,
    }


def cmd_generate(args: argparse.Namespace) -> int:
    settings = load_settings()
    target_buffer = int(settings.get("buffer_days", 3))
    existing = list_buffer_releases() if not args.offline and not args.draft else []
    if not args.force and len(existing) >= target_buffer:
        print(f"Buffer already has {len(existing)} >= {target_buffer} releases; skipping.")
        return 0
    with tempfile.TemporaryDirectory() as td:
        heroes = args.heroes.split(",") if args.heroes else None
        res = generate_episode_bundle(
            Path(td),
            forced_format=args.format,
            forced_heroes=heroes,
            forced_villain=args.villain,
            offline=args.offline,
            upload_release=not args.no_release,
            draft_release=args.draft,
        )
        print(json.dumps(res, indent=2))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    releases = list_buffer_releases()
    if not releases:
        open_alert_issue(
            "[Alert] Publish Buffer Empty",
            "No buffered episodes found in GitHub Releases.",
            dedup_key="buffer-empty",
        )
        return 1

    pub_state = load_state("published.json", default={"episodes": {}, "daily_posts": {}})
    chosen = None
    for rel in releases:
        tag = rel.get("tagName", "")
        ep_id = tag.removeprefix("buffer-").removeprefix("ep-")
        ep_rec = pub_state.get("episodes", {}).get(ep_id, {})
        if not (ep_rec.get("youtube", {}).get("id") and ep_rec.get("instagram", {}).get("id")):
            chosen = (tag, ep_id)
            break

    if not chosen:
        print("All buffered releases are already published to both platforms.")
        return 0

    tag, ep_id = chosen
    if not can_publish_episode_today(ep_id, pub_state=pub_state):
        print(f"Daily publish cap already reached for today; skipping {ep_id}.")
        return 0

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        download_release_assets(tag, dest)
        meta = json.loads((dest / "metadata.json").read_text(encoding="utf-8"))
        yt_video = dest / f"{ep_id}_youtube.mp4"
        ig_video = dest / f"{ep_id}_instagram.mp4"

        ep_rec = pub_state.get("episodes", {}).get(ep_id, {})
        if not ep_rec.get("youtube", {}).get("id"):
            yt_id = publish_to_youtube(
                yt_video,
                episode_id=ep_id,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
                part_num=meta.get("part_num", 1),
                part_count=meta.get("part_count", 1),
            )
            record_platform_publish(ep_id, "youtube", yt_id)

        if not ep_rec.get("instagram", {}).get("id"):
            ig_id = publish_to_instagram(
                ig_video,
                episode_id=ep_id,
                caption=meta["caption"],
            )
            record_platform_publish(ep_id, "instagram", ig_id)

    cleanup_old_releases(retention_days=30)
    print(f"Published episode {ep_id}.")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    releases = list_buffer_releases()
    if len(releases) < 2:
        print("Not enough episodes to compile yet.")
        return 0
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        wides: list[Path] = []
        for rel in releases[:6]:
            tag = rel["tagName"]
            sub = dest / tag
            sub.mkdir(parents=True, exist_ok=True)
            download_release_assets(tag, sub)
            wides.extend(sorted(sub.glob("*_wide.mp4")))
        if len(wides) < 2:
            print("No wide clips found for compilation.")
            return 0
        out_mp4 = dest / "toonocalypse_compilation.mp4"
        compile_wide_film("Toonocalypse Movie Compilation", wides, out_mp4, dest / "work")
        qa = check_render_qa(out_mp4, is_vertical=False)
        if not qa.passed:
            raise RuntimeError(f"Compilation QA failed: {qa.reasons}")
        if not args.dry_run:
            upload_episode_to_release(
                tag=f"compilation-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                files=[out_mp4],
                title="Toonocalypse Long-Form Compilation",
                draft=args.draft,
            )
    return 0


def cmd_build_refs(args: argparse.Namespace) -> int:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_scale_chart.py")], check=True)
    chars = load_all_characters()
    quota = QuotaTracker()
    built = 0
    for slug in sorted(chars.keys()):
        ref_path = build_ref_sheet(slug, offline=args.offline, quota=quota)
        print(f"Ref ready: {ref_path}")
        built += 1
    print(f"Built/verified {built} character reference sheets.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="toonocalypse")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--format", default=None)
    p_gen.add_argument("--heroes", default=None)
    p_gen.add_argument("--villain", default=None)
    p_gen.add_argument("--offline", action="store_true")
    p_gen.add_argument("--draft", action="store_true")
    p_gen.add_argument("--no-release", action="store_true")
    p_gen.add_argument("--force", action="store_true")

    sub.add_parser("publish")

    p_comp = sub.add_parser("compile")
    p_comp.add_argument("--dry-run", action="store_true")
    p_comp.add_argument("--draft", action="store_true")

    p_refs = sub.add_parser("build-refs")
    p_refs.add_argument("--offline", action="store_true")

    p_tok = sub.add_parser("tokens-refresh")
    p_tok.add_argument("--force", action="store_true")

    sub.add_parser("watchdog")

    p_ana = sub.add_parser("analytics")
    p_ana.add_argument("--offline", action="store_true")

    p_rep = sub.add_parser("health-report")
    p_rep.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "publish":
        return cmd_publish(args)
    if args.cmd == "compile":
        return cmd_compile(args)
    if args.cmd == "build-refs":
        return cmd_build_refs(args)
    if args.cmd == "tokens-refresh":
        print(json.dumps(refresh_instagram_token(force=args.force), indent=2))
        return 0
    if args.cmd == "watchdog":
        res = run_watchdog()
        print(json.dumps(res, indent=2))
        return 1 if res.get("problems") else 0
    if args.cmd == "analytics":
        print(json.dumps(run_learning_loop(offline=args.offline), indent=2))
        return 0
    if args.cmd == "health-report":
        print(publish_weekly_health_report(dry_run=args.dry_run))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
