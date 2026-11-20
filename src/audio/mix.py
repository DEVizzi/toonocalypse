"""M5 sound conductor: schedules MC Tuno's narration, procedural SFX and the chiptune bed on the REAL output timeline
(cold open + gameplay incl. hitstops + replay + card), ducks the music under the voice, soft-limits and writes a WAV.
Final loudness (-14 LUFS, -1.5 dBTP) is applied by ffmpeg's loudnorm at encode time.

Returns {"wav", "speech": [{t0, t1, text, words:[(t0, t1, word)]}], "tts", "gemini_lines", "sfx"} and may append
winner-card frames to ep.shots so the outro line is never cut off."""
from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np

from src.audio import music, sfx
from src.audio.sfx import SR
from src.config import FPS, settings


def _db(x: float) -> float:
    return float(10 ** (x / 20))


def _place(buf: np.ndarray, clip: np.ndarray, t: float, gain: float) -> None:
    i0 = int(t * SR)
    if i0 >= buf.size or clip.size == 0:
        return
    if i0 < 0:
        clip = clip[-i0:]
        i0 = 0
    n = min(clip.size, buf.size - i0)
    buf[i0:i0 + n] += clip[:n] * gain


def _prompt_pair(prompt: str, heroes: list) -> tuple[str, str]:
    m = re.match(r"^\s*(.+?) or (.+?) tomorrow", prompt or "")
    if m:
        return m.group(1), m.group(2)
    names = [h.name for h in heroes] or ["Bonk", "Pip"]
    return names[0], names[min(1, len(names) - 1)]


