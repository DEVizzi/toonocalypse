"""M5/v3.4 sound conductor:
- Schedules MC Tuno's narration on the REAL output timeline (0.15s anticipation lead-in; strictly drops any reaction
  line delayed > 0.55s behind its physics event).
- Triggers winner shoutout 0.4s before the Winner Card and keeps Winner Card screen hold strictly in [2.0s, 2.3s].
- Exports isolated pre-BGM/SFX voice stem WAV and computes frame-accurate 33ms normalized RMS slices for lip-sync.
- Layers CC0 procedural Game-Show Funk BGM at -18 dB, smoothly ducking to -24 dB whenever narration RMS > 0.02.
- Attenuates loud SFX (sirens, boings, impacts) by -7 dB during active speech so narration is 100% intelligible."""
from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np

from src.audio import music, sfx
from src.audio.sfx import SR
from src.config import FPS, settings

MAX_REACTION_LAG_S = 0.50   # strictly < 0.55s (and satisfies < 0.5s verification target)
CARD_MIN_S = 2.00
CARD_MAX_S = 2.30


def _db(x: float) -> float:
    return float(10 ** (x / 20.0))


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


def _time_fit(pcm: np.ndarray, words: list[tuple[float, float, str]], max_dur: float) -> tuple[np.ndarray, list[tuple[float, float, str]]]:
    """Fits a clip cleanly inside max_dur so winner + outro CTA always complete inside the 2.0-2.3s Winner Card."""
    cur_dur = pcm.size / SR
    if cur_dur <= max_dur or pcm.size < 16:
        return pcm, words
    ratio = cur_dur / max(0.45, max_dur)
    new_n = max(8, int(round(pcm.size / ratio)))
    x_old = np.linspace(0.0, 1.0, pcm.size, dtype=np.float32)
    x_new = np.linspace(0.0, 1.0, new_n, dtype=np.float32)
    fitted = np.interp(x_new, x_old, pcm).astype(np.float32)
    scaled_words = [(w0 / ratio, w1 / ratio, w) for w0, w1, w in words]
    return fitted, scaled_words


