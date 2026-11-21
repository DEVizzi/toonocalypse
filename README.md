# ToonToonCastle (`@ToonToonCastle`)

Autonomous 1-episode/day 2D physics marble-race championship pipeline on GitHub Actions, publishing daily to **YouTube Shorts** and **Instagram Reels**.

- **Zero AI video/image generation**: 100% real `pymunk` 2D rigid-body physics (`pygame-ce` 1080x1920@30 + `ffmpeg` H.264/AAC), procedural 8-season themes, procedural chiptune BGM, `edge-tts` voiceover (**MC Tuno**), and Gemini punch-up with a 115+ line offline comedy bank fallback.
- **IPL-Style 30-Episode Season League**: 26 Regular League races + Play-In (Ep 27) + Qualifier 1 (Ep 28) + Qualifier 2 (Ep 29) + Championship Grand Final (Ep 30), with automatic season rollover into `state/hall_of_fame.json`.
- **Unclipped High-Contrast Video Branding (`_draw_brand_overlay`)**:
  - `TOONTOONCASTLE` dark-navy + gold broadcast plate (`#0F172A` / `#FACC15`) on MC Tuno's Booth Cam (`y = 238`).
  - `62%`-opacity (`alpha = 160`) `@ToonToonCastle` anti-scraper watermark (`30px` bold + `4px` black outline) centered at `(540, 282)`.
  - `TOONTOONCASTLE` gold-on-navy header bar (`34px`) atop the IPL Standings Winner Card (`(540, 336)`).
- **Transactional 1x/Day Production Lock (`.github/workflows/daily_episode.yml` -> `run_daily_episode.py`)**:
  - Single daily cron `17 14 * * *` (~8:00 PM IST), `concurrency: { group: toontooncastle-daily, cancel-in-progress: false }`, and a startup **Same-Day Duplicate Guard** (`utc_date` + `published: true`).
  - Staged safe publish (Step A render/gates -> Step B IG Reels container `FINISHED` -> Step C YouTube upload + IG `media_publish` -> Step D temp release cleanup + atomic `state/*.json` commit/push).
  - Hard **10-minute (`600s`) watchdog** with full local/remote/state rollback (`videos.delete`, temp IG release delete, verbatim `state/*.json` restore) and 1 automatic recreation (`MAX_ATTEMPTS = 2`).
- **60-Day Instagram Token Maintenance (`0 10 1,15 * *`)**: Automatically refreshes `IG_ACCESS_TOKEN` every 45–50 days and opens a GitHub Issue immediately if refresh fails.
- **v4.6 Viral SEO & Engagement ([metadata.py](src/publish/metadata.py), [engage.py](src/publish/engage.py))**:
  - Spoiler-free rotating "pick a ball" titles (≤ 60 chars, no `#shorts`), separate YouTube description vs Instagram caption (DM-share prompt, ≤ 5 hashtags), truthful keyword tags, Gaming category.
  - Best-effort "Which ball did you pick?" first comment on YouTube + Instagram after every publish (never blocks or rolls back a live episode). **Pin the YouTube comment manually** (the API can't pin).
  - `.github/workflows/engage.yml` (manual): re-applies the SEO metadata + first comments to an already-published episode.

## Quick Commands

```bash
# Reset state cleanly to Season 1 • Race 1 / 30
python -m src.state.reset --yes

# Transactional dry-run preview + brand verification stills (no uploads, state/ untouched)
python run_daily_episode.py --dry-run --brand-stills --out output/dry_run_s1_e1.mp4
```
