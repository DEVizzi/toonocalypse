"""Camera (§15, v3.3): critically damped spring on (x, y, zoom) in world coordinates, computed from the trace.

SIDE_VIEW: frames the densest action cluster (4-6 heroes inside a 750 px window) with a strict zoom floor of 0.86x so
balls never shrink into dots; only locks onto a runaway #1 near the finish or when <= 3 heroes remain.
v4.3: smooth-damp with strict max pan velocity (680 / 520 px/s) + 0.85 s lead-switch hysteresis (zero teleports);
collapse_tower X locked to the shaft (+-90 px) with a downward-gliding Y; final 2-3 duel zoom bands
(<650 px -> 1.12-1.30x close-up, 650-1100 px -> >= 0.76x, >1100 px -> lead cluster at >= 0.86x + edge rival pill).
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


def duel_zoom(spread: float, duel_min: float = 0.76) -> tuple[float, bool]:
    """v4.3 final 2-3 framing. Returns (target zoom, edge_mode).
    spread < 650 px  -> dramatic close-up 1.30x (tight) .. 1.12x (650 px);
    650-1100 px      -> gentle pull-back, never below `duel_min` (0.76x);
    > 1100 px        -> stay on the lead cluster at >= 0.86x (edge rival pill + wall acceleration handle the rest)."""
    if spread < 650.0:
        return 1.30 - (1.30 - 1.12) * (spread / 650.0), False
    if spread <= 1100.0:
        return max(duel_min, min(1.12, (W * 0.86) / (spread + 360.0))), False
    return 0.92, True


def track(trace: T.Trace) -> list[Cam]:
    """One camera per trace frame (v4.3 smooth-damp: critically damped springs + strict max pan velocity +
    0.85 s target-switch hysteresis -> the camera never teleports between heroes)."""
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
    duel_min = float(rs.get("duel_min_zoom", 0.76))
    max_vx = float(rs.get("cam_max_vx", 680.0))
    max_vy = float(rs.get("cam_max_vy", 520.0))
    hyst_f = int(round(float(rs.get("cam_switch_hysteresis_s", 0.85)) * FPS))
    window = float(rs["cluster_window_px"])
    lock_px = float(rs["leader_lock_px"])
    top_zmax = float(rs["top_zoom_max"])
    hero_kos = [(pre + int(e.t * FPS), e.pos[0], e.pos[1]) for e in trace.events
                if e.kind == "elimination" and e.data.get("hero") and e.pos is not None]
    bias_win = int(0.50 * FPS)
    r0 = trace.zones[0].get("ring_r", 1.0)
    vert_tower = bool(meta.get("vertical_tower", False))
    held_lead: int | None = None                 # hysteresis: the #1 the camera is currently committed to
    cand_lead: int | None = None
    cand_since = 0
    tower_ty: float | None = None
    track.rescues = 0                           # type: ignore[attr-defined]  (diagnostic: last-resort snaps)
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        everyone = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        focus = None
        floor_z = zmin
        act: list[int] = []                      # contestants the camera is framing (their velocity lifts the pan cap)
        if top:
            # v4.0 Part A.3: Lock TOP_DOWN camera center strictly at (0, 0) (zoom + micro-shake only!)
            tx, ty = 0.0, 0.0
            z0 = trace.zones[f]
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * z0.get("ring_r", 1.0) / max(1.0, r0)
            tz = base_zoom * min(top_zmax, 1.0 / max(ek, 1e-3))
        elif vert_tower:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            if not alive:
                tx, ty, tz = (cx if cx is not None else 660.0), (cy if cy is not None else 0.0), max(zmin, 0.86)
            else:
                ys = [float(rows[i, 1]) for i in alive]
                m = [alive[j] for j in action_cluster(ys, 620.0)]      # front-most (lowest) dense pack
                act = m
                mx = rows[m, 0]
                my = rows[m, 1]
                # v4.3: X locked near the tower centre (+-90 px drift max); Y glides DOWN with the lead pack and
                # may only creep back up slowly (never snaps up two floors when #1 changes)
                tx = 660.0 + max(-90.0, min(90.0, float(np.mean(mx)) - 660.0))
                # ...but never let the lead pack itself leave the frame (a stray hero wide on a floor)
                half_w = W / 2 / max(zmin, 0.86) - 90.0
                tx = max(float(mx.max()) - half_w, min(float(mx.min()) + half_w, tx))
                ty_raw = float(np.mean(my))
                tower_ty = ty_raw if tower_ty is None else max(ty_raw, tower_ty - 70.0 * dt)
                ty = tower_ty
                span_y = float(my.max() - my.min()) + 480.0
                tz = max(zmin, min(1.02, ((VIEW_BOTTOM - VIEW_TOP) * 0.82) / span_y, 0.86 if len(alive) > 4 else 1.0))
                tx = min(max(tx, x0 + W / 2 / tz), x1 - W / 2 / tz)
                ty = min(max(ty, y0 + 280), y1 - 220)
        else:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            tz = base_zoom
            if not alive:
                tx, ty = (cx if cx is not None else 0.0), (cy if cy is not None else 0.0)
            else:
                xs = [float(rows[i, 0]) for i in alive]
                raw_lead = alive[int(np.argmax(xs))]
                # hysteresis: only re-target after the new #1 holds the lead for 0.85 s
                if held_lead is None or not (flags[held_lead] & T.ALIVE):
                    held_lead, cand_lead = raw_lead, None
                elif raw_lead != held_lead:
                    if cand_lead != raw_lead:
                        cand_lead, cand_since = raw_lead, f
                    elif f - cand_since >= hyst_f:
                        held_lead, cand_lead = raw_lead, None
                else:
                    cand_lead = None
                lead = held_lead
                lead_x, lead_y = float(rows[lead, 0]), float(rows[lead, 1])
                near_finish = finish_x is not None and finish_x - lead_x < lock_px
                if len(alive) <= 3:
                    sx_ = np.array(xs)
                    sy_ = np.array([float(rows[i, 1]) for i in alive])
                    spread = float(math.hypot(sx_.max() - sx_.min(), (sy_.max() - sy_.min()) * 0.6))
                    tz, edge_mode = duel_zoom(spread, duel_min)
                    floor_z = duel_min
                    act = list(alive)
                    if edge_mode:
                        tx, ty = lead_x - 120, lead_y - 30            # frame the lead/action cluster, big & readable
                        focus = lead
                        floor_z = 0.86
                        act = [lead]
                    else:
                        tx, ty = float(sx_.mean()), float(sy_.mean()) - 30
                elif near_finish:
                    m = [alive[j] for j in action_cluster(xs, window)]
                    act = m
                    tx = 0.65 * lead_x + 0.35 * float(np.mean(rows[m, 0]))
                    ty = 0.65 * lead_y + 0.35 * float(np.median(rows[m, 1])) - 30
                    focus = lead
                else:
                    m = [alive[j] for j in action_cluster(xs, window)]
                    act = m
                    mx = rows[m, 0]
                    wts = np.ones(len(m))
                    wts[0] = 1.3
                    tx = float(np.sum(mx * wts) / np.sum(wts))
                    ty = float(np.median(rows[m, 1])) - 30
                    span = float(mx.max() - mx.min()) + 320
                    tz = (W * 0.86) / span
                chase = trace.zones[f].get("chase_x")
                if chase is not None and any(float(rows[i, 0]) < chase + 240 for i in everyone):
                    tzc = max(floor_z, min(zmax, tz))
                    tx_wall = chase + (W / 2 - 110) / tzc
                    if tx > tx_wall and lead_x - tx_wall < (W / 2 - 70) / tzc:
                        tx = tx_wall
                for kf, kx, ky in hero_kos:
                    if 0 <= kf - f <= bias_win:
                        w_ko = 0.6 * (1.0 - (kf - f) / max(1, bias_win))
                        tx = tx * (1.0 - w_ko) + kx * w_ko
                        ty = ty * (1.0 - w_ko) + ky * w_ko
                        focus = None
                        break
                tz = max(floor_z, min(zmax, tz))
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
        px, py = cx, cy
        if top:
            cx, cy, vx, vy = 0.0, 0.0, 0.0, 0.0
        else:
            cx, vx = _spring(cx, vx, tx, 4.5, dt)
            cy, vy = _spring(cy, vy, ty, 3.2, dt)
        cz, vz = _spring(cz, vz, tz, 7.0 if not top else 3.5, dt)
        if not top:
            cz = max(duel_min, min(zmax, cz))
        if focus is not None:             # lock mode: keep #1 inside the middle 65% of the frame
            fx, fy = float(rows[focus, 0]), float(rows[focus, 1])
            hw = W * 0.35 / cz
            mid, half = (VIEW_TOP + VIEW_BOTTOM) / 2, (VIEW_BOTTOM - VIEW_TOP) * 0.30
            cx = min(max(cx, fx - hw), fx + hw)
            cy = min(max(cy, fy + (SCREEN_CY - mid - half) / cz), fy + (SCREEN_CY - mid + half) / cz)
        cap_k = 1.0
        if everyone and not top:
            def on_screen(i: int, ccx: float, ccy: float) -> bool:
                sx = (rows[i, 0] - ccx) * cz + W / 2
                sy = (rows[i, 1] - ccy) * cz + SCREEN_CY
                return 40 < sx < W - 40 and VIEW_TOP + 40 < sy < VIEW_BOTTOM - 40
            if not any(on_screen(i, cx, cy) for i in everyone):
                # fast (but still eased) recovery pan toward the FRAMED target first, then heroes, then anyone
                off_y = (SCREEN_CY - (VIEW_TOP + VIEW_BOTTOM) / 2) / cz
                alive_h = [i for i in heroes if flags[i] & T.ALIVE]
                cands = [(tx, ty)] + [(float(rows[j, 0]), float(rows[j, 1]) - off_y)
                                      for j in sorted(alive_h or everyone, key=lambda i: -rows[i, 0])]
                cx, cy = next(((qx, qy) for qx, qy in cands if any(on_screen(i, qx, qy) for i in everyone)), cands[-1])
                cap_k = 3.0
        if not top and px is not None:
            # v4.3 strict max pan velocity -> zero teleports. The cap is RELATIVE to the framed action (680 / 520 px/s
            # on top of the pack's own velocity): the camera keeps pace with fast packs but can never whip-pan
            # between targets faster than that.
            avx = abs(float(np.mean(rows[act, 3]))) if act else 0.0
            avy = abs(float(np.mean(rows[act, 4]))) if act else 0.0
            mdx, mdy = (max_vx + avx) * cap_k * dt, (max_vy + avy) * cap_k * dt
            ncx = px + max(-mdx, min(mdx, cx - px))
            ncy = py + max(-mdy, min(mdy, cy - py))
            if everyone and cap_k > 1.0 and not any(on_screen(i, ncx, ncy) for i in everyone):
                ncx, ncy = cx, cy                             # last-resort rescue: never show an empty arena
                track.rescues += 1                            # type: ignore[attr-defined]
            if ncx != cx:
                vx = (ncx - px) / dt
            if ncy != cy:
                vy = (ncy - py) / dt
            cx, cy = ncx, ncy
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
