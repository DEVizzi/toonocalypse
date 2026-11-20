"""Trace recorder (§10.8): compact per-frame record of every body at 30 fps. The renderer draws ONLY from this."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# contestant flag bits
ALIVE, STUNNED, AIRBORNE, WINNER, FALLING, FAN_FAV, HAS_BOMB, VICTORY = 1, 2, 4, 8, 16, 32, 64, 128


@dataclass
class Event:
    t: float                    # gameplay time (s)
    kind: str                   # elimination | impact | lead_change | mass_wipeout | trait | escalation | twist | win | ...
    actors: list[str]           # contestant keys involved (first = subject)
    data: dict[str, Any] = field(default_factory=dict)
    pos: tuple[float, float] | None = None


@dataclass
class Trace:
    fps: int
    mode: str
    keys: list[str]                                   # contestant keys (column order)
    frames: list[np.ndarray] = field(default_factory=list)   # each: [n, 6] x, y, angle, vx, vy, scale
    flags: list[np.ndarray] = field(default_factory=list)    # each: [n] uint8
    expr: list[np.ndarray] = field(default_factory=list)     # each: [n] uint8 (index into EXPRESSIONS)
    props: list[np.ndarray] = field(default_factory=list)    # each: [m, 3] x, y, angle for dynamic/kinematic props
    zones: list[dict[str, Any]] = field(default_factory=list)  # per-frame zone state (lava y, tiles, shrink, items...)
    events: list[Event] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)       # static geometry, prop styles, winner, timings

    def record(self, rows: np.ndarray, flags: np.ndarray, expr: np.ndarray, props: np.ndarray, zone: dict) -> None:
        self.frames.append(rows.astype(np.float32))
        self.flags.append(flags.astype(np.uint8))
        self.expr.append(expr.astype(np.uint8))
        self.props.append(props.astype(np.float32))
        self.zones.append(zone)

    @property
    def n_frames(self) -> int:
        return len(self.frames)

    @property
    def duration(self) -> float:
        return self.n_frames / self.fps

    def index(self, key: str) -> int:
        return self.keys.index(key)

    def sample(self, t: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Interpolated positions at time t (used by the slow-mo replay)."""
        f = max(0.0, min(t * self.fps, self.n_frames - 1.001))
        i = int(f)
        a = f - i
        j = min(i + 1, self.n_frames - 1)
        rows = self.frames[i] * (1 - a) + self.frames[j] * a
        return rows, self.flags[i], self.expr[i]

    def events_of(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]
