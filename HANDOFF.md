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
- **M2 cast: rendered and reviewed, still needs a re-render and commit.**
  - `tests/render_cast_sheet.py` produced the cast sheet, and it looked good.
  - Later tweaks: stronger rim, bigger Pip face, toned-down Glitch stripes, popups in 2 rows.
  - TODO: re-render via preview.yml, then commit `docs/cast_sheet.png` (acceptance).
  - Modules: `src/characters/{roster,expressions,renderer,tuno}.py`, `src/rendering/effects.py`.
- **M3 physics, recipes and scorer: IN PROGRESS** (code written, tuning not done).
  - Modules:
    - `src/physics/{engine,ai,trace,scorer,camera}.py`
    - `src/games/{base,arenas,goals,hazards,twists,themes,recipe_generator}.py`
  - Dev harnesses: `python -m tests.simstat any`, then `python -m tests.batch SIDE_VIEW 3` and `TOP_DOWN 5`.
  - Tests written but not yet run in CI: `tests/test_anti_repeat.py`, `tests/test_timeline.py`.
  - Tests still to write: test_physics_modes, test_scorer, test_balance (1000 runs per mode, which will need a sharded slow workflow).
  - Key fixes so far:
    - Drive forces are re-applied every substep (`Sim.push` / `_apply_drives`), because pymunk resets forces after each step.
    - Side-view drive also overcomes sliding friction, since rotation is locked.
    - Top-down uses capped velocity-error steering.
    - The left-behind camera proxy is eased, not monotonic.
    - In side view a "collapsing floor" chase (`chase_x`) is paced to reach the finish at about 36 s.
    - In top-down the walkable edge creeps inward from 12 s (`edge_k`).
    - Hex tiles use a load model (2.4 contestant-seconds), regrow until 22 s, and the AI flees loaded tiles.
    - Top-down avoidance steers away from the actual direction of the nearest drop (`edge_vector`).
  - Current state:
    - Simulations take about 0.5–1.8 s each.
    - Durations are mostly 26–36 s now.
    - **Extras still win about 50% of runs; the balance target is ≤15%.**
  - Next balance ideas:
    - Make extras less competent; they already have rim anchors, speed 130–180 before compression, a 0.6 force factor and poor jumping.
    - Run a parameter sweep.
    - Check per-hero win shares (5–20%).
- **M4 silent render: CODE WRITTEN, never run.**
  - `src/rendering/{hud,pipeline}.py` (shot planning, world, props, zones, contestants, juice, HUD, ffmpeg pipe) and `src/physics/camera.py`.
  - Next:
    1. Add `src/main.py` (CLI: `--dry-run --seed --arena --goal`). It should generate a recipe, simulate N seeds, score, pick the best, then call `pipeline.encode()`.
    2. Run it via preview.yml to make the 3 silent samples (side-view race, top-down sumo, Sunday rumble).
    3. Fix the bugs that show up.
- **M5–M8: not started.** Commentary/TTS/audio, state and lore, workflows and tokens, publishing.

## Notes
- The user wants progress links posted in chat and low polling/token use.
- Earlier projects (comic/Kaggle/FLUX) are abandoned; do not resume them.
