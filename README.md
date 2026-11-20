# Toon Toon Castle

A 100% free, fully automated pipeline on GitHub Actions. It simulates real 2D physics elimination games with
procedurally drawn cartoon contestants, picks the funniest real run, adds commentary from Rick Ricochet,
renders and publishes vertical Shorts and Reels. No AI image or video generation.

Build status: being built milestone by milestone (brief §24). Earlier projects: see `CLEANUP_LOG.md`.

## Decisions (documented per the brief)
- **Music**: procedural chiptune loops generated in code instead of downloaded CC0 tracks (zero licence risk).
- **Local runs**: every step runs on GitHub Actions; `preview.yml` renders previews (cast sheet, sample videos)
  and publishes them to the `preview` pre-release.

## Owner overrides to spec v3.0 (2026-11-20 review)
- **Extras are "bots"**: grey round robots with an antenna, hero-sized (r=24), 10-14 per Spotlight episode and 16 on
  Sundays (spec: 24-30 small sand-coloured extras). They panic at drops, jump lower and mostly lose (target <= 15%).
- **Shorter episodes for retention**: gameplay 20-27 s (forced resolution 27 s, hard stop 29 s), escalation at 9 s /
  17 s, winner replay 1.5 s at 0.3x, winner card 3.0 s with "COMMENT YOUR PICK!". Total video ~25-32 s.
- **HUD**: single-row status bar directly under the castle wall (y 312-416), clear of the Shorts/Reels bottom UI;
  Sundays show the 6 best-placed heroes. Comic popups render above the HUD.
- **Early action**: top-down arenas start shrinking at 3 s and open with Lord Tuno's "TUNO QUAKE!" lever at 1.5 s;
  hazards escalate harder than racers (speed multiplier ^ 1.8). Twists trigger earlier (generic 5 s, giant ball 7 s,
  shrinking arena 3 s).
- **Side-view courses end at the finish line for every goal**: the first contestant across resolves the episode.
- **Camera**: follows the top-3 leaders, hard-clamps the leader inside the middle 50% of the frame, never shows an
  empty frame, and zooms 1.5x on the final 3 survivors when they fit in frame.
- Cold-open teaser text is "WHO SURVIVES?".
