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


def track_window(trace: T.Trace, view_w: float = 1080.0, view_h: float = 810.0) -> list[Cam]:
    """Part 5 recap camera: frames the action for a `view_w x view_h` (4:3) window centred on SCREEN_CY.

    Unlike `track` (tuned for the tall 9:16 Shorts viewport), this fits BOTH axes of the widescreen window:
    - SIDE_VIEW: densest cluster of living heroes (front-runners win ties) + any hero knockout happening within
      the next 0.5 s / last 0.6 s, fitted with padding; zoom 0.60x-1.55x (tight on the final 3).
    - TOP_DOWN: whole platform fitted to the 4:3 window, zooming in as the arena shrinks / on the final 3.
    Guarantees at least one living hero inside the window on every frame (when any is alive)."""
    meta = trace.meta
    rs = settings()["render"]
    top = trace.mode == "TOP_DOWN"
    x0, y0, x1, y1 = meta["bounds"]
    hero_idx = {trace.index(k) for k in meta["heroes"] if k in trace.keys}
    pre = meta.get("preroll_frames", 0)
    kos = [(pre + int(e.t * FPS), float(e.pos[0]), float(e.pos[1])) for e in trace.events
           if e.kind == "elimination" and e.data.get("hero") and e.pos is not None]
    ko_pre, ko_post = int(0.5 * FPS), int(0.6 * FPS)
    dt = 1.0 / FPS
    pad = 140.0
    zmin, zmax_live, zmax_f3 = 0.56, 1.22, 1.55
    win_w, win_h = view_w / 0.62, view_h / 0.62          # cluster window in world px
    top_zmax = float(rs.get("top_zoom_max", 2.0))
    if top:
        span = max(x1 - x0, (y1 - y0) * view_w / view_h)
        base = min(1.15, view_w / max(1.0, span)) * float(rs.get("top_zoom", 1.0))
        r0 = next((float(s["r"]) for s in meta.get("statics", []) if s.get("type") == "ring"),
                  float(trace.zones[0].get("ring_r", 1.0)))
    cams: list[Cam] = []
    cx = cy = None
    cz = 1.0
    vx = vy = vz = 0.0
    last_t = (0.0, 0.0)
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        alive = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        alive_h = [i for i in alive if i in hero_idx] or alive
        ko_pts = [(kx, ky) for kf, kx, ky in kos if -ko_pre <= f - kf <= ko_post]
        if top:
            z0 = trace.zones[f]
            ring_scale = float(z0.get("ring_r", r0)) / max(1.0, r0)
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * ring_scale
            tz = base * min(top_zmax, max(1.0, 1.0 / max(ek, 1e-3)))
            tx = ty = 0.0
            if 1 <= len(alive) <= 3:
                xs = [float(rows[i, 0]) for i in alive]
                ys = [float(rows[i, 1]) for i in alive]
                lim = 135.0 * max(0.35, ek)
                tx = max(-lim, min(lim, 0.5 * (min(xs) + max(xs))))
                ty = max(-lim, min(lim, 0.5 * (min(ys) + max(ys))))
                tz = min(base * 2.0, max(tz, base * 1.35))
        elif not alive_h:
            tx, ty = last_t
            tz = cz
        else:
            hp = np.array([[float(rows[i, 0]), float(rows[i, 1])] for i in alive_h])
            order_x = np.argsort(np.argsort(hp[:, 0])) / max(1, len(hp) - 1)   # 0 = last, 1 = front
            best_j, best_s = 0, -1.0
            for j in range(len(hp)):
                m = (np.abs(hp[:, 0] - hp[j, 0]) <= win_w / 2) & (np.abs(hp[:, 1] - hp[j, 1]) <= win_h / 2)
                s = float(m.sum()) + 0.35 * float(order_x[j])
                if s > best_s:
                    best_j, best_s = j, s
            c = hp[best_j]
            m = (np.abs(hp[:, 0] - c[0]) <= win_w / 2) & (np.abs(hp[:, 1] - c[1]) <= win_h / 2)
            pts = [tuple(p) for p in hp[m]]
            for kx, ky in ko_pts:
                if abs(kx - c[0]) <= win_w * 0.7 and abs(ky - c[1]) <= win_h * 0.7:
                    pts.append((kx, ky))
            px_ = [p[0] for p in pts]
            py_ = [p[1] for p in pts]
            bw = max(px_) - min(px_) + 2 * pad
            bh = max(py_) - min(py_) + 2 * pad
            cap = zmax_f3 if len(alive) <= 3 else zmax_live
            tz = max(zmin, min(cap, view_w / bw, view_h / bh))
            tx = 0.5 * (min(px_) + max(px_))
            ty = 0.5 * (min(py_) + max(py_))
            hw = view_w / 2 / tz
            if x1 - x0 > 2 * hw:
                tx = min(max(tx, x0 + hw), x1 - hw)
        last_t = (tx, ty)
        if cx is None:
            cx, cy, cz = tx, ty, tz
        cx, vx = _spring(cx, vx, tx, 3.4 if not top else 4.0, dt)
        cy, vy = _spring(cy, vy, ty, 3.0 if not top else 4.0, dt)
        cz, vz = _spring(cz, vz, tz, 2.6, dt)
        # Hard guarantee: >= 1 living hero inside the window (with a 48 px margin)
        if alive_h and not top:
            hw_s, hh_s = view_w / 2 - 48.0, view_h / 2 - 48.0
            inside = any(abs((float(rows[i, 0]) - cx) * cz) <= hw_s and abs((float(rows[i, 1]) - cy) * cz) <= hh_s
                         for i in alive_h)
            if not inside:
                anc = min(alive_h, key=lambda i: abs(float(rows[i, 0]) - cx) + abs(float(rows[i, 1]) - cy))
                ax, ay = float(rows[anc, 0]), float(rows[anc, 1])
                cx = min(max(cx, ax - hw_s / cz), ax + hw_s / cz)
                cy = min(max(cy, ay - hh_s / cz), ay + hh_s / cz)
                vx = vy = 0.0
        shake = (0.0, 0.0)
        for kf, _, _ in kos:
            k = f - kf
            if 0 <= k < 8:
                amp = 7.0 * (1 - k / 8)
                shake = (amp * math.sin(k * 2.7 + kf), amp * math.cos(k * 3.1 + kf))
        cams.append(Cam(cx, cy, cz, shake))
    return cams


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


