# 05 — Editing brain (core logic)

The brain is a **rules engine guided by an LLM**. The LLM decides intent (style, story, which shots matter, what the prompt means); the rules guarantee rhythm, pacing and quality. With no LLM available, the rules alone still produce a complete edit. Code lives in `worker/app/domain/brain/` (pure functions, see `11-coding-standards.md` §4).

```
music analysis ──► B1 music map ──┐
shot analysis  ──► B2 shot scores ┼──► B10 director (LLM) ──► constraints
prompt ────────────────────────────┘                              │
                                                                   ▼
            B3 pacing → B4 assignment → B5 effects → B6 ramps → B7 reframe → B8 text/audio
                                                                   │
                                                          B11 validation → edit plan
```

## B1. Music map (`music_map.py`)

Output, used by every later step:

- `beats[]` with time (s) and strength (0–1), `downbeats[]`, `bpm`.
- Energy curve `E(t)`: RMS loudness, smoothed over 0.5 s, normalized 0–1.
- **Accent beats:** beats whose onset strength is in the top 15%.
- **Sections**, with boundaries only on downbeats where the 4-bar energy change is > 0.25:
  - **Drop:** mean E ≥ 0.75 and preceded by a rise.
  - **Build:** E rising across 4 or more bars.
  - **Break:** E < 0.4 after a drop.
  - **Intro / Outro:** first and last sections.
  - Anything else: **Verse** (treated like Build for pacing, weight 0.6).
- **Edit window:** default up to 60 s (or user length). Starts on a downbeat 8 bars before the first drop and ends on a downbeat. If the song has no drop, the window is the highest-energy 60 s aligned to downbeats.

## B2. Shot scoring (`scoring.py`)

Every shot is sampled at 4 fps on the proxy and scored 0–1:

```
S = 0.25·M + 0.20·F + 0.15·Sh + 0.15·A + 0.15·Ae + 0.10·St
```

| Term | Meaning | Measured by | Normalization |
| --- | --- | --- | --- |
| M | Motion | Mean optical-flow magnitude | Percentile rank within the project |
| F | Subject | Face/person presence × box area | 0 none … 1 large subject |
| Sh | Sharpness | Laplacian variance | Percentile rank |
| A | Action | Pose keypoint and object velocity peaks | Percentile rank |
| Ae | Aesthetics | CLIP aesthetic predictor | Model output scaled 0–1 |
| St | Stability | 1 − camera shake (global flow variance) | 0–1 |

Each shot also stores: peak moment (frame with the highest M × F), usable windows (sharp, not too dark), CLIP tags, caption, motion direction, dominant color, `cameraMode`, `nativeFps`.

**Reject** when S < 0.2, mean luma < 0.08, or it duplicates a better shot (CLIP cosine similarity > 0.95).

## B3. Pacing and style presets (`pacing.py`)

Cuts land only on beats. Cut length is in beats per section; section changes always cut on a downbeat. No segment is shorter than 0.25 s (if it would be, the cut length doubles).

| Style | Intro | Build | Drop | Break | Outro | FX intensity | Grade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Velocity | 2 | 1 | ½ and 1 alternating, with ramps | 2 | 4 | 0.9 | Teal-orange, contrast |
| Hype | 1 | ½ | ½ | 1 | 2 | 1.0 | Vibrant, glow |
| Cinematic | 4 | 2 | 2 | 4 | 8 | 0.3 | Film LUT, grain, 2.39 bars |
| Anime-style | 2 | 1 | ½ | 2 | 4 | 0.9 | Saturated, flashes, RGB split |
| Travel | 4 | 2 | 1 | 4 | 4 | 0.5 | Warm, light leaks |
| Car edit | 2 | 1 | ½ | 2 | 4 | 0.8 | Moody, motion blur |
| Sports | 2 | 1 | ½ | 2 | 4 | 0.8 | Punchy, high contrast |

Output: an ordered list of **slots** `{start, end, section, beatStrength, isDownbeat}` covering the edit window exactly.

## B4. Shot assignment (`assign.py`)

1. Each slot gets importance `I = sectionWeight × beatStrength`, with weights drop 1.0, build 0.7, verse 0.6, intro 0.5, outro 0.5, break 0.4.
2. Slots are filled from the highest I down. For each slot, every candidate shot gets `match = S × fit`, where `fit` is the product of:
   - **Energy fit:** `1 − |M − E(slot)|`.
   - **Length fit:** 1 if a usable window covers the slot's source length after its speed curve (B6), else 0.
   - **Slow-mo fit:** 1.3 if the slot gets a slow-mo ramp and the clip is native 100/120 fps, else 1.
   - **Prompt fit:** 1.5 for each included tag matched (CLIP similarity > 0.25), 0 if an excluded tag matches.
