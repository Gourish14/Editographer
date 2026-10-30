# 11 — Coding standards (enterprise level)

All code in this repo follows these rules. They are checked by tools in CI-style scripts (`scripts/check.bat`) and by the review checklist at the end. When a rule must be broken, record why in `tracking/DECISIONS.md`.

## 1. SOLID, applied to this project

| Principle | Rule here | Concrete example |
| --- | --- | --- |
| **S** — Single responsibility | One class/module = one reason to change. Controllers only map HTTP; services hold use-case logic; repositories only persist. | `brain/pacing.py` only builds slots; it never picks shots. `RenderController` never touches the file system. |
| **O** — Open/closed | New behavior is added by registering a new implementation, not by editing a switch. | Effects, transitions and styles are registries: add `GlitchTransition` + register it; the compositor is unchanged. |
| **L** — Liskov substitution | Every implementation of a port honors the port's contract (inputs, outputs, errors). Contract tests run against every implementation. | `LocalStorageService` and a future `MinioStorageService` pass the same `StorageServiceContractTest`. |
| **I** — Interface segregation | Small, focused ports. No "god" interfaces. | `MediaReader`, `MediaWriter`, `MediaLocator` instead of one `MediaService`. |
| **D** — Dependency inversion | Domain and application code depend on interfaces (ports); infrastructure implements them. Wiring happens only at the composition root. | The brain depends on `LlmClient` (Protocol); `OllamaLlmClient` lives in `adapters/`. Spring injects `WorkerClient`, not `RestClient`. |

Also: **DRY** (no copy-paste logic; extract), **KISS** (simplest design that meets the spec), **YAGNI** (build only what a spec or task asks for), **composition over inheritance**, **immutability by default** (Java records, Python frozen dataclasses / pydantic models, TypeScript `readonly`).

## 2. Architecture style: hexagonal (ports and adapters), packaged by feature

```
            ┌──────────── api / inbound adapters ────────────┐
            │  REST controllers, FastAPI routes, Angular UI  │
            └───────────────────────┬────────────────────────┘
                                    ▼
            ┌──────────────── application ───────────────────┐
            │  use cases / services, orchestrate, transactions│
            └───────────────────────┬────────────────────────┘
                                    ▼
            ┌────────────────── domain ──────────────────────┐
            │  entities, value objects, pure rules, ports     │
            └───────────────────────▲────────────────────────┘
                                    │ implements ports
            ┌───────── infrastructure / outbound adapters ───┐
            │  JPA, files, FFmpeg, PyTorch models, Ollama     │
            └─────────────────────────────────────────────────┘
```

Dependency rule: arrows point inward only. Domain never imports framework code. Enforced by ArchUnit (Java) and import-linter (Python).

## 3. Backend — Spring Boot 4, Java 25

### Package structure

```
backend/src/main/java/com/editographer/
  EditographerApplication.java
  common/
    error/          ApiException, ErrorCode enum, GlobalExceptionHandler (RFC 9457 ProblemDetail)
    logging/        RequestIdFilter (MDC), LoggingConstants
    config/         AppProperties (@ConfigurationProperties), WebConfig, SchedulingConfig
  project/
    api/            ProjectController, dto/ (CreateProjectRequest, ProjectResponse — records)
    application/    ProjectService
    domain/         Project, ProjectId, ProjectRepository (port)
    infrastructure/ JpaProjectEntity, JpaProjectRepository, ProjectRepositoryAdapter, ProjectMapper
  asset/            same four layers
  upload/           tus integration (infrastructure), UploadCompletedHandler (application)
  render/           same four layers + RenderSettings value object
  job/              JobQueue port, JobDispatcher (@Scheduled), JpaJobQueueAdapter
  worker/           WorkerClient port, HttpWorkerClient adapter, InternalCallbackController
  storage/          StorageService ports (MediaReader/Writer/Locator), LocalStorageAdapter
  events/           EventPublisher port, SseEventPublisher adapter
  system/           SystemStatusController, GpuStatus from worker /health
```

### Rules

- Constructor injection only; no field `@Autowired`. Classes `final` where possible.
- DTOs are Java `record`s; JPA entities never leave the infrastructure layer (map with MapStruct or hand-written mappers).
- Validation with Jakarta Bean Validation on request DTOs; domain invariants checked in domain constructors.
- All errors become `ProblemDetail` responses with a stable `errorCode` (e.g. `RENDER_NOT_FOUND`, `WORKER_UNAVAILABLE`).
- Transactions only in the application layer (`@Transactional` on services, never on controllers or repositories).
- No `null` returns from public methods; use `Optional` for lookups.
- Config only through `AppProperties`; no `@Value` scattered in classes. No magic numbers: constants or config.
- Flyway owns the schema (`V1__init.sql`, …); `ddl-auto=validate`.

