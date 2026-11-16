"""Tiny JSON state store under state/. Writes are atomic (temp file + rename)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.common.config import STATE_DIR


def state_path(name: str) -> Path:
    return STATE_DIR / name


def load_state(name: str, default: Any = None) -> Any:
    p = state_path(name)
    if not p.exists():
        return {} if default is None else json.loads(json.dumps(default))
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(name: str, data: Any) -> None:
    p = state_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
