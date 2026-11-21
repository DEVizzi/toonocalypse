# HANDOFF — ToonToonCastle (`@ToonToonCastle`) v4.5 Production Lock

## Production Summary
- **Brand & Handle:** `ToonToonCastle` / `@ToonToonCastle`
- **Schedule:** `.github/workflows/daily_episode.yml` (`17 14 * * *` -> ~8:00 PM IST, strictly 1 episode/day, `concurrency: toontooncastle-daily`, Same-Day Duplicate Guard) + manual `workflow_dispatch` (`dry_run`, `force_run`, `privacy`).
- **Transactional Supervisor (`run_daily_episode.py`):** Pre-attempt `state/*.json` snapshot, Staged Publish (Step A render + `ffprobe`/loudness/camera gates -> Step B IG Reels container `FINISHED` -> Step C YouTube Short upload + IG `media_publish` -> Step D temp IG release cleanup + atomic `state/*.json` push), strict `600s` (10-min) watchdog, full local/remote/state rollback, and 1 automatic recreation (`MAX_ATTEMPTS = 2`).
- **Token Maintenance:** `.github/workflows/token-keepalive.yml` (weekly YouTube OAuth check) + `.github/workflows/ig-token-refresh.yml` (`0 10 1,15 * *` 45-day Instagram long-lived token refresh & secret update).
- **SEO & Engagement (v4.6):** `src/publish/metadata.py` builds spoiler-free titles/descriptions/captions/tags; `src/publish/engage.py` posts best-effort first comments after Step D (pin the YouTube one manually). Comments + YouTube metadata edits need the `youtube.force-ssl` scope and an Instagram token with comment permission; `token-keepalive.yml` prints the granted YouTube scopes. `.github/workflows/engage.yml` retrofits an already-published episode.
- **Active Repository Secrets (7 total):** `GOOGLE_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `IG_ACCESS_TOKEN`, `IG_USER_ID`, `GH_TOKEN`.
- **State Persistence:** Only lightweight JSON files in `state/` (`season_state.json`, `episode_history.json`, `hall_of_fame.json`) are committed via atomic `.tmp` + `os.replace` writes and `git pull --rebase origin main`. All media (`*.mp4`, `*.wav`, `output/`, `renders/`, `tmp/`) is strictly gitignored.
