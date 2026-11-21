"""Re-authorize the ToonToonCastle YouTube OAuth token with comment + edit scopes (run locally, once).

Why: the current YOUTUBE_REFRESH_TOKEN (minted by the old scripts/oauth_bootstrap.py) only has youtube.upload,
youtube.readonly and yt-analytics.readonly. Auto-comments, title/description edits and rollback deletes of partial
uploads also need youtube.force-ssl.

Usage (macOS system python3, no extra packages):
    python3 scripts/youtube_reauth.py --client-secrets ~/Downloads/client_secret_XXXX.json

- Use the Desktop-app OAuth client JSON from Google Cloud Console -> APIs & Services -> Credentials.
- Opens Google's consent screen in your browser (loopback redirect on 127.0.0.1 with PKCE + state).
- Verifies youtube.force-ssl was granted, then stores YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET /
  YOUTUBE_REFRESH_TOKEN directly in the GitHub repo secrets via `gh secret set` (stdin). Tokens are never printed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
REQUIRED_SCOPES = {SCOPES[0], SCOPES[1]}
_SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CALLBACK_TIMEOUT_S = 300


def load_client(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    block = data.get("installed") or data.get("web") or {}
    cid = str(block.get("client_id") or "").strip()
    csec = str(block.get("client_secret") or "").strip()
    if not cid.endswith(".apps.googleusercontent.com") or not csec:
        raise ValueError("client secrets JSON is missing a valid client_id/client_secret")
    return cid, csec


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(query)}"


def parse_callback(path: str, expected_state: str) -> str:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if qs.get("error"):
        raise ValueError(f"consent was not granted ({qs['error'][0][:60]})")
    got_state = (qs.get("state") or [""])[0]
    if not secrets.compare_digest(got_state.encode("utf-8"), expected_state.encode("utf-8")):
        raise ValueError("state mismatch (possible CSRF); aborting")
    code = (qs.get("code") or [""])[0]
    if not code:
        raise ValueError("no authorization code in the callback")
    return code


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if urllib.parse.urlparse(self.path).path != "/":
            self.send_response(404)
            self.end_headers()
            return
        self.server.callback_path = self.path  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h2>ToonToonCastle: authorization received. You can close this tab.</h2>")

    def log_message(self, *_args) -> None:  # never log the authorization code
        return


def wait_for_callback(server: http.server.HTTPServer, timeout_s: float = CALLBACK_TIMEOUT_S) -> str:
    deadline = time.monotonic() + timeout_s
    server.timeout = 2
    while time.monotonic() < deadline:
        server.handle_request()
        path = getattr(server, "callback_path", None)
        if path:
            return str(path)
    raise TimeoutError("no browser callback received within 5 minutes")


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str, verifier: str) -> dict:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode("ascii")
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https Google endpoint
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err = str(json.loads(exc.read().decode("utf-8")).get("error", "unknown"))[:60]
        except ValueError:
            err = "unparseable"
        raise RuntimeError(f"token exchange failed: HTTP {exc.code} ({err})") from None


def gh_secret_set(gh: str, repo: str, name: str, value: str) -> None:
    res = subprocess.run([gh, "secret", "set", name, "--repo", repo], input=value, text=True,
                         capture_output=True, timeout=60, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"`gh secret set {name}` failed (exit {res.returncode}); is `gh auth status` OK?")


def detect_repo(gh: str) -> str:
    res = subprocess.run([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                         capture_output=True, text=True, timeout=30, check=False,
                         cwd=str(Path(__file__).resolve().parent.parent))
    return res.stdout.strip() if res.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-authorize YouTube OAuth with youtube.force-ssl")
    ap.add_argument("--client-secrets", required=True, help="Desktop-app OAuth client JSON from Google Cloud Console")
    ap.add_argument("--repo", default=None, help="owner/name (default: this checkout's GitHub repo)")
    a = ap.parse_args(argv)
    gh = shutil.which("gh")
    if not gh:
        print("GitHub CLI `gh` not found; install it and run `gh auth login` first.", file=sys.stderr)
        return 2
    repo = a.repo or detect_repo(gh)
    if not _SAFE_REPO.match(repo or ""):
        print("Could not determine the GitHub repo; pass --repo owner/name", file=sys.stderr)
        return 2
    try:
        client_id, client_secret = load_client(Path(a.client_secrets).expanduser())
    except (OSError, ValueError) as exc:
        print(f"Could not read client secrets: {exc}", file=sys.stderr)
        return 2

    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    url = build_auth_url(client_id, redirect_uri, state, challenge)
    print("Opening Google consent in your browser. Sign in with the ToonToonCastle channel account and allow ALL")
    print("requested permissions (if you see 'Google hasn't verified this app': Advanced -> Go to app).")
    print(f"If the browser does not open, visit:\n{url}\n")
    webbrowser.open(url)
    try:
        code = parse_callback(wait_for_callback(server), state)
        tok = exchange_code(code, client_id, client_secret, redirect_uri, verifier)
    except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
        print(f"Re-authorization failed: {exc}", file=sys.stderr)
        return 1
    finally:
        server.server_close()

    granted = set(str(tok.get("scope") or "").split())
    missing = sorted(s.rsplit("/", 1)[-1] for s in REQUIRED_SCOPES - granted)
    refresh = str(tok.get("refresh_token") or "")
    if missing or not refresh:
        why = f"missing scopes: {', '.join(missing)}" if missing else "no refresh_token returned"
        print(f"Re-authorization incomplete ({why}). Re-run and tick every permission box.", file=sys.stderr)
        return 1
    try:
        gh_secret_set(gh, repo, "YOUTUBE_CLIENT_ID", client_id)
        gh_secret_set(gh, repo, "YOUTUBE_CLIENT_SECRET", client_secret)
        gh_secret_set(gh, repo, "YOUTUBE_REFRESH_TOKEN", refresh)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Got a new token but could not save it: {exc}", file=sys.stderr)
        return 1
    print("Done: YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN updated with scopes: "
          + ", ".join(sorted(s.rsplit("/", 1)[-1] for s in granted)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
