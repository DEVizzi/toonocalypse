"""Personality-driven expressions (v5.1): the same game moment reads differently on every ball.

Grumble is grumpy everywhere (even on the podium), Juggernaut is never scared, Floater is too chill to panic, Sly
stays smug, Pip is a nervous wreck, Dash and Boing grin through chaos. Applied centrally in `balls.draw_ball`, so
Shorts, recap cards, awards and thumbnails all agree. Dizzy / eliminated faces always stay (physical comedy).
"""
from __future__ import annotations

PERSONALITY: dict[str, dict[str, str]] = {
    "grumble": {"happy": "angry", "neutral": "angry", "celebrating": "angry", "scared": "angry"},
    "juggernaut": {"scared": "angry"},
    "floater": {"scared": "neutral", "angry": "happy"},
    "sly": {"scared": "neutral", "happy": "neutral"},
    "pip": {"angry": "scared"},
    "bonk": {"scared": "neutral"},
    "dash": {"scared": "happy"},
    "boing": {"angry": "happy", "scared": "happy"},
    "magneto": {"scared": "angry"},
    # Season 2+ rookies
    "zap": {"neutral": "happy", "scared": "angry"},
    "goo": {"angry": "happy"},
    "frosty": {"happy": "neutral", "angry": "neutral"},
    "blaze": {"neutral": "angry", "scared": "angry"},
    "shadow": {"happy": "neutral", "scared": "neutral"},
    "comet": {"scared": "celebrating"},
}
ALWAYS_GRUMPY = {"grumble"}


def expression_for(hero_key: str | None, expression: str) -> str:
    if not hero_key:
        return expression
    return PERSONALITY.get(hero_key, {}).get(expression, expression)