### Tooling

| Tool | Purpose | Gate |
| --- | --- | --- |
| JUnit 5 + AssertJ + Mockito | Unit tests | All pass |
| Spring Boot test slices (`@WebMvcTest`, `@DataJpaTest`) | Adapter tests | All pass |
| ArchUnit | Enforce layer and dependency rules | All pass |
| JaCoCo | Coverage | ≥ 80% lines on `domain` + `application` |
| Spotless (google-java-format) | Formatting | No diff |
| Checkstyle + SpotBugs | Static analysis | No errors |

## 4. Worker — Python 3.12

### Package structure

```
worker/
  pyproject.toml          deps, ruff, mypy, pytest, import-linter config
  app/
    main.py               composition root: builds adapters, injects into services, creates FastAPI app
    config.py             pydantic-settings Settings (reads config/local.env)
    logging_setup.py      structlog JSON config
    api/                  routes.py (FastAPI), schemas.py (pydantic request/response models)
    domain/               pure, no I/O, fully unit-testable
      models.py           MusicMap, Beat, Section, Shot, Slot, EditPlan, Segment, Constraints …
      brain/              music_map.py, scoring.py, pacing.py, assign.py, effects.py, ramps.py,
                          reframe.py, prompt_rules.py, style_rules.py, validate.py
      registries.py       effect / transition / style registries (open/closed)
    ports/                Protocols: MediaProbe, FrameSource, BeatTracker, ShotDetector, Detector,
                          Embedder, Captioner, LlmClient, Interpolator, Upscaler, Compositor,
                          Encoder, BackendNotifier, Cache, GpuGuard
    application/          use cases: analyze_asset.py, plan_render.py, render_job.py, job_runner.py
    adapters/             ffmpeg_probe.py, pyav_frames.py, beat_this_tracker.py, scenedetect.py,
                          mediapipe_detector.py, yolo_detector.py, clip_embedder.py,
                          ollama_llm.py, rife_interpolator.py, realesrgan_upscaler.py,
                          moderngl_compositor.py, nvenc_encoder.py, http_backend_notifier.py,
                          file_cache.py, nvml_gpu_guard.py
  tests/
    unit/                 domain tests (no GPU, no files)
    contract/             one contract test per port, run against every adapter
    integration/          adapters with small sample media (marked `gpu` when they need CUDA)
    fixtures/             tiny sample clips, a 20 s test song, expected music maps
```

### Rules

- Full type hints; `mypy --strict` passes. Data crosses boundaries as pydantic models or frozen dataclasses, never raw dicts.
- `domain/` imports nothing from `adapters/`, `api/`, FastAPI, torch, cv2 or ffmpeg (import-linter contract).
- Brain functions are **pure and deterministic**: same inputs + same seed = same edit plan. Randomness only via an injected `random.Random(seed)`.
- Every GPU model is loaded through `GpuGuard` (context manager): acquire lock → load → run batch → unload → `empty_cache()`.
- Long work is cancellable: application loops check a `CancellationToken` between segments.
- No bare `except:`; catch specific errors, wrap into domain errors (`AnalysisError`, `RenderError`) with an error code.
- Subprocess calls (ffmpeg) go through one adapter with argument lists (never shell strings) and logged command lines.

### Tooling

| Tool | Purpose | Gate |
| --- | --- | --- |
| pytest + pytest-cov | Tests | All pass; ≥ 85% on `domain/` |
| ruff (lint + format) | Lint, formatting, import order | No errors |
| mypy --strict | Types | No errors |
| import-linter | Layer rules | No violations |

## 5. Frontend — Angular

### Structure

```
frontend/src/app/
  core/          api/ (typed API clients per backend feature), interceptors/ (request-id, error),
                 services/ (SseService, NotificationService), models/ (TypeScript interfaces from 07 spec)
  shared/        ui/ (presentational components: buttons, badges, progress, waveform, player),
                 pipes/, directives/
  features/
    projects/    projects-page (smart), project-card (presentational)
    project/     project-page, upload-zone, asset-grid, music-waveform
    render/      render-settings, render-progress, render-result
  app.routes.ts, app.config.ts
```

### Rules

