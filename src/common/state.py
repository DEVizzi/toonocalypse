"""Atomic state JSON helpers."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.common.config import STATE_DIR


def load_state(filename: str, default: Any = None) -> Any:
    path = STATE_DIR / filename
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(filename: str, data: Any) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / filename
    fd, tmp_name = tempfile.mkstemp(dir=str(STATE_DIR), prefix=f".{filename}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path
