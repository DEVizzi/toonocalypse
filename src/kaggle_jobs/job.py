"""Build job.json for the Kaggle kernel (PORTRAITS / PANELS / REPAIR) and render the kernel file."""
from __future__ import annotations

import base64
import io
import json
import zlib
from pathlib import Path
from typing import Any

from src.common.config import ROOT, models, style_guide

KERNEL_DIR = ROOT / "kaggle"


def char_seed(story_id: str, name: str, salt: int = 0) -> int:
    return (zlib.crc32(f"{story_id}|{name}".encode()) + salt * 104729) % 2_000_000_000


def panel_id(part: int, pid: int) -> str:
    return f"p{part}-{pid}"


def slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def portrait_id(name: str) -> str:
    return f"portrait-{slug(name)}"


def _img_b64(path: Path, size: int = 512) -> str:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size * 2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def _base_item(**kw) -> dict[str, Any]:
    im = models()["image"]
    return {"steps": im["steps"], "guidance": im["guidance"], "width": im["width"], "height": im["height"],
            "upscale": True} | kw


def portrait_items(story: dict[str, Any], names: list[str] | None = None, salt: int = 0) -> list[dict[str, Any]]:
    im, sg = models()["image"], style_guide()
    items = []
    for c in story["cast"]:
        if names and c["name"] not in names:
            continue
        emphasis = ", ".join(f"({x})1.25" for x in [c.get("outfit"), c.get("accessory"), *c.get("anchors", [])] if x)
        prompt = (f"({sg['positive']})1.3, solo character portrait of ONE person only, {c['visual_prompt']}, {emphasis}, "
                  f"(full body, head to feet, front view, standing, centered)1.2, (plain flat light grey background)1.3")
        negative = (f"{sg['negative']}, photo, photograph, photorealistic, realistic skin, 3d render, cgi, "
                    f"character sheet, turnaround, multiple views, collage, grid, duplicate person, two people, crowd, "
                    f"split screen, monochrome, busy background, scenery, cropped, cut off feet, signature")
        anchors = list(dict.fromkeys(f"a cartoon person with {x}" for x in [c.get("hair"), c.get("accessory"), *c.get("anchors", [])] if x))
        items.append(_base_item(id=portrait_id(c["name"]), kind="portrait", prompt=prompt, negative=negative,
                                seed=char_seed(story["story_id"], c["name"], salt), n=im["candidates"]["portrait"],
                                keep=im["candidates"]["portrait_keep"], clip_text=c["visual_prompt"][:300],
                                anchors=anchors, upscale=False, refs=[]))
    return items


def short_tag(c: dict[str, Any]) -> str:
    """Compact look for panel prompts; the IP-Adapter portrait carries the rest of the identity."""
    who = f"{c['age']} year old {c.get('gender', '')}".strip() if c.get("age") else c.get("gender", "")
    bits = [b for b in [who, c.get("hair"), (c.get("anchors") or [c.get("outfit")])[0]] if b]
    return f"{c['name']} ({', '.join(bits)})" if bits else c["name"]


def panel_prompt(panel: dict[str, Any], cast_by_name: dict[str, dict[str, Any]]) -> str:
    # Scene/action first and the prompt kept short: the dry run showed long style + full lock cards drowning the action.
    chars = ", ".join(f"{short_tag(cast_by_name[c['name']])} on the {c['position']}" for c in panel.get("characters", []))
    n = len(panel.get("characters", []))
    if n > 1:
        chars = f"{n} separate people side by side: {chars}"
    shot = f"{panel.get('camera', '')} shot, {panel.get('lighting', '')} lighting, {panel.get('emotion', '')} mood"
    return (f"{panel['image_prompt']}. {chars + '. ' if chars else ''}{shot}. "
            f"(comic book panel, bold ink lines, cel shading)1.2, uncluttered sky or dark background at the top.")


PANEL_NEGATIVE_EXTRA = "photo, photograph, photorealistic, 3d render, cgi, character portrait, plain studio background"
NO_PEOPLE_NEGATIVE = "person, people, human, man, woman, face, figure, crowd"


def panel_items(story: dict[str, Any], only: set[str] | None = None, salt: int = 0, repair: bool = False) -> list[dict[str, Any]]:
    im, sg = models()["image"], style_guide()
    cast = {c["name"]: c for c in story["cast"]}
    items = []
    for part in story["parts"]:
        for p in part["panels"]:
            pid = panel_id(part["part"], int(p["id"]))
            if only is not None and pid not in only:
                continue
            chars = p.get("characters", [])
            refs = []
            for c in chars:
                where = "full" if len(chars) == 1 else ("left" if c["position"] == "left" else "right" if c["position"] == "right" else "center")
                refs.append({"char": c["name"], "where": where})
            seed = sum(char_seed(story["story_id"], c["name"], salt) for c in chars) % 2_000_000_000 if chars \
                else char_seed(story["story_id"], pid, salt)
            items.append(_base_item(id=pid, kind="panel", prompt=panel_prompt(p, cast),
                                    negative=f"{sg['negative']}, {PANEL_NEGATIVE_EXTRA}{'' if chars else ', ' + NO_PEOPLE_NEGATIVE}",
                                    seed=seed, n=im["candidates"]["panel"], keep=im["candidates"]["panel_keep"],
                                    clip_text=p["image_prompt"][:300], refs=refs,
                                    ip_scale=im["ip_adapter"]["repair_scale" if repair else "scale"]))
    return items


def build_job(story: dict[str, Any], phase: str, items: list[dict[str, Any]], portrait_files: dict[str, Path],
              job_id: str) -> dict[str, Any]:
    im = models()["image"]
    pip = [ln.strip() for ln in (KERNEL_DIR / "requirements.txt").read_text().splitlines() if ln.strip()]
    return {
        "job_id": job_id, "phase": phase, "story_id": story["story_id"], "pip": pip,
        "models": {"base": im["base"], "ip_adapter_repo": im["ip_adapter"]["repo"], "ip_adapter_weight": Path(im["ip_adapter"]["weight"]).name,
                   "ip_adapter_encoder": im["ip_adapter"]["image_encoder"], "clip": im["prefilter"]["clip_model"],
                   "dino": im["prefilter"]["dino_model"], "esrgan_url": im["upscaler_url"]},
        "thresholds": {"dino_min": im["prefilter"]["dino_min_similarity"]},
        "time_budget_s": int(im["kernel_time_budget_hours"] * 3600),
        "refs": {name: _img_b64(path) for name, path in portrait_files.items()},
        "items": items,
    }


def estimate_gpu_hours(job: dict[str, Any]) -> float:
    n = sum(it["n"] for it in job["items"])
    return round(n * models()["image"]["est_gpu_seconds_per_image"] / 3600 + 0.25, 2)


def render_kernel(job: dict[str, Any], out_dir: Path, username: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    code = (KERNEL_DIR / "art_kernel.py").read_text(encoding="utf-8")
    payload = base64.b64encode(json.dumps(job).encode()).decode()
    (out_dir / "art_kernel.py").write_text(code.replace("__JOB_B64__", payload), encoding="utf-8")
    meta = (KERNEL_DIR / "kernel-metadata.json.template").read_text()
    meta = meta.replace("__KAGGLE_USERNAME__", username).replace("__KERNEL_SLUG__", models()["kaggle"]["kernel_slug"])
    (out_dir / "kernel-metadata.json").write_text(meta)
    return out_dir
