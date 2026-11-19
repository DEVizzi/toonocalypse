# Style guide

Both phrases are used VERBATIM by `src/art/prompt_builder.py` (never reworded). Tests enforce this.

## STYLE_PHRASE
bold comic book art, thick black outlines, flat cel-shaded colours, clean simple background, dramatic rim lighting, expressive faces, high detail

## NEGATIVE_PHRASE
text, letters, words, speech bubble, caption, watermark, signature, logo, extra fingers, extra limbs, deformed hands, distorted face, blurry, lowres, crowd, photorealistic, 3d render, gore, blood, superhero costume, cowl, emblem

## Rules
- One focal point per panel; characters large in frame.
- Keep the upper 25% of every panel empty (sky/wall) for speech bubbles.
- No studio, artist or brand names anywhere.
- FLUX.1-schnell runs without classifier-free guidance, so NEGATIVE_PHRASE is not fed to the model; it is used by
  QA and recorded with every job.
