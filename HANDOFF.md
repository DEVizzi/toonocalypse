# HANDOFF — ToonToonCastle (`@ToonToonCastle`) v4.4 Production Launch

## Production Summary
- **Brand & Handle:** `ToonToonCastle` / `@ToonToonCastle`
- **Schedule:** `.github/workflows/daily.yml` (`17 14 * * *` -> ~8:00 PM IST, 1 episode/day) + manual `workflow_dispatch` (`dry_run: true/false`).
- **Dual Publishing:** Sequential YouTube Shorts (`src/publish/youtube.py`) + Instagram Reels (`src/publish/instagram.py`) after `ffprobe` + loudness + camera zoom sanity gates (`src/publish/validate.py`).
- **Token Maintenance:** `.github/workflows/token-keepalive.yml` (weekly YouTube OAuth check) + `.github/workflows/ig-token-refresh.yml` (`0 10 1,15 * *` 45-day Instagram long-lived token refresh & secret update).
- **State Persistence:** Only lightweight JSON files in `state/` (`season_state.json`, `episode_history.json`, `hall_of_fame.json`) are committed via atomic `.tmp` + `os.replace` writes and `git pull --rebase origin main`. All media (`*.mp4`, `*.wav`, `output/`, `renders/`, `tmp/`) is strictly gitignored.
