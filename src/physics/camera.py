"""Camera (§15, v3.3): critically damped spring on (x, y, zoom) in world coordinates, computed from the trace.

SIDE_VIEW: frames the densest action cluster (4-6 heroes inside a 750 px window) with a strict zoom floor of 0.86x so
balls never shrink into dots; only locks onto a runaway #1 near the finish or when <= 3 heroes remain.
TOP_DOWN: fixed on the arena centre; zoom = initial_radius / current_radius (capped 2.05x), interpolated continuously
while the disc shrinks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config import FPS, H, LAYOUT, W, settings
from src.physics import trace as T
from src.physics.cluster import action_cluster

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

    def on_screen(self, wx: float, wy: float, pad: float = 0.0) -> bool:
        """Strictly inside the visible gameplay viewport (used to drop off-screen popups)."""
        sx, sy = self.to_screen(wx, wy)
        return pad <= sx <= W - pad and VIEW_TOP + pad <= sy <= VIEW_BOTTOM - pad


def _spring(x: float, v: float, target: float, omega: float, dt: float) -> tuple[float, float]:
    """Critically damped spring step (exact integration)."""
    e = math.exp(-omega * dt)
    d = x - target
    temp = (v + omega * d) * dt
    return target + (d + temp) * e, (v - omega * temp) * e


def top_base_zoom(meta: dict) -> float:
    x0, y0, x1, y1 = meta["bounds"]
    span = max(x1 - x0, (y1 - y0) * W / (VIEW_BOTTOM - VIEW_TOP))
    return min(1.15, W / span) * settings()["render"]["top_zoom"]


def track(trace: T.Trace) -> list[Cam]:
    """One camera per trace frame."""
    meta = trace.meta
    rs = settings()["render"]
    heroes = [trace.index(k) for k in meta["heroes"]]
    x0, y0, x1, y1 = meta["bounds"]
    finish_x = meta.get("finish_x")
    cams: list[Cam] = []
    chaos: list[tuple[int, float]] = []         # (frame, strength)
    pre = meta.get("preroll_frames", 0)
    for e in trace.events:
        if (e.kind == "elimination" and e.data.get("hero")) or (e.kind == "impact" and e.data.get("impulse", 0) > 1400):
            chaos.append((pre + int(e.t * FPS), 1.0 if e.kind == "elimination" else 0.7))
    thuds = [pre + int(e.t * FPS) for e in trace.events if e.kind == "heavy_land" and e.data.get("shake", True)]
    top = trace.mode == "TOP_DOWN"
    base_zoom = top_base_zoom(meta) if top else rs["side_zoom"]
    cx, cy, cz = None, None, base_zoom
    vx = vy = vz = 0.0
    dt = 1 / FPS
    zmin, zmax = rs["side_zoom_range"]
    window = float(rs["cluster_window_px"])
    lock_px = float(rs["leader_lock_px"])
    top_zmax = float(rs["top_zoom_max"])
    hero_kos = [(pre + int(e.t * FPS), e.pos[0], e.pos[1]) for e in trace.events
                if e.kind == "elimination" and e.data.get("hero") and e.pos is not None]
    bias_win = int(0.50 * FPS)
    r0 = trace.zones[0].get("ring_r", 1.0)
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        everyone = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        focus = None
        if top:
            tx, ty = (x0 + x1) / 2, (y0 + y1) / 2 + 20
            z0 = trace.zones[f]
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * z0.get("ring_r", 1.0) / max(1.0, r0)
            # v3.3: zoom tracks initial_radius / current_radius continuously while the disc shrinks
            tz = base_zoom * min(top_zmax, 1.0 / max(ek, 1e-3))
        else:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            tz = base_zoom
            if not alive:
                tx, ty = (cx if cx is not None else 0.0), (cy if cy is not None else 0.0)
            else:
                xs = [float(rows[i, 0]) for i in alive]
                lead = alive[int(np.argmax(xs))]
                lead_x, lead_y = float(rows[lead, 0]), float(rows[lead, 1])
                near_finish = finish_x is not None and finish_x - lead_x < lock_px
                if len(alive) <= 3:
                    sx_ = np.array(xs)
                    sy_ = np.array([float(rows[i, 1]) for i in alive])
                    tx, ty = float(sx_.mean()), float(sy_.mean()) - 30
                    span = float(sx_.max() - sx_.min()) + 360
                    tz = max(zmin, min(rs["final3_zoom"], (W * 0.88) / span))
                    if span * zmin > W * 0.9:          # survivors too spread: keep the leader's side
                        tx, ty = lead_x - 120, lead_y - 30
                    focus = lead if span * zmin > W * 0.9 else None
                elif near_finish:
                    m = [alive[j] for j in action_cluster(xs, window)]
                    tx = 0.65 * lead_x + 0.35 * float(np.mean(rows[m, 0]))
                    ty = 0.65 * lead_y + 0.35 * float(np.median(rows[m, 1])) - 30
                    focus = lead
                else:
                    m = [alive[j] for j in action_cluster(xs, window)]
                    mx = rows[m, 0]
                    wts = np.ones(len(m))
                    wts[0] = 1.3
                    tx = float(np.sum(mx * wts) / np.sum(wts))
                    ty = float(np.median(rows[m, 1])) - 30
                    span = float(mx.max() - mx.min()) + 320
                    tz = (W * 0.86) / span
                # keep the fire wall + doomed stragglers on screen when the wall is about to torch someone
                chase = trace.zones[f].get("chase_x")
                if chase is not None and any(float(rows[i, 0]) < chase + 240 for i in everyone):
                    tzc = max(zmin, min(zmax, tz))
                    tx_wall = chase + (W / 2 - 110) / tzc
                    if tx > tx_wall and lead_x - tx_wall < (W / 2 - 70) / tzc:
                        tx = tx_wall
                # 2-pass death cam: bias toward an upcoming hero KO (never zooming below the floor)
                for kf, kx, ky in hero_kos:
                    if 0 <= kf - f <= bias_win:
                        w_ko = 0.6 * (1.0 - (kf - f) / max(1, bias_win))
                        tx = tx * (1.0 - w_ko) + kx * w_ko
                        ty = ty * (1.0 - w_ko) + ky * w_ko
                        focus = None
                        break
                tz = max(zmin, min(zmax, tz))
            tx = min(max(tx, x0 + W / 2 / tz), x1 - W / 2 / tz)
            ty = min(max(ty, y0 + 250), y1 - 250)
        strength = 0.0
        for cf, s in chaos:
            if 0 <= f - cf < int(0.6 * FPS):
                strength = max(strength, s)
                if not top:
                    tz = min(zmax, tz * 1.08)
        if cx is None:
            cx, cy, cz = tx, ty, tz
        cx, vx = _spring(cx, vx, tx, 4.5, dt)
        cy, vy = _spring(cy, vy, ty, 3.2, dt)
        cz, vz = _spring(cz, vz, tz, 7.0 if not top else 3.5, dt)
        if not top:
            cz = max(zmin, min(zmax, cz))
        if focus is not None:             # lock mode: keep #1 inside the middle 65% of the frame
            fx, fy = float(rows[focus, 0]), float(rows[focus, 1])
            hw = W * 0.35 / cz
            mid, half = (VIEW_TOP + VIEW_BOTTOM) / 2, (VIEW_BOTTOM - VIEW_TOP) * 0.30
            cx = min(max(cx, fx - hw), fx + hw)
            cy = min(max(cy, fy + (SCREEN_CY - mid - half) / cz), fy + (SCREEN_CY - mid + half) / cz)
        if everyone and not top:
            def on_screen(i: int) -> bool:
                sx = (rows[i, 0] - cx) * cz + W / 2
                sy = (rows[i, 1] - cy) * cz + SCREEN_CY
                return 40 < sx < W - 40 and VIEW_TOP + 40 < sy < VIEW_BOTTOM - 40
            if not any(on_screen(i) for i in everyone):
                j = max(everyone, key=lambda i: rows[i, 0])
                cx, cy, vx, vy = float(rows[j, 0]), float(rows[j, 1]) - (SCREEN_CY - (VIEW_TOP + VIEW_BOTTOM) / 2) / cz, 0.0, 0.0
        shake = (0.0, 0.0)
        for cf in thuds:
            if 0 <= f - cf < 3:
                shake = (0.0, 3.0 * (1 if (f - cf) % 2 == 0 else -1))
        for cf, s in chaos:
            k = f - cf
            if 0 <= k < 10:
                amp = (14 if not top else 7) * s * (1 - k / 10)
                shake = (amp * math.sin(k * 2.7 + cf), amp * math.cos(k * 3.1 + cf))
        cams.append(Cam(cx, cy, cz, shake))
    return cams
