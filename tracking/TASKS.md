# Task board

Current phase: **Phase 1 — Core engine** (gate in `specs/10-roadmap.md`).
Rules: pick the first `Todo` task whose dependencies are `Done`; Critical/High bugs first. See `specs/12-spec-driven-development.md`.

## Summary

| ID | Title | Status | Depends on |
| --- | --- | --- | --- |
| T-101 | Repository scaffold and conventions | Done | — |
| T-102 | setup.bat and model download script | Done | T-101 |
| T-103 | Backend scaffold (Spring Boot 4, H2, Flyway, errors, logging, ArchUnit) | Done | T-101 |
| T-104 | Backend: projects feature | Done | T-103 |
| T-105 | Backend: storage service and tus uploads, assets | Done | T-104 |
| T-106 | Backend: job queue, dispatcher, worker client, internal callbacks | Done | T-105 |
| T-107 | Backend: render API and SSE events | Done | T-106 |
| T-108 | Worker scaffold (uv, FastAPI, settings, logging, GPU guard, health) | Done | T-101 |
| T-109 | Worker: ingest (probe, hash, proxy, camera mode, cache) | Done | T-108 |
| T-110 | Worker: music analysis and music map (B1) | Done | T-109 |
| T-111 | Worker: shot detection and basic scoring (B2 partial) | Done | T-109 |
| T-112 | Worker brain: pacing, assignment, basic effects, validation → edit plan | Done | T-110, T-111 |
| T-113 | Worker render: compose, crop all ratios, effects, audio, NVENC encode, Preview + Fast | Done | T-112 |
| T-114 | Frontend scaffold (Angular, structure, API clients, interceptors, lint, tests) | Done | T-101 |
| T-115 | Frontend: projects, upload, asset grid, music waveform | Done | T-114, T-105 |
| T-116 | Frontend: render settings, live progress, result player and download | Done | T-115, T-107 |
| T-117 | start.bat / stop.bat / scripts/check.bat, Angular build into backend | Done | T-107, T-113, T-116 |
| T-118 | Phase 1 gate: end-to-end run, beat-accuracy check, timing | Todo | T-117 |
| T-201 | Worker: full shot analysis (YOLO, OpenCLIP tags and aesthetics, full B2) | Todo | T-117 |
| T-202 | Worker: prompt constraints, Ollama director, keyword fallback, 7 styles (B9, B10) | Todo | T-117 |
| T-301 | Worker: RIFE and Real-ESRGAN adapters | Todo | T-117 |
| T-302 | Worker: ramps, reframe and camera path rules, 360 projection (B6, B7, 08) | Done | T-117 |
| T-303 | Worker: LUTs, D-Log M, transitions, motion blur, SFX, ducking, cool mode | Todo | T-117 |
| T-401 | Backend and frontend: render tonight, 360 preview, subject picker, live GPU status | Done | T-117 |
| T-402 | Worker: speech detection, text rules, text layers | Done | T-117 |
| T-403 | Worker: photo analysis, Ken Burns, depth parallax | Done | T-117 |
| T-404 | Wire photos, speech and text into analysis, planner and renderer | Todo | T-202, T-303, T-402, T-403 |
| T-405 | Wire ramps, smart reframe and 360 into planner and renderer, add the spec 08 effects | Todo | T-202, T-301, T-302, T-303 |

## Details

### T-401 — Backend and frontend: render tonight, 360 preview, subject picker
- Status: Done
- Spec: 09-local-setup.md#cool-mode, 08-osmo360.md#ui-additions, 07-api-and-data.md#angular-screens
- Notes: Migration V3. The three.js preview has not been seen in a real browser, because the tests have no WebGL. It assumes thumbnails of 360 clips are equirect frames, which is unchecked. The worker does not read `followPoint` yet. "Make another version" drops `startAt`. Skipped prompts are found by matching "skipped" in the plan log.

### T-404 — Wire photos, speech and text into the pipeline
- Status: Todo
- Spec: 05-editing-brain.md#b4, #b7, #b8, 06-edit-plan-schema.md
- Depends on: T-202, T-303, T-402, T-403
- Acceptance criteria:
  - [ ] `analyze_asset.py` runs photo analysis and speech detection; the plan gains `text[]`; photo segments render.
  - [ ] B4: photos fill at most 30% of slots and never a drop, unless the input is only photos.
  - [ ] Clip audio is kept and music ducks 8 dB only where speech exists.

