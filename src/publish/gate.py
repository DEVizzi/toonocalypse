"""Publishable quality gate (§6.2): non-publishable episodes never reach buffer or platforms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.render.qa import RenderQAResult
from src.story.title_validator import validate_title


@dataclass
class PublishableResult:
    publishable: bool
    reasons: list[str]


def evaluate_publishable(
    script: dict[str, Any],
    art_qa_passed: bool,
    used_library_art: bool,
    yt_qa: RenderQAResult,
    ig_qa: RenderQAResult,
) -> PublishableResult:
    """Enforce every §6.2 publishable criterion."""
    reasons: list[str] = []

    if script.get("source") != "llm":
        reasons.append(f"non-LLM/fallback script source ({script.get('source')})")
    if not script.get("is_llm_judged"):
        reasons.append("hook score did not come from real LLM judge")

    title_ok, title_reasons = validate_title(str(script.get("title", "")))
    if not title_ok:
        reasons.extend(title_reasons)

    panels = script.get("panels", [])
    if len(panels) < 6:
        reasons.append(f"fewer than 6 panels ({len(panels)})")

    if not art_qa_passed:
        reasons.append("panel consistency QA failed")
    if not used_library_art:
        reasons.append("non-library or placeholder artwork used")

    for name, qa in (("youtube", yt_qa), ("instagram", ig_qa)):
        if not qa.passed:
            reasons.extend(f"{name}: {r}" for r in qa.reasons)

    return PublishableResult(publishable=not reasons, reasons=reasons)
