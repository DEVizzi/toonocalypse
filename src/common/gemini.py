"""Gemini text + vision client (google-genai, api_version v1beta).

- models.list() at startup, cached 24h in state/models_cache.json.
- 404 -> model skipped for the rest of this run. 429 -> retryDelay recorded in state/quota.json.
- Never returns template text: if no model answers, raises Abort.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.common.config import models
from src.common.quota import Quota
from src.common.retry import Abort
from src.common.state import load_state, save_state

_client = None
_skipped_this_run: set[str] = set()


def client():
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise Abort("GOOGLE_API_KEY is not set")
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version=models()["gemini"]["api_version"]))
    return _client


def discover(kind: str = "text") -> list[str]:
    """Return configured models (in preference order) that exist for this key."""
    cfg = models()["gemini"]
    cache = load_state("models_cache.json", {})
    fresh = cache.get("at") and datetime.fromisoformat(cache["at"]) > datetime.now(timezone.utc) - timedelta(hours=cfg["discovery_cache_hours"])
    if not fresh:
        names = sorted({m.name.split("/")[-1] for m in client().models.list()})
        cache = {"at": datetime.now(timezone.utc).isoformat(), "available": names}
        save_state("models_cache.json", cache)
    available = set(cache.get("available", []))
    return [m for m in cfg[kind] if m in available and m not in _skipped_this_run]


def _retry_seconds(err: Exception) -> float:
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(err))
    return float(m.group(1)) if m else 60.0


def generate(contents: list[Any] | str, step: str, kind: str = "text", want_json: bool = False,
             quota: Quota | None = None) -> tuple[str, str]:
    """Return (text, model_used). Tries discovered models in order; logs which one served."""
    from google.genai import errors, types

    q = quota or Quota()
    cfg = types.GenerateContentConfig(response_mime_type="application/json") if want_json else None
    last = "no models available"
    for model in discover(kind):
        if not q.gemini_model_available(model):
            last = f"{model} waiting on retryDelay"
            continue
        try:
            resp = client().models.generate_content(model=model, contents=contents, config=cfg)
            q.gemini_record_call()
            q.save()
            text = (resp.text or "").strip()
            if not text:
                last = f"{model} returned empty text"
                continue
            print(f"[gemini:{step}] served by {model}", flush=True)
            return text, model
        except errors.ClientError as e:
            if e.code == 404:
                _skipped_this_run.add(model)
                last = f"{model} 404"
            elif e.code == 429:
                q.gemini_rate_limited(model, _retry_seconds(e))
                q.save()
                last = f"{model} 429"
            else:
                raise
            print(f"[gemini:{step}] {last}; next model", flush=True)
        except errors.ServerError as e:
            last = f"{model} {e.code}"
            print(f"[gemini:{step}] {last}; next model", flush=True)
    raise Abort(f"Gemini unavailable for {step}: {last}")


def generate_json(contents: list[Any] | str, step: str, kind: str = "text", quota: Quota | None = None) -> tuple[Any, str]:
    text, model = generate(contents, step, kind=kind, want_json=True, quota=quota)
    m = re.search(r"[\[{][\s\S]*[\]}]", text)
    if not m:
        raise ValueError(f"No JSON in {step} response from {model}")
    return json.loads(m.group(0)), model
