# Toon Toon Castle

A 100% free, fully automated pipeline on GitHub Actions. It simulates real 2D physics elimination games with
procedurally drawn cartoon contestants, picks the funniest real run, adds commentary from Rick Ricochet,
renders and publishes vertical Shorts and Reels. No AI image or video generation.

Build status: being built milestone by milestone (brief §24). Earlier projects: see `CLEANUP_LOG.md`.

## Decisions (documented per the brief)
- **Music**: procedural chiptune loops generated in code instead of downloaded CC0 tracks (zero licence risk).
- **Local runs**: every step runs on GitHub Actions; `preview.yml` renders previews (cast sheet, sample videos)
  and publishes them to the `preview` pre-release.
- **M5 sound (v3.3)**: MC Tuno's commentary beats come only from real trace events; Gemini Flash (free tier,
  `GOOGLE_API_KEY`) punches up the lines and templated comedy lines are the automatic fallback. Voice = edge-tts
  (free, word-boundary timings drive karaoke captions in y 1440-1620 and MC Tuno's lip-sync). SFX are synthesized in
  numpy (bonks, slide-whistle falls, splats, airhorn, crowd, fanfare); music is ducked under the voice; final mix is
  normalised to -14 LUFS / -1.5 dBTP by ffmpeg `loudnorm`. `--no-audio` renders silently.
- **v3.3 overrides**: Rotating Disc never resolves while > 1 ball is alive (scripted shrink to a 44 px radius, final
  10 s centrifugal push, 38 s safety cap; Best-of-N rejects non-last-standing runs) and zooms by initial/current
  radius up to 2.05x. Side view frames the densest 4-6 hero cluster with a 0.86x-1.25x zoom band; the fire wall
  rubber-bands to <= 850 px behind it. Side-view backstop walls keep an invisible tall physics barrier but render as
  130 px stone bumpers; the finish line is a visual pass-through tape.

## Owner overrides to spec v3.0 (v3.0–v3.2 polish passes, 2026-11-20)
- **All 10 Heroes + 3–5 Crash Dummies**: Every episode spawns all 10 elemental rolling Heroes plus 3–5 Crash Dummies (`r=20`, yellow/grey 4-quadrant crash-test shell, goofy `NORMAL` / `HIT` / `FALLING` faces, `0.72x` side / `0.60x` top-down propulsion, `-1000` Best-of-N win penalty so Dummies exit early as chaotic bumper pins).
- **Zero Legs + Retractable Event-Only Arms**: Pure spinning physical balls (`moment_for_circle`/`moment_for_poly`); zero legs anywhere; cartoon stick arms pop out only on `flail` (falling/launched), `splat` (0.22 s heavy impact), and `victory` (Winner Card).
- **Tighter Retention Timeline (20–28 s)**: `0.8 s` cold-open teaser (`WHO SURVIVES?`) + `16–23 s` gameplay (`forced_resolution_s: 23`, `hard_stop_s: 24`, escalation at `8 s` / `18 s`) + `1.5 s` `0.3x` winner replay + `2.0 s` bold game-show sunburst Winner Card (`loop_tail_s: 0.0` so zero trailing cold-open flash frames).
- **Broadcast Header & Commentator Host ("MC Tuno")**: Compact `y = 0..255` broadcast header with episode ribbon, `ALIVE: X/14` pill, Top-5 alive Heroes bar, and a `220x220` top-right booth cam starring **MC Tuno** (studio headphones, boom mic, crooked mini crown, 6 vivid reaction poses, and speech callouts anchored cleanly below the circle at `y ~ 235`). Lower-third `y = 1440..1620` is kept clear for M5 captions.
- **Architectural 2D Platforms & Diegetic Modifiers**: Stitched beveled stone castle masonry slabs & riveted bridge beams with vertical support pillars, compact retracting mechanical drop-gate, chunky gear-hub seesaws, 3-layer parallax sky/spires/arches, recessed dark hazard pit trench, and flush surface modifiers (`>>>` boost chevrons, cracked glossy ice, scalloped bubbling mud).
- **Sharpened Elemental Contrasts & Camera**: Juggernaut `0.65x` flat roll with corner clunk sparks + downhill momentum; Floater `0.24x` low-gravity gliding arcs; Boing perpetual superball hopping + exaggerated squash-stretch; Glitch `Cyan`/`Crimson` phase aura + 3-frame RGB split + pixel sparks; Dash rigid ice puck + cyan frost afterimage trail; Magneto electric grip sparks; Grumble slope grip ticks. `TOP_DOWN` disc rim scales proportionally (`0.14 * r`) while camera zoom ramps smoothly `1.0x -> 1.95x`.