### T-403 — Worker: photo analysis, Ken Burns, depth parallax
- Status: Done
- Spec: 04-pipeline.md#stages (4), 05-editing-brain.md#b4, #b7
- Notes: Merged but not wired in (T-404). Verified on one generated image, 45 of 45 frames for both motions. Not tested on a real face or a rotated JPEG, and peak VRAM was not measured.

### T-402 — Worker: speech detection, text rules, text layers
- Status: Done
- Spec: 05-editing-brain.md#b8, 06-edit-plan-schema.md
- Notes: Merged but not wired in (T-404). Real Whisper found speech in a synthesized clip and none in the test song. The CUDA path is unverified. Text is drawn in front: SAM 2 text-behind-subject is still to do.

### T-303 — Worker: look, sound and cool mode
- Status: Todo
- Spec: 04-pipeline.md, 05-editing-brain.md#b5, #b8, 08-osmo360.md, 09-local-setup.md#cool-mode
- Depends on: T-117
- Acceptance criteria:
  - [ ] Style LUTs and D-Log M to Rec.709 applied by the compositor; transitions and motion blur in the filter graph.
  - [ ] SFX at -18 dB, speech ducking 8 dB.
  - [ ] Cool mode: 10 s pause between GPU stages, NVML watch every 2 s, pause at 83 °C, resume at 75 °C.

### T-302 — Worker: motion rules and 360 projection
- Status: Done
- Spec: 05-editing-brain.md#b6, #b7, 08-osmo360.md
- Depends on: T-117
- Acceptance criteria:
  - [x] Pure `ramps.py` with the B6 curve and source-length integral; pure `reframe.py` with B7 rules and camera360 keyframes.
  - [x] Filter builder renders rectilinear, tiny planet and rabbit hole from equirect.
- Notes: Modules only, not wired in (T-405). Generated media and CPU only, not real footage or NVENC. Call `limit_pitch` last on every 360 path. Ramps need B11 to use `curve_source_length` and a timeline-to-source mapping before `camera_filter`, or they play at 1×. `crop_path` has no plan field yet. FOV punch and the other spec 08 effects are not built.

### T-301 — Worker: frame interpolation and upscaling adapters
- Status: Todo
- Spec: 03-tech-stack.md, 04-pipeline.md#stages (6, 7), 09-local-setup.md
- Depends on: T-117
- Acceptance criteria:
  - [ ] `Interpolator` and `Upscaler` ports with RIFE 4.x and realesr-general-x4v3 adapters through `GpuGuard`; tiled 512 px, fp16, RIFE scale 0.5 above 4K.
  - [ ] Weights in `scripts/models.json` at phase 3 and 4 with real checksums.

### T-201 — Worker: full shot analysis
- Status: Todo
- Spec: 05-editing-brain.md#b2-shot-scoring-scoringpy, 09-local-setup.md#6-gb-vram-model-profile
- Depends on: T-117
- Acceptance criteria:
  - [ ] YOLO nano objects and OpenCLIP ViT-B/32 tags and aesthetics on proxies, loaded through `GpuGuard`.
  - [ ] Full B2 formula with A and Ae; rejects duplicates at CLIP cosine > 0.95.
  - [ ] Tags, motion direction and dominant color stored per shot; weights added to `scripts/models.json` with real checksums.

### T-202 — Worker: prompt constraints and director
- Status: Todo
- Spec: 05-editing-brain.md#b9-prompt-to-constraints-promptpy, #b10-llm-director-and-fallback-directorpy, 06-edit-plan-schema.md#prompt-constraint-json
- Depends on: T-117
- Acceptance criteria:
  - [ ] Pydantic constraint model; Ollama adapter with `format: json`, `keep_alive: 0`, one retry; keyword fallback; the B10 style fallback.
  - [ ] All 7 styles in `style_rules.py`; constraints change the plan: tags, `slowmoAt` recorded, `effectsOff`, `fxIntensity`, `durationSec`, order; unmapped requests in `plan.log`.
  - [ ] With Ollama stopped an edit is still produced; `setup.bat` pulls both models.

### T-101 — Repository scaffold and conventions
- Status: Done
- Spec: 02-architecture.md#project-folder-layout, 11-coding-standards.md#10-git-and-versioning
- Depends on: —
- Acceptance criteria:
  - [x] Folder layout from 02 exists (`frontend/ backend/ worker/ models/ luts/ sfx/ media/ data/ config/ tools/ scripts/ logs/ tracking/`).
  - [x] `git init`, `.gitignore` (media, models, data, logs, venv, node_modules, target, local.env), `.editorconfig`, `VERSION` = 0.0.1.
  - [x] `config/local.env.example` with ports, paths, token placeholder.
