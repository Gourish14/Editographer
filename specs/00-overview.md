# 00 — Overview

The app turns raw clips, photos and a music track into a finished, beat-synced, effect-heavy edit with zero manual work. The user picks an aspect ratio and a resolution, optionally types a prompt, and gets the final video back.

## Inputs

- Raw videos (built for DJI Osmo 360 single-lens and 360 footage; any MP4/MOV also works)
- Raw photos (JPG, PNG, HEIC, DJI panoramic photos)
- One or more music tracks (MP3, WAV, M4A, FLAC)
- Optional text prompt

## User choices

| Option | Values | Default |
| --- | --- | --- |
| Aspect ratio | 16:9, 9:16, 1:1, 4:5, 4:3, 21:9 | 9:16 |
| Quality | 4K, 6K, 8K | 4K |
| Frame rate | 24, 30, 60 | 30 |
| Style | Auto, Velocity, Hype, Cinematic, Anime-style, Travel, Car edit, Sports | Auto |
| Render mode | Preview, Fast, Max quality | Fast |
| Length | Auto (up to 60 s) or a number of seconds | Auto |
| Cool mode | On / Off | Off |
| Prompt | Free text | Empty |

## Modes of operation

- **Auto mode:** with no prompt, the AI director picks a style from the music's energy and the footage content, and edits on its own.
- **Prompt mode:** instructions like "slow-mo on the drop, heavy shakes, cinematic grade" override the defaults (see `05-editing-brain.md` B9).
- **Variations:** "Make another version" re-runs planning with a new seed on the same inputs.

## Output sizes

The long edge is 3840 (4K), 6144 (6K) or 7680 (8K); the short edge follows the ratio and is rounded to an even number.

| Ratio | 4K | 6K | 8K |
| --- | --- | --- | --- |
| 16:9 | 3840 × 2160 | 6144 × 3456 | 7680 × 4320 |
| 9:16 | 2160 × 3840 | 3456 × 6144 | 4320 × 7680 |
| 1:1 | 3840 × 3840 | 6144 × 6144 | 7680 × 7680 |
| 4:5 | 3072 × 3840 | 4916 × 6144 | 6144 × 7680 |
| 4:3 | 3840 × 2880 | 6144 × 4608 | 7680 × 5760 |
| 21:9 | 3840 × 1646 | 6144 × 2634 | 7680 × 3292 |

Output file: MP4, HEVC (H.265) 10-bit, AAC 320 kbps stereo, encoded with NVENC.
