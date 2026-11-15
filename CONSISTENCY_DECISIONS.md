# Character & Story Consistency Decisions (Bible v1)

This log records every authoritative resolution, trademark adjustment, colour-separation fix, and all-ages rewrite applied when freezing `bible_version: 1`. Any future character change MUST bump `bible_version` and append an entry here.

---

## 1. Species Conflicts (`heroes.json` vs Cast Table)

Per §7.0.1–7.0.3, `heroes.json` is authoritative for **name** and **species**. Eight characters had species mismatches with the Cast Table; in all 8 cases `heroes.json` won and the silhouette/palette/anchors were re-derived to preserve §7.4 uniqueness:

1. **Captain Thorn** (`captain-thorn`): `heroes.json` = `Cactus` (Cast Table had `hedgehog`). Re-derived as a spindly anthropomorphic green-olive cactus (`#827717` / `#E8D5B0`) with neon-pink spine mohawk tips, mechanical courier arms, and a long olive-tan ranger duster. Separated from *Snuggle Doom* (`Hedgehog`) and *Sir Quackalot* (`Duck`).
2. **Squeakshadow** (`squeakshadow`): `heroes.json` = `Squirrel` (Cast Table had `bat*`). Re-derived as a small wiry midnight-indigo ninja squirrel (`#311B92`) with a bushy squirrel tail bearing a neon-green streak (`#76FF03`), no bat wings. Separated from *Cranktail* (`Scorpion`).
3. **Muffin Max** (`muffin-max`): `heroes.json` = `Rabbit` (Cast Table had `hamster*`). Re-derived as a tiny golden-butter rabbit (`#FFE600` / `#E8B04A`) with floppy ears beside a white baker hat and pastry scroll tubes. Separated from *Dusty Comet* (`Donkey`).
4. **Fizzy Fang** (`fizzy-fang`): `heroes.json` = `Bat` (Cast Table had `snake*`). Re-derived as a small coral-pink fruit bat (`#FF4081`) with translucent mint-banded bubble wings (`#9CF6D6`), two tiny cute rounded fangs, and a giant bubble wand. Separated from *Squeakshadow* (`Squirrel`).
5. **Glitchpaw** (`glitchpaw`): `heroes.json` = `Tiger (Holographic)` (Cast Table had `raccoon*`). Re-derived as a large steel-slate holographic tiger (`#2F4F4F`) in a charcoal hoodie with magenta/cyan pixel-glitch LED stripes and a shimmering pixel-glitch LEFT paw.
6. **Dusty Comet** (`dusty-comet`): `heroes.json` = `Donkey` (Cast Table had `jackrabbit*`). Re-derived as a sturdy big-headed tan space donkey (`#D7B38C`) with tall donkey ears poking cleanly through a glowing bubble space helmet and an indigo courier jacket.
7. **Snuggle Doom** (`snuggle-doom`): `heroes.json` = `Hedgehog` (Cast Table had `lamb*`). Re-derived as a small fluffy plum-violet hedgehog (`#AA00FF`) with pastel-pink glittering quills, permanent cute tiny scowl, royal-purple cape, and glitter-trap prank kit.
8. **Cranktail** (`cranktail`): `heroes.json` = `Scorpion` (Cast Table had `squirrel*`). Re-derived as a small friendly mechanical bronze-taupe scorpion (`#A1887F`) with rounded claws, a blinking amber tail-light GPS beacon, brass wind-up key, and mechanic tool belt.

---

## 2. Trademark Safety & Rename Suggestion (§7.0.5)

- **Percival the Platypus** (`percival-the-platypus`): `heroes.json` originally described `"teal bill"`. Removed all teal (`#5B6770` slate-grey bill instead, `#6E4726` brown fur, `#C8102E` red explorer scarf) and added `teal fur`, `teal bill`, `fedora`, `any hat`, `spy suit`, `trench coat` to `forbidden`.
  - **Rename suggestion**: Consider renaming display name in `config/settings.yaml` (`display_names.percival-the-platypus`) to **"Pip the Platypus"** or **"Barnaby Bill"** for even stronger trademark distance. All display names are config-driven so renaming requires zero code changes.
- **Captain Thorn** (`captain-thorn`): `forbidden` blocks blue fur, red sneakers, spin-dash poses.
- **Blitzshell** (`blitzshell`): `forbidden` blocks eye masks, bandanas, ninja weapons.
- **Sir Quackalot** (`sir-quackalot`): `forbidden` blocks white duck feathers, sailor outfits/hats, metal swords.

---

## 3. Primary Colour Separation (CIEDE2000 ΔE ≥ 20)

To guarantee every hero's primary colour has **CIEDE2000 ΔE ≥ 20.0** across all 325 hero pairs (validated in `scripts/check_bible.py`), primary hexes were tuned in `characters/heroes/*.json` while preserving each character's visual identity (e.g., *Dr. Pancake* uses `#181818` panda-black primary with `#FFFFFF` fur and `#F4B400` syrup; *Brewtan* uses `#F2FAFF` icy white; *LLA-M4* uses `#00B8D4` cyan trim; *DJ Meowgic* uses `#3E2723` dark espresso-black; *Mango Mike* `#FF9E00` vs *Detective Bubbles* `#FF5500` vs *Muffin Max* `#FFE600`). Minimum pairwise hero ΔE is **20.68**.

Villains reserve `#C0C4C8` chrome + one glow (`#B2FF00`, `#FFB000`, `#9D00FF`). *Baron Byte-Bat* and *Overclock Octo* use `#B2FF00` (acid-lime) rather than `#9D00FF` so same-species ΔE against *Fizzy Fang* (`#FF4081`) and *Bubblebeard* (`#A30063`) exceeds 35.

---

## 4. All-Ages Quirk & Story Rewrites (§7.11 & §2.9)

- **Turbo Tusk**: `"Eats motor oil"` → `"Eats gear-shaped cookies"`; `"Sleeps inside car engines"` → `"Sleeps inside cozy car garages"`.
- **Zapzilla**: `"Addicted to static"` → `"Loves static-charged party balloons"`.
- **Detective Bubbles**: `"Addicted to kelp coffee"` → `"Obsessive clue-jar collector"`.
- **Snuggle Doom**: `"Sweet but vengeful"` → `"Sweet on the outside, dramatic prankster at heart"` (glitter traps & pranks, then hugs).
- **Captain Slobber**: drool is strictly sparkly comic gag, never gross close-ups.
- **Legacy `action_story.json` ideas**: `src/story/ideas.py` automatically filters/rewrites any legacy seed containing sniper, Latin sacrifice/chanting, blackmail, headbutting off cliffs, mind-control, hypnosis, or force-feeding before use, and generates fresh all-ages ideas from the character bibles.