- Standalone components, `ChangeDetectionStrategy.OnPush`, signals for state, new control flow (`@if`, `@for`).
- **Smart vs presentational:** pages (smart) talk to services; `shared/ui` components only use `input()` / `output()`.
- Components never call `HttpClient` directly; only `core/api` clients do.
- `strict: true` TypeScript; no `any`. API models match `07-api-and-data.md` exactly.
- All user-facing errors go through `NotificationService`; the error interceptor maps `ProblemDetail.errorCode` to a readable message.
- Accessibility: every control has a label; keyboard reachable.

### Tooling

| Tool | Purpose | Gate |
| --- | --- | --- |
| Vitest (Angular unit tests) | Component and service tests | All pass |
| ESLint (angular-eslint) | Lint | No errors |
| Prettier | Formatting | No diff |

## 6. Logging (all three apps)

- **Format:** JSON lines. Fields: `ts`, `level`, `service` (backend / worker / frontend), `requestId`, `jobId`, `renderId`, `event`, `message`, `durationMs`, `errorCode`.
- **Correlation:** the backend creates `X-Request-Id` per request and passes `requestId` + `jobId` to the worker; the worker logs them on every line. One render can be traced end to end with `jobId`.
- **Levels:** `ERROR` = failed operation needing attention; `WARN` = degraded but continuing (e.g. LLM fallback used); `INFO` = stage start/finish with timing; `DEBUG` = details, off by default.
- **Files:** `logs/backend.log`, `logs/worker.log`, rotated daily, 14 days kept. The frontend sends errors to `POST /api/client-logs` (rate-limited).
- **Never log:** file contents, full prompts above 500 chars, the worker token, personal paths outside the project.
- Every caught `ERROR` that is not an expected user error is also written to `tracking/BUGS.md` as a candidate during development (see `12-spec-driven-development.md`).

## 7. Error codes

One shared catalog in `specs/07-api-and-data.md` style, implemented as `ErrorCode` (Java enum) and `ErrorCode` (Python `StrEnum`) with the same values, e.g. `PROJECT_NOT_FOUND`, `UPLOAD_FAILED`, `ASSET_UNSUPPORTED`, `ANALYSIS_FAILED`, `WORKER_UNAVAILABLE`, `GPU_OUT_OF_MEMORY`, `LLM_INVALID_OUTPUT`, `PLAN_INVALID`, `RENDER_FAILED`, `RENDER_CANCELLED`.

## 8. Naming

| Item | Java | Python | TypeScript |
| --- | --- | --- | --- |
| Classes | `PascalCase` | `PascalCase` | `PascalCase` |
| Methods / functions | `camelCase` | `snake_case` | `camelCase` |
| Constants | `UPPER_SNAKE` | `UPPER_SNAKE` | `UPPER_SNAKE` |
| Files | `PascalCase.java` | `snake_case.py` | `kebab-case.component.ts` |
| Ports | `XxxRepository`, `XxxClient` | `Xxx` Protocol | — |
| Adapters | `JpaXxxAdapter`, `HttpXxxClient` | `xxx_adapter.py` | — |

Names say what, not how: `assign_shots_to_slots()`, not `process()`.

## 9. Traceability comments

Every module that implements a spec rule starts with one line naming it, e.g.

```python
"""Shot assignment. Spec: specs/05-editing-brain.md#b4-shot-assignment"""
```

Tests for a spec rule carry the rule id in their name: `test_b4_two_consecutive_slots_never_share_source_clip`.

## 10. Git and versioning

- Branch per task: `task/T-105-uploads`, `bug/BUG-012-sse-drop`, `cr/CR-004-…`.
- Conventional Commits: `feat(render): add zoom punch effect [T-113]`, `fix(worker): free VRAM after CLIP [BUG-012]`. Every commit references a task, bug or CR id.
- Semantic Versioning in `VERSION`; each phase gate = minor release (`0.1.0` after Phase 1).
- `CHANGELOG.md` follows Keep a Changelog.

## 11. Review checklist (run before marking any task Done)

- [ ] Matches the referenced spec sections; spec updated if behavior changed.
- [ ] SOLID and layer rules respected (ArchUnit / import-linter green).
- [ ] Tests added for every acceptance criterion of the task; all tests pass.
- [ ] Lint, format, type checks pass (`scripts/check.bat`).
- [ ] Logging with correlation ids; no secrets logged.
- [ ] Errors use the shared error codes.
- [ ] No new paid dependency; license recorded in `03-tech-stack.md` if a dependency was added.
- [ ] Tracking files updated (TASKS, CHANGELOG, DEV_LOG, BUGS if any).
