"""Tuno Report clip worker: re-simulates ONE race inside a given code tree and renders its highlight clip.

Run as a standalone script (never imported by the recap process) so the race can be replayed with the EXACT code
version that produced it (a `git archive` tree from `src/recap/timemachine.py`) or with the current tree:

    python src/recap/clip_worker.py --root <tree> --job <job.json>

Job JSON: {"record": {...replay record...}, "label": "S1 R3/30 • CRUSHER GAUNTLET", "out_dir": "...", "tag": "s1_r03",
           "width": 608, "height": 1080, "freeze": {"victim": "pip", "t": 4.2} | null}
Writes `<tag>_clip.mp4` (+ `<tag>_freeze.mp4`) and `<tag>.json` (verification, per-frame timeline, events).
Only JSON is read or written (no pickle). Renders only after the re-simulated ranking matches the published one.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

FPS = 30
DEFAULT_W, DEFAULT_H = 1080, 810
MIN_CLIP_FRAMES = int(37.0 * FPS)
MAX_CLIP_FRAMES = int(41.0 * FPS)
REACTION_S = 0.20


def _json_safe(v):
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    if isinstance(v, float):
        return round(v, 3) if math.isfinite(v) else None
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v][:8]
    return str(v)[:40]


def _event_dict(e) -> dict:
    keep = ("cause", "hero", "by_hero", "impulse", "hero_pair", "name", "banner", "overtime", "twist", "how")
    return {"t": round(float(e.t), 3), "kind": str(e.kind), "actors": [str(a) for a in (e.actors or [])][:3],
            "data": {k: _json_safe(e.data.get(k)) for k in keep if k in (e.data or {})}}


def _event_rank(e) -> float:
    if e.kind == "elimination" and e.data.get("hero"):
        return 4.5 + (1.5 if e.data.get("by_hero") else 0.0)
    if e.kind == "crush_hit":
        return 3.2
    if e.kind == "twist" or (e.kind == "escalation" and e.data.get("overtime")):
        return 2.6
    if e.kind == "trait":
        return 2.0
    if e.kind == "impact" and e.data.get("hero_pair"):
        return 1.2 + min(1.2, float(e.data.get("impulse", 0)) / 3600.0)
    return 0.0


def _pick_chaos_events(trace, end_t: float, max_picks: int = 2) -> list:
    """Up to `max_picks` top action moments spaced >= 4.0s apart before the final 2.8s."""
    lim = max(2.2, end_t - 2.8)
    cands = sorted(
        (e for e in trace.events if 1.4 <= e.t <= lim and _event_rank(e) > 0),
        key=lambda e: (_event_rank(e), -e.t),
        reverse=True,
    )
    chosen = []
    for e in cands:
        if all(abs(e.t - c.t) >= 4.0 for c in chosen):
            chosen.append(e)
            if len(chosen) >= max_picks:
                break
    return sorted(chosen, key=lambda e: e.t)


def _frames_for(pre: int, t0: float, t1: float, n_frames: int) -> list[int]:
    a = max(0, pre + int(round(t0 * FPS)))
    b = min(n_frames - 1, pre + int(round(t1 * FPS)))
    return list(range(a, b + 1))


def _load_window_tracker():
    """Returns (track_window, SCREEN_CY). Prefers the replay tree's own camera; otherwise loads the CURRENT tree's
    camera module (its imports resolve against the replay tree) so archived races also get the 4:3 recap framing."""
    try:
        from src.physics import camera as cam_mod
        if hasattr(cam_mod, "track_window"):
            return cam_mod.track_window, float(cam_mod.SCREEN_CY)
    except Exception:  # noqa: BLE001
        pass
    try:
        import importlib.util
        here = Path(__file__).resolve().parents[2] / "src" / "physics" / "camera.py"
        spec = importlib.util.spec_from_file_location("recap_window_camera", here)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod.track_window, float(mod.SCREEN_CY)
    except Exception:  # noqa: BLE001 - fall back to the tree's own Shorts camera
        return None, 950.0


def _render_crop(r, shot, idx: int, w: int, h: int, Shot, pygame, scy: float = 950.0):
    """Renders a clean 4:3 widescreen world crop on current trees, or crops the 4:3 focal band on legacy pinned trees."""
    if hasattr(r, "render_world_crop"):
        return r.render_world_crop(shot, idx, w, h)
    seg = "play" if shot.segment == "chaos_slomo" else shot.segment
    legacy_shot = Shot(shot.tf, seg, shot.seg_t, shot.zoom_mult, shot.focus)
    full = r.render_shot(legacy_shot, idx)
    fw, fh = full.get_size()
    crop_h = min(fh, int(round(fw * h / max(1, w))))
    y0 = max(0, min(fh - crop_h, int(round(scy)) - crop_h // 2))
    sub = full.subsurface(pygame.Rect(0, y0, fw, crop_h))
    return pygame.transform.smoothscale(sub, (w, h)) if (fw, crop_h) != (w, h) else sub.copy()


def _build_highlight_plan(trace, pre: int, end_t: float, Shot) -> tuple[list[tuple[object, str, float]], list]:
    """Builds a 31.5-35.5s widescreen highlight sequence:
    Gate drop -> Full/Extended race with zoomed 0.4x Chaos Cam slomo beats -> Final-3 breathing zoom -> 0.3x Finish Replay."""
    n = trace.n_frames
    side_view = trace.mode == "SIDE_VIEW"
    end_f = min(n - 1, pre + int(round((end_t + REACTION_S) * FPS)))
    chaos_list = _pick_chaos_events(trace, end_t, max_picks=3)

    plan: list[tuple[object, str, float]] = []
    # 1. Opening starting-gate beat (0.8s)
    gate_f0 = max(0, pre - int(round(0.8 * FPS)))
    for f in range(gate_f0, pre):
        plan.append((Shot(float(f), "cold", (f - gate_f0) / FPS), "opening", (f - pre) / FPS))

    def _add_chaos_slomo(ev) -> None:
        focus = None          # the 4:3 recap camera already frames the knockout + attacker
        cf = min(end_f, max(pre, pre + int(round(ev.t * FPS))))
        s0 = max(float(pre), cf - 0.55 * FPS)
        s1 = min(float(end_f), cf + 0.25 * FPS)
        n_sl = int(round(2.0 * FPS))
        for k in range(n_sl):
            tf = s0 + (s1 - s0) * k / max(1, n_sl)
            plan.append((Shot(tf, "chaos_slomo", k / FPS, 1.15, focus), "chaos", (tf - pre) / FPS))

    def _append_range(t_start: float, t_stop: float, seg_name: str, slow_tail_s: float = 0.0, tail_rate: float = 0.72) -> None:
        f_start = max(pre, min(end_f, pre + int(round(t_start * FPS))))
        f_stop = max(f_start, min(end_f, pre + int(round(t_stop * FPS))))
        f_slow = max(f_start, f_stop - int(round(slow_tail_s * FPS)))
        chaos_by_f = {min(end_f, max(pre, pre + int(round(e.t * FPS)) + 6)): e for e in chaos_list}
        for f in range(f_start, f_slow):
            plan.append((Shot(float(f), "play", (f - pre) / FPS), seg_name, (f - pre) / FPS))
            if f in chaos_by_f:
                _add_chaos_slomo(chaos_by_f.pop(f))
        tf = float(f_slow)
        while tf <= float(f_stop) + 1e-6:
            fi_chk = int(round(tf))
            plan.append((Shot(tf, "play", (tf - pre) / FPS), "final" if tf >= end_f - 6 * FPS else seg_name, (tf - pre) / FPS))
            for cf_k in list(chaos_by_f.keys()):
                if fi_chk >= cf_k:
                    _add_chaos_slomo(chaos_by_f.pop(cf_k))
            tf += tail_rate

    # 2. Main race highlight body (adaptive so total clip cleanly hits ~32-35s)
    if end_t <= 26.0:
        # Play full race continuously + let Final-3 endgame breathe!
        est_play = end_t + 0.8 + 2.0 * len(chaos_list) + 3.8
        need_extra_s = max(0.0, 37.5 - est_play)
        # Pace the final 6-9s smoothly (0.58x-0.78x) to let Final-3 collisions & expressions shine
        tail_window = min(max(4.5, end_t * 0.45), 9.0)
        # Each second at rate r takes (1/r) seconds -> extra = tail_window * (1/r - 1)
        rate = tail_window / (tail_window + min(need_extra_s, tail_window * 0.72))
        rate = max(0.58, min(0.85, rate))
        _append_range(0.0, end_t + REACTION_S, "play", slow_tail_s=tail_window, tail_rate=rate)
    else:
        # Extended 3-act highlight cut for longer archival races (>26s)
        _append_range(0.0, 7.0, "opening")
        mid_c = chaos_list[0] if chaos_list else None
        m0 = max(7.2, (mid_c.t - 4.0) if mid_c else end_t * 0.42)
        m1 = min(end_t - 11.5, m0 + 7.5)
        if m1 > m0 + 1.5:
            _append_range(m0, m1, "chaos")
        _append_range(max(7.2, end_t - 11.2), end_t + REACTION_S, "final", slow_tail_s=5.5, tail_rate=0.72)

    # 3. Slow-motion Instant Replay of the decisive finish (3.8s at ~0.30x)
    rep_s = 3.8
    src_span = 1.15 * FPS
    src0 = max(float(pre), float(end_f) - src_span)
    n_rep = int(round(rep_s * FPS))
    for i in range(n_rep):
        tf = src0 + (float(end_f) - src0) * i / max(1, n_rep)
        plan.append((Shot(tf, "replay", i / FPS, 1.18, None), "replay", (tf - pre) / FPS))

    # 4. If a flash knockout finished ultra-early (<13s), add a crisp Photo-Finish Wide Angle replay so clip >= 31.5s
    if len(plan) < MIN_CLIP_FRAMES:
        rem = MIN_CLIP_FRAMES - len(plan)
        p0 = max(float(pre), float(end_f) - min(float(end_f - pre), 2.4 * FPS))
        for i in range(rem):
            tf = p0 + (float(end_f) - p0) * i / max(1, rem)
            plan.append((Shot(tf, "replay", (n_rep + i) / FPS, 1.18, None), "replay", (tf - pre) / FPS))
    elif len(plan) > MAX_CLIP_FRAMES:
        # Trim early middle play frames if slightly over cap while keeping replay intact
        keep_tail = n_rep + int(8.0 * FPS)
        excess = len(plan) - MAX_CLIP_FRAMES
        head_cut = max(int(3.0 * FPS), len(plan) - keep_tail - excess)
        plan = plan[:head_cut] + plan[head_cut + excess:]

    return plan, chaos_list


class _Encoder:
    def __init__(self, path: Path, w: int, h: int) -> None:
        self.w, self.h = w, h
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
               "-pix_fmt", "yuv420p", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.n = 0

    def write(self, surf, pygame) -> None:
        out = surf if surf.get_size() == (self.w, self.h) else pygame.transform.smoothscale(surf, (self.w, self.h))
        assert self.proc.stdin is not None
        self.proc.stdin.write(pygame.image.tobytes(out, "RGB"))
        self.n += 1

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg clip encode failed")


def run(root: Path, job: dict) -> dict:
    sys.path.insert(0, str(root))
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import dataclasses

    import pygame

    from src.characters.roster import HERO_BY_KEY, Behaviour, Extra
    from src.games.base import Recipe
    from src.physics.engine import Sim
    from src.rendering import pipeline

    rec = job["record"]
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = str(job["tag"])
    w, h = int(job.get("width", DEFAULT_W)), int(job.get("height", DEFAULT_H))
    side: dict = {"ok": False, "verified": False, "root": str(root), "tag": tag, "width": w, "height": h}

    rfields = {f.name for f in dataclasses.fields(Recipe)}
    recipe = Recipe(**{k: v for k, v in (rec.get("recipe") or {}).items() if k in rfields})
    heroes = [HERO_BY_KEY[k] for k in rec.get("heroes") or []]
    xfields = {f.name for f in dataclasses.fields(Extra)}
    extras = []
    for d in rec.get("extras") or []:
        d = {k: v for k, v in d.items() if k in xfields}
        if isinstance(d.get("behaviour"), (list, tuple)):
            d["behaviour"] = Behaviour(*[float(x) for x in d["behaviour"]])
        elif isinstance(d.get("behaviour"), dict):
            d["behaviour"] = Behaviour(**d["behaviour"])
        extras.append(Extra(**d))
    trace = Sim(recipe, heroes, extras, int(rec["sim_seed"])).run()

    ranking = [str(k) for k in trace.meta.get("ranking") or []]
    side.update(winner=trace.meta.get("winner"), ranking=ranking,
                resolved_at=float(trace.meta.get("resolved_at") or 0.0),
                preroll=int(trace.meta.get("preroll_frames", 0)), mode=trace.mode)
    side["events"] = [_event_dict(e) for e in trace.events
                      if e.kind in ("elimination", "impact", "crush_hit", "trait", "glitch_blink", "escalation",
                                    "twist", "lead_change", "win", "finish", "reverse", "heavy_land")]
    exp_rank = [str(k) for k in rec.get("ranking") or []]
    side["verified"] = bool(trace.meta.get("winner") == rec.get("winner") and (not exp_rank or ranking == exp_rank))
    if not side["verified"]:
        side["reason"] = "re-simulated outcome differs from the published race"
        return side

    ep = pipeline.Episode(trace, str(job.get("label") or ""), season_line="", prompt="", flash_event=None,
                          outcome=None, league_ctx={"stage": job.get("stage", "league")})
    r = pipeline.Renderer(ep)
    tracker, scy = _load_window_tracker()
    if tracker is not None:
        try:   # dedicated 4:3 recap camera (falls back to the tree's 9:16 Shorts camera on any error)
            r.cams = tracker(trace, 1080.0, 1080.0 * h / max(1, w))
            side["camera"] = "track_window"
        except Exception as exc:  # noqa: BLE001
            side["camera"] = f"shorts ({type(exc).__name__})"
    pre = r.pre
    end_t = float(trace.meta.get("resolved_at") or (trace.n_frames - pre) / FPS)
    n = trace.n_frames
    Shot = pipeline.Shot

    plan, chaos_list = _build_highlight_plan(trace, pre, end_t, Shot)
    chaos0 = chaos_list[0] if chaos_list else None

    enc = _Encoder(out_dir / f"{tag}_clip.mp4", w, h)
    timeline = []
    for idx, (shot, seg, gt) in enumerate(plan):
        enc.write(_render_crop(r, shot, idx, w, h, Shot, pygame, scy), pygame)
        timeline.append([round(gt, 3), seg])
    enc.close()
    side["clip"] = {"path": str(out_dir / f"{tag}_clip.mp4"), "frames": enc.n, "width": w, "height": h,
                    "timeline": timeline,
                    "chaos_t": round(chaos0.t, 3) if chaos0 is not None else None,
                    "chaos_kind": chaos0.kind if chaos0 is not None else None,
                    "chaos_actors": [str(a) for a in chaos0.actors] if chaos0 is not None else [],
                    "decisive_index": next((i for i, x in enumerate(timeline) if x[1] == "replay"), len(timeline))}

    # ---- optional cold-open freeze: 1.5 s leading into a hero's elimination, rendered in matching 4:3 crop
    fz = job.get("freeze") or None
    if fz and fz.get("victim") in trace.keys:
        vi = trace.keys.index(fz["victim"])
        te = float(fz.get("t") or 0.0)
        frames = [f for f in _frames_for(pre, te - 1.7, te - 0.2, n)
                  if trace.flags[f][vi] & 1]
        if len(frames) >= 12:
            from src.physics.camera import Cam

            enc2 = _Encoder(out_dir / f"{tag}_freeze.mp4", w, h)
            last_pos = [round(w * 0.5, 1), round(h * 0.5, 1)]
            cap = r.cams[min(pre, len(r.cams) - 1)].zoom * 2.6
            crop_h_src = int(round(1080 * h / max(1, w)))
            y0_src = max(0, min(1920 - crop_h_src, int(round(scy)) - crop_h_src // 2))
            for k, f in enumerate(frames):
                side_view = trace.mode == "SIDE_VIEW"
                shot = Shot(float(f), "play", (f - pre) / FPS, 1.3, fz["victim"]) if side_view else Shot(float(f), "play", (f - pre) / FPS)
                surf = _render_crop(r, shot, len(plan) + k, w, h, Shot, pygame, scy)
                enc2.write(surf, pygame)
                base = r.cams[f]
                rows = trace.frames[f]
                if side_view:
                    cam = Cam(float(rows[vi, 0]), float(rows[vi, 1]), min(base.zoom * 1.3, cap))
                else:
                    cam = Cam(base.x, base.y, min(base.zoom, cap), base.shake)
                sx, sy = cam.to_screen(float(rows[vi, 0]), float(rows[vi, 1]))
                px_ = max(60.0, min(w - 60.0, sx * w / 1080.0))
                py_ = max(60.0, min(h - 60.0, (sy - y0_src) * h / max(1.0, float(crop_h_src))))
                last_pos = [round(px_, 1), round(py_, 1)]
            enc2.close()
            side["freeze"] = {"path": str(out_dir / f"{tag}_freeze.mp4"), "frames": enc2.n, "victim": fz["victim"],
                              "width": w, "height": h, "pos": last_pos}
    try:   # camera QA: share of living heroes inside the 4:3 window + frames with no hero visible
        hidx = [trace.index(k) for k in trace.meta.get("heroes") or [] if k in trace.keys]
        crop_h = 1080.0 * h / max(1, w)
        vis, empty, nf = 0.0, 0, 0
        for shot, seg, _ in plan:
            if seg == "replay":
                continue
            fi = int(min(n - 1, max(0, round(shot.tf))))
            alive = [i for i in hidx if trace.flags[fi][i] & 1]
            if not alive:
                continue
            cam = r.cams[fi]
            inw = sum(1 for i in alive if 0 <= cam.to_screen(*trace.frames[fi][i][:2])[0] <= 1080
                      and abs(cam.to_screen(*trace.frames[fi][i][:2])[1] - scy) <= crop_h / 2)
            vis += inw / len(alive)
            empty += inw == 0
            nf += 1
        side["camera_qa"] = {"avg_visible_pct": round(100 * vis / max(1, nf), 1),
                             "empty_frame_pct": round(100 * empty / max(1, nf), 1)}
    except Exception as exc:  # noqa: BLE001
        side["camera_qa"] = {"error": type(exc).__name__}
    side["ok"] = True
    return side


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--job", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    job_path = Path(a.job).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    # never let the recap package directory shadow anything in the replay tree
    here = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != here]
    try:
        side = run(root, job)
    except Exception as exc:  # noqa: BLE001 - report to the parent, which falls back to a results card
        side = {"ok": False, "verified": False, "reason": f"{type(exc).__name__}: {str(exc)[:200]}", "root": str(root)}
    out = Path(job["out_dir"]) / f"{job['tag']}.json"
    out.write_text(json.dumps(side), encoding="utf-8")
    print(f"[CLIP WORKER] {job['tag']} ok={side.get('ok')} verified={side.get('verified')} "
          f"reason={side.get('reason', '')}", flush=True)
    return 0 if side.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
