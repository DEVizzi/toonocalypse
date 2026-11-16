"""Family-friendly all-ages moderation gate (§8)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from src.common.config import load_models
from src.common.quota import QuotaTracker

BLOCKED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(pixar|dreamworks|ghibli|disney|nickelodeon|illumination)\b", "studio_or_brand_name"),
    (r"\b(sniper|gun|rifle|pistol|shotgun|knife|dagger|stab|bleed|blood|gore|murder|kill|deadly|corpse|suicide)\b", "violence_or_weapons"),
    (r"\b(sacrifice|chanting in latin|occult|demon|satan)\b", "scary_or_ritual"),
    (r"\b(blackmail|extort|hypnoti[sz]e|mind[- ]control|force[- ]feed)\b", "harmful_coercion"),
    (r"\b(headbutting climbers off cliffs|push(?:ing)? off (?:a )?cliff)\b", "unsafe_imitable_harm"),
    (r"\b(alcohol|beer|wine|vodka|cigarette|vape|smoke|drug|addict(?:ed|ion)?)\b", "adult_substances"),
    (r"\b(kiss(?:ing)?|romance|dating|flirt(?:y|ing)?|boyfriend|girlfriend)\b", "romance"),
    (r"\b(election|president|parliament|protest|warfare)\b", "politics_or_news"),
)


@dataclass
class ModerationResult:
    passed: bool
    reasons: list[str]


def check_text(text: str, use_llm: bool = False, quota: QuotaTracker | None = None) -> ModerationResult:
    """Run deterministic all-ages checks, plus optional Gemini safety review."""
    reasons: list[str] = []
    lower = text.lower()
    for pat, label in BLOCKED_PATTERNS:
        if re.search(pat, lower):
            reasons.append(label)
    if reasons:
        return ModerationResult(passed=False, reasons=sorted(set(reasons)))

    from src.common.gemini import call_with_key_failover, has_gemini_keys

    if use_llm and has_gemini_keys():
        qt = quota or QuotaTracker()
        if qt.can_spend("text", 1):
            try:
                models = load_models().get("text_models", ["gemini-3.1-flash-lite-preview"])
                prompt = (
                    "Reply ONLY 'PASS' or 'FAIL: <reason>'. Is this 100% safe, wholesome, "
                    "all-ages family-friendly cartoon content with no scary imagery, real brands, "
                    "romance, weapons aimed at characters, or unsafe imitable behaviour?\n\n"
                    f"{text[:4000]}"
                )
                for model in models:
                    try:
                        resp = call_with_key_failover(
                            lambda client, m=model: client.models.generate_content(model=m, contents=prompt)
                        )
                        qt.spend("text", 1)
                        ans = (resp.text or "").strip()
                        if ans.upper().startswith("FAIL"):
                            return ModerationResult(passed=False, reasons=[ans])
                        break
                    except Exception:
                        continue
            except Exception:
                pass
    return ModerationResult(passed=True, reasons=[])


def check_script(script: dict[str, Any], use_llm: bool = False) -> ModerationResult:
    parts = [script.get("title", ""), script.get("logline", ""), script.get("on_screen_hook", "")]
    for p in script.get("panels", []):
        parts.append(p.get("action", ""))
        parts.append(p.get("narrator", ""))
        for d in p.get("dialogue", []):
            parts.append(d.get("line", ""))
    return check_text("\n".join(parts), use_llm=use_llm)


def check_metadata(title: str, description: str, caption: str, tags: list[str]) -> ModerationResult:
    blob = "\n".join([title, description, caption, " ".join(tags)])
    return check_text(blob, use_llm=False)