- Notes: Added `.gitattributes` so `.bat` files stay CRLF. Empty folders are kept with `.gitkeep`.

### T-102 — setup.bat and model download script
- Status: Done
- Spec: 09-local-setup.md#setupbat-run-once, 03-tech-stack.md
- Depends on: T-101
- Acceptance criteria:
  - [x] Checks Java ≥ 25, Node ≥ 24.15, `nvidia-smi`; clear message on failure (CR-005).
  - [x] Installs FFmpeg and Ollama via winget only if missing; verifies `hevc_nvenc`.
  - [x] Installs uv, Python 3.12, `uv sync` in `worker/`.
  - [x] `scripts/download_models.py` downloads Phase 1 weights with SHA-256 checks, idempotent.
  - [x] Creates `config/local.env` with a random worker token; safe to re-run.
- Notes: `setup.bat` completed twice on the target machine after BUG-001; the second run skipped finished work and kept the token. A third full run after T-108 covered `uv sync` too.

### T-103 — Backend scaffold
- Status: Done
- Spec: 11-coding-standards.md#3-backend--spring-boot-4-java-25, 07-api-and-data.md#database-h2-file-mode-flyway-migrations
- Depends on: T-101
- Acceptance criteria:
  - [x] Spring Boot 4 / Java 25 Maven project with wrapper; package layout from 11 §3.
  - [x] H2 file DB in `data/`, Flyway `V1__init.sql` with all tables from 07.
  - [x] `GlobalExceptionHandler` returns ProblemDetail with `errorCode`; `ErrorCode` enum.
  - [x] JSON logging to `logs/backend.log`, `RequestIdFilter` with MDC.
  - [x] ArchUnit test enforcing layer rules; JaCoCo, Spotless, Checkstyle configured.
- Notes: Verified with `mvnw verify` under the test profile (in-memory H2, formatter unit tests). The packaged jar was started against the file database during T-106. `AppProperties` is added by the first task that needs a setting.

### T-104 — Backend: projects feature
- Status: Done
- Spec: 07-api-and-data.md#backend-rest-api-spring-boot-port-8080
- Depends on: T-103
- Acceptance criteria:
  - [x] `GET/POST /api/projects`, `GET/DELETE /api/projects/{id}` across all four layers.
  - [x] Unit tests for service, `@WebMvcTest` for controller, `@DataJpaTest` for adapter.
- Notes: Spec 07 says GET by id includes assets and renders, and DELETE removes media. T-105 adds assets and media deletion; T-107 adds renders. Until then GET returns the project only and DELETE removes database rows only.

### T-105 — Backend: storage and uploads
- Status: Done
- Spec: 02-architecture.md#storage-replaces-minio, 07-api-and-data.md
- Depends on: T-104
- Acceptance criteria:
  - [x] `MediaReader/MediaWriter/MediaLocator` ports + `LocalStorageAdapter` with contract test.
  - [x] tus endpoint at `/api/uploads/**`, resumable, files land in `media/uploads/{projectId}/`.
  - [x] Upload complete → `asset` row (PENDING) + ANALYZE job queued.
  - [x] Asset list, thumbnail, delete endpoints.
- Notes: `UploadFlowIntegrationTest` runs a real tus conversation with a resume. Finished files are renamed, not copied. The thumbnail endpoint answers 404 until T-109 writes the file (CR-007). `GET /api/projects/{id}` now includes assets, and DELETE removes the project's upload folder. `JobQueue` only has `enqueue` so far; T-106 adds dispatching and must mark a job FAILED when its asset was deleted while it waited. Not yet tried with a real multi-GB file.

### T-106 — Backend: job queue and worker integration
- Status: Done
- Spec: 02-architecture.md#job-queue-replaces-rabbitmq, 07-api-and-data.md#internal-worker--backend-header-x-worker-token
- Depends on: T-105
- Acceptance criteria:
  - [x] `JobQueue` port + JPA adapter; priority ordering; restart resets RUNNING → QUEUED.
  - [x] `JobDispatcher` polls worker `/health` every 2 s and sends one job when idle.
  - [x] `/internal/*` endpoints secured by `X-Worker-Token`; requestId/jobId propagated.