def build_soundtrack(r, ep, wav_path: Path, log=print) -> dict:
    from src.narration import script, tts

    a = settings()["audio"]
    shots = ep.shots
    pre = r.pre
    play_out: dict[int, int] = {}
    for i, s in enumerate(shots):
        if s.segment == "play":
            play_out.setdefault(int(round(s.tf)), i)
    replay_i = next((i for i, s in enumerate(shots) if s.segment == "replay"), len(shots))
    card_i = next((i for i, s in enumerate(shots) if s.segment == "card"), len(shots))

    def to_out(t: float) -> float | None:
        f = pre + int(round(t * FPS))
        for d in (0, 1, -1, 2, -2, 3, -3):
            if f + d in play_out:
                return play_out[f + d] / FPS
        return None

    video_len = len(shots) / FPS
    pair = _prompt_pair(ep.prompt, r.heroes)

    # ------------------------------------------------------------------ narration
    beats = script.build_beats(r, to_out, video_len, replay_i / FPS, card_i / FPS, pair)
    gem = script.punch_up(beats, log=log)
    speech: list[dict] = []
    voice_pcm: list[tuple[float, np.ndarray]] = []
    use_tts = tts.available()
    if use_tts:
        placed: list[tuple[float, float]] = []
        for b in sorted(beats, key=lambda b: (-b.prio, b.t)):
            res = tts.synthesize(b.text)
            if res is None:
                continue
            pcm, words = res
            d = pcm.size / SR
            slack = 1.8 if b.prio >= 9 else 0.9
            ok_t = None
            for k in range(0, int(slack / 0.1) + 1):
                t0 = max(0.0, b.t + k * 0.1)
                t1 = t0 + d
                if b.kind not in ("outro", "winner") and t1 > card_i / FPS + 0.2:
                    break
                if all(t1 + 0.12 <= p0 or t0 >= p1 + 0.12 for p0, p1 in placed):
                    ok_t = t0
                    break
            if ok_t is None:
                continue
            placed.append((ok_t, ok_t + d))
            speech.append({"t0": ok_t, "t1": ok_t + d, "text": b.text, "kind": b.kind,
                           "words": [(ok_t + w0, ok_t + w1, w) for w0, w1, w in words]})
            voice_pcm.append((ok_t, pcm))
        speech.sort(key=lambda s: s["t0"])
        log(f"  narration: {len(speech)}/{len(beats)} lines voiced (gemini {gem})")
    else:
        log("  narration: edge-tts/ffmpeg unavailable -> SFX + music only")

    # extend the winner card so the outro is never cut off
    if speech:
        from src.rendering.pipeline import Shot
        need = max(s["t1"] for s in speech) + 0.45
        last = shots[-1]
        extra = int(np.ceil((need - video_len) * FPS))
        for k in range(max(0, extra)):
            shots.append(Shot(last.tf, "card", last.seg_t + (k + 1) / FPS))
        video_len = len(shots) / FPS

    n = int(video_len * SR)
    voice = np.zeros(n, np.float32)
    for t0, pcm in voice_pcm:
        m = float(np.max(np.abs(pcm))) or 1.0
        _place(voice, pcm / m * 0.92, t0, _db(a["narration_db"]))

    # ------------------------------------------------------------------ SFX from real events
    events: list[tuple[float, int, np.ndarray, float]] = []      # (t, prio, clip, gain_db)

    def add(t: float | None, prio: int, clip: np.ndarray, gain_db: float) -> None:
        if t is not None and 0 <= t < video_len:
            events.append((t, prio, clip, gain_db))

    first_play = min(play_out.values()) / FPS if play_out else 0.0
    add(first_play, 6, sfx.gate_clank(), -2)
    tr = r.tr
    side = tr.mode == "SIDE_VIEW"
    elims = sorted((e for e in tr.events if e.kind == "elimination"), key=lambda e: e.t)
    for e in tr.events:
        t = to_out(e.t)
        if t is None:
            continue
        if e.kind == "impact":
            imp = e.data.get("impulse", 0)
            if e.data.get("hero_pair") and imp > 900:
                add(t, 2, sfx.bonk(round(min(1.3, max(0.7, 1.4 - imp / 6000)), 1)), -4)
            elif imp > 1400:
                add(t, 1, sfx.thud(), -9)
        elif e.kind == "elimination":
            hero = bool(e.data.get("hero"))
            cause = e.data.get("cause", "")
            if cause == "left_behind":
                add(t, 3, sfx.fire_crackle(), -5 if hero else -10)
                add(t, 2, sfx.zap(), -9 if hero else -14)
            elif side:
                add(t - 0.5, 3, sfx.fall_whistle(), -5 if hero else -11)
                add(t + 0.03, 3, sfx.splat(), -6 if hero else -12)
            else:
                add(t, 3, sfx.fall_whistle(0.55), -5 if hero else -11)
            if hero and e.data.get("by_hero"):
                add(t, 5, sfx.betrayal_sting(), -4)
        elif e.kind == "glitch":
            add(t, 1, sfx.zap(), -13)
        elif e.kind == "heavy_land" and e.data.get("shake"):
            add(t, 1, sfx.thud(), -9)
        elif e.kind == "trait" and e.actors and e.actors[0] == "boing":
            add(t, 2, sfx.boing(), -7)
        elif e.kind == "escalation":
            add(t, 4, sfx.airhorn(), -3 if e.data.get("overtime") else -6)
        elif e.kind == "twist":
            add(t - 0.6, 4, sfx.riser(), -6)
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5:
            add(t, 2, sfx.ding(), -10)
    i = 0
    while i < len(elims):                                    # crowd "ooh" on wipeouts
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.2:
            j += 1
        if j - i >= 2:
            add(to_out(elims[j - 1].t), 3, sfx.crowd_ooh(), -7)
            i = j
        else:
            i += 1
    for t0, _word, _pos, _seed in r.popups:
        add(to_out(t0), 1, sfx.pop(), -11)
    add(replay_i / FPS, 5, sfx.rewind(), -8)
    add(card_i / FPS, 7, sfx.fanfare(), -2)
    add(card_i / FPS + 0.2, 6, sfx.cheer(), -6)
    # cap simultaneous clutter: <= sfx_cap_per_s in any 1 s window, higher priority first
    cap = int(a["sfx_cap_per_s"])
    kept: list[float] = []
    fx = np.zeros(n, np.float32)
    n_fx = 0
    for t, prio, clip, gdb in sorted(events, key=lambda e: (-e[1], e[0])):
        if sum(1 for k in kept if t - 1.0 < k <= t) >= cap and prio < 5:
            continue
        kept.append(t)
        _place(fx, clip, t, _db(gdb))
        n_fx += 1
    fx *= _db(a["sfx_db"] + 7)          # sfx_db is relative to the voice; individual gains above are fine-tuned

    # ------------------------------------------------------------------ music bed with ducking
    ot = to_out(r.overtime_t) if r.overtime_t < 900 else None
    card_t = card_i / FPS
    bed = music.chiptune(card_t + 0.4, bpm=float(a["bpm"]), intense_from=ot if ot is not None else 1e9,
                         seed=int(tr.meta.get("seed", 0)))
    mus = np.zeros(n, np.float32)
    mus[: min(n, bed.size)] = bed[: min(n, bed.size)]
    fade_i0, fade_n = int(card_t * SR), int(0.35 * SR)
    if fade_i0 < n:
        seg = mus[fade_i0:fade_i0 + fade_n]
        mus[fade_i0:fade_i0 + seg.size] = seg * np.linspace(1, 0, seg.size, dtype=np.float32)
        mus[fade_i0 + fade_n:] = 0
    duck = np.zeros(n, np.float32)
    for s in speech:
        duck[int(s["t0"] * SR):int(s["t1"] * SR)] = 1.0
    k = int(0.18 * SR)
    duck = np.clip(np.convolve(duck, np.ones(k, np.float32) / k, mode="same") * 1.6, 0, 1)
    mus *= _db(a["music_db"]) * (1.0 - (1.0 - _db(a["duck_db"])) * duck)

    mix = (voice + fx + mus) * 0.6
    mix = np.tanh(mix * 1.2) * 0.95                             # gentle soft-clip (< 0 dBFS); loudnorm sets level
    pcm16 = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(pcm16[:, None], 2, axis=1)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    return {"wav": wav_path, "speech": speech, "tts": bool(speech), "gemini_lines": gem, "sfx": n_fx,
            "duration": video_len}
