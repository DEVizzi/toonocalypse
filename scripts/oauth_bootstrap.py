"""One-time local OAuth2 bootstrap helper to obtain a YouTube refresh token.

Run locally ONLY when setting up or rotating YOUTUBE_REFRESH_TOKEN:
    python3 scripts/oauth_bootstrap.py --client-secrets client_secret.json
"""
from __future__ import annotations

import argparse
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secrets", required=True, help="Path to OAuth client_secret.json")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\nCopy these values into GitHub Repository Secrets:")
    print(f"YOUTUBE_CLIENT_ID     = {creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET = {creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN = {creds.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