- Notes: Done with `asset-analyzed` and `complete`; `progress`, `preview-ready` and the RENDER sender come with T-107. A job whose asset was deleted is marked FAILED. Tested against mocks and with the real jar, not yet against the real worker, which T-108 builds. T-108's Python `ErrorCode` must also include `JOB_NOT_FOUND`, `WORKER_TOKEN_INVALID`, `ASSET_NOT_FOUND`, `RENDER_NOT_FOUND`, `VALIDATION_FAILED`, `REQUEST_INVALID` and `INTERNAL_ERROR`.

### T-107 — Backend: render API and SSE
- Status: Done
- Spec: 07-api-and-data.md, 04-pipeline.md#preview-first-rule
- Depends on: T-106
- Acceptance criteria:
  - [x] Render create/get/regenerate/cancel, preview and download streaming with Range.
  - [x] SSE `progress`, `preview-ready`, `done`, `failed` events per render.
  - [x] `/api/system` and `/api/styles`.
- Notes: `RenderFlowIntegrationTest` runs the whole flow over real HTTP with only the worker faked. Stage names the worker must send: PLANNING, COMPOSING, UPSCALING, ENCODING; any other stage keeps the status. A render needs at least one music track and one clip (CR-010). Spec 07 promises an SSE update when an asset finishes but has no endpoint for it, so T-115 polls assets (CR-011).

### T-108 — Worker scaffold
- Status: Done
- Spec: 11-coding-standards.md#4-worker--python-312, 07-api-and-data.md#worker-api-fastapi-port-8090-localhost-only
- Depends on: T-101
- Acceptance criteria:
  - [x] uv project on Python 3.12 with layout from 11 §4; ruff, mypy --strict, pytest, import-linter configured.
  - [x] FastAPI app on 127.0.0.1:8090 with `/health`, `/jobs/analyze`, `/jobs/render`, `/jobs/{id}/cancel` (202, one job at a time).
  - [x] structlog JSON logs to `logs/worker.log` with requestId/jobId.
  - [x] `GpuGuard` (lock, load/unload, empty_cache) and NVML status.
- Notes: Verified with the live worker and backend together on the RTX 3050: upload, dispatch, worker report, asset status. `/jobs/analyze` and `/jobs/render` are accepted but fail on purpose until T-109 and T-113 plug in the real work. A second job gets 409, which the backend treats as "stay queued". PyTorch is added by T-110, the first task that needs it. The `worker` ErrorCode test compares against the Java enum, so the two cannot drift.

### T-109 — Worker: ingest
- Status: Done
- Spec: 04-pipeline.md#stages (1), 08-osmo360.md#handling-rules (1–2)
- Depends on: T-108
- Acceptance criteria:
  - [x] ffprobe adapter returns codec, fps, size, rotation, duration, transfer.
  - [x] Content hash and file cache at `media/cache/{hash}/`.
  - [x] 720p NVENC proxy, or `.LRF` reuse; `cameraMode` detection with unit tests per mode.
  - [x] `/internal/asset-analyzed` posted on success.
- Notes: Verified live: a generated 1080p clip went from upload to DONE with a real NVENC proxy and thumbnail. Osmo detection thresholds are unproven against real Osmo files (ADR-010). `GET /api/assets/{id}/waveform` from spec 07 belongs to no task yet, so T-110 adds it.

### T-110 — Worker: music map (B1)
- Status: Done
- Spec: 05-editing-brain.md#b1-music-map-music_mappy
- Depends on: T-109
- Acceptance criteria:
  - [x] Beat This! adapter + librosa energy/onsets.
  - [x] Pure `build_music_map()` with sections, accent beats, edit window; unit tests on synthetic beat/energy data.
  - [x] Fixture song produces stable output (golden test).
- Notes: Energy is scaled against the song's peak, not min to max, so a steady song stays steady (ADR-011). Thresholds still need checking on real songs at the gate. Also added `GET /api/assets/{id}/waveform`, which no task covered. PyTorch 2.11 + CUDA 12.8 is the newest pair with a matching torchaudio.

### T-111 — Worker: shots and basic scoring
- Status: Done
- Spec: 05-editing-brain.md#b2-shot-scoring-scoringpy
- Depends on: T-109
- Acceptance criteria:
  - [x] PySceneDetect shots; motion (optical flow), sharpness, MediaPipe faces, luma at 4 fps on proxies.
  - [x] Pure scoring function using available terms (others weighted 0 until Phase 2, weights renormalized); reject rules.
  - [x] Peak moment and usable windows stored in analysis JSON.
