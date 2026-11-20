"""Camera (§15): critically damped spring on (x, y, zoom) in world coordinates, computed from the trace."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config import FPS, H, LAYOUT, W, settings
from src.physics import trace as T

VIEW_TOP, VIEW_BOTTOM = LAYOUT["viewport"]
ACTION_TOP, ACTION_BOTTOM = LAYOUT["action_bias"]
SCREEN_CY = (ACTION_TOP + ACTION_BOTTOM) / 2 + 40      # world focus point lands in the action band


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
    if trace.mode == "TOP_DOWN":
        span = max(x1 - x0, (y1 - y0) * W / (VIEW_BOTTOM - VIEW_TOP))
        base_zoom = min(1.15, W / span) * settings()["render"]["top_zoom"]
    else:
        base_zoom = settings()["render"]["side_zoom"]
    cx, cy, cz = None, None, base_zoom
    vx = vy = vz = 0.0
    dt = 1 / FPS
    final_zoom = settings()["render"]["final3_zoom"]
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        everyone = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        focus = None                                   # the contestant that must stay in the middle of the frame
        if trace.mode == "TOP_DOWN":
            tx, ty = (x0 + x1) / 2, (y0 + y1) / 2 + 20
        else:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            if not alive:
                tx, ty = (cx if cx is not None else 0.0), (cy if cy is not None else 0.0)
            else:
                order = sorted(alive, key=lambda i: rows[i, 0], reverse=True)
                focus = order[0]
                lead = order[: max(1, min(3, math.ceil(len(order) * 0.4)))]   # top-3 living leaders
                w = np.array([1.0 + 0.5 * (k == 0) for k in range(len(lead))])
                tx = float(np.average(rows[lead, 0], weights=w)) + 90
                ty = float(np.average(rows[lead, 1], weights=w)) - 60
            tx = min(max(tx, x0 + W / 2 / base_zoom), x1 - W / 2 / base_zoom)
            ty = min(max(ty, y0 + 300), y1 - 300)
        tz = base_zoom
        if trace.mode == "TOP_DOWN":      # follow the shrinking arena in so the fight stays big on screen
            z0 = trace.zones[f]
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * z0.get("ring_r", 1.0) / max(1.0, trace.zones[0].get("ring_r", 1.0))
            tz = base_zoom / max(0.38, ek)
        tx_lead, ty_lead = tx, ty
        if 0 < len(everyone) <= 3:        # final-3: tight zoom on the survivors' faces (all of them stay in frame)
            xs, ys = rows[everyone, 0], rows[everyone, 1]
            tx, ty = float(xs.mean()), float(ys.mean())
            spanx = float(xs.max() - xs.min()) + 360
            spany = float(ys.max() - ys.min()) + 420
            fit = min(W / spanx, (VIEW_BOTTOM - VIEW_TOP) / spany)
            if fit >= base_zoom:          # only when they can all share the frame; else keep following the leader
                tz = max(tz, min(base_zoom * final_zoom, fit))
                focus = None
            else:
                tx, ty = tx_lead, ty_lead
        strength = 0.0
        for cf, s in chaos:
            if 0 <= f - cf < int(0.6 * FPS):
                strength = max(strength, s)
                tz = tz * 1.15
        if cx is None:
            cx, cy = tx, ty
        cx, vx = _spring(cx, vx, tx, 4.5, dt)
        cy, vy = _spring(cy, vy, ty, 3.2, dt)
        cz, vz = _spring(cz, vz, tz, 7.0, dt)
        if focus is not None:             # hard clamp: the leader is always inside the middle 50% of the frame
            fx, fy = float(rows[focus, 0]), float(rows[focus, 1])
            hw = W * 0.25 / cz
            mid, half = (VIEW_TOP + VIEW_BOTTOM) / 2, (VIEW_BOTTOM - VIEW_TOP) * 0.25
            cx = min(max(cx, fx - hw), fx + hw)
            # screen_y = (fy - cy) * cz + SCREEN_CY must stay within mid +- half
            cy = min(max(cy, fy + (SCREEN_CY - mid - half) / cz), fy + (SCREEN_CY - mid + half) / cz)
        if everyone:                      # safety net: never a frame with nobody on screen (teleports, launches)
            def on_screen(i: int) -> bool:
                sx = (rows[i, 0] - cx) * cz + W / 2
                sy = (rows[i, 1] - cy) * cz + SCREEN_CY
                return 40 < sx < W - 40 and VIEW_TOP + 40 < sy < VIEW_BOTTOM - 40
            if not any(on_screen(i) for i in everyone):
                j = focus if focus is not None else max(everyone, key=lambda i: rows[i, 0])
                cx, cy, vx, vy = float(rows[j, 0]), float(rows[j, 1]) - (SCREEN_CY - (VIEW_TOP + VIEW_BOTTOM) / 2) / cz, 0.0, 0.0
        shake = (0.0, 0.0)
        for cf, s in chaos:
            k = f - cf
            if 0 <= k < 10:
                amp = 14 * s * (1 - k / 10)
                shake = (amp * math.sin(k * 2.7 + cf), amp * math.cos(k * 3.1 + cf))
        cams.append(Cam(cx, cy, cz, shake))
    return cams
