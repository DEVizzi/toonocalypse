"""Encode a part (frames piped to ffmpeg + mixed audio) and run render QA (§9)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from PIL import Image

from src.audio import mix as audio
from src.common.config import settings
from src.render import frames as fr
from src.render.timeline import Timeline, speech_track


def encode(tl: Timeline, images: dict[str, Image.Image], mood: str, out: Path, w: int | None = None, h: int | None = None) -> Path:
    v = settings()["video"]
    w, h, fps = w or v["width"], h or v["height"], v["fps"]
    imgs = {k: im.convert("RGB").resize((w, h), Image.LANCZOS) if im.size != (w, h) else im.convert("RGB") for k, im in images.items()}
    work = out.parent
    sfx_events = [(ev.start, "impact" if ev.action else "whoosh") for ev in tl.panels if ev.index > 0 and ev.action]
    if tl.moral_start is not None:
        sfx_events.append((tl.moral_start, "chime"))
    mixed = audio.mix(speech_track(tl, audio.SR), mood, tl.duration, sfx_events)
    raw_wav = audio.write_wav(work / f"{out.stem}_mix.wav", mixed)
    norm_wav = audio.loudnorm(raw_wav, work / f"{out.stem}_norm.wav")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-i", str(norm_wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for frame in fr.frames(tl, imgs, w, h, fps):
        proc.stdin.write(frame)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    return out


def probe(path: Path) -> dict:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def render_qa(path: Path, expect_w: int | None = None, expect_h: int | None = None) -> list[str]:
    s = settings()
    v, lim = s["video"], s["story"]["part_seconds"]
    errs = []
    info = probe(path)
    vs = [x for x in info["streams"] if x["codec_type"] == "video"]
    aus = [x for x in info["streams"] if x["codec_type"] == "audio"]
    dur = float(info["format"]["duration"])
    if not vs:
        return ["no video stream"]
    if (vs[0]["width"], vs[0]["height"]) != (expect_w or v["width"], expect_h or v["height"]):
        errs.append(f"resolution {vs[0]['width']}x{vs[0]['height']}")
    num, den = map(int, vs[0]["r_frame_rate"].split("/"))
    if round(num / den) != v["fps"]:
        errs.append(f"fps {num}/{den}")
    if not lim["min"] - 0.5 <= dur <= lim["hard_cap"] + 0.05:
        errs.append(f"duration {dur:.2f}s outside {lim['min']}-{lim['hard_cap']}s")
    if not aus:
        errs.append("no audio stream")
    else:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
        m = re.findall(r"I:\s+(-?\d+\.\d)\s+LUFS", r.stderr)
        if m and abs(float(m[-1]) - v["loudness_lufs"]) > 1.5:
            errs.append(f"loudness {m[-1]} LUFS")
    d = v["max_black_or_frozen_seconds"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"blackdetect=d={d}:pix_th=0.05,freezedetect=n=0.001:d={d}",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    if "black_start" in r.stderr:
        errs.append(f"black segment > {d}s")
    if "freeze_start" in r.stderr:
        errs.append(f"frozen segment > {d}s")
    return errs
