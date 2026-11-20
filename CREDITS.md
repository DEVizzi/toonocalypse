# Credits & licences

Every asset is free for commercial use. No AI-generated images, video or music are used anywhere.

## Fonts (`assets/fonts/`)
| File | Licence | Source |
|---|---|---|
| LuckiestGuy-Regular.ttf | Apache-2.0 (`LICENSE-LuckiestGuy.txt`) | https://github.com/google/fonts/tree/main/apache/luckiestguy |
| Fredoka.ttf (variable) | SIL OFL 1.1 (`OFL-Fredoka.txt`) | https://github.com/google/fonts/tree/main/ofl/fredoka |
| Bangers-Regular.ttf | SIL OFL 1.1 (`OFL-Bangers.txt`) | https://github.com/google/fonts/tree/main/ofl/bangers |
| Anton-Regular.ttf | SIL OFL 1.1 (`OFL-Anton.txt`) | https://github.com/google/fonts/tree/main/ofl/anton |
| ComicNeue-Bold.ttf | SIL OFL 1.1 (`OFL-ComicNeue.txt`) | https://github.com/google/fonts/tree/main/ofl/comicneue |

## Graphics
All characters, faces, limbs, obstacles, backgrounds, particles and HUD are drawn procedurally in Python
(pygame-ce). No image files are used.

## Audio
- SFX: generated procedurally with NumPy/SciPy at render time (`src/audio/sfx_gen.py`). No third-party samples.
- Music: procedural chiptune loops (`src/audio/`). Decision: generating music in code avoids licence risk entirely;
  CC0 loops can be dropped into `assets/music/` later and must be listed here with their source and licence.
- Lord Tuno's voice: procedural "castle babble" (NumPy).
- Narration: edge-tts (Microsoft neural voices via an unofficial endpoint) → Kokoro-82M (Apache-2.0) → Piper (MIT).

## Software
pygame-ce (LGPL-2.1), pymunk (MIT), NumPy/SciPy (BSD-3), FFmpeg (LGPL/GPL, invoked as a CLI tool).
