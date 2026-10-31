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
- Energy curve `E(t)`: RMS loudness, smoothed over 0.5 s, divided by its peak (0–1). Pacing and slot fit use it.
- **Intensity curve `I(t)`:** how full the song sounds, as a **rank within the song itself** (0 = its quietest moment, 1 = its fullest). It is the percentile rank of smoothed loudness, averaged with the percentile rank of smoothed brightness (spectral centroid) and ranked again. Sections and the edit window use `I`, not `E`. Why: compressed electronic music is about as loud at its drop as everywhere else (a real 289 s track had one flat section at mean peak-relative energy 0.71, so no drop, build or break could be found), but its filter sweeps change the brightness. Ranking against the song's own moments makes the 0.75/0.4 style thresholds mean the same thing for every song. Section `mean_energy` is the mean of `I`.
- **Accent beats:** beats whose onset strength is in the top 15%.
- **Beat grid:** the tracker's beats, with two corrections. (1) **Half tempo:** if the tracked tempo is above 140 BPM and the onset curve repeats at least 2 times more strongly every 2 beats than every beat, the tracker locked onto the double of the pulse; every other beat is kept, on the phase that holds the most downbeats (else the stronger onsets). Every kept beat is a real tracked beat, so cuts stay on the beat. The real 170.21 BPM song has an onset autocorrelation of 0.18 at the beat but 0.57 at 2 beats, and reads as 84.96 BPM. (2) **Downbeats** that are not on a kept beat, or are less than 1.5 beats after the previous downbeat, are dropped (the tracker emitted 81 of 246 inside 0.8 s on that song).
- **Sections**, with boundaries only on downbeats where the 4-bar change is large: loudness and brightness are each divided by their median over the song, and the distance between the 4-bar mean after and before a downbeat (the two changes combined as a Euclidean distance) must be over **0.3**. The biggest change wins and others within 4 bars are dropped. A steady song (all parts within 30% of its typical level) stays one section.
  - **Long parts are split (T-413):** a part longer than **32 bars** is too long to be one part, because its mean hides a step inside it. Inside it, the biggest 4-bar change over **0.15** (still a downbeat, still 4 bars from other boundaries) is a boundary too, repeated until no part is over 32 bars or no change over 0.15 is left. Measured on the real 289 s song: one 135.5 s "drop" (mean `I` 0.658) was a bright half (brightness 1.2x its median, `I` 0.75, to 111.5 s) followed by an average half (1.0x, `I` 0.55) with a 4-bar change of only 0.16, below 0.3. It becomes drop 45.2–111.5 s (0.75) and build 111.5–180.7 s (0.57); the drop share falls from 47% to 23%. The edit window is unchanged (the first drop still starts at 45.2 s). The other 4 songs keep their sections except AcidJazz (2 to 6, with two short drops) and Crunk Knight (102.7 s outro split into build and a 65.8 s outro). `ANALYSIS_VERSION` is 7 so cached maps are rebuilt.
  - **Drop:** mean `I` ≥ **0.6** and at least 0.1 above the section before. (It was E ≥ 0.75 "after a rise": on a rank scale a section that fills half the song cannot average 0.75, and a mean of 0.6 is "above the song's median".)
  - **Build:** `I` rising across 4 or more bars (a rise of at least 0.1).
  - **Break:** `I` < 0.4 after a drop.
  - **Intro / Outro:** first and last sections.
  - Anything else: **Verse** (treated like Build for pacing, weight 0.6).
- **Edit window:** default up to 60 s (or user length). Starts on a downbeat 8 bars before the first drop and ends on a downbeat. **If the song has no drop, the window is the 60 s (aligned to downbeats, full length) with the highest mean `I`, the most climactic stretch.**

Measured on 5 real songs (T-406): sections found go from 3, 1, 3, 1 and 5 to 6, 4, 16, 1 and 8 (the CC0 electronic track, Aces High, Call to Adventure, the steady AcidJazz piece, Crunk Knight), with drops found in 3 of them where there were none; the two with no drop get the most-intense-stretch window.

## B2. Shot scoring (`scoring.py`)

Every shot is sampled at 4 fps on the proxy and scored 0–1:

```
S = 0.25·M + 0.20·F + 0.15·Sh + 0.15·A + 0.15·Ae + 0.10·St
```

