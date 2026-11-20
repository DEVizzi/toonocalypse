# ToonToonCastle (`@ToonToonCastle`)

Autonomous 1-episode/day 2D physics marble-race championship pipeline on GitHub Actions, publishing daily to **YouTube Shorts** and **Instagram Reels**.

- **Zero AI video/image generation**: 100% real `pymunk` 2D rigid-body physics (`pygame-ce` 1080x1920@30 + `ffmpeg` H.264/AAC), procedural 8-season themes, procedural chiptune BGM, `edge-tts` voiceover (**MC Tuno**), and Gemini/Groq punch-up with a 115+ line offline comedy bank fallback.
- **IPL-Style 30-Episode Season League**: 26 Regular League races + Play-In (Ep 27) + Qualifier 1 (Ep 28) + Qualifier 2 (Ep 29) + Championship Grand Final (Ep 30), with automatic season rollover into `state/hall_of_fame.json`.
- **UI-Safe Video Branding**:
  - `TOONTOONCASTLE` network pill on MC Tuno's top-right Broadcast Booth frame.
  - Subtle `25%`-opacity `@ToonToonCastle` anti-scraper watermark centered at `y = 275`.
  - `@ToonToonCastle` header tag atop the IPL Standings Winner Card.
- **Daily Schedule (`17 14 * * *`)**: Renders 1 episode/day (~8:00 PM IST), validates with `ffprobe` + loudness + camera zoom sanity gates, sequentially publishes to YouTube Shorts and Instagram Reels with independent fault-tolerance + GitHub Issue alerts, and atomically commits `state/*.json`.
- **60-Day Instagram Token Maintenance (`0 10 1,15 * *`)**: Automatically refreshes `IG_ACCESS_TOKEN` every 45–50 days and opens a GitHub Issue immediately if refresh fails.

## Quick Commands

```bash
# Reset state cleanly to Season 1 • Race 1 / 30
python -m src.state.reset --yes

# Local dry-run preview (renders & validates without uploading or mutating state/)
python -m src.main --dry-run --stills 4 --out output/dry_run_s1_e1.mp4
python -m src.publish.validate output/dry_run_s1_e1.mp4
```
