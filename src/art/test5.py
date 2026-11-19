"""Proof 1 (TEST5): 2 characters from "The Golden Rickshaw", 5 panels
(2 close-ups, 2 medium two-shots, 1 establishing shot), one Kaggle session.

  python -m src.art.test5 job <kernel_dir>          build job + kernel folder
  python -m src.art.test5 report <kout_dir> <out>   Gemini QA, contact sheet, prompts.json, qa.json
"""
from __future__ import annotations

import base64
import json
import os
import sys
import zlib
from pathlib import Path

from src.art import blocks, prompt_builder
from src.common.config import ROOT, models, phrases

STORY_ID = "test5-golden-rickshaw"
PORTRAIT_CANDIDATES = 4
PANEL_CANDIDATES = 3

CAST = [
    {"name": "Devan Thorai", "age": 32, "gender": "man", "build": "wiry build", "face_shape": "long narrow face",
     "hair": "short wavy black", "eye_colour": "dark brown", "skin_tone": "deep brown",
     "outfit": "a faded mustard-yellow kurta and rolled-up grey trousers", "accessory": "a red cotton scarf around his neck",
     "home_side": "left"},
    {"name": "Neela Varsi", "age": 64, "gender": "woman", "build": "small plump build", "face_shape": "round face",
     "hair": "silver-white, in a tight bun,", "eye_colour": "hazel", "skin_tone": "light brown",
     "outfit": "a deep blue sari with a thin gold border", "accessory": "round gold-rimmed spectacles",
     "home_side": "right"},
]
LOCATIONS = [
    {"id": "street", "description": "a narrow old city street at dusk, a yellow cycle rickshaw, glowing paper lanterns, "
                                    "warm orange sky, simple clean background"},
    {"id": "stall", "description": "a small roadside tea stall at night, a wooden bench, a steaming kettle, "
                                   "soft yellow bulb light, simple clean background"},
]
PANELS = [
    {"id": "1-closeup-devan", "characters": [{"name": "Devan Thorai", "side": "left"}], "location": "street",
     "action": "close-up, stunned expression, staring down at an open cloth bag full of gold coins"},
    {"id": "2-closeup-neela", "characters": [{"name": "Neela Varsi", "side": "right"}], "location": "stall",
     "action": "close-up, worried expression, pressing both hands to her chest"},
    {"id": "3-twoshot-return", "characters": [{"name": "Devan Thorai", "side": "left"}, {"name": "Neela Varsi", "side": "right"}],
     "location": "street", "action": "medium two-shot, Devan holds out the cloth bag of gold coins, Neela gasps with relief"},
    {"id": "4-twoshot-tea", "characters": [{"name": "Devan Thorai", "side": "left"}, {"name": "Neela Varsi", "side": "right"}],
     "location": "stall", "action": "medium two-shot, Neela laughs and hands Devan a small cup of tea, both smiling"},
    {"id": "5-establishing", "characters": [], "location": "street",
     "action": "wide establishing shot, the empty rickshaw parked under the lanterns"},
]


def seed_of(key: str) -> int:
    return zlib.crc32(f"{STORY_ID}|{key}".encode()) % 2_000_000_000


def build_items(frozen: dict) -> list[dict]:
    items = [{"id": f"portrait-{blocks.sha(c['name'])[:6]}", "kind": "portrait", "character": c["name"],
              "prompt": prompt_builder.portrait_prompt(c["name"], frozen), "seed": seed_of(c["name"]),
              "n": PORTRAIT_CANDIDATES} for c in CAST]
    for i, p in enumerate(PANELS):
        # seed = character_seed + panel_index (left-most character), so reruns reproduce the same image
        base = seed_of(p["characters"][0]["name"]) if p["characters"] else seed_of(p["id"])
        items.append({"id": p["id"], "kind": "panel", "prompt": prompt_builder.build(p, frozen), "seed": base + i,
                      "n": PANEL_CANDIDATES})
    return items


