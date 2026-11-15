"""Word-highlighted ASS caption generator inside platform safe zones (§6 & §10.E)."""
from __future__ import annotations

from pathlib import Path

from src.audio.timings import WordTiming


def _fmt_ass_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass_captions(
    chunks: list[list[WordTiming]],
    out_ass: Path,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    hook_text: str = "",
) -> Path:
    """Write ASS subtitles with word highlighting inside vertical safe zones (bottom 20% clear)."""
    # Bottom 20% of 1920 = 384px -> MarginV=420 keeps captions safely above Reels/Shorts UI
    margin_v = int(play_res_y * 0.22) if play_res_y > play_res_x else int(play_res_y * 0.08)
    font_size = 66 if play_res_y > play_res_x else 54
    hook_margin_v = int(play_res_y * 0.14)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,DejaVu Sans,{font_size},&H0000E5FF,&H00FFFFFF,&H00101010,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,80,80,{margin_v},1\n"
        f"Style: Hook,DejaVu Sans,{font_size + 10},&H0000E6FF,&H00FFFFFF,&H00101010,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,5,2,8,80,80,{hook_margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    if hook_text:
        words = " ".join(hook_text.strip().split()[:6]).upper()
        events.append(f"Dialogue: 1,{_fmt_ass_time(0.15)},{_fmt_ass_time(2.35)},Hook,,0,0,0,,{words}")

    for group in chunks:
        if not group:
            continue
        # Emit 4-word rolling lines so captions are huge and easy to read on mobile
        for i in range(0, len(group), 4):
            sub = group[i : i + 4]
            t0 = sub[0].start
            t1 = max(t0 + 0.3, sub[-1].end)
            parts = []
            for wt in sub:
                cs = max(8, int(round((wt.end - wt.start) * 100)))
                parts.append(f"{{\\k{cs}}}{wt.word}")
            events.append(f"Dialogue: 0,{_fmt_ass_time(t0)},{_fmt_ass_time(t1)},Default,,0,0,0,,{' '.join(parts)}")

    out_ass.parent.mkdir(parents=True, exist_ok=True)
    out_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_ass
