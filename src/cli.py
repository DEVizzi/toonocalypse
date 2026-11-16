"""Unified CLI entrypoint for Toonocalypse GitHub Actions workflows (§6 & §7)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analytics.learning_loop import run_learning_loop
from src.art.image_gen import render_offline_comic_page
from src.art.library import (
    available_assets_for_cast,
    ensure_art_library_downloaded,
    load_library_index,
    queue_missing_assets,
    save_library_index,
)
from src.art.qa import check_page_qa
from src.art.ref_builder import build_ref_sheet
from src.audio.sfx import ensure_sfx_library
from src.audio.tts import tts_reachable
from src.common.config import ROOT, load_all_characters, load_settings
from src.common.gemini import AllTextModelsFailed, discover_text_models, extract_retry_delay_seconds, has_gemini_key
from src.common.ids import make_episode_id, make_release_tag, make_story_id
from src.common.quota import QuotaTracker
from src.common.state import load_state, save_state
from src.monitoring.alerts import close_alert_issue, open_alert_issue
from src.monitoring.health_report import publish_weekly_health_report
from src.panels.compose import compose_comic_page
from src.panels.cover import build_cover_image
from src.panels.slicer import slice_page
from src.publish.buffer import add_to_buffer, buffer_size, pick_next_publishable, remove_from_buffer
from src.publish.coordinator import can_publish_episode_today, record_platform_publish, today_local_str
from src.publish.gate import evaluate_publishable
from src.publish.instagram import publish_to_instagram
from src.publish.releases import cleanup_old_releases, download_release_assets, upload_episode_to_release
from src.publish.youtube import publish_to_youtube
from src.render.compiler import compile_wide_film
from src.render.qa import check_render_qa
from src.render.vertical import render_episode_formats
from src.story.generator import generate_part_script
from src.story.ideas import check_holiday_trigger, pick_unused_seed_idea
from src.story.planner import choose_format, pick_setting, rotate_cliffhangers, select_cast
from src.tokens.instagram_auth import refresh_instagram_token
from src.tokens.watchdog import run_watchdog


class AbortPipeline(RuntimeError):
    """Expected fail-fast abort (§6.4): ends job with success and ABORTED summary."""

    def __init__(self, reason: str, retry_delay_sec: float = 0.0):
        super().__init__(reason)
        self.reason = reason
        self.retry_delay_sec = retry_delay_sec


def _write_step_summary(line: str) -> None:
    print(line)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def run_preflight(
    quota: QuotaTracker,
    forced_heroes: list[str] | None = None,
    forced_villain: str | None = None,
    offline: bool = False,
    force_fail_preflight: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Fail-fast §6.1a preflight check (<= 2 min) before any scripting, TTS, or rendering."""
    if force_fail_preflight:
        raise AbortPipeline("Deliberate preflight failure check")

    paused, until = quota.is_paused()
    if paused:
        raise AbortPipeline(f"Generation paused until {until}")

    if offline:
        return {"characters": {}, "backgrounds": {}}, ["idle", "talking", "surprised", "laughing", "jump", "point"], ["frosty-espresso-bar"]

    if not has_gemini_key():
        raise AbortPipeline("GOOGLE_API_KEY is not set")

    if not quota.can_spend("text", 3):
        raise AbortPipeline("Insufficient daily text quota headroom")

    models = discover_text_models()
    if not models:
        raise AbortPipeline("No usable Gemini text models available on v1beta")

    tts_ok, tts_msg = tts_reachable()
    if not tts_ok:
        raise AbortPipeline(f"TTS unreachable: {tts_msg}")

    lib_idx = ensure_art_library_downloaded()
    if not lib_idx.get("characters") or not lib_idx.get("backgrounds"):
        chars = list(forced_heroes or ["brewtan-the-yeti", "detective-bubbles"])
        if forced_villain:
            chars.append(forced_villain)
        queue_missing_assets(chars, ["frosty-espresso-bar"])
        raise AbortPipeline("Art library missing; queued required assets for next Kaggle batch")

    check_slugs = list(forced_heroes or [])
    if forced_villain:
        check_slugs.append(forced_villain)
    if check_slugs:
        ok, poses, bgs = available_assets_for_cast(check_slugs, lib_idx)
        if not ok:
            queue_missing_assets(check_slugs, [])
            raise AbortPipeline(f"Art library missing assets for cast {check_slugs}; queued")
        return lib_idx, poses, bgs

    # Pick any available poses/backgrounds from the library
    first_poses = sorted(next(iter(lib_idx["characters"].values())).keys())
    return lib_idx, first_poses, sorted(lib_idx["backgrounds"].keys())


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
    draft_release: bool = True,
    force_fail_preflight: bool = False,
) -> dict[str, Any]:
    """Run §6.1 fail-fast generation pipeline and §6.2 publishable gate."""
    work_dir.mkdir(parents=True, exist_ok=True)
    quota = QuotaTracker()
    lib_idx, allowed_poses, allowed_bgs = run_preflight(
        quota,
        forced_heroes=forced_heroes,
        forced_villain=forced_villain,
        offline=offline,
        force_fail_preflight=force_fail_preflight,
    )

    bible = load_state("story_bible.json", default={"used_ideas": [], "episodes": [], "active_arc": None})
    ensure_sfx_library()

    holiday = check_holiday_trigger()
    fmt, part_count = choose_format(bible, holiday=holiday, forced_format=forced_format)
    if part_count_override is not None:
        part_count = part_count_override

    heroes, villain = select_cast(bible, fmt, forced_heroes=forced_heroes, forced_villain=forced_villain)
    if not offline:
        ok, poses, bgs = available_assets_for_cast(heroes + [villain], lib_idx)
        if not ok:
            # Try selecting a cast that IS in the library
            lib_chars = sorted(s for s, poses in lib_idx.get("characters", {}).items() if poses)
            all_chars = load_all_characters()
            lib_heroes = [s for s in lib_chars if s in all_chars and all_chars[s]["role"] == "hero"]
            lib_villains = [s for s in lib_chars if s in all_chars and all_chars[s]["role"] == "villain"]
            if len(lib_heroes) < 2 or not lib_villains:
                queue_missing_assets(heroes + [villain], [])
                raise AbortPipeline("Not enough cast characters in art library; queued missing cast")
            heroes = lib_heroes[:2]
            villain = lib_villains[0]
            ok, poses, bgs = available_assets_for_cast(heroes + [villain], lib_idx)
            if not ok:
                raise AbortPipeline("No compatible cast poses in art library")
        allowed_poses, allowed_bgs = poses, bgs

    setting = allowed_bgs[0] if allowed_bgs else pick_setting(bible)
    idea = pick_unused_seed_idea(bible)
    cliffhangers = rotate_cliffhangers(part_count)
    cliff = cliffhangers[min(part_num - 1, len(cliffhangers) - 1)]

    story_id = story_id_override or make_story_id()
    episode_id = make_episode_id(story_id, part_num, part_count)
    release_tag = make_release_tag(episode_id)

    try:
        script = generate_part_script(
            story_id=story_id,
            title=title_override,
            part_num=part_num,
            part_count=part_count,
            heroes=heroes,
            villain=villain,
            setting=setting,
            idea=idea,
            cliffhanger_type=cliff,
            offline=offline,
            quota=quota,
            allowed_poses=allowed_poses,
            allowed_backgrounds=allowed_bgs,
        )
    except AllTextModelsFailed as exc:
        raise AbortPipeline(str(exc), retry_delay_sec=extract_retry_delay_seconds(exc)) from exc

    page_path = work_dir / f"{episode_id}_page.png"
    panel_layers: list[dict[str, Path]] | None = None
    used_library_art = False
    if offline:
        render_offline_comic_page(script, page_path)
    else:
        print(f"[pipeline] Composing comic page for {episode_id}...", flush=True)
        _, panel_layers = compose_comic_page(script, lib_idx, work_dir, page_path)
        used_library_art = True

    print(f"[pipeline] Running panel QA for {episode_id}...", flush=True)
    art_qa = check_page_qa(page_path, script, offline=offline, quota=quota)
    if not art_qa.passed and not offline:
        raise AbortPipeline(f"Panel QA failed: {art_qa.reasons}")

    panels_dir = work_dir / "panels"
    panel_paths = slice_page(page_path, panels_dir)
    if len(panel_paths) != 6:
        raise AbortPipeline(f"Expected 6 sliced panels, got {len(panel_paths)}")

    cover_path = work_dir / f"{episode_id}_cover.jpg"
    build_cover_image(
        panel_paths[0],
        cover_path,
        hook_words=script.get("on_screen_hook", "WATCH THIS!"),
        part_num=part_num,
        part_count=part_count,
    )

    is_one_shot = part_count <= 1
    print(f"[pipeline] Rendering video formats for {episode_id}...", flush=True)
    videos = render_episode_formats(script, panel_paths, work_dir / "render", panel_layers=panel_layers, offline=offline)
    print(f"[pipeline] Running render QA for {episode_id}...", flush=True)
    yt_qa = check_render_qa(videos["youtube"], is_vertical=True, is_one_shot=is_one_shot)
    ig_qa = check_render_qa(videos["instagram"], is_vertical=True, is_one_shot=is_one_shot)
    wide_qa = check_render_qa(videos["wide"], is_vertical=False, is_one_shot=is_one_shot)

    pub_gate = evaluate_publishable(
        script=script,
        art_qa_passed=art_qa.passed,
        used_library_art=used_library_art,
        yt_qa=yt_qa,
        ig_qa=ig_qa,
    )
    if not offline and not pub_gate.publishable:
        raise AbortPipeline(f"Episode not publishable: {pub_gate.reasons}")

    meta = {
        "episode_id": episode_id,
        "release_tag": release_tag,
        "story_id": story_id,
        "format": fmt,
        "title": script["title"],
        "part_num": part_num,
        "part_count": part_count,
        "heroes": heroes,
        "villain": villain,
        "setting": setting,
        "cliffhanger_type": cliff,
        "description": script.get("description", f"{script['title']} - Toonocalypse motion comic!"),
        "caption": script.get("caption", f"{script['title']} #Toonocalypse #MotionComic #Shorts"),
        "tags": script.get("tags", ["Toonocalypse", "MotionComic", "Animation", "FamilyFriendly"]),
        "hook_score": script.get("hook_gate", {}).get("avg", 0.0),
        "model_used": script.get("model_used", ""),
        "art_anchor_score": art_qa.anchor_score,
        "youtube_duration": yt_qa.duration,
        "instagram_duration": ig_qa.duration,
        "wide_duration": wide_qa.duration,
        "publishable": pub_gate.publishable,
        "publishable_reasons": pub_gate.reasons,
    }

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

    if upload_release and pub_gate.publishable:
        upload_episode_to_release(
            tag=release_tag,
            files=[yt_final, ig_final, wide_final, cover_path, page_path, script_path, meta_path],
            title=f"Episode {episode_id}: {meta['title']}",
            notes=f"Format: {fmt} | Model: {meta['model_used']} | Hook: {meta['hook_score']}",
            draft=draft_release,
        )
        add_to_buffer(meta)

    if not offline and pub_gate.publishable:
        used = set(bible.get("used_ideas", []))
        if idea:
            used.add(idea)
        bible["used_ideas"] = sorted(used)
        save_state("story_bible.json", bible)
        quota.record_success()
        close_alert_issue("generation-paused-buffer-low", "Episode generated successfully; generation resumed.")

    return {
        "episode_id": episode_id,
        "publishable": pub_gate.publishable,
        "publishable_reasons": pub_gate.reasons,
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


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def cmd_generate(args: argparse.Namespace) -> int:
    settings = load_settings()
    target_buffer = int(settings.get("buffer_days", 3))
    quota = QuotaTracker()

    paused, until = quota.is_paused()
    if paused and not args.force:
        _write_step_summary(f"ABORTED: Generation paused until {until}")
        return 0

    if not args.force and not args.offline and buffer_size() >= target_buffer:
        _write_step_summary(f"Buffer already has {buffer_size()} >= {target_buffer} publishable episodes; idle exit.")
        return 0

    try:
        with tempfile.TemporaryDirectory() as td:
            heroes = [h.strip() for h in args.heroes.split(",") if h.strip()] if args.heroes else None
            res = generate_episode_bundle(
                Path(td),
                forced_format=args.format or None,
                forced_heroes=heroes,
                forced_villain=args.villain or None,
                offline=args.offline,
                upload_release=not args.no_release,
                draft_release=args.draft,
                force_fail_preflight=args.fail_preflight,
            )
            print(json.dumps(res["meta"], indent=2))
            return 0
    except AbortPipeline as exc:
        state = quota.record_abort(exc.reason, retry_delay_sec=exc.retry_delay_sec)
        open_alert_issue(
            title="Generation paused / buffer low",
            body=(
                f"- Reason: `{exc.reason}`\n"
                f"- Consecutive aborts: `{state.get('consecutive_aborts')}`\n"
                f"- Next retry (`paused_until`): `{state.get('paused_until')}`\n"
                f"- Buffer size: `{buffer_size()}`"
            ),
            dedup_key="generation-paused-buffer-low",
        )
        _write_step_summary(f"ABORTED: {exc.reason}")
        return 0


def cmd_publish(_args: argparse.Namespace) -> int:
    pub_state = load_state("published.json", default={"episodes": {}, "daily_posts": {}})
    chosen = pick_next_publishable(pub_state=pub_state)
    if not chosen:
        today = today_local_str()
        pub_state.setdefault("daily_posts", {})[today] = {"status": "skipped_empty_buffer"}
        save_state("published.json", pub_state)
        open_alert_issue(
            title="Generation paused / buffer low",
            body=f"- Publish skipped on `{today}`: buffer empty or waiting for missing story part.\n- Buffer size: `{buffer_size()}`",
            dedup_key="generation-paused-buffer-low",
        )
        _write_step_summary(f"SKIPPED: No publishable episode ready for {today} (recorded no-op).")
        return 0

    ep_id = chosen["episode_id"]
    tag = chosen.get("release_tag") or make_release_tag(ep_id)
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
            repo_slug = os.environ.get("GITHUB_REPOSITORY", "DEVizzi/toonocalypse")
            ig_video_url = f"https://github.com/{repo_slug}/releases/download/{tag}/{ig_video.name}"
            ig_id = publish_to_instagram(
                ig_video,
                episode_id=ep_id,
                caption=meta["caption"],
                video_url=ig_video_url,
            )
            record_platform_publish(ep_id, "instagram", ig_id)

    remove_from_buffer(ep_id)
    cleanup_old_releases(retention_days=30)
    print(f"Published episode {ep_id}.")
    return 0


def cmd_import_art_library(args: argparse.Namespace) -> int:
    src_dir = Path(args.dir)
    idx_file = src_dir / "library_index.json"
    if not idx_file.exists():
        raise FileNotFoundError(f"Missing {idx_file}")
    index = json.loads(idx_file.read_text(encoding="utf-8"))
    dest_root = ROOT / "assets" / "art_library"
    dest_root.mkdir(parents=True, exist_ok=True)
    ensure_art_library_downloaded(dest_root)
    shutil.copytree(src_dir, dest_root, dirs_exist_ok=True)
    save_library_index(index)

    # Clear fulfilled items from art_queue.json
    q = load_state("art_queue.json", {"characters": [], "backgrounds": []})
    q["characters"] = [c for c in q.get("characters", []) if not index.get("characters", {}).get(c)]
    q["backgrounds"] = [b for b in q.get("backgrounds", []) if b not in index.get("backgrounds", {})]
    save_state("art_queue.json", q)

    tag = f"art-library-v{index.get('version', 1)}"
    archive = shutil.make_archive(str(src_dir.parent / tag), "zip", root_dir=str(dest_root))
    upload_episode_to_release(
        tag=tag,
        files=[Path(archive), idx_file],
        title=f"Toonocalypse Art Library v{index.get('version', 1)}",
        notes=f"Characters: {len(index.get('characters', {}))} | Backgrounds: {len(index.get('backgrounds', {}))}",
        draft=False,
    )
    print(f"Imported and released {tag}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    pub = load_state("published.json", default={"episodes": {}})
    eps = [k for k in pub.get("episodes", {}).keys()]
    if len(eps) < 2:
        print("Not enough published episodes to compile yet.")
        return 0
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        wides: list[Path] = []
        for ep_id in eps[:6]:
            tag = make_release_tag(ep_id)
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
    for slug in sorted(chars.keys()):
        build_ref_sheet(slug, offline=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="toonocalypse")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--format", default=os.environ.get("TOON_FORMAT", ""))
    p_gen.add_argument("--heroes", default=os.environ.get("TOON_HEROES", ""))
    p_gen.add_argument("--villain", default=os.environ.get("TOON_VILLAIN", ""))
    p_gen.add_argument("--offline", action="store_true", default=_env_bool("TOON_OFFLINE", False))
    p_gen.add_argument("--draft", action="store_true", default=_env_bool("TOON_DRAFT", True))
    p_gen.add_argument("--no-release", action="store_true", default=_env_bool("TOON_NO_RELEASE", False))
    p_gen.add_argument("--force", action="store_true", default=_env_bool("TOON_FORCE", False))
    p_gen.add_argument("--fail-preflight", action="store_true", default=_env_bool("TOON_FAIL_PREFLIGHT", False))

    sub.add_parser("publish")

    p_imp = sub.add_parser("import-art-library")
    p_imp.add_argument("--dir", required=True)

    p_comp = sub.add_parser("compile")
    p_comp.add_argument("--dry-run", action="store_true", default=_env_bool("TOON_DRY_RUN", False))
    p_comp.add_argument("--draft", action="store_true", default=_env_bool("TOON_DRAFT", False))

    sub.add_parser("build-refs")

    p_tok = sub.add_parser("tokens-refresh")
    p_tok.add_argument("--force", action="store_true", default=_env_bool("TOON_FORCE", False))

    sub.add_parser("watchdog")

    p_ana = sub.add_parser("analytics")
    p_ana.add_argument("--offline", action="store_true", default=_env_bool("TOON_OFFLINE", False))

    p_rep = sub.add_parser("health-report")
    p_rep.add_argument("--dry-run", action="store_true", default=_env_bool("TOON_DRY_RUN", False))

    args = parser.parse_args()
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "publish":
        return cmd_publish(args)
    if args.cmd == "import-art-library":
        return cmd_import_art_library(args)
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
