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
                  f"full body, front view, standing, centered, plain light grey background")
        negative = (f"{sg['negative']}, photo, photograph, photorealistic, realistic skin, 3d render, cgi, "
                    f"character sheet, turnaround, multiple views, collage, grid, duplicate person, two people, crowd, "
                    f"split screen, monochrome")
        anchors = list(dict.fromkeys(f"a cartoon person with {x}" for x in [c.get("hair"), c.get("accessory"), *c.get("anchors", [])] if x))
        items.append(_base_item(id=portrait_id(c["name"]), kind="portrait", prompt=prompt, negative=negative,
                                seed=char_seed(story["story_id"], c["name"], salt), n=im["candidates"]["portrait"],
                                keep=im["candidates"]["portrait_keep"], clip_text=c["visual_prompt"][:300],
                                anchors=anchors, upscale=False, refs=[]))
    return items


def panel_prompt(panel: dict[str, Any], cast_by_name: dict[str, dict[str, Any]]) -> str:
    sg = style_guide()
    chars = "; ".join(f"{c['name']} on the {c['position']}: {cast_by_name[c['name']]['visual_prompt']}"
                      for c in panel.get("characters", []))
    shot = f"{panel.get('camera', '')} shot, {panel.get('lighting', '')} lighting, {panel.get('emotion', '')} mood"
    return (f"({sg['positive']})1.2, {panel['image_prompt']}. {chars + '. ' if chars else ''}{shot}. "
            f"Empty sky or plain wall in the upper quarter of the frame.")


PANEL_NEGATIVE_EXTRA = "photo, photograph, photorealistic, 3d render, cgi"


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
                                    negative=f"{sg['negative']}, {PANEL_NEGATIVE_EXTRA}",
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
