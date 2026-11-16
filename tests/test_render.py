import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from src.audio.tts import SR, Speech
from src.render import layout, timeline

W, H = 1080, 1920


def test_zones_respect_safe_margins():
    z = layout.zones(W, H)
    assert z["usable"].y0 == 192 and z["usable"].y1 == 1536  # top 10% / bottom 20% clear
    assert z["sfx"].x0 >= int(W * 0.06) and z["sfx"].x1 <= W - int(W * 0.06)
    assert not z["bubbles"].overlaps(z["captions"])


def test_bubble_near_speaker_and_no_collisions():
    left = layout.bubble_box(W, H, 400, 120, "left")
    right = layout.bubble_box(W, H, 400, 120, "right")
    assert left.x0 < right.x0
    cap = layout.caption_box(W, H, 700, 90)
    assert layout.check_layout(W, H, {"bubbles": [left], "captions": [cap]}) == []
    bad = layout.Box(10, 10, 300, 100)
    assert any("outside" in e for e in layout.check_layout(W, H, {"bubbles": [bad]}))
    assert any("overlaps" in e for e in layout.check_layout(W, H, {"bubbles": [cap], "captions": [cap]}))


def fake_tts(text, voice, speed):
    words = text.split()
    dur = 0.32 * len(words) / speed
    t = np.arange(int(dur * SR)) / SR
    audio = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    return Speech(audio, [{"word": w, "start": i * 0.32 / speed, "end": (i + 1) * 0.32 / speed} for i, w in enumerate(words)])


STORY = {"cast": [{"name": "Jin"}, {"name": "Madam Wong"}]}


def part(n, final=False):
    panels = [{"id": i, "duration": 6, "sfx": "THUD" if i == 3 else "", "narration": "The city sleeps." if i == 2 else "",
               "characters": [{"name": "Jin", "position": "left"}],
               "dialogue": [{"speaker": "Jin", "line": "Whose gold is this?"}]} for i in range(1, 9)]
    p = {"part": n, "hook_text": "Gold. In my rickshaw.", "panels": panels, "previously": "Jin found gold." if n > 1 else None}
    if final:
        p["moral_card"] = "Honesty is the richest fare."
    return p


VOICES = {"Jin": "am_adam", "Madam Wong": "af_heart", "Narrator": "bm_george"}


def test_timeline_hook_first_and_window():
    tl = timeline.build(part(1), STORY, VOICES, fake_tts)
    first = tl.panels[0].lines[0]
    assert first.text == "Gold. In my rickshaw." and first.start < 2.0
    assert 45 <= tl.duration <= 60


def test_final_part_has_moral_and_loop():
    tl = timeline.build(part(3, final=True), STORY, VOICES, fake_tts, final=True)
    assert tl.moral and tl.moral_start is not None and tl.loop_tail > 0


def test_stretch_to_minimum():
    p = part(1)
    for x in p["panels"]:
        x["duration"] = 3
    tl = timeline.build(p, STORY, VOICES, fake_tts)
    assert tl.duration >= 45


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_end_to_end_small_render(tmp_path):
    from src.render import video

    tl = timeline.build(part(3, final=True), STORY, VOICES, fake_tts, final=True)
    colors = ["#335", "#553", "#535", "#355", "#533", "#353", "#444", "#246"]
    imgs = {str(i): Image.new("RGB", (270, 480), colors[i - 1]) for i in range(1, 9)}
    for i, im in imgs.items():  # add texture so freezedetect sees motion under Ken Burns
        arr = np.array(im)
        arr[::8, :, :] = 255
        imgs[i] = Image.fromarray(arr)
    out = video.encode(tl, imgs, "mystery", tmp_path / "t.mp4", w=270, h=480)
    errs = video.render_qa(out, expect_w=270, expect_h=480)
    assert errs == [], errs