| Term | Meaning | Measured by | Normalization |
| --- | --- | --- | --- |
| M | Motion | Mean optical-flow magnitude | Percentile rank within the project |
| F | Subject | Larger of the MediaPipe face box and the YOLO person box, as a share of the frame; a quarter of the frame is full marks | 0 none … 1 large subject |
| Sh | Sharpness | Laplacian variance | Percentile rank |
| A | Action | Object velocity peak: the 90th percentile of the fastest object's speed, in frame widths per second. Pose keypoints are not used yet. Object speed is measured in the frame, so a camera pan counts as speed | Percentile rank |
| Ae | Aesthetics | LAION aesthetic predictor on CLIP embeddings | (output − 1) / 9, clamped to 0–1 |
| St | Stability | 1 − camera shake (global flow variance) | 0–1 |

A shot's first sampled frame is left out of M, St, the peak moment and the motion direction, because its optical flow was measured across the cut.

Each shot also stores: peak moment (frame with the highest M × F), usable windows (sharp, not too dark), tags, caption, motion direction, dominant color, CLIP embedding, `cameraMode`, `nativeFps`.

- **Tags:** vocabulary words (`TAG_VOCABULARY` in `shot_tags.py`) with CLIP similarity > 0.25, at most 5, plus YOLO labels seen in at least 25% of the shot's frames. Tags are compared as the phrase "a photo of {tag}".
- **Motion direction:** `left`, `right`, `up`, `down` or `none`, the way the picture moves, so a camera panning right gives `left`. It is `none` when the mean flow is under 0.2 px at 320 px width, or under 30% of the mean flow magnitude.
- **Dominant color:** the most common per-frame color, where a frame's color is the fullest 32-level RGB bin, as `#rrggbb`.
- **Embedding:** the normalized mean of the frames' unit CLIP vectors, stored as plain floats rounded to 5 decimals.