def final3_zoom_target(spread: float, duel_min: float = 0.76) -> tuple[float, bool]:
    """v5.0 Final-3 dynamic zoom (1.40x-1.60x when clustered, smooth pullback for mid-spread, leader lock if >1100px)."""
    if spread <= 520.0:
        return 1.60 - 0.20 * (spread / 520.0), False
    if spread <= 1100.0:
        return max(duel_min, min(1.40, (W * 0.86) / (spread + 260.0))), False
    return 1.42, True


def track(trace: T.Trace, screen_w: float | None = None, screen_cy: float | None = None) -> list[Cam]:
    """One camera per trace frame:
    - Smooth spring damping + top-3 leader tracking on side-scrolling courses.
    - Automated Final-3 dynamic zoom (1.4x-1.6x) centered on remaining survivors' bounding box across ALL modes.
    - Hard viewport clamp guaranteeing >= 1 living character stays inside the middle 50% horizontal frame at all times."""
    sw = float(screen_w or W)
    scy = float(screen_cy or SCREEN_CY)
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
    max_vx = float(rs.get("cam_max_vx", 760.0))
    max_vy = float(rs.get("cam_max_vy", 560.0))
    hyst_f = int(round(float(rs.get("cam_switch_hysteresis_s", 0.55)) * FPS))
    window = float(rs["cluster_window_px"])
    lock_px = float(rs["leader_lock_px"])
    top_zmax = float(rs["top_zoom_max"])
    hero_kos = [(pre + int(e.t * FPS), e.pos[0], e.pos[1]) for e in trace.events
                if e.kind == "elimination" and e.data.get("hero") and e.pos is not None]
    bias_win = int(0.45 * FPS)
    r0 = next((float(s["r"]) for s in meta.get("statics", []) if s.get("type") == "ring"),
              float(trace.zones[0].get("ring_r", 1.0)))
    vert_tower = bool(meta.get("vertical_tower", False))
    held_lead: int | None = None
    cand_lead: int | None = None
    cand_since = 0
    tower_ty: float | None = None
    track.rescues = 0                           # type: ignore[attr-defined]
    for f in range(trace.n_frames):
        rows, flags = trace.frames[f], trace.flags[f]
        everyone = [i for i in range(len(rows)) if flags[i] & T.ALIVE]
        focus = None
        floor_z = zmin
        act: list[int] = []
        if top:
            z0 = trace.zones[f]
            ring_scale = float(z0.get("ring_r", r0)) / max(1.0, r0)
            ek = z0.get("edge_k", 1.0) * z0.get("shrink", 1.0) * ring_scale
            tz = base_zoom * min(top_zmax, max(1.0, 1.0 / max(ek, 1e-3)))
            if 1 <= len(everyone) <= 3:
                # P1.4: Automated Final-3 dynamic zoom (1.4x-1.6x+) centered on remaining characters' bounding box
                sx_ = np.array([float(rows[i, 0]) for i in everyone])
                sy_ = np.array([float(rows[i, 1]) for i in everyone])
                bx = float(0.5 * (sx_.min() + sx_.max()))
                by = float(0.5 * (sy_.min() + sy_.max()))
                lim = 135.0 * max(0.35, ek)
                tx = max(-lim, min(lim, bx))
                ty = max(-lim, min(lim, by))
                f3_floor = min(base_zoom * 2.02, max(1.42, base_zoom * 1.50))
                tz = min(base_zoom * 2.02, max(tz, f3_floor))
            else:
                tx, ty = 0.0, 0.0
        elif vert_tower:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            if not alive:
                tx, ty, tz = (cx if cx is not None else 660.0), (cy if cy is not None else 0.0), max(zmin, 0.86)
            elif len(everyone) <= 3:
                sx_ = np.array([float(rows[i, 0]) for i in everyone])
                sy_ = np.array([float(rows[i, 1]) for i in everyone])
                spread = float(math.hypot(sx_.max() - sx_.min(), sy_.max() - sy_.min()))
                tz, _ = final3_zoom_target(spread, duel_min)
                tx = float(0.5 * (sx_.min() + sx_.max()))
                ty = float(0.5 * (sy_.min() + sy_.max())) - 20.0
                act = list(everyone)
                tx = min(max(tx, x0 + sw / 2 / tz), x1 - sw / 2 / tz)
                ty = min(max(ty, y0 + 240), y1 - 200)
            else:
                ys = [float(rows[i, 1]) for i in alive]
                m = [alive[j] for j in action_cluster(ys, 620.0)]
                act = m
                mx = rows[m, 0]
                my = rows[m, 1]
                tx = 660.0 + max(-90.0, min(90.0, float(np.mean(mx)) - 660.0))
                half_w = sw / 2 / max(zmin, 0.86) - 90.0
                tx = max(float(mx.max()) - half_w, min(float(mx.min()) + half_w, tx))
                ty_raw = float(np.mean(my))
                tower_ty = ty_raw if tower_ty is None else max(ty_raw, tower_ty - 70.0 * dt)
                ty = tower_ty
                span_y = float(my.max() - my.min()) + 480.0
                tz = max(zmin, min(1.05, ((VIEW_BOTTOM - VIEW_TOP) * 0.82) / span_y, 0.88 if len(alive) > 4 else 1.15))
                tx = min(max(tx, x0 + sw / 2 / tz), x1 - sw / 2 / tz)
                ty = min(max(ty, y0 + 280), y1 - 220)
        else:
            alive = [i for i in heroes if flags[i] & T.ALIVE] or everyone
            tz = base_zoom
            if not alive:
                tx, ty = (cx if cx is not None else 0.0), (cy if cy is not None else 0.0)
            else:
                xs = [float(rows[i, 0]) for i in alive]
                raw_lead = alive[int(np.argmax(xs))]
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

                # P0.2: Weighted centroid of top 3 living characters (55% #1, 30% #2, 15% #3)
                top3 = sorted(alive, key=lambda i: -float(rows[i, 0]))[:3]
                w3 = (0.55, 0.30, 0.15)[:len(top3)]
                w3_sum = sum(w3)
                top3_x = sum(float(rows[idx, 0]) * wt for idx, wt in zip(top3, w3)) / w3_sum
                top3_y = sum(float(rows[idx, 1]) * wt for idx, wt in zip(top3, w3)) / w3_sum

                if len(everyone) <= 3:
                    # P1.4: Automated Final-3 dynamic zoom (1.4x-1.6x) centered on remaining survivors' bounding box
                    sx_ = np.array([float(rows[i, 0]) for i in everyone])
                    sy_ = np.array([float(rows[i, 1]) for i in everyone])
                    spread = float(math.hypot(sx_.max() - sx_.min(), (sy_.max() - sy_.min()) * 0.6))
                    tz, edge_mode = final3_zoom_target(spread, duel_min)
                    floor_z = duel_min
                    act = list(everyone)
                    if edge_mode:
                        tx, ty = lead_x - 80, lead_y - 24
                        focus = lead
                        floor_z = 1.40
                        act = [lead]
                    else:
                        tx = float(0.5 * (sx_.min() + sx_.max()))
                        ty = float(0.5 * (sy_.min() + sy_.max())) - 24
                elif near_finish:
                    act = top3
                    tx = 0.72 * lead_x + 0.28 * top3_x
                    ty = 0.72 * lead_y + 0.28 * top3_y - 28
                    focus = lead
                else:
                    m = [alive[j] for j in action_cluster(xs, window)]
                    act = list(dict.fromkeys(top3 + m))
                    mx = rows[m, 0]
                    clust_x = float(np.mean(mx))
                    clust_y = float(np.median(rows[m, 1]))
                    # Blend top-3 weighted centroid (70%) with pack cluster (30%) so fast leaders on Flat Track never leave frame
                    tx = 0.70 * top3_x + 0.30 * clust_x
                    ty = 0.65 * top3_y + 0.35 * clust_y - 28
                    t3_span = float(max(rows[i, 0] for i in top3) - min(rows[i, 0] for i in top3))
                    span = max(t3_span, min(720.0, float(mx.max() - mx.min()))) + 340.0
                    tz = (sw * 0.86) / span
                chase = trace.zones[f].get("chase_x")
                if chase is not None and any(float(rows[i, 0]) < chase + 240 for i in everyone):
                    tzc = max(floor_z, min(zmax, tz))
                    tx_wall = chase + (sw / 2 - 110) / tzc
                    if tx > tx_wall and lead_x - tx_wall < (sw * 0.24) / tzc:
                        tx = tx_wall
                for kf, kx, ky in hero_kos:
                    if 0 <= kf - f <= bias_win and abs(kx - top3_x) < sw * 0.42:
                        w_ko = 0.45 * (1.0 - (kf - f) / max(1, bias_win))
                        tx = tx * (1.0 - w_ko) + kx * w_ko
                        ty = ty * (1.0 - w_ko) + ky * w_ko
                        focus = None
                        break
                tz = max(floor_z, min(zmax, tz))
            tx = min(max(tx, x0 + sw / 2 / tz), x1 - sw / 2 / tz)
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
            cx, vx = _spring(cx, vx, tx, 4.2, dt)
            cy, vy = _spring(cy, vy, ty, 4.2, dt)
        else:
            cx, vx = _spring(cx, vx, tx, 5.2, dt)
            cy, vy = _spring(cy, vy, ty, 3.8, dt)
        cz, vz = _spring(cz, vz, tz, 6.5 if not top else 4.2, dt)
        if not top:
            cz = max(duel_min, min(zmax, cz))
        if focus is not None and not top:
            fx, fy = float(rows[focus, 0]), float(rows[focus, 1])
            hw = sw * 0.24 / cz
            mid, half = (VIEW_TOP + VIEW_BOTTOM) / 2, (VIEW_BOTTOM - VIEW_TOP) * 0.28
            cx = min(max(cx, fx - hw), fx + hw)
            cy = min(max(cy, fy + (scy - mid - half) / cz), fy + (scy - mid + half) / cz)
        if not top and px is not None:
            avx = abs(float(np.mean(rows[act, 3]))) if act else 0.0
            avy = abs(float(np.mean(rows[act, 4]))) if act else 0.0
            mdx, mdy = (max_vx + avx) * dt, (max_vy + avy) * dt
            cx = px + max(-mdx, min(mdx, cx - px))
            cy = py + max(-mdy, min(mdy, cy - py))

        shake = (0.0, 0.0)
        for cf in thuds:
            if 0 <= f - cf < 3:
                shake = (0.0, 3.0 * (1 if (f - cf) % 2 == 0 else -1))
        for cf, s in chaos:
            k = f - cf
            if 0 <= k < 10:
                amp = (14 if not top else 7) * s * (1 - k / 10)
                shake = (amp * math.sin(k * 2.7 + cf), amp * math.cos(k * 3.1 + cf))

        # P0.2 Hard Viewport Clamp: guarantee >= 1 living character is inside the middle 50% horizontal frame [0.25*sw, 0.75*sw]
        if everyone and not top:
            x_lo_s, x_hi_s = sw * 0.25 + 4.0, sw * 0.75 - 4.0
            y_lo_s, y_hi_s = VIEW_TOP + 100.0, VIEW_BOTTOM - 84.0   # margin > test band so no edge-pixel misses

            def in_mid50(i: int, ccx: float, ccy: float) -> bool:
                sx = (float(rows[i, 0]) - ccx) * cz + sw / 2.0 + shake[0]
                sy = (float(rows[i, 1]) - ccy) * cz + scy + shake[1]
                return x_lo_s <= sx <= x_hi_s and y_lo_s <= sy <= y_hi_s

            if not any(in_mid50(i, cx, cy) for i in everyone):
                alive_h = [i for i in heroes if flags[i] & T.ALIVE] or everyone
                anc = min(
                    alive_h,
                    key=lambda i: abs(float(rows[i, 0]) - cx) + 0.5 * abs(float(rows[i, 1]) - cy),
                )
                ax, ay = float(rows[anc, 0]), float(rows[anc, 1])
                cx_min = ax + (sw / 2.0 + shake[0] - x_hi_s) / cz
                cx_max = ax + (sw / 2.0 + shake[0] - x_lo_s) / cz
                cx = min(max(cx, cx_min), cx_max)
                cy_min = ay + (scy + shake[1] - y_hi_s) / cz
                cy_max = ay + (scy + shake[1] - y_lo_s) / cz
                if cy_min <= cy_max:
                    cy = min(max(cy, cy_min), cy_max)
                else:
                    cy = ay
                vx = (cx - px) / dt if px is not None else 0.0
                vy = (cy - py) / dt if py is not None else 0.0
                track.rescues += 1                            # type: ignore[attr-defined]

        cams.append(Cam(cx, cy, cz, shake))
    return cams
