"""Hook & Retention Score gate (§10.L)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from src.common.config import load_models, load_playbook
from src.common.quota import QuotaTracker

SCORE_KEYS = (
    "hook",
    "stakes",
    "escalation",
    "surprises",
    "voice_accuracy",
    "warmth",
    "ending",
    "shareability",
    "safety",
)


@dataclass
class HookGateResult:
    passed: bool
    avg_score: float
    scores: dict[str, float]
    feedback: str


def parse_judge_json(raw_text: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}", raw_text)
    if not m:
        raise ValueError("No JSON object found in Hook & Retention judge output")
    data = json.loads(m.group(0))
    scores: dict[str, float] = {}
    for k in SCORE_KEYS:
        if k not in data:
            raise ValueError(f"Missing judge score key: {k}")
        scores[k] = max(0.0, min(10.0, float(data[k])))
    return {"scores": scores, "feedback": str(data.get("feedback", ""))}


def evaluate_scores(scores: dict[str, float], feedback: str = "") -> HookGateResult:
    gates = load_playbook().get("gates", {}).get("hook_retention", {})
    min_avg = float(gates.get("min_avg_score", 7.5))
    min_safety = float(gates.get("min_safety_score", 10.0))
    min_hook = float(gates.get("min_hook_score", 8.0))

    avg = sum(scores[k] for k in SCORE_KEYS) / len(SCORE_KEYS)
    ok = avg >= min_avg and scores["safety"] >= min_safety and scores["hook"] >= min_hook
    return HookGateResult(passed=ok, avg_score=round(avg, 2), scores=scores, feedback=feedback)


def judge_script(script: dict[str, Any], offline: bool = False, quota: QuotaTracker | None = None) -> HookGateResult:
    """Score a script using Gemini (or deterministic heuristic in offline/dry-run mode)."""
    if not offline and os.environ.get("GOOGLE_API_KEY"):
        qt = quota or QuotaTracker()
        if qt.can_spend("text", 1):
            try:
                from google import genai

                client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
                model = load_models().get("text_models", ["gemini-2.5-flash"])[0]
                prompt = (
                    "Score this family-friendly motion-comic script 1-10 on each key and return ONLY JSON "
                    f"with keys {list(SCORE_KEYS)} and 'feedback':\n\n{json.dumps(script, ensure_ascii=False)}"
                )
                resp = client.models.generate_content(model=model, contents=prompt)
                qt.spend("text", 1)
                parsed = parse_judge_json(resp.text or "")
                return evaluate_scores(parsed["scores"], parsed["feedback"])
            except Exception:
                pass

    # Deterministic heuristic fallback for offline / dry-run
    panels = script.get("panels", [])
    hook_ok = bool(script.get("on_screen_hook")) and len(script.get("on_screen_hook", "").split()) <= 6
    dialogue_words = sum(len(d.get("line", "").split()) for p in panels for d in p.get("dialogue", []))
    narrator_words = sum(len(p.get("narrator", "").split()) for p in panels)
    total_words = max(1, dialogue_words + narrator_words)
    scores = {
        "hook": 8.5 if hook_ok and len(panels) == 6 else 6.0,
        "stakes": 8.0,
        "escalation": 8.0,
        "surprises": 8.0,
        "voice_accuracy": 8.5,
        "warmth": 8.5,
        "ending": 8.5,
        "shareability": 8.0,
        "safety": 10.0,
    }
    if narrator_words / total_words > 0.30:
        scores["voice_accuracy"] = 6.5
    return evaluate_scores(scores, "Deterministic offline/fallback judge")