- Notes: Percentile ranks need every clip, so the analysis stores raw numbers and scoring runs at planning. Face detection has only been exercised on clips with no faces.

### T-112 — Worker brain → edit plan
- Status: Done
- Spec: 05-editing-brain.md#b3, #b4, #b5, #b11; 06-edit-plan-schema.md
- Depends on: T-110, T-111
- Acceptance criteria:
  - [x] Pacing for Velocity and Cinematic; slots cover the window exactly, all on beats.
  - [x] Assignment with all B4 constraints; deterministic with seed.
  - [x] Basic B5 effects (zoom punch, shake, flash, hard cut) with caps.
  - [x] Validation B11; plan JSON matches 06 schema (pydantic model).
  - [x] Unit tests named after rules (`test_b4_…`).
- Notes: Half-beat cuts use a grid of beats plus midpoints (ADR-011). A slot longer than every shot is halved on the grid. Other styles fall back to Velocity or Cinematic with a log line until Phase 2. Slow-mo and prompt fit are Phase 2 and 3. Photos are not used yet: they arrive with Ken Burns in Phase 3.

### T-113 — Worker render (Phase 1 scope)
- Status: Done
- Spec: 04-pipeline.md#stages (6, 8, 9), 00-overview.md#output-sizes, 09-local-setup.md#render-modes
- Depends on: T-112
- Acceptance criteria:
  - [x] Decode only needed windows; center crop for all 6 ratios at 4K.
  - [x] Zoom punch, shake, flash rendered; music cut on downbeats; -14 LUFS.
  - [x] `hevc_nvenc` 10-bit output; preview.mp4 (1080p) first, then final.
  - [x] Progress posted with stage weights from 04.
- Notes: First real end-to-end edit through the live API: 44 cuts, worst 16.7 ms from the grid, 719 of 719 frames, 79 s render for 24 s of 4K on simple test clips. Compositor is FFmpeg filters (ADR-012), which encode as they compose, so progress groups compose and encode. Crop is center only: subject tracking is Phase 3 (B7), and spec 10 lists subject crop for Phase 1, recorded in CR-012.

### T-114 — Frontend scaffold
- Status: Done
- Spec: 11-coding-standards.md#5-frontend--angular
- Depends on: T-101
- Acceptance criteria:
  - [ ] Angular app with `core/ shared/ features/`, routing, standalone + OnPush + signals.
  - [ ] Typed API clients and models from 07; request-id and error interceptors; NotificationService.
  - [ ] ESLint, Prettier, Vitest configured; one passing test per service.

### T-115 — Frontend: projects and uploads
- Status: Done
- Spec: 07-api-and-data.md#angular-screens
- Depends on: T-114, T-105
- Acceptance criteria:
  - [ ] Projects page; project page with tus drag-and-drop upload and progress.
  - [ ] Asset grid with status and badges; music waveform with beats (wavesurfer.js).

### T-116 — Frontend: render flow
- Status: Done
- Spec: 07-api-and-data.md#angular-screens, 00-overview.md#user-choices
- Depends on: T-115, T-107
- Acceptance criteria:
  - [ ] Render settings form with every option from 00; prompt box.
  - [ ] Live progress via SSE; preview plays as soon as ready; cancel.
  - [ ] Result page with player, download, "Make another version".

### T-117 — Scripts and build integration
- Status: Done
- Spec: 09-local-setup.md#startbat, 11-coding-standards.md#11-review-checklist-run-before-marking-any-task-done
- Depends on: T-107, T-113, T-116
- Acceptance criteria:
  - [ ] `start.bat` starts Ollama, worker, backend; opens browser when `/api/system` answers.
  - [ ] `stop.bat` stops all.
  - [ ] `scripts/check.bat` runs all tests, lint, types, ArchUnit, import-linter for the three apps.
  - [ ] Angular production build served by the backend at `/`.

### T-118 — Phase 1 gate
- Status: Todo
- Spec: 10-roadmap.md#phase-1--core-engine
- Depends on: T-117
- Acceptance criteria:
  - [ ] 10 clips + 1 song → 4K edit in all 6 ratios.
  - [ ] `scripts/check_beats.py` confirms every cut within one frame of a beat.
  - [ ] 60 s edit in Fast mode < 15 min on the RTX 3050 (recorded in DEV_LOG).
  - [ ] VERSION → 0.1.0, CHANGELOG release section, features set to Verified.