3. **Constraints:**
   - A shot is reused only after every shot is used, and then with a different window.
   - Two consecutive slots never come from the same source clip.
   - Photos fill at most 30% of slots and never a drop, unless the input is only photos.
   - At least 70% of drop slots get shots with M in the top half.
4. **Window placement:** inside the chosen shot, the window is placed so the peak moment lands on the slot's beat.
5. **Order:** chronological (by capture time) for Travel; energy-driven for every other style. Ties are broken by the seed.

## B5. Effect rules (`effects.py`)

| Moment | Effects applied |
| --- | --- |
| First beat of a drop | Speed ramp, white flash (0.08 s), shake, zoom punch or FOV punch (360) |
| Accent beat | Shake (strength = onset strength) or zoom punch 1.0 → 1.15, alternating |
| Regular beat cut | Hard cut or whip transition, alternating |
| Section change | Signature transition: zoom-through, spin or glitch; tiny planet for 360 |
| Build | Slow push-in, rising shake, speed rising 1.0× → 1.5× |
| Break | Slow motion, grain, no shake |
| Final downbeat | Freeze frame, then fade to black |

**Caps:** shakes on at most 40% of beats; at most one flash per bar outside drops; transitions on at most half of all cuts. Every strength is multiplied by the style's FX intensity and any prompt override. Motion blur is applied to every segment with zoom, spin or whip, amount = style FX intensity × 0.7.

## B6. Speed ramp curve (`ramps.py`)

For a ramped slot of length D (timeline seconds):

| Phase | Timeline span | Speed |
| --- | --- | --- |
| Fast | 0 → 0.4 D | 2.5× |
| Ease down | 0.4 D → 0.5 D | 2.5× → 0.25× |
| Hold slow | 0.5 D → 0.8 D | 0.25× |
| Ease up | 0.8 D → D | 0.25× → 1× |

- Easing: cubic-bezier(0.7, 0, 0.3, 1).
- The start of the slow hold sits on the beat.
- Slow frames come from native 100/120 fps footage when available, otherwise RIFE.
- Source length needed = ∫ speed(τ) dτ over D; B4's length fit uses this.

## B7. Reframing rules (`reframe.py`)

- **Flat clips:** crop window at the output ratio, as large as possible. Center = subject center smoothed with a 1€ filter; 10% dead zone; max pan 15% of frame width per second (unlimited across cuts). A single subject sits on a rule-of-thirds line in the direction of motion.
- **360 clips:** yaw follows the subject at pitch −5°, FOV 100° (90° for 9:16 and 4:5). Drop → 360° yaw spin over one beat. Section change → tiny planet (pitch −90°, FOV 160°, stereographic). Pitch stays above −60° except during tiny planet, keeping the selfie stick out of frame.
- **Photos:** Ken Burns from 1.0 to 1.12 scale toward the subject, or depth parallax when depth contrast is high.

## B8. Text and audio (`effects.py`, `render/audio.py`)

- Text appears only when the prompt gives it, popping on the next downbeat, placed behind the subject when a SAM 2 mask exists.
- Captions only when speech is detected (faster-whisper) and the style is not Cinematic.
- Music normalized to −14 LUFS. Whoosh on transitions at −18 dB, impact on each drop.
- Clip audio muted unless speech is detected; then kept, and music ducks 8 dB under it.

## B9. Prompt to constraints (`prompt.py`)

The LLM turns the prompt into a constraint JSON (schema in `06-edit-plan-schema.md`) that the rules engine applies. A keyword fallback parser handles common phrases ("slow mo", "no shake", "cinematic", "only car") if the LLM fails. Any request that maps to nothing is skipped and listed in the job log shown to the user.

## B10. LLM director and fallback (`director.py`)

- **Input to the LLM:** compact JSON with music sections (type, start, end, energy), the top 40 shots (id, tags, caption, score, cameraMode), user settings and the prompt. Max ~3,000 tokens.
- **Output:** `{ style, storyHints[], constraints }`, requested with Ollama `format: json` and validated against the schema; one retry on invalid JSON.
- **Fallback** (invalid output or Ollama not running): style picked by rule, in order:
  1. BPM ≥ 140 → Hype
  2. BPM ≥ 120 and drop energy ≥ 0.75 → Velocity
  3. Most shots tagged car/vehicle → Car edit
  4. Most shots tagged outdoor/landscape/beach/mountain → Travel
  5. BPM < 100 → Cinematic
  6. Otherwise → Velocity
- **Variations:** "Make another version" changes the seed, which changes tie-breaks, transition picks and shot order among equal scores.

## B11. Validation before render (`validate.py`)

The plan is rejected and repaired (or the job fails with a clear message) unless:

- Every segment starts on a beat, within one frame.
- No gaps or overlaps; the total equals the edit window.
- Every source window covers its speed curve.
- The subject box stays inside the frame for at least 90% of each segment.
- The caps in B5 hold.
- All segments are conformed to the output fps.
