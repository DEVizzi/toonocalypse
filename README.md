# Toonocalypse — Automated Motion-Comic Pipeline

Zero-cost, quality-first, automated family-friendly motion-comic channel starring the 26-hero Toonocalypse cast, running exclusively on **GitHub Actions** and publishing up to **1 episode per day** to **YouTube Shorts** and **Instagram Reels**, plus weekly **long-form 16:9 compilations**.

## Core Principles
1. **Quality over cadence**: Substandard or fallback episodes are never published. Skipping a day is acceptable; degrading is not.
2. **Zero cost**: Free tiers and open-source tools only (`GOOGLE_API_KEY` free tier, Kaggle free GPU batch notebooks, Piper TTS fallback, FFmpeg).
3. **Fail fast**: Preflight checks run first (`<= 2 min`) before scripting, TTS, or rendering.
4. **Never degrade**: No placeholder images, no template/offline story text, and no heuristic hook scores ever enter `state/buffer.json`.

## Architecture
- **Character Bible (`characters/heroes/`, `characters/villains/`)**: Strict visual anchors, forbidden items, scale classes (`XS`–`XL`), and CIEDE2000 color separation (`>= 20` ΔE). Validated by `scripts/check_bible.py`.
- **Text & Hook Gate (`src/common/gemini.py`, `src/story/`)**: Single `GOOGLE_API_KEY` on `v1beta` (`GOOGLE_GENAI_API_VERSION=v1beta`), 24h cached `client.models.list()` discovery across `gemini-3.8-flash → gemini-3.6-flash → gemini-3.5-flash-lite → gemma-4`, strict title validation (`src/story/title_validator.py`), and LLM Hook & Retention judge.
- **Reusable Art Library (`kaggle/`, `src/art/library.py`, `art_library.yml`)**: Batch-generated on Kaggle's free GPU (12 transparent 1024px poses/character via `rembg` + 30 empty 16:9/9:16 backgrounds + consistency QA) and published as `art-library-vN` GitHub Releases with `assets/library_index.json`.
- **Layered Compositor & 30fps Render (`src/panels/compose.py`, `src/render/`)**: Scale-chart heights, contact shadows, lighting match, cubic in-out eased camera moves, 0.5x/1.0x layer parallax, mouth-flap + impact squash-and-stretch, Gemini TTS primary + Piper fallback with line-hash caching, and render QA.
- **Buffer, Abort Policy & Publishing (`src/publish/buffer.py`, `src/publish/gate.py`)**: Only `publishable=true` episodes enter `state/buffer.json` + draft Release. `publish.yml` posts 1 in-order episode/day (or skips cleanly if buffer is empty).

## One-Time Setup Checklist

### 1. GitHub Repository Secrets
Add these secrets in **Settings → Secrets and variables → Actions**:
- `GOOGLE_API_KEY`: Single Gemini API key (unused `GOOGLE_API_KEY1/2/3`, `GOOGLE_API_KEYS`, and `HF_TOKEN` are no longer used and should be deleted).
- `KAGGLE_USERNAME` & `KAGGLE_KEY`: For `art_library.yml` (`kaggle kernels push`).
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`: With OAuth Consent Screen set to **In production**.
- `IG_ACCESS_TOKEN`, `IG_USER_ID`, and `GH_PAT_SECRETS` (fine-grained PAT with **Secrets: Read and write**).

### 2. Kaggle Free GPU Quota & Terms
- **Weekly Quota**: **30 hours/week** (rolling weekly reset), using 1× P100 or 2× T4 GPUs, max **12 hours** per session.
- **Verification**: Phone number verification is required in Kaggle account settings to enable GPU accelerators.
- **Terms**: Kaggle prohibits persistent external service/API hosting ("server farming"). Toonocalypse uses Kaggle strictly for periodic batch ML image generation (`art_library.yml`).

### 3. Initial Run Order (Before Enabling Schedules)
1. Run **Build Art Library (Kaggle GPU)** (`art_library.yml`) once via `workflow_dispatch` to generate and release `art-library-v1` + `assets/library_index.json`.
2. Run **Generate Episode Buffer** (`generate.yml`) via `workflow_dispatch` to verify preflight, LLM scripting, layered composition, TTS, and `state/buffer.json`.
3. Scheduled runs (`generate.yml` every 6h, `publish.yml` daily) will then maintain the 3-day buffer and publish automatically.

## Reading `ABORTED` Job Summaries
- Expected operational aborts (e.g. `paused_until`, missing art library assets, all text models rate-limited) exit cleanly with **`success`** and write **`ABORTED: <reason>`** to the GitHub Actions job summary.
- After **3 consecutive aborts**, `state/quota.json` sets `paused_until = max(now + 12h, longest retryDelay)` and opens/updates a single GitHub Issue titled **`Generation paused / buffer low`** (auto-closed on the next successful generation).
- Unexpected code bugs still fail the workflow loudly.
