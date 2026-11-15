# Toonocalypse — Automated Motion-Comic Pipeline

Zero-cost, fully automated, family-friendly motion-comic channel starring the 26-hero Toonocalypse cast, running exclusively on **GitHub Actions** and publishing **1 episode per day** to **YouTube Shorts** and **Instagram Reels**, plus weekly **long-form 16:9 compilations**.

## Architecture
- **Character Bible (`characters/heroes/`, `characters/villains/`)**: Strict visual anchors, forbidden items, scale classes (`XS`–`XL`), and CIEDE2000 color separation (`>= 20` ΔE). Validated by `scripts/check_bible.py`.
- **Story & Hook Gate (`src/story/`, `src/moderation/`)**: Multi-part arcs (`Mini-Arc`, `Epic-Arc`) and `One-Shot` episodes, holiday calendar triggers, deterministic family-safety & studio-name moderation, and Hook & Retention scoring (`>= 7.5` avg, `10.0` safety).
- **Art & Panels (`src/art/`, `src/panels/`)**: 2×3 comic page generation, anchor QA, uniform gutter detection, code-drawn speech bubbles, and 9:16 cover images.
- **Audio & Render (`src/audio/`, `src/render/`)**: Synthesized SFX, word-timed captions, 9:16 YouTube Shorts / Instagram Reels renders, 16:9 wide renders for compilations, and FFmpeg/FFprobe QA gates.
- **Buffer & Publishing (`src/publish/`, `src/tokens/`)**: 3-day GitHub Releases episode buffer, strict 1-episode/day coordinator with per-platform idempotency, and automated token refresh + watchdog alerts.
- **Analytics & Monitoring (`src/analytics/`, `src/monitoring/`)**: Weekly YT/IG metrics loop updating bounded `config/playbook.yaml` weights and weekly GitHub Issue health reports.

## One-Time Setup Checklist

### 1. Security Hygiene
- Revoke any legacy GCP service-account keys (legacy `myvoiceoverbot-*.json` was purged from git history).
- Never commit `.env`, credentials, or tokens; `ci.yml` runs `gitleaks` on every push.

### 2. GitHub Repository Secrets
Add the following secrets in **Settings → Secrets and variables → Actions**:
- `GOOGLE_API_KEY`: Single Gemini API key (protected by `QuotaTracker` in `state/quota.json`).
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
- `IG_ACCESS_TOKEN`, `IG_USER_ID`
- `GH_PAT_SECRETS`: Fine-grained GitHub PAT with **Secrets: Read and write** on this repository (used by `tokens.yml` to rotate `IG_ACCESS_TOKEN` automatically).

### 3. YouTube OAuth2 & API Audit
1. In Google Cloud Console, set your OAuth Consent Screen publishing status to **In production** (otherwise refresh tokens expire every 7 days).
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Run the one-time bootstrap locally with your downloaded `client_secret.json`:
   ```bash
   pip install google-auth-oauthlib
   python3 scripts/oauth_bootstrap.py --client-secrets client_secret.json
   ```
   Copy `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` into GitHub Secrets.
4. **YouTube API Audit & COPPA**: Unaudited YouTube Data API projects have uploads locked to `private`. Submit the YouTube API Compliance Audit to enable `public` uploads. Also note `self_declared_made_for_kids` in `config/settings.yaml`: setting `true` complies with COPPA for kid-directed content (disabling personalized ads/comments), while `false` targets general family/all-ages audiences.

### 4. Instagram Graph API
1. Connect your Instagram Professional account to a Facebook Page and generate a long-lived token with `instagram_basic`, `instagram_content_publish`, and `instagram_manage_insights`.
2. Store `IG_ACCESS_TOKEN` and `IG_USER_ID` in GitHub Secrets. `tokens.yml` refreshes `IG_ACCESS_TOKEN` automatically when `< 20` days remain.

## Running on GitHub Actions
All comic generation, reference sheets, tests, and publishing run on GitHub Actions:
- **CI & Offline Dry-Run**: `.github/workflows/ci.yml` (runs `check_bible.py`, `pytest`, `gitleaks`, and offline `Mini-Arc` & `One-Shot` dry runs).
- **Build Reference Sheets**: Trigger `.github/workflows/build_refs.yml` via `workflow_dispatch`.
- **Generate Buffer / Publish / Watchdog / Analytics / Compile / Report**: Scheduled automatically via cron, or trigger manually via `workflow_dispatch`.
