"""The Tuno Report CLI: render (and when live, publish) a ToonToonCastle season recap to YouTube.

    python -m src.recap.run --mode auto                    # daily cron: publishes the next due part, else exits 0
    python -m src.recap.run --mode part1 --season 1 --dry-run
    python -m src.recap.run --mode preview --dry-run       # the latest (up to) 10 races so far, never uploads
    python -m src.recap.run --mode demo --dry-run          # CI end-to-end: simulates a 10-race demo season in output/

Live publishing fails closed: the rebuilt table must match `state/` exactly, MC Tuno's voice must be synthesized, and
ffprobe must confirm a 1920x1080 H.264 + AAC file before anything is uploaded. Only `state/recaps.json` is written.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.recap import schedule  # noqa: E402

STATE_DIR = ROOT / "state"
OUT_DIR = ROOT / "output" / "recap"
PART_TITLES = {
    "part1": "Season {s} Recap Part 1: Races 1-10 😂 The Tuno Report | ToonToonCastle",
    "part2": "Season {s} Recap Part 2: Races 11-20 💥 The Tuno Report | ToonToonCastle",
    "part3": "Season {s} FINALE: Playoffs + Grand Final 👑 The Tuno Report | ToonToonCastle",
    "preview": "Season {s} So Far: Races {a}-{b} 😂 The Tuno Report | ToonToonCastle",
}
TAGS = ["ToonToonCastle", "The Tuno Report", "marble race", "marble race recap", "marble league", "ball race",
        "season recap", "funny marble race", "marble race compilation", "physics simulation", "marble run",
        "cartoon race"]


def _fmt_ts(sec: float) -> str:
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def build_metadata(recap, info: dict, awards: list) -> dict[str, Any]:
    from src.recap.comedy import name

    s = recap.season
    title = PART_TITLES.get(recap.kind, PART_TITLES["preview"]).format(s=s, a=recap.start_race, b=recap.end_race)[:100]
    hook = {
        "part1": f"The first 10 races of ToonToonCastle Season {s}, replayed and roasted by MC Tuno.",
        "part2": f"Races 11-20 of ToonToonCastle Season {s}: more chaos, more betrayals, more crash dummies.",
        "part3": f"The ToonToonCastle Season {s} finale: the last league races, the playoffs and the Grand Final.",
    }.get(recap.kind, f"ToonToonCastle Season {s}, races {recap.start_race}-{recap.end_race}, replayed by MC Tuno.")
    lines = [hook, "", "⏱️ Chapters"] + [f"{_fmt_ts(t)} {c}" for t, c in info.get("chapters", [])]
    if awards:
        lines += ["", "🏆 The Tunos"] + [f"• {a.title.title()}: {name(a.hero)} ({a.stat.lower()})" for a in awards]
    table = recap.standings[:5]
    lines += ["", ("👑 Final table" if recap.end_race >= 30 else f"📊 Table after race {recap.end_race}")]
    lines += [f"{i + 1}. {name(k)} — {v['points']} pts" for i, (k, v) in enumerate(table)]
    if recap.champion:
        lines += ["", f"👑 Season {s} champion: {name(recap.champion)}"]
    lines += ["", "Every race is a real 2D physics simulation — nothing is scripted. Replays are re-simulated from "
              "each race's original seed.", "New race every day at 8 PM IST in our Shorts. Comment your ball! 👇", "",
              "#ToonToonCastle #marblerace #marblerun #satisfying"]
    return {"title": title, "description": "\n".join(lines)[:4800], "tags": TAGS, "category_id": "20"}


def validate_long_video(mp4: Path, expect_s: float) -> list[str]:
    from src.publish.validate import _safe_path, probe

    fails: list[str] = []
    meta = probe(_safe_path(str(mp4)))
    v = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), {})
    if (int(v.get("width") or 0), int(v.get("height") or 0)) != (1920, 1080):
        fails.append(f"resolution {v.get('width')}x{v.get('height')} != 1920x1080")
    if v.get("codec_name") != "h264":
        fails.append(f"video codec {v.get('codec_name')} != h264")
    if a.get("codec_name") != "aac":
        fails.append("missing AAC audio stream")
    dur = float((meta.get("format") or {}).get("duration") or 0.0)
    if dur < 60.0 or abs(dur - expect_s) > 1.5:
        fails.append(f"duration {dur:.1f}s (expected {expect_s:.1f}s)")
    if mp4.stat().st_size > 250 * 1024 * 1024:
        fails.append("file larger than 250 MB")
    return fails


def _contact_sheet(stills_dir: Path) -> Path:
    """Tiles every QA still into one labelled 4-column image (cheap single-image review of the whole video)."""
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    files = sorted(p for p in stills_dir.glob("*.png") if p.name != "contact_sheet.png")
    if not files:
        raise FileNotFoundError("no stills")
    cw_, ch_, cols = 480, 270, 4
    rows = (len(files) + cols - 1) // cols
    sheet = pygame.Surface((cw_ * cols, (ch_ + 26) * rows))
    sheet.fill((12, 12, 20))
    font = pygame.font.Font(None, 26)
    for i, f in enumerate(files):
        x, y = (i % cols) * cw_, (i // cols) * (ch_ + 26)
        sheet.blit(pygame.transform.smoothscale(pygame.image.load(str(f)), (cw_, ch_)), (x, y + 26))
        sheet.blit(font.render(f.stem, True, (250, 204, 21)), (x + 6, y + 4))
    out = stills_dir / "contact_sheet.png"
    pygame.image.save(sheet, str(out))
    return out


# ---------------------------------------------------------------------------------------------- demo season (CI)
def build_demo_state(n_races: int, state_dir: Path, log=print) -> None:
    """Simulates an n-race Season 1 with the real pipeline steps into `state_dir` (never touches repo `state/`)."""
    from src import main as ep_main
    from src.games import recipe_generator
    from src.games.themes import for_season
    from src.recap.record import build_record
    from src.state import league

    from src.characters.roster import HERO_BY_KEY
    from src.physics.engine import Sim

    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    state = league.fresh_season_state(1, None, 1)
    hof: dict = {"seasons": []}
    entries: list[dict] = []
    for race in range(1, n_races + 1):
        seed = 31000 + race * 97
        recipe, _ = recipe_generator.generate(entries, race, seed, season_theme=for_season(1).key)
        heroes, extras, gf = league.select_cast_for_race(copy.deepcopy(state), random.Random(seed))
        recipe.finale = gf
        trace = None
        for k in range(4):
            cand = Sim(recipe, heroes, extras, seed * 1000 + k).run()
            trace = cand
            if cand.meta.get("winner") in HERO_BY_KEY:
                break
        assert trace is not None
        outcome, nxt, hof = league.evaluate_and_advance(state, trace, hall_of_fame=hof, mutate=True)
        entry = recipe_generator.history_entry(recipe, race)
        entry.update(season=1, race=race, stage=outcome.stage, winner=outcome.winner_key, published=True,
                     utc_date=f"2099-01-{race:02d}", recap=build_record(seed, recipe, heroes, extras, trace,
                                                                         code_sha=sha or None))
        entries.append(entry)
        state = nxt
        log(f"  [DEMO] race {race}: {recipe.arena} -> {outcome.winner_key}")
    league.save_all_state(state, hof, entries, state_dir=state_dir)


# ---------------------------------------------------------------------------------------------- main flow
def race_drama(ri) -> float:
    """How much a race deserves screen time: lead changes, hero-on-hero KOs, upsets, dummy humiliations."""
    s = 0.0
    s += 3.0 if getattr(ri, "lead_changed", False) else 0.0
    s += 1.4 * sum(1 for e in (ri.elims or []) if e.get("hero") and e.get("by_hero"))
    s += 0.5 * sum(1 for e in (ri.elims or []) if e.get("hero"))
    before = ri.stats_before or {}
    if before and ri.winner in before:
        order = sorted(before, key=lambda k: (-int(before[k].get("points", 0)), k))
        if order.index(ri.winner) >= len(order) // 2:
            s += 2.2   # an upset win from the bottom half of the table
    s += 0.8 * len(ri.behind_dummy or [])
    return s


def race_formats(part_races) -> dict[int, str]:
    """FEATURE for the 3 most dramatic races, QUICK for the 3 least (never the opener or the closer, never back to
    back), STANDARD otherwise. Deterministic, so re-runs render the same film."""
    races = list(part_races)
    if len(races) < 5:
        return {ri.race: "FEATURE" for ri in races}
    score = {ri.race: race_drama(ri) for ri in races}
    first, last = races[0].race, races[-1].race
    out = {ri.race: "STANDARD" for ri in races}
    for r in sorted(score, key=lambda r: (-score[r], r))[:3]:
        out[r] = "FEATURE"
    n_quick = 3 if len(races) >= 8 else 1
    order = [r for r in sorted(score, key=lambda r: (score[r], r)) if out[r] == "STANDARD" and r not in (first, last)]
    nums = [ri.race for ri in races]
    for r in order:
        if n_quick <= 0:
            break
        i = nums.index(r)
        neigh = [nums[j] for j in (i - 1, i + 1) if 0 <= j < len(nums)]
        if any(out[x] == "QUICK" for x in neigh):
            continue
        out[r] = "QUICK"
        n_quick -= 1
    return out


def run(mode: str, season: int | None, dry_run: bool, privacy: str, end_race: int | None, use_tts: bool,
        stills: bool, max_frames: int | None, commit_git: bool, demo_races: int, log=print) -> int:
    from src.recap import data, timemachine
    from src.rendering import biomes
    from src.recap.comedy import Writer
    from src.state import league

    state_dir = STATE_DIR
    out_dir = OUT_DIR
    if mode == "demo":
        dry_run = True
        out_dir = ROOT / "output" / "recap_demo"
        state_dir = out_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        build_demo_state(demo_races, state_dir, log=log)
        season, kind = 1, ("part1" if demo_races >= 10 else "preview")
    elif mode == "auto":
        due = schedule.load_due(state_dir)
        if not due:
            log("[RECAP] no recap is due today")
            return 0
        season, kind = int(due["season"]), str(due["kind"])
    else:
        kind = mode
        if season is None:
            st = league.load_json(state_dir / "season_state.json", {})
            season = int(st.get("season_number") or 1)
    if kind == "preview":
        dry_run = True

    key = schedule.recap_key(season, kind)
    recaps = league.load_json(state_dir / "recaps.json", {"recaps": {}})
    if not dry_run and key in recaps.get("recaps", {}):
        log(f"[RECAP] {key} already published: {recaps['recaps'][key].get('url')}")
        return 0

    if kind == "widescreen_finale":
        from src.rendering.widescreen_finale import render_widescreen_finale
        out_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = out_dir / f"tuno_report_{key}.mp4"
        info_wf = render_widescreen_finale(
            season=season,
            seed=3000 + season * 30,
            out_mp4=out_mp4,
            use_tts=use_tts,
            stills_dir=(out_dir / "stills") if stills else None,
            max_frames=max_frames,
            log=log,
        )
        if max_frames:
            return 0
        fails = validate_long_video(out_mp4, float(info_wf["duration_s"]))
        if fails:
            for f in fails:
                log(f"[FINALE GATE FAIL] {f}")
            return 3
        log("[FINALE] ffprobe gate PASS (1920x1080 h264 + aac)")
        if dry_run:
            log(f"[FINALE DRY-RUN] {out_mp4} ready (state/ untouched)")
            return 0
        from src.publish import alerts, youtube
        wf_title = f"Season {season} WIDESCREEN FINALE: 20-Ball Championship 👑 | ToonToonCastle"[:100]
        wf_desc = (
            f"The exclusive 16:9 ToonToonCastle Season {season} Championship Finale!\n"
            "20 balls enter across 3 elimination rounds — only ONE claims the Season Crown! 👑\n\n"
            "#ToonToonCastle #marblerace #marblerun #seasonfinale"
        )
        vid = youtube.upload_short(out_mp4, wf_title, wf_desc, TAGS, privacy=privacy, category_id="20")
        url = f"https://www.youtube.com/watch?v={vid}"
        recaps.setdefault("recaps", {})[key] = {
            "video_id": vid, "url": url, "title": wf_title, "season": season, "kind": kind,
            "duration_s": info_wf["duration_s"],
            "posted_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        league.atomic_write_json(state_dir / "recaps.json", recaps)
        if commit_git:
            league.git_commit_state_safe(f"chore(finale): S{season} widescreen_finale published", ROOT)
        return 0

    t0 = time.time()
    recap = data.build_recap(season, kind, state_dir=state_dir, end_race=end_race, strict=True)
    log(f"[RECAP] {key}: races {recap.start_race}-{recap.end_race} | {recap.verify_note}")

    # ---- replay every race of the part in parallel across CPU cores (after pre-warming git trees)
    from concurrent.futures import ThreadPoolExecutor
    import os as _os

    clip_dir = out_dir / "clips"
    writer = Writer(recap, log=log)
    pick = writer.cold_open_pick({r.race for r in recap.part_races})
    for sha_u in sorted({str(ri.record.get("code_sha") or "") for ri in recap.part_races if ri.record.get("code_sha")}):
        timemachine.ensure_tree(sha_u, log=log)

    formats = race_formats(recap.part_races)
    style_of = {ri.race: i % 3 for i, ri in enumerate(r for r in recap.part_races if formats.get(r.race) != "QUICK")}
    log("[RECAP] formats: " + ", ".join(f"R{ri.race}={formats[ri.race][0]}" for ri in recap.part_races))

    def _one_clip(ri):
        freeze = {"victim": pick[0], "t": pick[2]} if (pick and pick[1].race == ri.race) else None
        label = league.header_label(ri.season, ri.race, ri.arena.replace("_", " ").upper())
        side = timemachine.render_race_clip(ri.record, label, ri.stage, clip_dir, ri.tag, freeze=freeze, log=log,
                                            fmt=formats.get(ri.race, "STANDARD"),
                                            replay_style=style_of.get(ri.race, 0),
                                            biome=biomes.biome_for(ri.season, ri.race))
        return ri.race, freeze is not None, side

    clips: dict[int, dict] = {}
    cold = None
    workers = max(1, min(4, _os.cpu_count() or 2, len(recap.part_races)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r_no, wanted_freeze, side in pool.map(_one_clip, recap.part_races):
            clips[r_no] = side
            if wanted_freeze and side.get("freeze"):
                cold = side["freeze"]
    replayed = sum(1 for c in clips.values() if c.get("ok"))
    log(f"[RECAP] replayed {replayed}/{len(clips)} races in {time.time() - t0:.0f}s "
        f"(workers={workers}, cold open: {'yes' if cold else 'no'})")

    # ---- compose the 16:9 film
    from src.recap.video import RecapVideo, render_thumbnail

    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"tuno_report_{key}.mp4"
    video = RecapVideo(recap, clips, cold, out_dir, use_tts=use_tts, log=log)
    video.plan()
    info = video.render(out_mp4, stills_dir=(out_dir / "stills") if stills else None, max_frames=max_frames)
    thumb = render_thumbnail(recap, video.awards, out_dir / f"tuno_report_{key}_thumb.jpg")
    meta = build_metadata(recap, info, video.awards)
    summary = {"key": key, "season": season, "kind": kind, "start_race": recap.start_race, "end_race": recap.end_race,
               "verified": recap.verified, "verify_note": recap.verify_note, "replayed": replayed,
               "races": len(clips), "duration_s": round(info["duration"], 2), "chapters": info["chapters"],
               "voice_ok": info["voice_ok"], "voice_failed": info["voice_failed"], "lines": info["lines"],
               "metadata": meta, "video": str(out_mp4), "thumbnail": str(thumb),
               "clip_sources": {r: c.get("source") for r, c in clips.items()},
               "render_s": round(time.time() - t0, 1),
               "qa": {**info.get("qa", {}),
                      "camera": {r: c.get("camera_qa") for r, c in clips.items()},
                      "size_mb": round(out_mp4.stat().st_size / 1e6, 1) if out_mp4.exists() else None}}
    if stills:
        try:
            _contact_sheet(out_dir / "stills")
        except Exception as exc:  # noqa: BLE001
            log(f"[RECAP WARN] contact sheet: {type(exc).__name__}: {exc}")
    out_mp4.with_suffix(".json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    q = summary.get("qa") or {}
    cams = [c for c in (q.get("camera") or {}).values() if isinstance(c, dict) and "avg_visible_pct" in c]
    log(f"[RECAP QA] duration={info['duration']:.1f}s size={q.get('size_mb')}MB narration={q.get('narration_pct')}% "
        f"worst_race_quiet={q.get('max_quiet_s')}s camera_visible_avg="
        f"{round(sum(c['avg_visible_pct'] for c in cams) / max(1, len(cams)), 1)}% "
        f"camera_empty_max={max((c['empty_frame_pct'] for c in cams), default='n/a')}%")
    log("[RECAP QA] variety: " + " ".join(
        f"R{r}={str(c.get('format') or '?')[0]}/{c.get('biome', '?')}/{c.get('replay_style', '-')}"
        for r, c in sorted(clips.items())) + f" | lines={len(info['lines'])} repeats={q.get('repeats', 'n/a')}"
        f" stories={sum(1 for s in video.segments if s.name.startswith('story_'))}")
    log(f"[RECAP] rendered {out_mp4.name}: {info['duration']:.1f}s, voice {info['voice_ok']} ok / "
        f"{info['voice_failed']} failed, {time.time() - t0:.0f}s total")

    if max_frames:
        log("[RECAP] partial render (--max-frames): skipping validation and upload")
        return 0
    fails = validate_long_video(out_mp4, info["duration"])
    if fails:
        for f in fails:
            log(f"[RECAP GATE FAIL] {f}")
        return 3
    log("[RECAP] ffprobe gate PASS (1920x1080 h264 + aac)")
    if dry_run:
        log(f"[RECAP DRY-RUN] {out_mp4} ready (state/ untouched)")
        return 0

    n_lines = len(info["lines"])
    if not use_tts or info["voice_failed"] > 0 or info["voice_ok"] < max(1, int(0.9 * n_lines)):
        log("[RECAP] MC Tuno voice incomplete -> refusing to publish a half-silent recap")
        return 4

    # ---- publish (YouTube long-form) + best-effort extras
    from src.publish import alerts, youtube

    vid = youtube.upload_short(out_mp4, meta["title"], meta["description"], meta["tags"], privacy=privacy,
                               category_id=meta["category_id"])
    url = f"https://www.youtube.com/watch?v={vid}"
    log(f"[RECAP PUBLISHED] {url}")
    for label_, fn in (("thumbnail", lambda: youtube.set_thumbnail(vid, thumb)),
                       ("first comment", lambda: youtube.post_comment(
                           vid, "Who's winning the next part? Drop your ball below 👇 (and roast the crash dummies)"))):
        try:
            fn()
            log(f"[RECAP] {label_}: ok")
        except Exception as exc:  # noqa: BLE001 - extras never undo a published recap
            log(f"[RECAP WARN] {label_}: {alerts.redact(f'{type(exc).__name__}: {exc}')[:160]}")
    recaps.setdefault("recaps", {})[key] = {
        "video_id": vid, "url": url, "title": meta["title"], "season": season, "kind": kind,
        "start_race": recap.start_race, "end_race": recap.end_race, "duration_s": round(info["duration"], 2),
        "replayed": f"{replayed}/{len(clips)}", "posted_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    league.atomic_write_json(state_dir / "recaps.json", recaps)
    if commit_git:
        ok = league.git_commit_state_safe(f"chore(recap): S{season} {kind} published", ROOT)
        log(f"[RECAP] state commit: {ok}")
        if not ok:
            alerts.open_alert_issue("[ToonToonCastle Alert] Recap state push failed",
                                    f"Recap `{key}` is live at {url} but pushing `state/recaps.json` failed.")
            return 5
    for p in (out_mp4, out_mp4.with_suffix(".json")):
        try:
            p.unlink()
        except OSError:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Tuno Report — ToonToonCastle season recaps")
    ap.add_argument("--mode", choices=["auto", "part1", "part2", "part3", "widescreen_finale", "preview", "demo"], default="auto")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--end-race", type=int, default=None, help="preview only: last race to include")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--max-frames", type=int, default=None, help="testing: stop after N frames")
    ap.add_argument("--no-git-push", action="store_true")
    ap.add_argument("--demo-races", type=int, default=10)
    a = ap.parse_args(argv)
    return run(a.mode, a.season, a.dry_run, a.privacy, a.end_race, not a.no_tts, a.stills, a.max_frames,
               not a.no_git_push, a.demo_races)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
