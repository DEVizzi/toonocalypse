# HANDOFF — Toon Toon Castle build (continue in a new conversation)

The governing spec is **"Toon Toon Castle: Master Build Brief & Technical Specification (v3.0)"**. The user pasted it on 2026-11-20 10:52 IST; ask them to paste it again if needed. Build strictly in the §24 milestone order.

## Environment
- **Repo:** `DEVizzi/toonocalypse` (public), local clone at `/Users/izazhaq/.gemini/jetski/scratch/toonocalypse`. The `gh` CLI is logged in as DEVizzi.
- **Local Python venv:** `/Users/izazhaq/.gemini/jetski/brain/cf3bf0c9-9524-4e74-aab1-43075b36ef1e/scratch/ttc-venv/bin/python` (Python 3.9).
  - It has pymunk 7.3.1, numpy, pyyaml and pytest.
  - It has **no pygame**: Santa blocks building it. ffmpeg is also Santa-blocked locally.
  - So physics and other pure-Python code can run locally; all rendering runs on GitHub Actions.
- **Code style:** `from __future__ import annotations` everywhere so 3.9 can run it. CI uses 3.11.
- **Preview workflow:** `.github/workflows/preview.yml`, input `command`. It runs any command on Actions and uploads `output/*` to the rolling `preview` pre-release. Links look like `https://github.com/DEVizzi/toonocalypse/releases/download/preview/<file>`.
- **Secrets in use:** GOOGLE_API_KEY, YOUTUBE_*, IG_*, GH_TOKEN. Still present but unused: KAGGLE_USERNAME, KAGGLE_API_TOKEN (listed in CLEANUP_LOG.md for revocation).

## Milestone status
- **M0 cleanup: DONE.** Tag `legacy-final` (also `legacy-v1`, `legacy-v2`); CLEANUP_LOG.md; gitleaks in CI; .gitignore.
- **M1 scaffold: DONE.**
  - `config/settings.yaml` holds the timeline, layout, physics and scorer values, plus `speed_centre` and `speed_spread`.
  - `src/config.py` provides TIMELINE, LAYOUT and W/H/FPS.
  - `requirements.txt` is pinned for Python 3.11 (numpy 2.3.5, scipy 1.16.3, pygame-ce 2.5.8, pymunk 7.3.1, ...).
  - Fonts: LuckiestGuy, Fredoka, Bangers, Anton, ComicNeue, each with its licence file; CREDITS.md.
- **M2 cast: DONE.** `docs/cast_sheet.png` committed (accepted).
- **M3 physics, recipes and scorer: tuning mostly done** (2026-11-20 session 2).
  - Pacing: `Sim._pacing()` computes a schedule-driven `pressure` (config `physics.pacing`) that drives the SIDE
    collapsing chase speed, TOP edge shrink (`edge_k` from 6 s, down to 0.12), bumper-ring shrink and hex crack load.
    LEFT BEHIND widens (`_behind_k`) when ahead of schedule. SIDE gap widths ramp along the course (`course_ramp`),
    courses are longer (`course_length_scale`).
  - Extras are now **bots** (owner decision): grey round robots with an antenna, hero-sized (r=24), 10-14 per
    Spotlight episode, 16 on Sundays; they freeze in cartoon panic at drops (`physics.extras`), jump lower, ignore
    far TOP goals. Goals: hold_a_zone is king-of-the-hill (contested = no points); hot potato tie-break = centre.
  - Hero tweaks: Juggernaut momentum (SIDE), Floater weak air control, TOP heroes keep wider edge margin.
  - Latest win shares (dev samples, `python -m tests.winstat MODE N`): SIDE extras ~12%, heroes 2-19%;
    TOP extras ~17-25%, Juggernaut ~25% (still over 20%). Still TODO: per-hero fine-tune with the 1,000-run
    sharded `test_balance.py` in a slow workflow; write test_physics_modes / test_scorer; ~45% of SIDE runs end
    < 26 s (Best-of-N now ranks in-range runs first, so the chosen run is usually fine).
  - Dev harnesses: `tests.winstat`, `tests.runlog`, `tests.simstat`, `tests.batch`.
- **M4 silent render: renders working; samples posted, awaiting owner review.**
  - `src/main.py` CLI (`--dry-run --seed --arena --goal --mode --kind rumble --flash-forward --stills N`).
  - Visual overhaul toward the owner's reference image: `src/rendering/scenery.py` (cloud sky + distant towers,
    castle header with Lord Tuno's balcony, white episode pill, bottom status panel with hero portraits and live
    ranks, floating rocky capped cliffs, floating top-down platforms with shadows), camera zoom 1.4 in SIDE and
    zoom-in as TOP arenas shrink (config `render`).
  - Latest samples (seeds 42 / 7 / 5): 38.1 s, 36.1 s, 44.2 s. Known: tiered_tower two-stage rumbles often end < 26 s
    (seeds 99/12 had no in-range run); TOP Juggernaut ~25% win share; the apt ffmpeg step occasionally times out (rerun).
  - Render takes ~10-20 s per video on Actions. `--stills N` saves half-size PNGs for review (I can't play mp4s).
- **M5–M8: not started.** Commentary/TTS/audio, state and lore, workflows and tokens, publishing.

## Notes
- The user wants progress links posted in chat and low polling/token use.
- Earlier projects (comic/Kaggle/FLUX) are abandoned; do not resume them.
