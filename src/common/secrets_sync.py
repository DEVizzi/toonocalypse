"""Encrypt and update GitHub Actions secrets via the GitHub REST API."""
from __future__ import annotations

import base64
import os
import requests
from nacl import encoding, public


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    pub = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    box = public.SealedBox(pub)
    encrypted = box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_github_secret(secret_name: str, secret_value: str, repo: str | None = None, pat: str | None = None) -> None:
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    pat = pat or os.environ.get("GH_PAT_SECRETS", "")
    if not repo or not pat:
        raise RuntimeError("GITHUB_REPOSITORY and GH_PAT_SECRETS are required to rotate secrets.")

    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    key_resp = requests.get(key_url, headers=headers, timeout=20)
    key_resp.raise_for_status()
    key_data = key_resp.json()

    encrypted_val = encrypt_secret(key_data["key"], secret_value)
    put_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
    put_resp = requests.put(
        put_url,
        headers=headers,
        json={"encrypted_value": encrypted_val, "key_id": key_data["key_id"]},
        timeout=20,
    )
    put_resp.raise_for_status()
