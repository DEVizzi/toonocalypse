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
CHAOS_PRE_S, CHAOS_POST_S = 2.0, 1.2
FINAL_S = 7.0
REACTION_S = 0.45


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


def _chaos_event(trace, end_t: float):
    """Biggest pre-final disaster: hero KO by a hero > hero KO > multi-KO burst > crusher hit > big hero collision."""
    def rank(e) -> float:
        if e.kind == "elimination" and e.data.get("hero"):
            return 4 + (1 if e.data.get("by_hero") else 0)
        if e.kind == "crush_hit":
            return 3
        if e.kind == "trait":
            return 2
        if e.kind == "impact" and e.data.get("hero_pair"):
            return 1 + min(1.0, float(e.data.get("impulse", 0)) / 4000)
        return 0
    lim = end_t - FINAL_S - CHAOS_POST_S - 0.6
    cands = [e for e in trace.events if 1.6 <= e.t <= lim and rank(e) > 0]
    return max(cands, key=lambda e: (rank(e), -e.t)) if cands else None


def _frames_for(pre: int, t0: float, t1: float, n_frames: int) -> list[int]:
    a = max(0, pre + int(round(t0 * FPS)))
    b = min(n_frames - 1, pre + int(round(t1 * FPS)))
    return list(range(a, b + 1))


class _Encoder:
    def __init__(self, path: Path, w: int, h: int) -> None:
        self.w, self.h = w, h
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
               "-pix_fmt", "yuv420p", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.n = 0

    def write(self, surf, pygame) -> None:
        small = pygame.transform.smoothscale(surf, (self.w, self.h))
        assert self.proc.stdin is not None
        self.proc.stdin.write(pygame.image.tobytes(small, "RGB"))
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
    w, h = int(job.get("width", 608)), int(job.get("height", 1080))
    side: dict = {"ok": False, "verified": False, "root": str(root), "tag": tag}

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
    pre = r.pre
    end_t = float(trace.meta.get("resolved_at") or (trace.n_frames - pre) / FPS)
    n = trace.n_frames
    Shot = pipeline.Shot

    # ---- highlight clip: [chaos 3.2 s] -> final 7 s up to the decisive moment (+0.45 s) -> 1.5 s 0.3x replay
    chaos = _chaos_event(trace, end_t)
    plan: list[tuple[object, str, float]] = []
    if chaos is not None:
        for f in _frames_for(pre, chaos.t - CHAOS_PRE_S, chaos.t + CHAOS_POST_S, n):
            plan.append((Shot(f, "play", (f - pre) / FPS), "chaos", (f - pre) / FPS))
    final_t0 = max(0.0, end_t - (FINAL_S if chaos is not None else FINAL_S + 2.5))
    final_frames = _frames_for(pre, final_t0, end_t + REACTION_S, n)
    for f in final_frames:
        plan.append((Shot(f, "play", (f - pre) / FPS), "final", (f - pre) / FPS))
    end_f = final_frames[-1] if final_frames else n - 1
    tl = pipeline.TIMELINE
    src0 = end_f - tl.replay_source_s * FPS
    n_rep = int(round(tl.replay_s * FPS))
    winner = trace.meta.get("winner")
    for i in range(n_rep):
        tf = src0 + (end_f - src0) * i / max(1, n_rep)
        plan.append((Shot(tf, "replay", i / FPS, tl.replay_zoom, winner), "replay", (tf - pre) / FPS))

    enc = _Encoder(out_dir / f"{tag}_clip.mp4", w, h)
    timeline = []
    for idx, (shot, seg, gt) in enumerate(plan):
        enc.write(r.render_shot(shot, idx), pygame)
        timeline.append([round(gt, 3), seg])
    enc.close()
    side["clip"] = {"path": str(out_dir / f"{tag}_clip.mp4"), "frames": enc.n, "timeline": timeline,
                    "chaos_t": round(chaos.t, 3) if chaos is not None else None,
                    "chaos_kind": chaos.kind if chaos is not None else None,
                    "chaos_actors": [str(a) for a in chaos.actors] if chaos is not None else [],
                    "decisive_index": next((i for i, x in enumerate(timeline) if x[1] == "replay"), len(timeline))}

    # ---- optional cold-open freeze: 1.5 s leading into a hero's elimination, camera tracking the victim
    fz = job.get("freeze") or None
    if fz and fz.get("victim") in trace.keys:
        vi = trace.keys.index(fz["victim"])
        te = float(fz.get("t") or 0.0)
        frames = [f for f in _frames_for(pre, te - 1.7, te - 0.2, n)
                  if trace.flags[f][vi] & 1]          # ALIVE bit: the victim must still be on screen
        if len(frames) >= 12:
            from src.physics.camera import Cam

            enc2 = _Encoder(out_dir / f"{tag}_freeze.mp4", w, h)
            last_pos = None
            cap = r.cams[min(pre, len(r.cams) - 1)].zoom * 2.6
            for k, f in enumerate(frames):
                side_view = trace.mode == "SIDE_VIEW"
                shot = Shot(f, "play", (f - pre) / FPS, 1.3, fz["victim"]) if side_view else Shot(f, "play", (f - pre) / FPS)
                surf = r.render_shot(shot, len(plan) + k)
                enc2.write(surf, pygame)
                base = r.cams[f]
                rows = trace.frames[f]
                if side_view:     # mirrors Renderer.render_shot (zoom_mult + focus branch)
                    cam = Cam(float(rows[vi, 0]), float(rows[vi, 1]), min(base.zoom * 1.3, cap))
                else:             # TOP_DOWN: camera locked at the arena centre
                    cam = Cam(0.0, 0.0, min(base.zoom, cap), base.shake)
                sx, sy = cam.to_screen(float(rows[vi, 0]), float(rows[vi, 1]))
                last_pos = [round(sx * w / surf.get_width(), 1), round(sy * h / surf.get_height(), 1)]
            enc2.close()
            side["freeze"] = {"path": str(out_dir / f"{tag}_freeze.mp4"), "frames": enc2.n, "victim": fz["victim"],
                              "pos": last_pos}
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
