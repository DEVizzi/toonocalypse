"""Time machine: replays each race with the exact code version that produced it.

`entry["recap"]["code_sha"]` pins the commit the daily workflow ran. We `git archive` that commit's `src/ config/
assets/` into `tmp/recap_trees/<sha>` (safe extraction, no absolute/parent paths, no links) and run
`src/recap/clip_worker.py` against it in a subprocess. Physics tuning after a race can therefore never change how that
race replays. Fallback order per race: pinned tree -> current tree -> results-card fallback (handled by the caller).
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TREES = ROOT / "tmp" / "recap_trees"
WORKER = Path(__file__).resolve().parent / "clip_worker.py"
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
WORKER_TIMEOUT_S = 900


def _safe_members(tf: tarfile.TarFile, dest: Path):
    root = dest.resolve()
    for m in tf.getmembers():
        if not (m.isfile() or m.isdir()):
            continue                                     # no symlinks / hardlinks / devices
        target = (root / m.name).resolve()
        if target != root and root not in target.parents:
            continue                                     # path traversal guard
        yield m


def ensure_tree(sha: str | None, log=print) -> Path | None:
    """Extracted code tree for `sha` (cached). None if the sha is invalid or not present in this clone."""
    sha = (sha or "").strip().lower()
    if not _SHA_RE.match(sha):
        return None
    dest = TREES / sha[:12]
    if (dest / "src" / "physics" / "engine.py").is_file():
        return dest
    try:
        full = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", f"{sha}^{{commit}}"],
                              check=True, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", full, "src", "config", "assets"],
                              check=True, capture_output=True).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        log(f"  [TIME MACHINE] commit {sha[:12]} unavailable ({type(exc).__name__}); using current tree")
        return None
    tmp = dest.with_name(dest.name + ".part")
    tmp.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
        tf.extractall(tmp, members=list(_safe_members(tf, tmp)))
    os.replace(tmp, dest)
    log(f"  [TIME MACHINE] extracted code tree {sha[:12]}")
    return dest


def run_worker(root: Path, job: dict[str, Any], log=print) -> dict[str, Any]:
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    job_path = out_dir / f"{job['tag']}_job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    side_path = out_dir / f"{job['tag']}.json"
    if side_path.exists():
        side_path.unlink()
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        subprocess.run([sys.executable, str(WORKER), "--root", str(root), "--job", str(job_path)],
                       cwd=str(root), env=env, timeout=WORKER_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "verified": False, "reason": "clip worker timed out"}
    try:
        return json.loads(side_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "verified": False, "reason": "clip worker wrote no sidecar"}


CLIP_W, CLIP_H = 1240, 930


def render_race_clip(record: dict, label: str, stage: str, out_dir: Path, tag: str,
                     freeze: dict | None = None, width: int = CLIP_W, height: int = CLIP_H,
                     log=print, fmt: str = "FEATURE", replay_style: int = 0, biome: str = "") -> dict[str, Any]:
    """Pinned tree first, then the current tree. Returns the worker sidecar (+ `source`)."""
    job = {"record": record, "label": label, "stage": stage, "out_dir": str(out_dir), "tag": tag,
           "width": int(width), "height": int(height), "freeze": freeze, "format": str(fmt),
           "replay_style": int(replay_style), "biome": str(biome)}
    tried = []
    pinned = ensure_tree(record.get("code_sha"), log=log)
    for src_name, root in (("pinned", pinned), ("current", ROOT)):
        if root is None or root in [r for _, r in tried]:
            continue
        tried.append((src_name, root))
        side = run_worker(root, job, log=log)
        side["source"] = src_name
        if side.get("ok") and side.get("verified"):
            log(f"  [CLIP] {tag}: replayed with {src_name} tree ({side.get('clip', {}).get('frames', 0)} frames)")
            return side
        log(f"  [CLIP] {tag}: {src_name} tree failed -> {side.get('reason', 'unknown')}")
    return {"ok": False, "verified": False, "source": "none", "reason": "no tree reproduced the race"}
