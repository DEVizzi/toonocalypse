"""Timeline: turn a part script + TTS into timed panels, spoken lines (with word timings), SFX and end cards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from src.audio.tts import SR, Speech
from src.common.config import settings

GAP = 0.18          # silence between lines
PANEL_LEAD = 0.25   # audio starts this long after a panel appears
PANEL_TAIL = 0.45   # hold after the last line of a panel


@dataclass
class Line:
    speaker: str            # character name or "Narrator"
    text: str
    start: float
    end: float
    words: list[dict]       # absolute times
    audio: np.ndarray
    position: str = "center"
    narration: bool = False


@dataclass
class PanelEvent:
    index: int
    image_key: str
    start: float
    end: float
    lines: list[Line] = field(default_factory=list)
    sfx: str = ""
    action: bool = False


@dataclass
class Timeline:
    panels: list[PanelEvent]
    duration: float
    previously: str = ""
    moral: str = ""
    moral_start: float | None = None
    loop_tail: float = 0.0


def build(part: dict, story: dict, voices: dict[str, str], tts: Callable[[str, str, float], Speech],
          speed: float = 1.0, final: bool = False) -> Timeline:
    s = settings()
    positions_cast = {c["name"] for c in story["cast"]}
    t, events = 0.0, []
    for i, p in enumerate(part["panels"]):
        pos = {c["name"]: c.get("position", "center") for c in p.get("characters", [])}
        speech_items = []
        if p.get("narration"):
            speech_items.append(("Narrator", p["narration"], True))
        for d in p.get("dialogue", []) or []:
            if d.get("line"):
                speech_items.append((d["speaker"], d["line"], False))
        if i == 0 and part.get("hook_text") and not any(part["hook_text"].strip().lower() in x[1].lower() for x in speech_items):
            speech_items.insert(0, ("Narrator", part["hook_text"], True))
        start = t
        cursor = t + (0.12 if i == 0 else PANEL_LEAD)
        lines = []
        for speaker, text, narr in speech_items:
            voice = voices.get(speaker) if speaker in positions_cast else voices["Narrator"]
            sp = tts(text, voice, speed)
            words = [{"word": w["word"], "start": cursor + w["start"], "end": cursor + w["end"]} for w in sp.words]
            lines.append(Line(speaker, text, cursor, cursor + sp.duration, words, sp.audio, pos.get(speaker, "center"), narr))
            cursor += sp.duration + GAP
        end = max(start + float(p.get("duration", 5)), (lines[-1].end if lines else start) + PANEL_TAIL)
        events.append(PanelEvent(i, str(p["id"]), start, end, lines, str(p.get("sfx") or "").strip(), bool(p.get("sfx"))))
        t = end
    moral_start = None
    if final and part.get("moral_card"):
        moral_start = t
        t += s["video"]["moral_card_seconds"]
    loop_tail = 0.4 if final else 0.0
    t += loop_tail
    tl = Timeline(events, round(t, 3), part.get("previously") or "", part.get("moral_card") or "", moral_start, loop_tail)
    return stretch_to_min(tl)


def stretch_to_min(tl: Timeline) -> Timeline:
    """If shorter than the minimum, extend panel holds (silence) evenly; never touches speech timing within a panel."""
    lo = settings()["story"]["part_seconds"]["min"]
    short = lo - tl.duration
    if short <= 0:
        return tl
    add = short / len(tl.panels)
    shift = 0.0
    for ev in tl.panels:
        ev.start += shift
        for ln in ev.lines:
            ln.start += shift
            ln.end += shift
            for w in ln.words:
                w["start"] += shift
                w["end"] += shift
        shift += add
        ev.end += shift
    if tl.moral_start is not None:
        tl.moral_start += shift
    tl.duration = round(tl.duration + shift, 3)
    return tl


def speech_track(tl: Timeline, sr_out: int = 48000) -> np.ndarray:
    out = np.zeros(int(tl.duration * sr_out) + sr_out, dtype=np.float32)
    for ev in tl.panels:
        for ln in ev.lines:
            n_out = int(len(ln.audio) * sr_out / SR)
            res = np.interp(np.linspace(0, len(ln.audio) - 1, n_out), np.arange(len(ln.audio)), ln.audio).astype(np.float32)
            i = int(ln.start * sr_out)
            out[i:i + len(res)] += res[: max(0, len(out) - i)]
    return out[: int(tl.duration * sr_out)]
