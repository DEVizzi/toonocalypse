"""Word-level caption timing alignment."""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or 22050
        return frames / float(rate)


def compute_word_timings(text: str, total_duration: float, offset: float = 0.0) -> list[WordTiming]:
    """Distribute word timings proportionally by character length (+ punctuation pause)."""
    words = [w for w in text.strip().split() if w]
    if not words or total_duration <= 0:
        return []
    weights = [max(1.0, len(w)) + (1.5 if w[-1] in ".!?," else 0.0) for w in words]
    total_w = sum(weights)
    out: list[WordTiming] = []
    cur = offset
    for w, wt in zip(words, weights):
        dur = total_duration * (wt / total_w)
        out.append(WordTiming(word=w, start=round(cur, 3), end=round(cur + dur, 3)))
        cur += dur
    return out
