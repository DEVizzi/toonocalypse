# Cleanup log — ToonToonCastle (M0)

The repo previously hosted retired comic prototypes before being rebuilt from scratch for **ToonToonCastle** (`@ToonToonCastle`).
They were removed without rewriting history in this cleanup. The last commit before cleanup is tagged **`legacy-final`**
(`b39b883`); older snapshots stay tagged `legacy-v1` and `legacy-v2`. Nothing outside this repo was modified,
and YouTube/Instagram were not touched.

## Paths deleted in this cleanup (`legacy-final` → M0)

| Path | What it was |
|---|---|
| `kaggle/art_kernel.py` | Kaggle GPU FLUX image-generation kernel |
| `src/art/blocks.py`, `src/art/prompt_builder.py`, `src/art/sheet.py`, `src/art/test5.py`, `src/art/__init__.py` | AI-comic prompt builder, TEST5 image-consistency test |
| `src/qa/vision.py`, `src/qa/__init__.py` | Gemini vision QA for generated images |
| `src/common/config.py`, `src/common/__init__.py`, `src/__init__.py` | Comic pipeline config loader |
| `config/models.yaml`, `config/settings.yaml`, `config/style_guide.md` | Image-model / comic style config |
| `tests/test_blocks.py`, `pytest.ini`, `requirements.txt` | Comic pipeline tests and deps |
| `.github/workflows/test5.yml` | Kaggle image-generation workflow |
| `README.md`, `LICENSES.md` | Comic project docs |
| `assets/music/cosy-quirky-comedy-248029.mp3`, `assets/music/kids-quirky-playful-262598.mp3`, `assets/music/quirky-fun-comedy-250869.mp3` | Pixabay-licensed tracks (not CC0; replaced by CC0/procedural audio) |
| `assets/fonts/DancingScript-VariableFont_wght.ttf`, `assets/fonts/Esteban-Regular.ttf`, `assets/fonts/PlayfairDisplay-Regular.ttf`, `assets/fonts/PlayfairDisplay-VariableFont_wght.ttf` | Unused decorative fonts |

Earlier cleanups, for reference:
- `legacy-v1`: the original pipeline (`Crazy_bot.py`, `heroes.json`, `action_story.json`, `history_story.txt`,
  `characters/`, sprite/art-library compositor, Gemini-image/Hugging Face/Pollinations/Cloudflare/Twitter code).
  These were removed before `legacy-v2`.
- 2026-11-17: a leaked `.env` was purged from all history with `git filter-repo`.

Generated media deleted: GitHub Releases `model-bakeoff` (image samples) and `test5-20261119-2021` (draft), plus
their tags. Older releases `art-library-v1..v4`, `st-*`, `smoke-test` and `ep-*` were deleted earlier.

## Secrets no longer used — revoke at the source, then delete from repo settings

| Secret name | Was used for | Action |
|---|---|---|
| `KAGGLE_USERNAME` (deleted from repo secrets) | Kaggle GPU image generation | Deleted |
| `KAGGLE_API_TOKEN` (deleted from repo secrets) | Kaggle GPU image generation | Revoke at kaggle.com → Settings → API if still active |
| `izaz246GemAPIKey` (already deleted from the repo) | Gemini image test | Revoke in Google AI Studio if it's not used elsewhere |
| `HUGGINGFACE_API_TOKEN`, `REPLICATE_API_TOKEN`, `CLOUDINARY_*`, `CHAINGPT_API_KEY`, `TWITTER_*`, `VOICEOVER_JSON_B64` (old `.env`, purged) | Legacy image/voice/Twitter pipelines | Revoke at each provider (see the leak cleanup notes) |

## Active production secrets (7 total)
`GOOGLE_API_KEY` (Gemini text only), `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`,
`IG_ACCESS_TOKEN`, `IG_USER_ID`, `GH_TOKEN`.
