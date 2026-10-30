# 10 — Build roadmap

Each phase ends with a working app. Build in order; do not start a phase until the previous gate passes.

## Phase 1 — Core engine

**Builds:** project folder, `setup.bat` / `start.bat`, Spring Boot (projects, tus uploads, H2, job dispatcher, SSE), Python worker (FastAPI, GPU lock), Angular (projects, upload, render settings, progress, result).
Music map (B1), shot detection and basic scoring (motion, sharpness, faces), pacing (B3, Velocity and Cinematic only), shot assignment (B4), hard cuts, zoom punch, shake, flash, center crop for all ratios, FFmpeg NVENC export at 4K, Preview and Fast modes.

**Gate:** 10 raw clips + 1 song → a beat-synced 4K edit in all 6 ratios. Every cut within one frame of a beat. 60-second edit in Fast mode under 15 minutes on the RTX 3050.

## Phase 2 — AI director

**Builds:** full B2 scoring (YOLO, CLIP tags and aesthetics, Qwen2.5-VL captions), Ollama director (B10), prompt to constraints (B9) with keyword fallback, all 7 style presets, CLIP shot search, variations (seed), skipped-prompt log.

**Gate:** prompts "only car shots", "slow-mo on the drop", "cinematic no shakes" each visibly change the edit. With Ollama stopped, an edit is still produced by the fallback.

## Phase 3 — Crazy FX + Osmo 360

**Builds:** speed ramps (B6) with RIFE and native high-fps, shader transitions, motion blur, LUTs incl. D-Log M, SAM 2 text-behind-subject, photo parallax, smart reframe (B7), Osmo detection, `.LRF` proxies, stitched-MP4 360 input, 360 camera paths, beat spin, tiny planet, rabbit hole, FOV punch.

**Gate:** an Osmo 360 8K clip produces a subject-following reframe with a beat spin on the drop and a tiny planet at a section change, in 9:16 and 16:9.

## Phase 4 — Ultra quality

**Builds:** Max quality mode (Real-ESRGAN tiled), 6K/8K output, 60 fps interpolation, raw `.OSV` in-app stitching, auto audio mix with SFX and ducking, captions, cool mode with temperature watch, overnight queue, UI polish.

**Gate:** 8K 9:16 export plays smoothly; cool mode keeps the GPU under 85 °C for a full Max quality render.

## Definition of done (every phase)

- Specs updated to match the code.
- `setup.bat` works on a clean copy of the folder.
- No paid service or API key anywhere.
