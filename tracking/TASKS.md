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
| T-110 | Worker: music analysis and music map (B1) | Todo | T-109 |
| T-111 | Worker: shot detection and basic scoring (B2 partial) | Todo | T-109 |
| T-112 | Worker brain: pacing, assignment, basic effects, validation → edit plan | Todo | T-110, T-111 |
| T-113 | Worker render: compose, crop all ratios, effects, audio, NVENC encode, Preview + Fast | Todo | T-112 |
| T-114 | Frontend scaffold (Angular, structure, API clients, interceptors, lint, tests) | Todo | T-101 |
| T-115 | Frontend: projects, upload, asset grid, music waveform | Todo | T-114, T-105 |
| T-116 | Frontend: render settings, live progress, result player and download | Todo | T-115, T-107 |
| T-117 | start.bat / stop.bat / scripts/check.bat, Angular build into backend | Todo | T-107, T-113, T-116 |
| T-118 | Phase 1 gate: end-to-end run, beat-accuracy check, timing | Todo | T-117 |

## Details

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
- Status: Todo
- Spec: 05-editing-brain.md#b1-music-map-music_mappy
- Depends on: T-109
- Acceptance criteria:
  - [ ] Beat This! adapter + librosa energy/onsets.
  - [ ] Pure `build_music_map()` with sections, accent beats, edit window; unit tests on synthetic beat/energy data.
  - [ ] Fixture song produces stable output (golden test).

### T-111 — Worker: shots and basic scoring
- Status: Todo
- Spec: 05-editing-brain.md#b2-shot-scoring-scoringpy
- Depends on: T-109
- Acceptance criteria:
  - [ ] PySceneDetect shots; motion (optical flow), sharpness, MediaPipe faces, luma at 4 fps on proxies.
  - [ ] Pure scoring function using available terms (others weighted 0 until Phase 2, weights renormalized); reject rules.
  - [ ] Peak moment and usable windows stored in analysis JSON.

### T-112 — Worker brain → edit plan
- Status: Todo
- Spec: 05-editing-brain.md#b3, #b4, #b5, #b11; 06-edit-plan-schema.md
- Depends on: T-110, T-111
- Acceptance criteria:
  - [ ] Pacing for Velocity and Cinematic; slots cover the window exactly, all on beats.
  - [ ] Assignment with all B4 constraints; deterministic with seed.
  - [ ] Basic B5 effects (zoom punch, shake, flash, hard cut) with caps.
  - [ ] Validation B11; plan JSON matches 06 schema (pydantic model).
  - [ ] Unit tests named after rules (`test_b4_…`).

### T-113 — Worker render (Phase 1 scope)
- Status: Todo
- Spec: 04-pipeline.md#stages (6, 8, 9), 00-overview.md#output-sizes, 09-local-setup.md#render-modes
- Depends on: T-112
- Acceptance criteria:
  - [ ] Decode only needed windows; subject/center crop for all 6 ratios at 4K.
  - [ ] Zoom punch, shake, flash rendered; music cut on downbeats; -14 LUFS.
  - [ ] `hevc_nvenc` 10-bit output; preview.mp4 (1080p) first, then final.
  - [ ] Progress posted with stage weights from 04.

### T-114 — Frontend scaffold
- Status: Todo
- Spec: 11-coding-standards.md#5-frontend--angular
- Depends on: T-101
- Acceptance criteria:
  - [ ] Angular app with `core/ shared/ features/`, routing, standalone + OnPush + signals.
  - [ ] Typed API clients and models from 07; request-id and error interceptors; NotificationService.
  - [ ] ESLint, Prettier, Vitest configured; one passing test per service.

### T-115 — Frontend: projects and uploads
- Status: Todo
- Spec: 07-api-and-data.md#angular-screens
- Depends on: T-114, T-105
- Acceptance criteria:
  - [ ] Projects page; project page with tus drag-and-drop upload and progress.
  - [ ] Asset grid with status and badges; music waveform with beats (wavesurfer.js).

### T-116 — Frontend: render flow
- Status: Todo
- Spec: 07-api-and-data.md#angular-screens, 00-overview.md#user-choices
- Depends on: T-115, T-107
- Acceptance criteria:
  - [ ] Render settings form with every option from 00; prompt box.
  - [ ] Live progress via SSE; preview plays as soon as ready; cancel.
  - [ ] Result page with player, download, "Make another version".

### T-117 — Scripts and build integration
- Status: Todo
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
