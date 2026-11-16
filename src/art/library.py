"""Reusable Art Library loader, GitHub Release downloader, and missing-asset queue (§3)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from src.common.config import ASSETS_DIR, ROOT
from src.common.state import load_state, save_state

POSES: tuple[str, ...] = (
    "idle",
    "walk",
    "run",
    "jump",
    "point",
    "surprised",
    "laughing",
    "comic-angry",
    "sad",
    "thinking",
    "cheering",
    "talking",
)

DEFAULT_BACKGROUNDS: tuple[str, ...] = (
    "frosty-espresso-bar",
    "sunny-town-square",
    "cozy-treehouse-hq",
    "neon-arcade-alley",
    "botanical-glasshouse",
    "clockwork-bakery",
    "starlight-observatory",
    "rainbow-skate-park",
    "cloudtop-lighthouse",
    "bamboo-tea-garden",
    "midnight-museum-hall",
    "coral-reef-cove",
    "snowy-mountain-lodge",
    "pumpkin-harvest-fair",
    "candy-factory-floor",
    "retro-comic-bookstore",
    "floating-sky-docks",
    "underground-crystal-cavern",
    "rooftop-pizzeria",
    "whimsical-science-lab",
    "autumn-park-bridge",
    "tropical-tiki-beach",
    "winter-ice-rink",
    "lantern-night-market",
    "toy-workshop-attic",
    "submarine-bridge",
    "desert-cactus-diner",
    "music-studio-stage",
    "library-spiral-tower",
    "carousel-carnival-plaza",
)

LIBRARY_INDEX_PATH = ASSETS_DIR / "library_index.json"
LIBRARY_CACHE_DIR = ROOT / "assets" / "art_library"


def load_library_index() -> dict[str, Any]:
    """Load assets/library_index.json; returns empty structure if not yet built."""
    if not LIBRARY_INDEX_PATH.exists():
        return {"version": 0, "characters": {}, "backgrounds": {}}
    return json.loads(LIBRARY_INDEX_PATH.read_text(encoding="utf-8"))


def save_library_index(index: dict[str, Any]) -> None:
    LIBRARY_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def latest_art_release_tag() -> str | None:
    """Find the highest art-library-vN GitHub Release tag."""
    res = subprocess.run(
        ["gh", "release", "list", "--json", "tagName", "--limit", "30"],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None
    best_n = -1
    best_tag = None
    for r in json.loads(res.stdout):
        tag = r.get("tagName", "")
        m = re.match(r"^art-library-v(\d+)$", tag)
        if m and int(m.group(1)) > best_n:
            best_n = int(m.group(1))
            best_tag = tag
    return best_tag


def _extract_art_zips(target: Path) -> None:
    import zipfile

    while True:
        zips = sorted(target.glob("art-library-v*.zip"))
        if not zips:
            break
        for zp in zips:
            with zipfile.ZipFile(zp, "r") as zf:
                zf.extractall(target)
            zp.unlink()


def ensure_art_library_downloaded(dest_dir: Path | None = None) -> dict[str, Any]:
    """Ensure assets/library_index.json and PNGs from art-library-vN are present locally."""
    target = dest_dir or LIBRARY_CACHE_DIR
    target.mkdir(parents=True, exist_ok=True)
    idx = load_library_index()
    if idx.get("characters") and idx.get("backgrounds"):
        first_char = next((v for v in idx["characters"].values() if v), {})
        first_pose = next(iter(first_char.values()), {})
        first_bg = next(iter(idx["backgrounds"].values()), {})
        char_ok = bool(first_pose.get("path")) and (ROOT / first_pose["path"]).exists()
        bg_ok = bool(first_bg.get("16x9")) and (ROOT / first_bg["16x9"]).exists()
        if char_ok and bg_ok:
            return idx

    tag = latest_art_release_tag()
    if not tag:
        return idx
    subprocess.run(
        ["gh", "release", "download", tag, "--dir", str(target), "--clobber"],
        check=True,
    )
    _extract_art_zips(target)
    idx_file = target / "library_index.json"
    if idx_file.exists():
        idx = json.loads(idx_file.read_text(encoding="utf-8"))
        save_library_index(idx)
    return idx


def available_assets_for_cast(
    slugs: list[str],
    index: dict[str, Any] | None = None,
) -> tuple[bool, list[str], list[str]]:
    """Return (all_cast_present, common_poses, available_backgrounds)."""
    idx = index if index is not None else load_library_index()
    chars_map = idx.get("characters", {})
    bgs_map = idx.get("backgrounds", {})

    if not slugs or not bgs_map:
        return False, [], []

    pose_sets = []
    for slug in slugs:
        poses = chars_map.get(slug, {})
        if not poses:
            return False, [], list(bgs_map.keys())
        pose_sets.append(set(poses.keys()))

    common_poses = sorted(set.intersection(*pose_sets)) if pose_sets else []
    # Need at least idle + talking (or 2+ poses) to animate
    if not common_poses:
        return False, [], list(bgs_map.keys())
    return True, common_poses, sorted(bgs_map.keys())


def queue_missing_assets(characters: list[str], backgrounds: list[str]) -> dict[str, Any]:
    """Append missing characters/backgrounds to state/art_queue.json for next Kaggle batch."""
    q = load_state("art_queue.json", {"characters": [], "backgrounds": []})
    existing_c = set(q.get("characters", []))
    existing_b = set(q.get("backgrounds", []))
    existing_c.update(characters)
    existing_b.update(backgrounds)
    q["characters"] = sorted(existing_c)
    q["backgrounds"] = sorted(existing_b)
    save_state("art_queue.json", q)
    return q
