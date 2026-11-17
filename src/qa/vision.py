"""Gemini vision QA for cast portraits and panels (§7.3, §7.4). Pass/fail logic is pure and tested."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.common.config import settings
from src.common.gemini import generate_json
from src.common.quota import Quota

PORTRAIT_CRITERIA = ["single_character", "comic_style", "hair", "outfit_colors", "accessory", "skin_tone", "age", "anatomy", "no_text", "safety"]
PANEL_CRITERIA = ["matches_description", "character_consistency", "comic_style", "anatomy", "no_text", "empty_top", "composition", "safety"]


def verdict(scores: dict[str, Any], criteria: list[str]) -> dict[str, Any]:
    cfg = settings()["panel_qa"]
    s = {k: int(scores.get(k, 0) or 0) for k in criteria}
    avg = round(sum(s.values()) / len(s), 2)
    passed = min(s.values()) >= cfg["min_each"] and avg >= cfg["min_avg"] and s["safety"] >= cfg["safety"]
    return {"scores": s, "avg": avg, "passed": passed}


def _img(path: Path):
    from PIL import Image

    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 1366))
    return img


STRICT = ("Be strict. First, for each lock-card item, write what you actually SEE in the image. "
          "Any item that is missing or a different colour/object scores at most 3. "
          "comic_style=10 only for illustrated comic-book art with ink lines; a photo, photorealistic or 3D-render look scores at most 3. ")


def portrait_qa(char: dict[str, Any], candidates: list[Path], quota: Quota | None = None) -> dict[str, Any]:
    lock = {k: char.get(k) for k in ["name", "age", "gender", "region", "build", "hair", "skin_tone", "outfit",
                                     "accessory", "signature_color", "anchors"]}
    prompt = (f"You check character design candidates for a comic. Lock card: {lock}. "
              f"There are {len(candidates)} candidate images in order. {STRICT}For EACH candidate score 1-10: {PORTRAIT_CRITERIA}. "
              "single_character=10 only if exactly ONE person/creature is shown once (no character sheets, turnarounds or duplicates); "
              "hair/outfit_colors/accessory/skin_tone/age must match the lock card exactly; anatomy = correct human (or creature) anatomy, "
              "right number of fingers and limbs; no_text=10 only if there are no letters/watermarks; safety=10 if suitable for ages 10+. "
              'Return JSON: {"candidates":[{"index":0,"seen":{"hair":"","outfit":"","accessory":""},"scores":{...},"note":""}]}')
    out, model = generate_json([prompt, *[_img(p) for p in candidates]], "qa_portrait", kind="vision", quota=quota)
    results = []
    for c in out.get("candidates", []):
        i = int(c.get("index", -1))
        if 0 <= i < len(candidates):
            results.append(verdict(c.get("scores", {}), PORTRAIT_CRITERIA) | {"index": i, "note": c.get("note", "")})
    passing = sorted((r for r in results if r["passed"]), key=lambda r: r["avg"], reverse=True)
    return {"model": model, "results": results, "best": passing[0]["index"] if passing else None}


def panel_qa(panel: dict[str, Any], cast: dict[str, dict[str, Any]], image: Path, portraits: dict[str, Path],
             quota: Quota | None = None) -> dict[str, Any]:
    chars = panel.get("characters", [])
    refs = [(c["name"], portraits[c["name"]]) for c in chars if c["name"] in portraits]
    locks = {n: {k: cast[n].get(k) for k in ["hair", "outfit", "accessory", "skin_tone", "age", "anchors"]} for n, _ in refs}
    prompt = (f"You are a strict comic panel QA reviewer. You get {len(refs) + 1} images. "
              f"{'Images 1-' + str(len(refs)) + ' are approved reference portraits of ' + str([n for n, _ in refs]) + ' (NOT to be judged). ' if refs else ''}"
              f"Image {len(refs) + 1} (the LAST one) is the PANEL to judge. "
              f"Panel description: {panel['image_prompt']}. Characters and positions: {chars or 'none (character-free shot)'}. "
              f"Lock cards: {locks}. {STRICT}Score 1-10: {PANEL_CRITERIA}. character_consistency=10 if there are no characters; "
              "otherwise faces, hair, outfit colours and accessory must match the portraits. empty_top: the upper 25% is "
              "uncluttered (sky, wall, ceiling, dark or blurred background) so a speech bubble can sit there without hiding a face. "
              "no_text=10 only with no letters/logos/watermarks. safety=10 only if fine for ages 10+ "
              '(no gore/blood). Return JSON: {"scores":{...},"note":"short reason"}')
    contents = [prompt, *[_img(p) for _, p in refs], _img(image)]
    out, model = generate_json(contents, "qa_panel", kind="vision", quota=quota)
    return verdict(out.get("scores", {}), PANEL_CRITERIA) | {"note": out.get("note", ""), "model": model}
