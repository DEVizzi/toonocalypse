"""Vertical 9:16 (1080x1920) motion-comic renderer for YouTube Shorts & Instagram Reels."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from src.audio.mixer import concat_wavs, mix_with_bgm
from src.audio.timings import WordTiming, compute_word_timings, wav_duration
from src.audio.tts import synthesize_line
from src.common.config import display_name, load_all_characters, load_models, load_playbook, load_settings
from src.panels.bubbles import draw_speech_bubble
from src.panels.effects import add_impact_effects
from src.render.captions import build_ass_captions
from src.render.motion import render_panel_clip


def render_episode_formats(
    script: dict[str, Any],
    panel_paths: list[Path],
    work_dir: Path,
) -> dict[str, Path]:
    """Render clean YouTube Shorts (9:16), Instagram Reels (9:16), and Wide (16:9) MP4s."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to render episode videos")

    chars = load_all_characters()
    settings = load_settings()
    narrator_cfg = load_models().get("tts", {}).get("narrator", {})
    hard_cap = float(load_playbook().get("durations", {}).get("hard_cap_sec", 59))

    work_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = work_dir / "audio"
    v_dir = work_dir / "v_clips"
    w_dir = work_dir / "w_clips"
    annot_dir = work_dir / "annotated"
    annot_dir.mkdir(exist_ok=True)

    all_wavs: list[Path] = []
    word_chunks: list[list[WordTiming]] = []
    panel_durations: list[float] = []
    annotated_panels: list[Path] = []
    t_cursor = 0.0

    for idx, (panel_data, p_path) in enumerate(zip(script["panels"][:6], panel_paths[:6]), start=1):
        img = Image.open(p_path).convert("RGB")
        if panel_data.get("impact"):
            img = add_impact_effects(img, panel_data.get("sfx") or "POW!")

        spoken_parts: list[tuple[str, dict[str, Any], bool]] = []
        if panel_data.get("narrator"):
            spoken_parts.append((panel_data["narrator"], narrator_cfg, True))
        for d in panel_data.get("dialogue", []):
            sp = d.get("speaker", "")
            line = d.get("line", "")
            if line:
                vc = chars[sp]["voice"] if sp in chars else narrator_cfg
                spoken_parts.append((line, vc, False))
                img = draw_speech_bubble(img, display_name(sp, settings), line, position="top" if idx % 2 else "bottom")

        ap = annot_dir / f"panel_{idx}.png"
        img.save(ap)
        annotated_panels.append(ap)

        p_dur = 0.0
        p_timings: list[WordTiming] = []
        for li, (line_txt, vc, is_narr) in enumerate(spoken_parts):
            wav_p = audio_dir / f"p{idx}_l{li}.wav"
            synthesize_line(line_txt, vc, wav_p, is_narrator=is_narr)
            d_sec = wav_duration(wav_p)
            p_timings.extend(compute_word_timings(line_txt, d_sec, offset=t_cursor))
            t_cursor += d_sec + 0.18
            p_dur += d_sec + 0.18
            all_wavs.append(wav_p)

        panel_durations.append(max(2.2, p_dur))
        word_chunks.append(p_timings)

    # Enforce hard cap <= 59s
    total_dur = sum(panel_durations)
    if total_dur > hard_cap - 1.5:
        scale = (hard_cap - 1.5) / total_dur
        panel_durations = [max(1.5, d * scale) for d in panel_durations]
        total_dur = sum(panel_durations)

    voice_wav = concat_wavs(all_wavs, work_dir / "voice_all.wav", gap_sec=0.18)
    mixed_audio = mix_with_bgm(voice_wav, work_dir / "audio_mixed.m4a", duration_sec=total_dur)

    # Render vertical 9:16 clips + 0.8s loop-tail matching panel 1 for seamless loop (§10.F)
    v_clips: list[Path] = []
    w_clips: list[Path] = []
    for idx, (pdata, ap, dur) in enumerate(zip(script["panels"][:6], annotated_panels, panel_durations), start=1):
        vc = v_dir / f"v_{idx}.mp4"
        wc = w_dir / f"w_{idx}.mp4"
        render_panel_clip(ap, vc, dur, 1080, 1920, camera=pdata.get("camera", "zoom_in"), impact=bool(pdata.get("impact")))
        render_panel_clip(ap, wc, dur, 1920, 1080, camera=pdata.get("camera", "zoom_in"), impact=bool(pdata.get("impact")))
        v_clips.append(vc)
        w_clips.append(wc)

    # Loop-tail clip matching opening panel (0.6s)
    loop_vc = v_dir / "v_loop.mp4"
    render_panel_clip(annotated_panels[0], loop_vc, 0.6, 1080, 1920, camera="static_loop")
    v_clips.append(loop_vc)

    v_list = work_dir / "v_concat.txt"
    v_list.write_text("".join(f"file '{c.resolve()}'\n" for c in v_clips), encoding="utf-8")
    v_raw = work_dir / "vertical_raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(v_list), "-c", "copy", str(v_raw)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ass_path = build_ass_captions(word_chunks, work_dir / "captions.ass", 1080, 1920, hook_text=script.get("on_screen_hook", ""))

    yt_out = work_dir / "youtube_short.mp4"
    ig_out = work_dir / "instagram_reel.mp4"
    subprocess.run(
        [
            ffmpeg, "-y",
            "-i", str(v_raw), "-i", str(mixed_audio),
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest", "-movflags", "+faststart",
            str(yt_out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ig_out.write_bytes(yt_out.read_bytes())

    # Wide 16:9 uniform encoding for stream-copy compilation
    w_list = work_dir / "w_concat.txt"
    w_list.write_text("".join(f"file '{c.resolve()}'\n" for c in w_clips), encoding="utf-8")
    w_raw = work_dir / "wide_raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(w_list), "-c", "copy", str(w_raw)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    wide_out = work_dir / "wide_16x9.mp4"
    subprocess.run(
        [
            ffmpeg, "-y",
            "-i", str(w_raw), "-i", str(mixed_audio),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest", "-movflags", "+faststart",
            str(wide_out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return {"youtube": yt_out, "instagram": ig_out, "wide": wide_out}