**Reject** when S < 0.2, mean luma < 0.08, or it duplicates a better shot (CLIP cosine similarity > **0.98**). Shots are compared best first, and only against shots that were kept. Why 0.98, not 0.95: on the real 10-clip set 45 of 112 shots were rejected as duplicates at 0.95, 39 of them from one 171 s trail-run POV clip. Looking at the pairs, shots at 0.95 to 0.97 were different moments of the same kind of rock and arms (CLIP scores one clip's frames around 0.92 against each other); only pairs at 0.985 and above were visibly the same moment. At 0.98, 10 are rejected.

**Shot detection** (`scenedetect_shots.py`): PySceneDetect `ContentDetector` at its default threshold 27, then a cut is kept only if its change is at least **2.5 times the clip's own median frame change** (never below 27). A steady clip has a median of 2 to 10 and is untouched. A shaky POV or handheld pan has a median near 20, so the fixed 27 fired on every shake: the same trail-run clip was cut into 57 shots (69 cuts before the rejection of tiny scenes), and frames on either side of those cuts show one continuous take.

**CLIP shot search** (`application/search_shots.py`): ranks shots by similarity to a text, marking those above 0.25. It gives B4's prompt fit its data for included and excluded tags; it never picks shots.

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
5. **Order:** chronological (by capture time) for Travel or when the prompt asks; energy-driven for every other style. Ties are broken by the seed. Chronological order walks the timeline and takes the least-used, earliest shot the constraints in step 3 allow. Capture time is not stored yet, so "by capture time" means asset order, then time inside the clip.
6. **Too few matches:** `includeTags` drop every other shot, unless the matching shots hold less usable footage than the edit window. Then the best-scoring other shots top them up until it is covered, and the plan log says so. A tag no shot has is logged and ignored. If `excludeTags` would remove every shot, that request is ignored and logged.

## B5. Effect rules (`effects.py`)

| Moment | Effects applied |
| --- | --- |
| First beat of a drop | Speed ramp, white flash (0.08 s), shake, zoom punch or FOV punch (360) |
| Accent beat | Shake (strength = onset strength) or zoom punch 1.0 → 1.15, alternating |
| Regular beat cut | Hard cut or whip transition, alternating (every other regular cut is a whip, left and right alternating) |
| Section change | Signature transition: zoom-through, spin or glitch; tiny planet for 360 |
| Build | Slow push-in, rising shake, speed rising 1.0× → 1.5× |
| Break | Slow motion, grain, no shake |
| Final downbeat | Freeze frame, then fade to black |

**Caps:** shakes on at most 40% of beats; at most one flash per bar outside drops; transitions on at most half of all cuts. Every strength is multiplied by the style's FX intensity; a prompt's `fxIntensity` replaces the style's value, so it can raise effects as well as lower them, and 0 means no effects. Motion blur is applied to every segment with zoom, spin or whip, amount = style FX intensity × 0.7.

## B6. Speed ramp curve (`ramps.py`)

For a ramped slot of length D (timeline seconds):

| Phase | Timeline span | Speed |
| --- | --- | --- |
| Fast | 0 → 0.4 D | 2.5× |
| Ease down | 0.4 D → 0.5 D | 2.5× → 0.25× |
| Hold slow | 0.5 D → 0.8 D | 0.25× |
| Ease up | 0.8 D → D | 0.25× → 1× |

- Easing: cubic-bezier(0.7, 0, 0.3, 1).
- The start of the slow hold sits on the beat grid: a slot is ramped only when its middle is on a grid point (every beat and half beat) and it is at least 0.5 s long. `slowmoAt` sections and the first slot of each Velocity drop get ramps; a slot no window can hold with the curve's extra source (1.34 D) stays at 1x.
- Slow frames come from native 100/120 fps footage when available, otherwise RIFE.
- Source length needed = ∫ speed(τ) dτ over D; B4's length fit uses this.

## B7. Reframing rules (`reframe.py`)

- **Flat clips:** crop window at the output ratio, as large as possible. Center = subject center smoothed with a 1€ filter; 10% dead zone; max pan 15% of frame width per second (unlimited across cuts). A single subject sits on a rule-of-thirds line in the direction of motion.
- **Flat clips, subject:** analysis stores the main subject (largest person, else largest object) per 4 fps sample as `subjectTrack`; the plan keeps the resulting crop path in `reframe.path`.
- **360 clips:** `settings.followPoint` (a tap on the equirect frame) starts the camera on that subject. When SAM 2 measured the subject (spec 08 rule 5, `ClipInput.followTrack`), the camera follows that track and holds its last bearing where the track ends; otherwise detections within 40 degrees of the point are followed, and failing that the camera holds the point. The planner only reads the measured track; the model work is in the application and adapter layers. Drop first beat: beat spin. Accents: FOV punch (140 to 70, spec 08) in place of the zoom punch. Last slot before a section change: tiny planet. Pitch limit last. Yaw follows the subject at pitch −5°, FOV 100° (90° for 9:16 and 4:5). Drop → 360° yaw spin over one beat. Section change → tiny planet (pitch −90°, FOV 160°, stereographic). Pitch stays above −60° except during tiny planet, keeping the selfie stick out of frame.
- **Photos:** Ken Burns from 1.0 to 1.12 scale toward the subject, or depth parallax when depth contrast is high.

## B8. Text and audio (`effects.py`, `render/audio.py`)

- Text appears only when the prompt gives it, popping on the next downbeat, placed behind the subject when a SAM 2 mask exists. The planner sets `behindSubject` when the shot under the text has a subject track. At render, a face found in the first frame of the text window (plus a torso point below it) prompts SAM 2.1 small, which follows the subject through the window; the mattes are exactly one per frame and the subject is composited over the text on the 10-bit pipeline. No face or no mask means the text stays in front, never a failed job. Shot captions (Qwen2.5-VL 3B via Ollama, `keep_alive` 0 on the last call of a clip) cover the 40 best shots of each clip; a failure means no caption.
- Captions only when speech is detected (faster-whisper) and the style is not Cinematic.
- Music normalized to −14 LUFS. Whoosh on transitions at −18 dB, impact on each drop.
- Clip audio muted unless speech is detected; then kept, and music ducks 8 dB under it.

## B9. Prompt to constraints (`prompt.py`)

The LLM turns the prompt into a constraint JSON (schema in `06-edit-plan-schema.md`) that the rules engine applies. A keyword fallback parser handles common phrases ("slow mo", "no shake", "cinematic", "only car") if the LLM fails. Any request that maps to nothing is skipped and listed in the job log shown to the user.

Requests the current phase cannot carry out (`text` and `effectsOn` until their effects exist) are recorded in `plan.log` too, so nothing is dropped silently. `durationSec` beats the length setting. The style comes from the prompt first, then the user's style setting, then the director's own pick, then the B10 rules.

## B10. LLM director and fallback (`director.py`)

- **Input to the LLM:** compact JSON with music sections (type, start, end, energy), the top 40 shots (id, tags, caption, score, cameraMode), user settings and the prompt. Max ~3,000 tokens.
- **Message shape:** the project JSON goes in the system message, worked examples follow as user and assistant turns, and the prompt is the last user turn. Thinking is off. With the JSON and prompt in one user message, `qwen3:4b` echoes its input.
- **Output:** `{ style, storyHints[], constraints }`, requested with Ollama `format: json` and validated against the schema; one retry on invalid JSON. Unknown fields are invalid, so an echo of the input cannot pass as an empty answer. `storyHints` are logged; no rule reads them yet.
- **Fallback** (invalid output or Ollama not running): style picked by rule, in order:
  1. BPM ≥ 140 → Hype
  2. BPM ≥ 120 and drop intensity ≥ 0.6 → Velocity
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
