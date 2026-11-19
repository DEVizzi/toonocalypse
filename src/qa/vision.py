"""Gemini client (api_version v1beta, models auto-discovered) + vision QA for portraits and panels (§7.4, §7.5)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from src.common.config import models

PORTRAIT_CRITERIA = ["single_character", "hair", "eye_colour", "outfit_colours", "accessory", "skin_tone", "age",
                     "anatomy", "comic_style", "no_text", "safety"]
PANEL_CRITERIA = ["matches_description", "character_consistency", "screen_side", "location", "anatomy", "no_text",
                  "empty_top", "composition", "safety"]
STRICT = ("Be strict. First write what you actually SEE for each lock-card item. A missing or wrong item scores at "
          "most 3. ")
_client = None
_models: list[str] | None = None


def _gemini():
    global _client, _models
    if _client is None:
        from google import genai
        from google.genai import types

        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"],
                               http_options=types.HttpOptions(api_version=models()["gemini"]["api_version"], timeout=120_000))
        have = {m.name.split("/")[-1] for m in _client.models.list()}
        _models = [m for m in models()["gemini"]["vision"] if m in have]
        print(f"[gemini] vision models: {_models}", flush=True)
    return _client, _models


def ask_json(contents: list[Any]) -> dict:
    from google.genai import types

    client, names = _gemini()
    last = None
    for model in names:
        for wait in (0, 10, 30):
            time.sleep(wait)
            try:
                r = client.models.generate_content(model=model, contents=contents,
                                                   config=types.GenerateContentConfig(response_mime_type="application/json"))
                m = re.search(r"\{[\s\S]*\}", r.text or "")
                if m:
                    return json.loads(m.group(0)) | {"_model": model}
                last = f"{model}: no JSON"
            except Exception as e:
                last = f"{model}: {type(e).__name__} {str(e)[:120]}"
                if "429" in str(e) or "404" in str(e):
                    break  # quota or missing model: next model
        print(f"[gemini] {last}; next model", flush=True)
    raise RuntimeError(f"Gemini unavailable: {last}")


def _img(path: Path):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((768, 1344))
    return im


def verdict(scores: dict, criteria: list[str]) -> dict:
    s = {k: int(scores.get(k, 0) or 0) for k in criteria}
    avg = round(sum(s.values()) / len(s), 2)
    return {"scores": s, "avg": avg, "passed": min(s.values()) >= 7 and avg >= 8 and s["safety"] >= 10}


def pick_portrait(card: dict, files: list[Path]) -> dict:
    lock = {k: card[k] for k in ["name", "age", "gender", "build", "face_shape", "hair", "eye_colour", "skin_tone",
                                 "outfit", "accessory"]}
    prompt = (f"You check comic character design candidates. Lock card: {lock}. There are {len(files)} images in order. "
              f"{STRICT}Score each 1-10 on {PORTRAIT_CRITERIA}. single_character=10 only if exactly one person is shown "
              "once. comic_style=10 for bold inked comic art. safety=10 if fine for ages 10+. Return JSON "
              '{"candidates":[{"index":0,"seen":"...","scores":{...},"note":"..."}]}')
    out = ask_json([prompt, *[_img(f) for f in files]])
    res = [verdict(c.get("scores", {}), PORTRAIT_CRITERIA) | {"index": int(c.get("index", i)), "note": c.get("note", "")}
           for i, c in enumerate(out.get("candidates", []))]
    best = max(res, key=lambda r: r["avg"])["index"] if res else 0
    return {"results": res, "best": best, "model": out.get("_model")}


def score_panel(panel: dict, cards: list[dict], portraits: dict[str, Path], location: str, image: Path) -> dict:
    refs = list(portraits.items())
    locks = {c["name"]: {k: c[k] for k in ["hair", "eye_colour", "skin_tone", "outfit", "accessory", "age"]} for c in cards}
    sides = {c["name"]: c["side"] for c in panel["characters"]}
    head = (f"Images 1-{len(refs)} are approved reference portraits of {[n for n, _ in refs]} (not judged). "
            if refs else "")
    prompt = (f"You are a strict comic panel QA reviewer. {head}The LAST image is the panel to judge. "
              f"Panel action: {panel['action']}. Location: {location}. Characters and screen sides: {sides or 'none'}. "
              f"Lock cards: {locks}. {STRICT}Score 1-10: {PANEL_CRITERIA}. character_consistency: same face, hair, eye "
              "colour, outfit colours and accessory as the portraits (10 if no characters). screen_side: each character "
              "on their side facing across the frame. empty_top: upper 25% uncluttered. safety=10 if fine for ages 10+. "
              'Return JSON {"scores":{...},"note":"short reason"}')
    out = ask_json([prompt, *[_img(p) for _, p in refs], _img(image)])
    return verdict(out.get("scores", {}), PANEL_CRITERIA) | {"note": out.get("note", ""), "model": out.get("_model")}