def make_job(kernel_dir: Path) -> dict:
    frozen = blocks.freeze(CAST, LOCATIONS)
    im = models()["image"]
    job = {"story_id": STORY_ID, "image": im, "negative": phrases()["NEGATIVE_PHRASE"], "blocks": frozen,
           "items": build_items(frozen)}
    kernel_dir.mkdir(parents=True, exist_ok=True)
    code = (ROOT / "kaggle" / "art_kernel.py").read_text(encoding="utf-8")
    payload = base64.b64encode(json.dumps(job).encode()).decode()
    (kernel_dir / "art_kernel.py").write_text(code.replace("__JOB_B64__", payload), encoding="utf-8")
    user = os.environ.get("KAGGLE_USERNAME", "user")
    meta = {"id": f"{user}/{models()['kaggle']['kernel_slug']}", "title": models()["kaggle"]["kernel_slug"],
            "code_file": "art_kernel.py", "language": "python", "kernel_type": "script", "is_private": True,
            "enable_gpu": True, "enable_internet": True, "machine_shape": models()["kaggle"]["machine_shape"],
            "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}
    (kernel_dir / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
    (kernel_dir.parent / "job.json").write_text(json.dumps(job, indent=1))
    return job


def report(kout: Path, out: Path) -> None:
    from src.qa import vision
    from src.art import sheet

    out.mkdir(parents=True, exist_ok=True)
    man = json.loads((kout / "manifest.json").read_text())
    job = json.loads((ROOT / "work" / "job.json").read_text()) if (ROOT / "work" / "job.json").exists() else None
    cards = {c["name"]: c for c in CAST}
    results: dict = {"manifest_errors": man.get("errors", []), "portraits": {}, "panels": {}}
    portraits: dict[str, Path] = {}
    for item_id, rec in man["items"].items():
        if rec["kind"] != "portrait" or not rec["files"]:
            continue
        name = rec["character"]
        res = vision.pick_portrait(cards[name], [kout / f for f in rec["files"]])
        results["portraits"][name] = res | {"files": rec["files"], "prompt": rec["prompt"], "seeds": rec["seeds"],
                                            "t5_tokens": rec["t5_tokens"], "clip_tokens": rec["clip_tokens"]}
        portraits[name] = kout / rec["files"][res["best"]]
        print(f"[qa] portrait {name}: best={rec['files'][res['best']]} avg={res['results'][res['best']]['avg']}", flush=True)
    for p in PANELS:
        rec = man["items"].get(p["id"])
        if not rec or not rec["files"]:
            results["panels"][p["id"]] = {"error": "not generated"}
            continue
        scored = []
        for f in rec["files"]:
            s = vision.score_panel(p, [cards[c["name"]] for c in p["characters"]],
                                   {c["name"]: portraits[c["name"]] for c in p["characters"] if c["name"] in portraits},
                                   dict((l["id"], l["description"]) for l in LOCATIONS)[p["location"]], kout / f)
            scored.append(s | {"file": f})
        best = max(scored, key=lambda s: s["avg"])
        results["panels"][p["id"]] = {"best": best, "candidates": scored, "prompt": rec["prompt"], "seeds": rec["seeds"],
                                      "t5_tokens": rec["t5_tokens"], "clip_tokens": rec["clip_tokens"]}
        print(f"[qa] {p['id']}: best={best['file']} avg={best['avg']} consistency={best['scores'].get('character_consistency')}",
              flush=True)
    cons = [results["panels"][p["id"]]["best"]["scores"].get("character_consistency", 0)
            for p in PANELS if p["characters"] and "best" in results["panels"][p["id"]]]
    results["avg_character_consistency"] = round(sum(cons) / len(cons), 2) if cons else None
    results["blocks"] = job["blocks"] if job else None
    (out / "qa.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    sheet.contact_sheet(results, portraits, kout, out / "test5_contact_sheet.jpg")
    print(f"[qa] average character consistency: {results['avg_character_consistency']}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "job":
        j = make_job(Path(sys.argv[2]))
        for it in j["items"]:
            print(f"{it['id']} seed={it['seed']}\n  {it['prompt']}\n")
    else:
        report(Path(sys.argv[2]), Path(sys.argv[3]))
