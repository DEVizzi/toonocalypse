"""Episode title quality validator (§6.2 & §7)."""
from __future__ import annotations

import re

CONNECTOR_ENDINGS = frozenset({
    "when", "and", "but", "the", "to", "with", "of", "a", "an", "or",
    "for", "in", "on", "at", "by", "from", "that", "which", "who",
    "as", "if", "so", "yet", "into", "onto", "until", "while",
})

COMMON_VERBS = frozenset({
    "is", "are", "was", "were", "be", "been", "being", "am",
    "has", "have", "had", "do", "does", "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "go", "goes", "went", "gone", "come", "comes", "came", "run", "runs", "ran",
    "chase", "chases", "chased", "catch", "catches", "caught", "steal", "steals", "stole", "stolen",
    "save", "saves", "saved", "stop", "stops", "stopped", "find", "finds", "found",
    "lose", "loses", "lost", "break", "breaks", "broke", "broken", "make", "makes", "made",
    "take", "takes", "took", "taken", "get", "gets", "got", "give", "gives", "gave",
    "freeze", "freezes", "froze", "melt", "melts", "melted", "fly", "flies", "flew",
    "jump", "jumps", "jumped", "bounce", "bounces", "bounced", "crash", "crashes", "crashed",
    "rescue", "rescues", "rescued", "build", "builds", "built", "bake", "bakes", "baked",
    "cook", "cooks", "cooked", "solve", "solves", "solved", "hide", "hides", "hid",
    "trap", "traps", "trapped", "escape", "escapes", "escaped", "launch", "launches", "launched",
    "swap", "swaps", "swapped", "ruin", "ruins", "ruined", "invade", "invades", "invaded",
    "battle", "battles", "battled", "guard", "guards", "guarded", "drop", "drops", "dropped",
    "slip", "slips", "slipped", "spill", "spills", "spilled", "blast", "blasts", "blasted",
    "shrunk", "shrink", "shrinks", "grow", "grows", "grew", "wake", "wakes", "woke",
    "dance", "dances", "danced", "sing", "sings", "sang", "laugh", "laughs", "laughed",
    "panic", "panics", "panicked", "vanish", "vanishes", "vanished", "appear", "appears", "appeared",
    "deliver", "delivers", "delivered", "eat", "eats", "ate", "hijack", "hijacks", "hijacked",
    "turn", "turns", "turned", "unlock", "unlocks", "unlocked", "unleash", "unleashes", "unleashed",
    "outsmart", "outsmarts", "outsmarted", "defend", "defends", "defended",
})

VERB_SUFFIX_RE = re.compile(r"^[a-z]{3,}(?:s|es|ed|ing)$")


def _has_verb(words: list[str]) -> bool:
    for w in words:
        clean = re.sub(r"[^a-z]", "", w.lower())
        if not clean:
            continue
        if clean in COMMON_VERBS:
            return True
    # Secondary morphology check only for non-initial words that look like inflected verbs
    # (excluding obvious nouns ending in 's' when no known verb matched).
    for w in words[1:]:
        clean = re.sub(r"[^a-z]", "", w.lower())
        if clean.endswith(("ed", "ing")) and len(clean) >= 5:
            return True
    return False


def validate_title(title: str) -> tuple[bool, list[str]]:
    """Validate LLM-generated title against §6.2 rules."""
    reasons: list[str] = []
    cleaned = " ".join((title or "").strip().split())
    words = [w for w in re.findall(r"[A-Za-z0-9']+", cleaned) if w]
    if len(words) < 4:
        reasons.append(f"title has fewer than 4 words ({len(words)})")
    if words and words[-1].lower() in CONNECTOR_ENDINGS:
        reasons.append(f"title ends with connector word '{words[-1].lower()}'")
    if words and not _has_verb(words):
        reasons.append("title has no verb")
    return not reasons, reasons
