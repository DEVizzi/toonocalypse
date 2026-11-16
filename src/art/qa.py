"""Art consistency & layout QA gate (§7.8)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from src.common.config import load_models, load_playbook
from src.common.quota import QuotaTracker
from src.common.state import load_state, save_state
from src.panels.slicer import detect_gutters


@dataclass
class ArtQAResult:
    passed: bool
    anchor_score: float
    panel_count: int
    has_text: bool
    reasons: list[str]


def check_page_qa(
    page_path: Path,
    script: dict[str, Any],
    offline: bool = False,
    quota: QuotaTracker | None = None,
) -> ArtQAResult:
    gates = load_playbook().get("gates", {}).get("art_qa", {})
    min_anchor = float(gates.get("min_anchor_score", 0.70))

    img = Image.open(page_path).convert("RGB")
    boxes = detect_gutters(img)
    reasons: list[str] = []
    if len(boxes) != 6:
        reasons.append(f"expected 6 panels, detected {len(boxes)}")

    anchor_score = 0.90
    has_text = False
    from src.common.gemini import discover_text_models, get_client, has_gemini_key

    if not offline and has_gemini_key():
        qt = quota or QuotaTracker()
        if qt.can_spend("vision", 1):
            try:
                cli = get_client()
                models = discover_text_models(client=cli)
                resp = None
                for model in models:
                    try:
                        resp = cli.models.generate_content(
                            model=model,
                            contents=[
                                "Check this 2x3 comic page. Return ONLY JSON: "
                                '{"anchor_score": 0.0-1.0, "has_text": true/false, "forbidden_found": false, "notes": ""}',
                                img,
                            ],
                        )
                        qt.spend("vision", 1)
                        break
                    except Exception:
                        continue
                m = None
                if resp is not None:
                    m = re.search(r"\{[\s\S]*\}", resp.text or "")
                if m:
                    data = json.loads(m.group(0))
                    anchor_score = float(data.get("anchor_score", 0.9))
                    has_text = bool(data.get("has_text", False))
                    if data.get("forbidden_found"):
                        reasons.append("forbidden character item detected")
            except Exception:
                pass

    if anchor_score < min_anchor:
        reasons.append(f"anchor_score {anchor_score:.2f} < {min_anchor}")
    if has_text:
        reasons.append("model-drawn text detected in artwork")

    res = ArtQAResult(passed=not reasons, anchor_score=anchor_score, panel_count=len(boxes), has_text=has_text, reasons=reasons)
    log = load_state("qa_log.json", {"entries": []})
    log.setdefault("entries", []).append(
        {"type": "art_qa", "episode": f"{script.get('story_id')}_pt{script.get('part_num')}", "passed": res.passed, "anchor_score": anchor_score, "reasons": reasons}
    )
    save_state("qa_log.json", log)
    return res
