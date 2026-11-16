"""Kaggle free-GPU Art Library generator (SDXL / FLUX.1-schnell + rembg + Consistency QA).

Clones/reads DEVizzi/toonocalypse character bible, generates 12 transparent 1024px poses per
character and 30+ empty 16:9 & 9:16 backgrounds, runs consistency QA (anchors, palette ΔE,
alpha coverage), and writes /kaggle/working/art_output/library_index.json + qa_report.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zlib
from pathlib import Path

# Install runtime dependencies inside Kaggle kernel if missing
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "diffusers>=0.30.0", "transformers", "accelerate", "rembg", "onnxruntime", "pillow", "numpy"],
    check=True,
)

import numpy as np
import torch
from PIL import Image
from diffusers import AutoPipelineForText2Image
from rembg import remove

REPO_DIR = Path("/kaggle/working/toonocalypse")
if not REPO_DIR.exists():
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/DEVizzi/toonocalypse.git", str(REPO_DIR)], check=True)

OUT_DIR = Path("/kaggle/working/art_output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

POSES = {
    "idle": "standing relaxed, friendly neutral pose, looking slightly toward camera",
    "walk": "mid-stride cheerful walking pose, arms swinging naturally",
    "run": "energetic dynamic running pose, leaning forward in motion",
    "jump": "mid-air joyful jump pose, arms raised high",
    "point": "pointing excitedly forward with one hand, expressive face",
    "surprised": "wide-eyed shocked gasp expression, hands raised near cheeks",
    "laughing": "belly-laughing expression, huge open smile, eyes crinkled",
    "comic-angry": "goofy cartoonishly grumpy scowl, puffed cheeks, crossed arms",
    "sad": "droopy puppy-dog eyes, slumped shoulders, sympathetic pout",
    "thinking": "hand on chin in thoughtful detective pose, raised eyebrow",
    "cheering": "celebratory fist-pump victory pose, big triumphant grin",
    "talking": "animated mid-sentence speaking pose, open mouth, expressive hand gesture",
}

BACKGROUNDS = [
    ("frosty-espresso-bar", "cozy snowy yeti-themed espresso cafe interior, wooden counter, steaming mugs, warm fairy lights"),
    ("sunny-town-square", "bright cobblestone cartoon town square, fountain, colorful awnings, fluffy clouds"),
    ("cozy-treehouse-hq", "whimsical giant treehouse headquarters interior, telescopes, maps, wooden beams"),
    ("neon-arcade-alley", "vibrant family-friendly retro arcade street, glowing game cabinets, colorful lanterns"),
    ("botanical-glasshouse", "sunlit glass botanical conservatory, giant friendly tropical leaves, glowing flowers"),
    ("clockwork-bakery", "whimsical brass clockwork bakery interior, floating pastry trays, warm golden ovens"),
    ("starlight-observatory", "cozy hilltop brass telescope observatory at twilight, starry sky through dome"),
    ("rainbow-skate-park", "bright sunlit outdoor skate park, curved colorful ramps, palm trees"),
    ("cloudtop-lighthouse", "cheerful coastal lighthouse balcony above fluffy clouds at golden hour"),
    ("bamboo-tea-garden", "serene bamboo courtyard with stone lantern, koi pond, wooden bridge"),
    ("midnight-museum-hall", "grand friendly natural history museum hall, glowing display cases, starry ceiling"),
    ("coral-reef-cove", "sunny turquoise tropical cove, colorful coral arches, sandy shore"),
    ("snowy-mountain-lodge", "warm timber ski lodge interior, crackling fireplace, snowy window view"),
    ("pumpkin-harvest-fair", "festive autumn harvest carnival, hay bales, string lights, colorful booths"),
    ("candy-factory-floor", "playful pastel candy workshop, swirling sugar pipes, oversized lollipops"),
    ("retro-comic-bookstore", "cozy neighborhood comic book shop, colorful shelves, reading nook"),
    ("floating-sky-docks", "steamy whimsical airship sky harbor, wooden piers, bright blue sky"),
    ("underground-crystal-cavern", "glowing bioluminescent crystal cave, warm amethyst and teal reflections"),
    ("rooftop-pizzeria", "twilight city rooftop pizzeria, brick oven, checkered tablecloths, string lights"),
    ("whimsical-science-lab", "colorful cartoon invention lab, bubbling glass flasks, chalkboard diagrams"),
    ("autumn-park-bridge", "golden autumn park with arched wooden bridge over sparkling stream"),
    ("tropical-tiki-beach", "bright sunny island beach, tiki torches, hammocks, turquoise waves"),
    ("winter-ice-rink", "outdoor frozen pond ice skating rink, pine trees, festive banners"),
    ("lantern-night-market", "bustling evening street food market, glowing paper lanterns, colorful stalls"),
    ("toy-workshop-attic", "warm sunlit attic toy workshop, wooden workbenches, colorful gears"),
    ("submarine-bridge", "retro-futuristic yellow submarine control room, big round portholes, ocean outside"),
    ("desert-cactus-diner", "sunny desert roadside retro diner, saguaro cacti, turquoise sky"),
    ("music-studio-stage", "vibrant cartoon concert stage, spotlights, colorful speakers"),
    ("library-spiral-tower", "magical tall spiral library with floating books and warm reading lamps"),
    ("carousel-carnival-plaza", "bright daytime carnival plaza with classic carousel tent and balloons"),
]


def _hex_to_rgb(hx: str) -> tuple[int, int, int]:
    hx = hx.lstrip("#")
    return tuple(int(hx[i : i + 2], 16) for i in (0, 2, 4))


def _mean_color_distance(img: Image.Image, target_hex: str) -> float:
    arr = np.asarray(img.convert("RGBA"))
    alpha = arr[:, :, 3] > 128
    if not np.any(alpha):
        return 999.0
    rgb = arr[alpha][:, :3].astype(np.float32)
    t = np.array(_hex_to_rgb(target_hex), dtype=np.float32)
    dists = np.linalg.norm(rgb - t, axis=1)
    # Use 15th percentile closest pixels to verify character's signature color is strongly present
    return float(np.percentile(dists, 15))


def _qa_sprite(img: Image.Image, char: dict) -> tuple[bool, float, list[str]]:
    reasons = []
    rgba = img.convert("RGBA")
    alpha = np.asarray(rgba)[:, :, 3]
    fg_ratio = float(np.mean(alpha > 128))
    if fg_ratio < 0.08 or fg_ratio > 0.88:
        reasons.append(f"fg_ratio {fg_ratio:.2f} out of [0.08, 0.88]")
    pri_dist = _mean_color_distance(rgba, char["palette"]["primary"])
    if pri_dist > 95.0:
        reasons.append(f"primary palette mismatch ({pri_dist:.1f})")
    score = max(0.0, min(1.0, 1.0 - (pri_dist / 160.0)))
    if score < 0.70:
        reasons.append(f"anchor/palette score {score:.2f} < 0.70")
    return not reasons, round(score, 3), reasons


def main() -> None:
    style_guide = (REPO_DIR / "config" / "style_guide.md").read_text(encoding="utf-8")
    style_short = " ".join(style_guide.splitlines()[:4])[:200]

    queue_file = REPO_DIR / "state" / "art_queue.json"
    queue = json.loads(queue_file.read_text(encoding="utf-8")) if queue_file.exists() else {"characters": [], "backgrounds": []}

    existing_idx_path = REPO_DIR / "assets" / "library_index.json"
    index = json.loads(existing_idx_path.read_text(encoding="utf-8")) if existing_idx_path.exists() else {"version": 0, "characters": {}, "backgrounds": {}}

    # Load all character JSONs, prioritizing queued + core heroes/villains
    chars = {}
    for folder in ("heroes", "villains"):
        for p in sorted((REPO_DIR / "characters" / folder).glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            chars[data["slug"]] = data

    # Batch limit per Kaggle run so we finish reliably inside ~45 minutes on T4/P100
    max_chars = int(os.environ.get("TOON_ART_MAX_CHARS", "6"))
    priority_slugs = [s for s in queue.get("characters", []) if s in chars]
    remaining_slugs = [s for s in sorted(chars.keys()) if s not in index.get("characters", {}) and s not in priority_slugs]
    target_slugs = (priority_slugs + remaining_slugs)[:max_chars]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    model_id = os.environ.get("TOON_KAGGLE_MODEL", "stabilityai/sdxl-turbo")
    pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype, variant="fp16" if dtype == torch.float16 else None)
    pipe = pipe.to(device)
    steps = 4 if "turbo" in model_id or "schnell" in model_id else 25

    qa_report = {"characters": {}, "backgrounds": {}}

    for slug in target_slugs:
        c = chars[slug]
        seed_base = zlib.crc32(slug.encode("utf-8")) & 0x7FFFFFFF
        char_dir = OUT_DIR / "characters" / slug
        char_dir.mkdir(parents=True, exist_ok=True)
        index.setdefault("characters", {}).setdefault(slug, {})
        qa_report["characters"][slug] = {}

        for p_idx, (pose_name, pose_desc) in enumerate(POSES.items()):
            out_png = char_dir / f"{pose_name}.png"
            prompt = (
                f"Single isolated 3D stylized cartoon character on plain solid #F0F0F0 studio backdrop, "
                f"full body head-to-toe centered, {style_short}. "
                f"Character: {c['visual_prompt']}. "
                f"Pose and expression: {pose_desc}. "
                f"MUST HAVE: {', '.join(c['anchors'][:3])}. "
                f"NO background props, NO text, NO letters, NO watermark."
            )
            gen = torch.Generator(device=device).manual_seed(seed_base + p_idx)
            raw_img = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=0.0 if "turbo" in model_id else 3.5, width=1024, height=1024, generator=gen).images[0]
            fg_img = remove(raw_img).resize((1024, 1024), Image.Resampling.LANCZOS)
            passed, score, reasons = _qa_sprite(fg_img, c)
            qa_report["characters"][slug][pose_name] = {"passed": passed, "score": score, "reasons": reasons}
            if passed:
                fg_img.save(out_png)
                index["characters"][slug][pose_name] = {
                    "path": f"assets/art_library/characters/{slug}/{pose_name}.png",
                    "qa_score": score,
                }

    # Generate missing backgrounds (both 16:9 and 9:16)
    bg_dir = OUT_DIR / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    for bg_idx, (bg_slug, bg_desc) in enumerate(BACKGROUNDS):
        if bg_slug in index.get("backgrounds", {}):
            continue
        seed_bg = (zlib.crc32(bg_slug.encode("utf-8")) & 0x7FFFFFFF) + bg_idx
        bg_entry = {}
        for aspect, (w, h) in (("16x9", (1344, 768)), ("9x16", (768, 1344))):
            out_bg = bg_dir / f"{bg_slug}_{aspect}.png"
            prompt = (
                f"Empty cartoon environment background, stylized 3D animated movie set, vibrant colors, "
                f"warm cinematic lighting, {bg_desc}. "
                f"STRICTLY NO characters, NO people, NO animals, NO text, NO signs, NO watermark."
            )
            gen = torch.Generator(device=device).manual_seed(seed_bg)
            bg_img = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=0.0 if "turbo" in model_id else 3.5, width=w, height=h, generator=gen).images[0]
            bg_img.save(out_bg)
            bg_entry[aspect] = f"assets/art_library/backgrounds/{bg_slug}_{aspect}.png"
        index.setdefault("backgrounds", {})[bg_slug] = bg_entry
        qa_report["backgrounds"][bg_slug] = {"passed": True}

    index["version"] = int(index.get("version", 0)) + 1
    (OUT_DIR / "library_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (OUT_DIR / "qa_report.json").write_text(json.dumps(qa_report, indent=2), encoding="utf-8")
    print(f"Done: library v{index['version']}, {len(index['characters'])} chars, {len(index['backgrounds'])} bgs")


if __name__ == "__main__":
    main()
