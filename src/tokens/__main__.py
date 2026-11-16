"""Token upkeep: Instagram long-lived token refresh (written back to GitHub Secrets via a libsodium sealed box),
daily watchdog for YouTube / Instagram / Kaggle / Gemini. Token values are never printed or stored in state."""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time

import requests

from src.common import alerts
from src.common.config import settings
from src.common.state import load_state, save_state

DAY = 86400


def days_left(expires_at: float | None, now: float) -> float | None:
    """None/0 expiry means a non-expiring token."""
    if not expires_at:
        return None
    return round((expires_at - now) / DAY, 2)


def needs_refresh(left: float | None, threshold: float) -> bool:
    return left is not None and left < threshold


def ig_expiry(token: str) -> float | None:
    """Return expires_at (epoch) or None if non-expiring. Works for EAA (Facebook login) and IGAA (Instagram login) tokens."""
    if token.startswith("IG"):
        r = requests.get("https://graph.instagram.com/me", params={"fields": "id", "access_token": token}, timeout=30)
        r.raise_for_status()
        return load_state("tokens.json", {}).get("instagram", {}).get("expires_at")
    r = requests.get("https://graph.facebook.com/debug_token", params={"input_token": token, "access_token": token}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", {})
    if not data.get("is_valid"):
        raise RuntimeError(f"Instagram token invalid: {data.get('error', {}).get('message', 'unknown')}")
    return data.get("expires_at") or data.get("data_access_expires_at") or None


def refresh_ig(token: str) -> tuple[str, float]:
    if not token.startswith("IG"):
        raise RuntimeError("Facebook-login (EAA) tokens can't be refreshed without the app secret. "
                           "Generate a new long-lived token (or a non-expiring Page token) and update IG_ACCESS_TOKEN.")
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j["access_token"], time.time() + int(j.get("expires_in", 60 * DAY))


def write_secret(name: str, value: str) -> None:
    from nacl import encoding, public

    repo = os.environ["GITHUB_REPOSITORY"]
    h = {"Authorization": f"Bearer {os.environ['GH_SECRETS_TOKEN']}", "Accept": "application/vnd.github+json"}
    key = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h, timeout=30).json()
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}", headers=h, timeout=30,
                 json={"encrypted_value": enc, "key_id": key["key_id"]}).raise_for_status()


def cmd_refresh() -> int:
    tok = os.environ["IG_ACCESS_TOKEN"]
    st = load_state("tokens.json", {})
    left = days_left(ig_expiry(tok), time.time())
    if needs_refresh(left, settings()["tokens"]["instagram_refresh_when_days_left"]):
        new, exp = refresh_ig(tok)
        print(f"::add-mask::{new}")
        write_secret("IG_ACCESS_TOKEN", new)
        st["instagram"] = {"expires_at": exp, "refreshed_at": time.time()}
        print(f"Instagram token refreshed; {days_left(exp, time.time())} days left")
    else:
        st.setdefault("instagram", {})["expires_at"] = None if left is None else time.time() + left * DAY
        print(f"Instagram token OK ({'non-expiring' if left is None else f'{left} days left'})")
    save_state("tokens.json", st)
    return 0


def cmd_watchdog() -> int:
    from src.publish import youtube

    problems, st = [], load_state("tokens.json", {})
    try:
        youtube.access_token()
    except Exception as e:
        problems.append(f"YouTube: {e}. Re-run the OAuth bootstrap (app must be 'In production').")
    try:
        left = days_left(ig_expiry(os.environ["IG_ACCESS_TOKEN"]), time.time())
        st.setdefault("instagram", {})["days_left"] = left
        if left is not None and left < 3:
            problems.append(f"Instagram token expires in {left} days")
    except Exception as e:
        problems.append(f"Instagram: {e}")
    if subprocess.run(["kaggle", "kernels", "list", "--mine", "--page-size", "1"], capture_output=True).returncode != 0:
        problems.append("Kaggle auth failed: kaggle.com -> Settings -> API -> Create New Token, update KAGGLE_API_TOKEN.")
    publish_problem = any(p.startswith(("YouTube", "Instagram")) for p in problems)
    st["publishing_paused"] = publish_problem
    st["pause_reason"] = "; ".join(p for p in problems if p.startswith(("YouTube", "Instagram"))) or None
    st["checked_at"] = time.time()
    save_state("tokens.json", st)
    if problems:
        alerts.open_or_update("Toonocalypse: token problem", "\n".join(f"- {p}" for p in problems)
                              + "\n\nPublishing is paused while YouTube/Instagram tokens are broken; generation continues.")
        return 0
    alerts.close_if_open("Tokens healthy again.")
    print("All tokens healthy.")
    return 0


if __name__ == "__main__":
    sys.exit({"refresh": cmd_refresh, "watchdog": cmd_watchdog}[sys.argv[1]]())
