# 04 — Processing pipeline

Two job types run on the worker: **analyze** (per asset, right after upload) and **render** (per render request). Analysis results are cached by file hash, so a render job usually starts at stage 5.

## Stages

1. **Ingest** (backend + worker)
   - tus upload into `media/uploads/{projectId}/`.
   - Worker runs `ffprobe`: codec, fps, resolution, rotation, duration, color transfer (to detect D-Log M).
   - Content hash (xxhash of first/last 16 MB + size) → cache key.
   - Proxy: if an Osmo `.LRF` with the same file name was uploaded to the project, the backend sends it as `proxySource` and the worker copies it; otherwise create a 720p H.264 proxy with NVENC.
   - Detect `cameraMode` (see `08-osmo360.md`).
   - Thumbnail: a JPEG at 10% of the clip, written to `media/cache/{fileHash}/thumbnail.jpg`. Music has none.
2. **Music analysis** (CPU)
   - Beat This! → beats, downbeats, BPM.
   - librosa → onset strength, RMS energy curve.
   - Section labeling → see `05-editing-brain.md` B1.
3. **Video analysis** (GPU, on proxies, 4 fps sampling)
   - PySceneDetect → shots.
   - Per shot: optical flow (OpenCV), Laplacian sharpness, MediaPipe faces and pose, YOLO nano objects, OpenCLIP tags + aesthetic score, luma.
   - Qwen2.5-VL 3B captions for the top 40 shots only.
   - Score and store per `05-editing-brain.md` B2.
4. **Photo analysis** (GPU)
   - Depth Anything V2 Small → depth map for parallax.
   - Saliency / face box → Ken Burns framing.
5. **Plan** (the brain, `05-editing-brain.md`)
   - Qwen3 4B turns the prompt into constraints and picks style and story hints.
   - Rules engine builds the full edit plan (`06-edit-plan-schema.md`).
   - Validation (B11). Plan saved to `media/renders/{renderId}/plan.json`.
6. **Compose** (GPU)
   - For each segment: decode only the needed window from the original file (NVDEC).
   - D-Log M → Rec.709 LUT if needed.
   - Speed curve: native high-fps frames or RIFE interpolation.
   - Reframe: subject-tracked crop (flat) or keyframed equirect projection (360).
   - Keyframed transforms, shader effects, transitions, motion blur, style LUT, text layers (SAM 2 mask for text-behind-subject).
   - Composited at the **working resolution**: target resolution in Fast mode, or source-limited resolution before upscaling in Max quality mode.
7. **Upscale** (GPU, Max quality only)
   - Real-ESRGAN realesr-general-x4v3, tiled 512 px, factor chosen per segment so each reaches the target size; final resize with Lanczos.
8. **Audio and encode**
   - Music cut to the edit window on downbeats, SFX at transitions (-18 dB) and drops, speech ducking, loudness to -14 LUFS (pyloudnorm). Audio lasts exactly as long as the edit, padded with silence if the music runs out; video frames are never trimmed to fit the audio.
   - FFmpeg `hevc_nvenc`, 10-bit (`p010le`), preset p5, CQ 19, AAC 320 kbps.
9. **Deliver**
   - `final.mp4` written to `media/renders/{renderId}/`, completion posted to the backend, SSE event to the browser.

## Progress weights (for the progress bar)

| Stage | Share of render progress |
| --- | --- |
| Plan | 5% |
| Compose | 50% (Fast) / 30% (Max) |
| Upscale | 0% (Fast) / 35% (Max) |
| Audio and encode | 40% (Fast) / 25% (Max) |
| Deliver | 5% |

## Preview-first rule

Every render request produces `preview.mp4` (1080p, Preview mode) first, then continues to the requested mode in the same job. The UI shows the preview as soon as it is ready.
