# Licenses

Toonocalypse may monetize, so every model, voice, font, music track and sound effect must allow **commercial use**.
Anything not listed here must not be used. Status: ✅ verified · ⏳ to verify before first use.

## Image generation (Kaggle GPU)
| Component | Source | License | Status |
|---|---|---|---|
| SDXL base 1.0 | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md) (commercial use allowed, with use-based restrictions) | ⏳ |
| IP-Adapter Plus SDXL (ViT-H) | [h94/IP-Adapter](https://huggingface.co/h94/IP-Adapter) | [Apache-2.0](https://huggingface.co/h94/IP-Adapter) | ✅ |
| OpenCLIP ViT-H/14 image encoder (bundled in h94/IP-Adapter `models/image_encoder`) | [laion/CLIP-ViT-H-14-laion2B-s32B-b79K](https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K) | MIT | ⏳ |
| Real-ESRGAN x2plus | [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause | ⏳ |
| CLIP ViT-L/14 (pre-filter) | [openai/clip-vit-large-patch14](https://huggingface.co/openai/clip-vit-large-patch14) | MIT | ⏳ |
| DINOv2 base (pre-filter) | [facebook/dinov2-base](https://huggingface.co/facebook/dinov2-base) | Apache-2.0 | ⏳ |
| EasyOCR (text detector) | [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) | Apache-2.0 | ⏳ |

**Not used, by design:** FLUX.1-dev (non-commercial), and InsightFace-based models (FaceID, InstantID, PuLID).

## Voices (GitHub Actions, CPU)
| Component | Source | License | Status |
|---|---|---|---|
| Kokoro-82M + built-in voices | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | Apache-2.0 | ✅ |
| Piper (fallback engine) | [rhasspy/piper](https://github.com/rhasspy/piper) | MIT (engine). Each voice has its own dataset license; only voices whose model card permits commercial use may be listed here. | ⏳ |

## Fonts (`assets/fonts/`)
| File | Family | License | Source |
|---|---|---|---|
| `Esteban-Regular.ttf` | Esteban | SIL OFL 1.1 | Google Fonts |
| `PlayfairDisplay-Regular.ttf` | Playfair Display | SIL OFL 1.1 | Google Fonts |
| `PlayfairDisplay-VariableFont_wght.ttf` | Playfair Display (variable) | SIL OFL 1.1 | Google Fonts |
| `DancingScript-VariableFont_wght.ttf` | Dancing Script (variable) | SIL OFL 1.1 | Google Fonts |
| `Bangers-Regular.ttf` | Bangers (SFX words, covers, moral card) | SIL OFL 1.1 | [google/fonts](https://github.com/google/fonts/tree/main/ofl/bangers) |
| `ComicNeue-Bold.ttf` | Comic Neue Bold (speech bubbles) | SIL OFL 1.1 | [google/fonts](https://github.com/google/fonts/tree/main/ofl/comicneue) |
| `Anton-Regular.ttf` | Anton (captions) | SIL OFL 1.1 | [google/fonts](https://github.com/google/fonts/tree/main/ofl/anton) |

## Libraries used in generation
| Library | License |
|---|---|
| [diffusers](https://github.com/huggingface/diffusers) | Apache-2.0 |
| [compel](https://github.com/damian0815/compel) (long-prompt encoding) | MIT |
| [spandrel](https://github.com/chaiNNer-org/spandrel) (loads Real-ESRGAN) | MIT |
| [transformers](https://github.com/huggingface/transformers) | Apache-2.0 |

## Music (`assets/music/`)
| File | Title & artist | License | Source |
|---|---|---|---|
| `cosy-quirky-comedy-248029.mp3` | Cosy Quirky Comedy (leberch) | Pixabay Content License | Pixabay Music ID 248029 |
| `kids-quirky-playful-262598.mp3` | Kids Quirky Playful (leberch) | Pixabay Content License | Pixabay Music ID 262598 |
| `quirky-fun-comedy-250869.mp3` | Quirky Fun Comedy (leberch) | Pixabay Content License | Pixabay Music ID 250869 |

**Mood beds (epic, mystery, emotional, tech):** unless a licensed track is placed in `assets/music/<mood>/` and listed here, the renderer synthesizes an original pad in code (`src/audio/mix.py`). That pad is dedicated to the public domain under **CC0 1.0**.

## Sound effects
Impact, whoosh and chime are synthesized in code (`src/audio/mix.py`) and dedicated to **CC0 1.0**. No external SFX files are used.
