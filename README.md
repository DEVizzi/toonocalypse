# Toon Toon Castle

A 100% free, fully automated pipeline on GitHub Actions. It simulates real 2D physics elimination games with
procedurally drawn cartoon contestants, picks the funniest real run, adds commentary from Rick Ricochet,
renders and publishes vertical Shorts and Reels. No AI image or video generation.

Build status: being built milestone by milestone (brief §24). Earlier projects: see `CLEANUP_LOG.md`.

## Decisions (documented per the brief)
- **Music**: procedural chiptune loops generated in code instead of downloaded CC0 tracks (zero licence risk).
- **Local runs**: every step runs on GitHub Actions; `preview.yml` renders previews (cast sheet, sample videos)
  and publishes them to the `preview` pre-release.
