"""ToonToonCastle v4.5 Transactional Daily Episode Supervisor (`run_daily_episode.py`).

Enforces:
1. Same-Day Duplicate Guard: checks `state/episode_history.json` for today's UTC date (`YYYY-MM-DD`) with
   `published == True` and exits `0` immediately unless `--force-run` or `--dry-run` is passed.
2. Pre-Attempt State Snapshot: captures verbatim copies of `state/season_state.json`, `state/episode_history.json`,
   and `state/hall_of_fame.json` before simulation/rendering begins. `state/*.json` is NEVER modified until Step D.
3. Staged Safe Publish Order (Steps A -> B -> C -> D):
   - Step A: Simulate, render MP4, pass `ffprobe` audio/loudness gate + camera zoom gate (`--stage-only`).
   - Step B: Upload temp MP4 asset -> create Instagram Reels container -> poll until `FINISHED` (no `media_publish` yet).
   - Step C: Upload YouTube Short (`yt_video_id`) -> immediately call IG `media_publish`.
   - Step D: Delete temp IG GitHub Release/tag, atomically commit & push `state/*.json`, delete local `.mp4`.
4. Hard 10-Minute (`600s`) Watchdog & Full Rollback + Auto-Recreate (`MAX_ATTEMPTS = 2`):
   - Runs Steps A-C in an isolated process group (`start_new_session=True`) under a strict `600s` wall-clock timer.
   - On timeout OR error, `rollback_attempt()` kills lingering child processes (`ffmpeg`, `edge-tts`, workers),
     deletes local media, deletes any temp IG GitHub Release, deletes any partial YouTube upload (`videos.delete`),
     and restores `state/*.json` verbatim to the pre-attempt snapshot.
   - If `attempt == 1` fails, waits `15s` and launches `attempt == 2` from scratch with a fresh random seed.
   - If `attempt == 2` also fails, rolls back cleanly, leaves `state/*.json` untouched, and opens a GitHub Issue alert.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.publish import alerts, instagram, validate, youtube  # noqa: E402
from src.state import league  # noqa: E402

STATE_DIR = ROOT / "state"
OUTPUT_DIR = ROOT / "output"
STATE_FILES = ("season_state.json", "episode_history.json", "hall_of_fame.json")
DEFAULT_TIMEOUT_S = 600.0
DEFAULT_RETRY_WAIT_S = 15.0
MAX_ATTEMPTS = 2


def utc_today_str(now: dt.datetime | None = None) -> str:
    cur = now or dt.datetime.now(dt.timezone.utc)
    return cur.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")


def is_today_published(state_dir: Path = STATE_DIR, today_utc: str | None = None) -> bool:
    """Returns True if `episode_history.json` already has a `published: true` entry for `today_utc`."""
    day_str = today_utc or utc_today_str()
    hist_path = state_dir / "episode_history.json"
    if not hist_path.is_file():
        return False
    try:
        raw = json.loads(hist_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    return any(
        isinstance(e, dict) and e.get("utc_date") == day_str and e.get("published") is True
        for e in entries
    )


def snapshot_state(state_dir: Path = STATE_DIR) -> dict[str, bytes | None]:
    snap: dict[str, bytes | None] = {}
    for name in STATE_FILES:
        p = state_dir / name
        snap[name] = p.read_bytes() if p.is_file() else None
    return snap


def restore_state_snapshot(snap: dict[str, bytes | None], state_dir: Path = STATE_DIR) -> None:
    """Atomically restores `state/*.json` verbatim to `snap` (`.tmp` + `os.replace`)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    for name, data in snap.items():
        target = state_dir / name
        if data is None:
            if target.exists():
                target.unlink()
        else:
            tmp = state_dir / f".{name}.rollback.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, target)


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _terminate_process_group(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def _delete_local_media(out_mp4: Path, preserve_dry_run: bool = False) -> None:
    if preserve_dry_run:
        wav = out_mp4.with_suffix(".wav")
        if wav.exists():
            wav.unlink()
        return
    out_dir = out_mp4.parent
    if not out_dir.is_dir():
        return
    stem = out_mp4.stem
    for p in list(out_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".mp4", ".mov", ".wav", ".mp3", ".png", ".tmp"} or p.name.startswith(stem):
            try:
                p.unlink()
            except OSError:
                pass


def rollback_attempt(
    proc: subprocess.Popen[Any] | None,
    manifest_path: Path,
    out_mp4: Path,
    snap: dict[str, bytes | None],
    state_dir: Path = STATE_DIR,
    delete_yt_fn: Callable[[str], bool] = youtube.delete_video,
    cleanup_ig_fn: Callable[[str], bool] = instagram.cleanup_ephemeral_release_by_tag,
) -> dict[str, Any]:
    """Full transactional rollback on >600s timeout or fatal error:
    1. Kills lingering child process group (`ffmpeg`, `edge-tts`, workers).
    2. Deletes local `.mp4`, audio stems, and temp frame files.
    3. Deletes temporary GitHub Release/tag staged for Instagram Reels.
    4. Deletes partial YouTube Short upload if `yt_video_id` was created before completion.
    5. Restores `state/season_state.json`, `episode_history.json`, and `hall_of_fame.json` verbatim."""
    _terminate_process_group(proc)
    manifest = _read_manifest(manifest_path)
    stage = str(manifest.get("stage") or "init")

    _delete_local_media(out_mp4, preserve_dry_run=False)

    ig_tag = str(manifest.get("ig_release_tag") or "").strip()
    ig_cleaned = False
    if ig_tag:
        try:
            ig_cleaned = bool(cleanup_ig_fn(ig_tag))
            print(f"[ROLLBACK] deleted temp IG release tag `{ig_tag}`: {ig_cleaned}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[ROLLBACK WARN] IG temp release cleanup error ({type(exc).__name__})", flush=True)

    yt_vid = str(manifest.get("yt_video_id") or "").strip()
    yt_deleted = False
    if yt_vid and not manifest.get("both_published"):
        try:
            yt_deleted = bool(delete_yt_fn(yt_vid))
            print(f"[ROLLBACK] deleted partial YouTube upload `{yt_vid}`: {yt_deleted}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[ROLLBACK WARN] YouTube rollback delete error ({type(exc).__name__})", flush=True)

    restore_state_snapshot(snap, state_dir=state_dir)
    if manifest_path.exists():
        try:
            manifest_path.unlink()
        except OSError:
            pass
    return {
        "stage": stage,
        "ig_cleaned": ig_cleaned,
        "yt_deleted": yt_deleted,
    }


def _worker_execute(
    seed: int,
    out_mp4: Path,
    manifest_path: Path,
    dry_run: bool,
    privacy: str,
    brand_stills: bool,
    no_audio: bool = False,
) -> int:
    """Executes Steps A-C inside the watchdog-monitored child process group."""
    from src import main as ep_main

    manifest: dict[str, Any] = {"stage": "step_a_render", "seed": seed, "mp4": str(out_mp4)}
    _write_manifest(manifest_path, manifest)

    cli_args = [
        "--dry-run" if dry_run else "--stage-only",
        "--seed", str(seed),
        "--out", str(out_mp4),
    ]
    if brand_stills:
        cli_args.append("--brand-stills")
    if no_audio:
        cli_args.append("--no-audio")

    rc = ep_main.main(cli_args)
    if rc != 0:
        manifest["error"] = f"Step A render/gate exited with code {rc}"
        _write_manifest(manifest_path, manifest)
        return rc

    if dry_run:
        fails = validate.validate(str(out_mp4))
        if fails:
            manifest["stage"] = "step_a_validate"
            manifest["error"] = "; ".join(fails)
            _write_manifest(manifest_path, manifest)
            for f in fails:
                print(f"[DRY-RUN GATE FAIL] {f}", file=sys.stderr)
            return 3
        manifest["stage"] = "dry_run_complete"
        _write_manifest(manifest_path, manifest)
        return 0

    meta_json = json.loads(out_mp4.with_suffix(".json").read_text(encoding="utf-8"))
    pub_meta = meta_json["upload_metadata"]

    # Step B: Stage temporary MP4 asset -> create Instagram Reels container -> poll until FINISHED (no publish yet)
    tag = instagram.make_stage_tag()
    manifest.update(stage="step_b_ig_stage", ig_release_tag=tag)
    _write_manifest(manifest_path, manifest)
    tag, video_url = instagram.stage_ephemeral_release(out_mp4, tag=tag)

    manifest.update(stage="step_b_ig_container_poll")
    _write_manifest(manifest_path, manifest)
    creation_id = instagram.prepare_reel_container(video_url, pub_meta["ig_caption"])
    manifest.update(ig_creation_id=creation_id)
    _write_manifest(manifest_path, manifest)

    # Step C: Upload YouTube Short -> immediately call IG media_publish
    manifest.update(stage="step_c_yt_upload")
    _write_manifest(manifest_path, manifest)
    yt_id = youtube.upload_short(
        out_mp4,
        pub_meta["title"],
        pub_meta["description"],
        pub_meta["tags"],
        privacy=privacy,
    )
    manifest.update(yt_video_id=yt_id, stage="step_c_ig_media_publish")
    _write_manifest(manifest_path, manifest)
    print(f"[PUBLISHED YT SHORTS] https://youtube.com/shorts/{yt_id}", flush=True)

    ig_id = instagram.publish_prepared_reel(creation_id)
    manifest.update(ig_media_id=ig_id, both_published=True, stage="step_c_complete")
    _write_manifest(manifest_path, manifest)
    print(f"[PUBLISHED IG REELS] media_id={ig_id}", flush=True)
    return 0


def _commit_step_d(
    out_mp4: Path,
    manifest: dict[str, Any],
    state_dir: Path,
    commit_git: bool,
    today_utc: str,
) -> bool:
    """Step D: Delete temporary IG release, atomically advance & push `state/*.json`, and remove local `.mp4`."""
    ig_tag = str(manifest.get("ig_release_tag") or "").strip()
    if ig_tag:
        instagram.cleanup_ephemeral_release_by_tag(ig_tag)

    meta_json = json.loads(out_mp4.with_suffix(".json").read_text(encoding="utf-8"))
    pending = meta_json["pending_state"]
    next_state = pending["next_state"]
    next_hof = pending["next_hof"]
    entry = dict(pending["history_entry"])
    entry.update(
        utc_date=today_utc,
        published=True,
        youtube_id=manifest.get("yt_video_id"),
        instagram_id=manifest.get("ig_media_id"),
    )

    hist_raw = league.load_json(state_dir / "episode_history.json", {"entries": []})
    entries = list(hist_raw.get("entries", []) if isinstance(hist_raw, dict) else hist_raw)
    entries.append(entry)
    league.save_all_state(next_state, next_hof, entries, state_dir=state_dir)

    pushed = True
    if commit_git:
        s_num = entry.get("season", 1)
        r_num = entry.get("race", 1)
        w_key = entry.get("winner", "hero")
        pushed = league.git_commit_state_safe(
            f"chore(league): S{s_num} R{r_num}/30 ({w_key} wins)",
            ROOT,
            dry_run=False,
        )
        print(f"[STEP D] git_commit_state_safe: {pushed}", flush=True)

    _delete_local_media(out_mp4, preserve_dry_run=False)
    return pushed


def run_transactional_pipeline(
    dry_run: bool = False,
    force_run: bool = False,
    privacy: str = "public",
    brand_stills: bool = False,
    commit_git: bool = True,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retry_wait_s: float = DEFAULT_RETRY_WAIT_S,
    max_attempts: int = MAX_ATTEMPTS,
    out_mp4: Path | None = None,
    state_dir: Path = STATE_DIR,
    worker_cmd_builder: Callable[[int, int, Path, Path], list[str]] | None = None,
    delete_yt_fn: Callable[[str], bool] = youtube.delete_video,
    cleanup_ig_fn: Callable[[str], bool] = instagram.cleanup_ephemeral_release_by_tag,
    alert_fn: Callable[[str, str], bool] = alerts.open_alert_issue,
    seed_override: int | None = None,
) -> int:
    today_utc = utc_today_str()
    if not dry_run and not force_run and is_today_published(state_dir=state_dir, today_utc=today_utc):
        print(f"[DUPLICATE GUARD] Episode for {today_utc} is already marked published=true; exiting 0.", flush=True)
        return 0

    target_mp4 = (out_mp4 or (OUTPUT_DIR / ("dry_run_s1_e1.mp4" if dry_run else "episode.mp4"))).resolve()
    target_mp4.parent.mkdir(parents=True, exist_ok=True)

    rng = random.SystemRandom()
    failure_notes: list[str] = []

    for attempt in range(1, max_attempts + 1):
        snap = snapshot_state(state_dir=state_dir)
        seed = (seed_override if (attempt == 1 and seed_override is not None) else rng.randint(10000, 99999))
        fd, mf_str = tempfile.mkstemp(prefix=f"ttc_attempt{attempt}_", suffix=".json")
        os.close(fd)
        manifest_path = Path(mf_str)

        if worker_cmd_builder is not None:
            cmd = worker_cmd_builder(attempt, seed, target_mp4, manifest_path)
        else:
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--seed", str(seed),
                "--out", str(target_mp4),
                "--manifest", str(manifest_path),
                "--privacy", privacy,
            ]
            if dry_run:
                cmd.append("--dry-run")
            if brand_stills:
                cmd.append("--brand-stills")

        print(f"\n=== [ATTEMPT {attempt}/{max_attempts}] seed={seed} timeout={timeout_s:.0f}s dry_run={dry_run} ===",
              flush=True)
        t0 = time.monotonic()
        proc: subprocess.Popen[Any] | None = None
        timed_out = False
        rc = 1

        try:
            proc = subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True)
            proc.wait(timeout=timeout_s)
            rc = int(proc.returncode or 0)
        except subprocess.TimeoutExpired:
            timed_out = True
            rc = 124
        except Exception as exc:  # noqa: BLE001
            rc = 125
            print(f"[SUPERVISOR ERROR] {type(exc).__name__}: {alerts.redact(str(exc))}", flush=True)

        elapsed = time.monotonic() - t0
        manifest = _read_manifest(manifest_path)

        if not timed_out and rc == 0:
            if manifest_path.exists():
                manifest_path.unlink()
            if dry_run:
                _delete_local_media(target_mp4, preserve_dry_run=True)
                restore_state_snapshot(snap, state_dir=state_dir)
                print(f"[DRY-RUN SUCCESS] {target_mp4} verified in {elapsed:.1f}s (state/ untouched)", flush=True)
                return 0
            ok_commit = _commit_step_d(
                target_mp4,
                manifest,
                state_dir=state_dir,
                commit_git=commit_git,
                today_utc=today_utc,
            )
            if ok_commit:
                print(f"[LIVE PUBLISH SUCCESS] Attempt {attempt} completed in {elapsed:.1f}s", flush=True)
                return 0
            reason = f"Attempt {attempt} failed at step_d_git_push after {elapsed:.1f}s"
            failure_notes.append(reason)
            print(f"[STEP D GIT WARN] {reason}", file=sys.stderr, flush=True)
            alert_fn(
                "[ToonToonCastle Alert] Step D State Git Push Failed",
                f"Video published on YT+IG, but pushing `state/*.json` failed:\n\n- {reason}",
            )
            return 5

        rb = rollback_attempt(
            proc,
            manifest_path,
            target_mp4,
            snap,
            state_dir=state_dir,
            delete_yt_fn=delete_yt_fn,
            cleanup_ig_fn=cleanup_ig_fn,
        )
        cause = f"TIMEOUT > {timeout_s:.0f}s" if timed_out else f"exit={rc} ({manifest.get('error', 'fatal error')})"
        note = f"Attempt {attempt}/{max_attempts} failed at `{rb['stage']}` after {elapsed:.1f}s — {alerts.redact(cause)}"
        failure_notes.append(note)
        print(f"[ATTEMPT {attempt} ROLLED BACK] {note}", file=sys.stderr, flush=True)

        if attempt < max_attempts:
            print(f"[AUTO-RECREATE] Waiting {retry_wait_s:.1f}s before launching Attempt {attempt + 1} with fresh seed...",
                  flush=True)
            time.sleep(retry_wait_s)

    summary_msg = "\n".join(f"- {n}" for n in failure_notes)
    if not dry_run:
        alert_fn(
            f"[ToonToonCastle Alert] Daily Episode Failed After {max_attempts} Attempts ({today_utc})",
            f"All {max_attempts} transactional attempts timed out or failed (`state/*.json` rolled back cleanly; "
            f"zero duplicate videos left behind):\n\n{summary_msg}",
        )
    return 1


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ToonToonCastle v4.5 Transactional 10-Min Watchdog Runner")
    ap.add_argument("--dry-run", action="store_true", help="run Step A + gates only; keep preview MP4, leave state/ untouched")
    ap.add_argument("--force-run", action="store_true", help="bypass Same-Day Duplicate Guard")
    ap.add_argument("--brand-stills", action="store_true",
                    help="export verify_gameplay_brand.png (t=5.0s) and verify_winner_brand.png")
    ap.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--no-git-push", action="store_true", help="update state/*.json locally without git commit/push")
    # Internal worker flags
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--manifest", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--no-audio", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.worker:
        if not a.out or not a.manifest or a.seed is None:
            raise SystemExit("worker requires --seed, --out, and --manifest")
        try:
            return _worker_execute(
                seed=int(a.seed),
                out_mp4=Path(a.out).resolve(),
                manifest_path=Path(a.manifest).resolve(),
                dry_run=bool(a.dry_run),
                privacy=a.privacy,
                brand_stills=bool(a.brand_stills),
                no_audio=bool(a.no_audio),
            )
        except Exception as exc:  # noqa: BLE001
            mf = Path(a.manifest).resolve()
            cur = _read_manifest(mf)
            cur["error"] = alerts.redact(f"{type(exc).__name__}: {exc}")
            _write_manifest(mf, cur)
            print(f"[WORKER ERROR] {cur['error']}", file=sys.stderr, flush=True)
            return 1

    out_path = Path(a.out).resolve() if a.out else None
    return run_transactional_pipeline(
        dry_run=bool(a.dry_run),
        force_run=bool(a.force_run),
        privacy=a.privacy,
        brand_stills=bool(a.brand_stills),
        commit_git=not a.no_git_push,
        timeout_s=float(a.timeout),
        out_mp4=out_path,
        seed_override=a.seed,
    )


if __name__ == "__main__":
    sys.exit(cli())
