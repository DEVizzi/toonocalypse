"""Thin wrappers around the kaggle CLI and the gh CLI (release assets). Secrets are never echoed."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from src.common.config import models
from src.common.retry import Abort


def _run(cmd: list[str], check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and res.returncode != 0:
        tail = (res.stderr or res.stdout)[-600:]
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} failed: {tail}")
    return res


# ------------------------------------------------------------------ Kaggle
def kernel_ref() -> str:
    user = os.environ.get("KAGGLE_USERNAME")
    if not user:
        raise Abort("KAGGLE_USERNAME is not set")
    return f"{user}/{models()['kaggle']['kernel_slug']}"


def preflight() -> None:
    res = _run(["kaggle", "kernels", "list", "--mine", "--page-size", "1"], check=False, timeout=120)
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip()[-400:]
        raise Abort("Kaggle preflight failed. If this is an auth error, rotate the token: kaggle.com -> Settings -> API -> "
                    f"Create New Token, then update the KAGGLE_API_TOKEN secret. CLI said: {detail}")


def push(kernel_dir: Path) -> str:
    res = _run(["kaggle", "kernels", "push", "-p", str(kernel_dir)], timeout=300)
    m = re.search(r"version (\d+)", res.stdout, re.I)
    return m.group(1) if m else "?"


def status() -> str:
    """Return one of: queued, running, complete, error, cancelled, unknown."""
    res = _run(["kaggle", "kernels", "status", kernel_ref()], check=False, timeout=120)
    text = (res.stdout + res.stderr).lower()
    for s in ["complete", "error", "cancel", "running", "queued"]:
        if s in text:
            return "cancelled" if s == "cancel" else s
    return "unknown"


def download_output(dest: Path) -> Path | None:
    dest.mkdir(parents=True, exist_ok=True)
    _run(["kaggle", "kernels", "output", kernel_ref(), "-p", str(dest)], check=False, timeout=900)
    found = list(dest.rglob("manifest.json"))
    return found[0].parent if found else None


# ------------------------------------------------------------------ GitHub release assets (one draft release per story)
def ensure_release(tag: str, title: str) -> None:
    if _run(["gh", "release", "view", tag], check=False).returncode != 0:
        _run(["gh", "release", "create", tag, "--draft", "--title", title,
              "--notes", "Toonocalypse draft (not published). Assets: portraits, panels, renders."])


def upload_assets(tag: str, files: list[Path]) -> None:
    for i in range(0, len(files), 20):
        _run(["gh", "release", "upload", tag, "--clobber", *map(str, files[i:i + 20])], timeout=900)


def download_assets(tag: str, names: list[str], dest: Path) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    missing = [n for n in names if not (dest / n).exists()]
    for n in missing:
        _run(["gh", "release", "download", tag, "-p", n, "-D", str(dest), "--clobber"], timeout=300)
    return {n: dest / n for n in names}


def release_upload_json(tag: str, name: str, data: dict, workdir: Path) -> None:
    p = workdir / name
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    upload_assets(tag, [p])