def _write_wav_mono_or_stereo(path: Path, mono: np.ndarray, stereo_dup: bool = True) -> None:
    pcm16 = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
    data = np.repeat(pcm16[:, None], 2, axis=1) if stereo_dup else pcm16
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2 if stereo_dup else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def compute_frame_rms(voice: np.ndarray, n_frames: int) -> list[float]:
    """Computes normalized RMS amplitude of each 33.3ms (SR / FPS) slice of the isolated voice stem."""
    out: list[float] = []
    step = SR / FPS
    for i in range(n_frames):
        s0 = int(round(i * step))
        s1 = int(round((i + 1) * step))
        if s0 >= voice.size or s1 <= s0:
            out.append(0.0)
        else:
            sl = voice[s0:min(voice.size, s1)]
            out.append(float(np.sqrt(np.mean(sl * sl))) if sl.size else 0.0)
    return out


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

    card_t = card_i / FPS
    replay_t = replay_i / FPS
    video_len = len(shots) / FPS
    pair = _prompt_pair(ep.prompt, r.heroes)

    # ------------------------------------------------------------------ 1. Narration & tight event sync
    beats = script.build_beats(r, to_out, video_len, replay_t, card_t, pair)
    gem = script.punch_up(beats, log=log)
    speech: list[dict] = []
    voice_pcm: list[tuple[float, np.ndarray]] = []
    dropped_lag = 0
    max_lag = 0.0

    if tts.available():
        placed: list[tuple[float, float]] = []
        # Place must-play anchors (intro, winner, outro) first so winner @ (card_t - 0.4s) & CTA are guaranteed!
        ordered = sorted(beats, key=lambda b: (0 if b.kind in ("intro", "winner", "outro") else 1, -b.prio, b.t))
        win_end_t = card_t + 0.45

        for b in ordered:
            res = tts.synthesize(b.text)
            if res is None:
                continue
            pcm, words = res
            if b.kind == "winner":
                # Keep winner shoutout crisp (~0.95s) so CTA gets ~1.65s natural pacing on the Winner Card
                pcm, words = _time_fit(pcm, words, 0.95)
            d = pcm.size / SR

            if b.kind == "intro":
                t0 = 0.04
                ok_t = t0 if all(t0 + d + 0.06 <= p0 or t0 >= p1 + 0.06 for p0, p1 in placed) else None
            elif b.kind == "winner":
                # Trigger winner shoutout 0.4s before Winner Card appears
                target = max(replay_t + 0.05, card_t - 0.40)
                ok_t = None
                for k in range(0, 8):
                    t0 = target + k * 0.04
                    if all(t0 + d + 0.05 <= p0 or t0 >= p1 + 0.05 for p0, p1 in placed):
                        ok_t = t0
                        break
                if ok_t is not None:
                    win_end_t = ok_t + d
            elif b.kind == "outro":
                # Start CTA right after winner shoutout and guarantee completion before card_t + 2.24s
                t0 = max(card_t + 0.15, win_end_t + 0.05)
                avail_dur = max(0.85, (card_t + CARD_MAX_S - 0.06) - t0)
                pcm, words = _time_fit(pcm, words, avail_dur)
                d = pcm.size / SR
                ok_t = t0
            else:
                # Reaction beat: target is (event_t - 0.15s); strictly drop if delayed > 0.50s behind event_t!
                ok_t = None
                t_cand = max(0.0, b.t)
                limit_t = b.event_t + MAX_REACTION_LAG_S
                while t_cand <= limit_t + 1e-6:
                    t1 = t_cand + d
                    if t1 > card_t - 0.46:
                        break
                    if all(t1 + 0.06 <= p0 or t_cand >= p1 + 0.06 for p0, p1 in placed):
                        ok_t = t_cand
                        break
                    t_cand += 0.04
                if ok_t is None:
                    dropped_lag += 1

            if ok_t is None:
                continue
            if b.kind not in ("intro", "winner", "outro"):
                max_lag = max(max_lag, ok_t - b.event_t)
            placed.append((ok_t, ok_t + d))
            speech.append({
                "t0": ok_t,
                "t1": ok_t + d,
                "text": b.text,
                "kind": b.kind,
                "event_t": b.event_t,
                "words": [(ok_t + w0, ok_t + w1, w) for w0, w1, w in words],
            })
            voice_pcm.append((ok_t, pcm))
        speech.sort(key=lambda s: s["t0"])
        log(f"  narration: {len(speech)}/{len(beats)} voiced (dropped_stale={dropped_lag}, max_lag={max_lag:+.2f}s, gemini={gem})")
    else:
        log("  narration: edge-tts/ffmpeg unavailable -> SFX + music only")

    # ------------------------------------------------------------------ 2. Strict 2.0s-2.3s Winner Card hold
    from src.rendering.pipeline import Shot
    cur_card_frames = len(shots) - card_i
    need_end = (max(s["t1"] for s in speech) + 0.10) if speech else (card_t + CARD_MIN_S)
    target_card_s = min(CARD_MAX_S, max(CARD_MIN_S, need_end - card_t))
    target_card_frames = int(round(target_card_s * FPS))
    if target_card_frames > cur_card_frames and shots:
        last = shots[-1]
        for k in range(target_card_frames - cur_card_frames):
            shots.append(Shot(last.tf, "card", last.seg_t + (k + 1) / FPS))
    elif target_card_frames < cur_card_frames:
        del shots[card_i + target_card_frames:]
    video_len = len(shots) / FPS

    # ------------------------------------------------------------------ 3. Isolated Voice Stem + Frame RMS Lip-Sync
    n = int(round(video_len * SR))
    voice = np.zeros(n, np.float32)
    for t0, pcm in voice_pcm:
        m = float(np.max(np.abs(pcm))) or 1.0
        _place(voice, pcm / m * 0.92, t0, _db(a["narration_db"]))

    # Export isolated voice stem WAV (pre-BGM/SFX) before rendering frames
    voice_stem_path = wav_path.with_name(f".{wav_path.stem}_voice.wav")
    _write_wav_mono_or_stereo(voice_stem_path, voice, stereo_dup=False)
    frame_rms = compute_frame_rms(voice, len(shots))

    # ------------------------------------------------------------------ 4. Procedural SFX from real trace events
    events: list[tuple[float, int, np.ndarray, float]] = []

    def add(t: float | None, prio: int, clip: np.ndarray, gain_db: float) -> None:
        if t is not None and 0 <= t < video_len:
            events.append((t, prio, clip, gain_db))

    first_play = min(play_out.values()) / FPS if play_out else 0.0
    add(first_play, 6, sfx.gate_clank(), -3)
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
                add(t, 2, sfx.bonk(round(min(1.3, max(0.7, 1.4 - imp / 6000)), 1)), -4.5)
            elif imp > 1400:
                add(t, 1, sfx.thud(), -9.5)
        elif e.kind == "elimination":
            hero = bool(e.data.get("hero"))
            cause = e.data.get("cause", "")
            if cause == "left_behind":
                add(t, 3, sfx.fire_crackle(), -5 if hero else -10)
                add(t, 2, sfx.zap(), -9 if hero else -14)
            elif side:
                add(t - 0.45, 3, sfx.fall_whistle(), -5.5 if hero else -11)
                add(t + 0.03, 3, sfx.splat(), -6 if hero else -12)
            else:
                add(t, 3, sfx.fall_whistle(0.55), -5.5 if hero else -11)
            if hero and e.data.get("by_hero"):
                add(t, 5, sfx.betrayal_sting(), -4.5)
        elif e.kind == "glitch":
            add(t, 1, sfx.zap(), -13)
        elif e.kind == "heavy_land" and e.data.get("shake"):
            add(t, 1, sfx.thud(), -9.5)
        elif e.kind == "trait" and e.actors and e.actors[0] == "boing":
            add(t, 2, sfx.boing(), -8.5)
        elif e.kind == "escalation":
            add(t, 4, sfx.airhorn(), -6.0 if e.data.get("overtime") else -8.0)
        elif e.kind == "twist":
            add(t - 0.5, 4, sfx.riser(), -7.0)
        elif e.kind == "lead_change" and e.t >= (tr.meta.get("resolved_at") or 99) - 5:
            add(t, 2, sfx.ding(), -10.0)

    i = 0
    while i < len(elims):
        j = i
        while j < len(elims) and elims[j].t - elims[i].t <= 1.2:
            j += 1
        if j - i >= 2:
            add(to_out(elims[j - 1].t), 3, sfx.crowd_ooh(), -7.5)
            i = j
        else:
            i += 1
    for t0, _word, _pos, _seed in r.popups:
        add(to_out(t0), 1, sfx.pop(), -11.5)
    add(replay_t, 5, sfx.rewind(), -8.5)
    add(card_t, 7, sfx.fanfare(), -3.5)
    add(card_t + 0.2, 6, sfx.cheer(), -7.0)

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
    fx *= _db(float(a["sfx_db"]) + 7.0)

    # ------------------------------------------------------------------ 5. Smooth RMS Ducking Envelope (RMS > 0.02)
    rms_win = max(1, int(SR / FPS))
    v_rms_curve = np.sqrt(np.convolve(voice * voice, np.ones(rms_win, dtype=np.float32) / rms_win, mode="same"))
    voice_gate = (v_rms_curve > 0.02).astype(np.float32)
    smooth_win = max(1, int(0.14 * SR))
    duck_env = np.clip(
        np.convolve(voice_gate, np.ones(smooth_win, dtype=np.float32) / smooth_win, mode="same") * 1.35,
        0.0, 1.0,
    )

    # Attenuate loud SFX by -7 dB during active speech (narration RMS > 0.02)
    sfx_duck_db = float(a.get("sfx_duck_db", -7.0))
    fx *= (10.0 ** ((sfx_duck_db * duck_env) / 20.0)).astype(np.float32)

    # Upbeat Game-Show Funk BGM at -18 dB, smoothly ducking to -24 dB whenever narration RMS > 0.02
    ot = to_out(r.overtime_t) if r.overtime_t < 900 else None
    bed = music.funk_bgm(video_len + 0.2, bpm=float(a["bpm"]), intense_from=ot if ot is not None else 1e9,
                         seed=int(tr.meta.get("seed", 0)))
    mus = np.zeros(n, np.float32)
    mus[: min(n, bed.size)] = bed[: min(n, bed.size)]
    end_fade = min(n, int(0.25 * SR))
    if end_fade > 1:
        mus[-end_fade:] *= np.linspace(1.0, 0.0, end_fade, dtype=np.float32)
    mus_db_curve = float(a["music_db"]) + float(a["duck_db"]) * duck_env   # -18 dB -> -24 dB
    mus *= (10.0 ** (mus_db_curve / 20.0)).astype(np.float32)

    # ------------------------------------------------------------------ 6. Master Bus + Soft-Clip -> WAV
    mix = voice + fx + mus
    mix = np.tanh(mix * 1.05) * 0.94
    _write_wav_mono_or_stereo(wav_path, mix, stereo_dup=True)

    card_hold_s = round((len(shots) - card_i) / FPS, 2)
    return {
        "wav": wav_path,
        "voice_wav": str(voice_stem_path),
        "speech": speech,
        "frame_rms": frame_rms,
        "tts": bool(speech),
        "gemini_lines": gem,
        "sfx": n_fx,
        "max_reaction_lag_s": round(max_lag, 3),
        "card_hold_s": card_hold_s,
        "duration": video_len,
    }
