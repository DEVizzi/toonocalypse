"""Camera (§15): critically damped spring on (x, y, zoom) in world coordinates, computed from the trace."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config import FPS, H, LAYOUT, W, settings
from src.physics import trace as T

VIEW_TOP, VIEW_BOTTOM = LAYOUT["viewport"]
ACTION_TOP, ACTION_BOTTOM = LAYOUT["action_bias"]
SCREEN_CY = (ACTION_TOP + ACTION_BOTTOM) / 2           # v3.1: track framed at y = 720..1220


@dataclass
class Cam:
    x: float
    y: float
    zoom: float
    shake: tuple[float, float] = (0.0, 0.0)

    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return ((wx - self.x) * self.zoom + W / 2 + self.shake[0], (wy - self.y) * self.zoom + SCREEN_CY + self.shake[1])

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return ((sx - W / 2 - self.shake[0]) / self.zoom + self.x, (sy - SCREEN_CY - self.shake[1]) / self.zoom + self.y)

    def visible(self, wx: float, wy: float, margin: float = 200) -> bool:
        sx, sy = self.to_screen(wx, wy)
        return -margin < sx < W + margin and -margin < sy < H + margin


def _spring(x: float, v: float, target: float, omega: float, dt: float) -> tuple[float, float]:
    """Critically damped spring step (exact integration)."""
    e = math.exp(-omega * dt)
    d = x - target
    temp = (v + omega * d) * dt
    return target + (d + temp) * e, (v - omega * temp) * e


def track(trace: T.Trace) -> list[Cam]:
    """One camera per trace frame."""
    meta = trace.meta
    heroes = [trace.index(k) for k in meta["heroes"]]
    x0, y0, x1, y1 = meta["bounds"]
    cams: list[Cam] = []
    chaos: list[tuple[int, float]] = []         # (frame, strength)
    pre = meta.get("preroll_frames", 0)
    for e in trace.events:
        if (e.kind == "elimination" and e.data.get("hero")) or (e.kind == "impact" and e.data.get("impulse", 0) > 1400):
            chaos.append((pre + int(e.t * FPS), 1.0 if e.kind == "elimination" else 0.7))
    thuds = [pre + int(e.t * FPS) for e in trace.events if e.kind == "heavy_land"]    # Juggernaut micro-shake
    if trace.mode == "TOP_DOWN":
        span = max(x1 - x0, (y1 - y0) * W / (VIEW_BOTTOM - VIEW_TOP))
        base_zoom = min(1.15, W / span) * settings()["render"]["top_zoom"]
    else:
        base_zoom = settings()["render"]["side_zoom"]
    cx, cy, cz = None, None, base_zoom
    vx = vy = vz = 0.0
    dt = 1 / FPS
    final_zoom = settings()["render"]["final3_zoom"]
    zmin, zmax_s = settings()["render"]["side_zoom_range"]
    # 2-pass death cam bias: pre-index hero KO frames so camera biases/zooms out 0.35 s before each KO
    hero_kos = []
    for e in trace.events:
        if e.kind == "elimination" and e.data.get("hero") and e.pos is not None:
            hero_kos.append((pre + int(e.t * FPS), e.pos[0], e.pos[1]))
    bias_win = int(0.50 * FPS)
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        everyone = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        focus = None
        tz = base_zoom
        if trace.mode == "TOP_DOWN":
            tx, ty = (x0 + x1) / 2, (y0 + y1) / 2 + 20
        else:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            if not alive:
                tx, ty = (cx if cx is not None else 0.0), (cy if cy is not None else 0.0)
            else:
                order = sorted(alive, key=lambda i: rows[i, 0], reverse=True)
                focus = order[0]
                pack = order[: min(5, len(order))]                    # top 4-5 alive Heroes
                xs = rows[pack, 0]
                ys = rows[pack, 1]
                # 60% main cluster (median/mean of pack), 40% #1 leader
                cluster_x, cluster_y = float(np.median(xs)), float(np.median(ys))
                lead_x, lead_y = float(xs[0]), float(ys[0])
                tx = 0.60 * cluster_x + 0.40 * lead_x
                ty = 0.60 * cluster_y + 0.40 * lead_y - 30
                # include approaching elimination wall if close behind pack
                chase = trace.zones[f].get("chase_x")
                left_x = float(xs.min())
                if chase is not None and left_x - chase < 500:
                    left_x = min(left_x, chase + 80)
                span_x = max(520.0, float(xs.max()) - left_x + 280)
                tz = min(zmax_s, max(zmin, (W * 0.88) / span_x))
                # 2-pass death cam bias: 0.35 s before a Hero KO, bias toward the KO & zoom out slightly
                for kf, kx, ky in hero_kos:
                    if 0 <= kf - f <= bias_win:
                        w_ko = 0.65 * (1.0 - (kf - f) / max(1, bias_win))
                        tx = tx * (1.0 - w_ko) + kx * w_ko
                        ty = ty * (1.0 - w_ko) + ky * w_ko
                        tz = min(tz, max(0.58, (W * 0.85) / max(600.0, abs(lead_x - kx) + 280)))
                        focus = None
                        break
            tx = min(max(tx, x0 + W / 2 / max(zmin, tz)), x1 - W / 2 / max(zmin, tz))
            ty = min(max(ty, y0 + 250), y1 - 250)
        if trace.mode == "TOP_DOWN":
            z0 = trace.zones[f]
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * z0.get("ring_r", 1.0) / max(1.0, trace.zones[0].get("ring_r", 1.0))
            zmax = settings()["render"]["top_zoom_max"]
            tz = base_zoom * min(zmax, 1.0 / max(ek, 1.0 / zmax))
        tx_lead, ty_lead = tx, ty
        if 0 < len(everyone) <= 3:
            xs, ys = rows[everyone, 0], rows[everyone, 1]
            tx, ty = float(xs.mean()), float(ys.mean())
            spanx = float(xs.max() - xs.min()) + 360
            spany = float(ys.max() - ys.min()) + 420
            fit = min(W / spanx, (VIEW_BOTTOM - VIEW_TOP) / spany)
            if fit >= zmin:
                tz = max(tz, min(base_zoom * final_zoom, fit))
                focus = None
            else:
                tx, ty = tx_lead, ty_lead
        strength = 0.0
        for cf, s in chaos:
            if 0 <= f - cf < int(0.6 * FPS):
                strength = max(strength, s)
                tz = tz * 1.12
        if cx is None:
            cx, cy = tx, ty
        cx, vx = _spring(cx, vx, tx, 4.5, dt)
        cy, vy = _spring(cy, vy, ty, 3.2, dt)
        cz, vz = _spring(cz, vz, tz, 7.0, dt)
        if focus is not None:             # keep #1 inside the frame (middle 65%) without hiding the pack
            fx, fy = float(rows[focus, 0]), float(rows[focus, 1])
            hw = W * 0.35 / cz
            mid, half = (VIEW_TOP + VIEW_BOTTOM) / 2, (VIEW_BOTTOM - VIEW_TOP) * 0.30
            cx = min(max(cx, fx - hw), fx + hw)
            cy = min(max(cy, fy + (SCREEN_CY - mid - half) / cz), fy + (SCREEN_CY - mid + half) / cz)
        if everyone:
            def on_screen(i: int) -> bool:
                sx = (rows[i, 0] - cx) * cz + W / 2
                sy = (rows[i, 1] - cy) * cz + SCREEN_CY
                return 40 < sx < W - 40 and VIEW_TOP + 40 < sy < VIEW_BOTTOM - 40
            if not any(on_screen(i) for i in everyone):
                j = focus if focus is not None else max(everyone, key=lambda i: rows[i, 0])
                cx, cy, vx, vy = float(rows[j, 0]), float(rows[j, 1]) - (SCREEN_CY - (VIEW_TOP + VIEW_BOTTOM) / 2) / cz, 0.0, 0.0
        shake = (0.0, 0.0)
        for cf in thuds:
            if 0 <= f - cf < 3:
                shake = (0.0, 3.0 * (1 if (f - cf) % 2 == 0 else -1))
        for cf, s in chaos:
            k = f - cf
            if 0 <= k < 10:
                amp = 14 * s * (1 - k / 10)
                shake = (amp * math.sin(k * 2.7 + cf), amp * math.cos(k * 3.1 + cf))
        cams.append(Cam(cx, cy, cz, shake))
    return cams
