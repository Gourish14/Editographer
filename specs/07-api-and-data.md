# 07 — API and data model

Single-user local app: no login. The backend binds to `localhost` only.

## Backend REST API (Spring Boot, port 8080)

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/projects | List projects |
| POST | /api/projects | Create a project `{ name }` |
| GET | /api/projects/{id} | `{ project, assets[], renders[] }` |
| DELETE | /api/projects/{id} | Delete a project and its media |
| POST/PATCH/HEAD | /api/uploads/** | tus resumable upload; metadata `{ projectId, filename }` |
| GET | /api/projects/{id}/assets | Assets with analysis status, thumbnails, camera mode |
| GET | /api/assets/{id}/thumbnail | JPEG thumbnail, 404 until analysis has made one |
| GET | /api/assets/{id}/waveform | Music: `{ durationSec, peaks[], beats[], downbeats[], sections[] }` from `media/cache/{fileHash}/waveform.json`; 404 until analysis has made it |
| DELETE | /api/assets/{id} | Remove an asset |
| POST | /api/projects/{id}/renders | Start a render `{ ratio, quality, fps, style, mode, lengthSec, prompt, coolMode, seed? }`. Omitted values take the defaults from spec 00. The project needs at least one music track and one clip. |
| GET | /api/renders/{id} | Status, progress, stage, log, edit plan |
| GET | /api/renders/{id}/events | SSE stream: `progress`, `preview-ready`, `done`, `failed` |
| POST | /api/renders/{id}/regenerate | New variation (new seed) with the same settings |
| POST | /api/renders/{id}/cancel | Cancel a queued or running render |
| GET | /api/renders/{id}/preview | Stream `preview.mp4` (supports Range) |
| GET | /api/renders/{id}/download | Stream `final.mp4` (supports Range) |
| GET | /api/styles | Style presets |
| GET | /api/system | GPU name, VRAM, temperature, worker and Ollama status |
| POST | /api/client-logs | Browser error `{ message }`, at most 10 logged per minute |

### Internal (worker → backend, header `X-Worker-Token`)

| Method | Endpoint | Body |
| --- | --- | --- |
| POST | /internal/progress | `{ jobId, stage, percent, message }` |
| POST | /internal/asset-analyzed | `{ assetId, analysisPath, fileHash, cameraMode, logProfile, durationSec, width, height, fps }` |
| POST | /internal/preview-ready | `{ jobId, path }` |
| POST | /internal/complete | `{ jobId, status: DONE or FAILED, outputPath?, plan?, error? }` |

## Worker API (FastAPI, port 8090, localhost only)

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /health | `{ busy, currentJobId, gpu: { name, vramFreeMb, tempC } }` |
| POST | /jobs/analyze | `{ jobId, assetId, path, type, proxySource? }` → 202 |
| POST | /jobs/render | `{ jobId, renderId, projectId, settings, assets[] }` → 202 |
| POST | /jobs/{jobId}/cancel | Stop after the current stage |

## Database (H2 file mode, Flyway migrations)

| Table | Columns |
| --- | --- |
| `project` | id (UUID), name, created_at |
| `asset` | id, project_id, type (VIDEO, PHOTO, MUSIC), filename, path, file_hash, size_bytes, duration_sec, width, height, fps, camera_mode, log_profile, analysis_status (PENDING, RUNNING, DONE, FAILED), analysis_path, created_at |
| `render_job` | id, project_id, ratio, quality, fps, style, mode, length_sec, prompt, cool_mode, seed, status (QUEUED, ANALYZING, PLANNING, COMPOSING, UPSCALING, ENCODING, DONE, FAILED, CANCELLED), stage, progress, log (JSON), edit_plan (JSON), preview_path, output_path, error, created_at, finished_at |
| `job` | id, kind (ANALYZE, RENDER), ref_id, priority, status (QUEUED, RUNNING, DONE, FAILED), attempts, created_at, started_at |
| `style_preset` | id, name, defaults (JSON) |

Analysis results stay as JSON files in `media/cache/{fileHash}/analysis.json`; the database only stores the path.

## Spring Boot packages

`project`, `asset`, `upload`, `render`, `job` (queue + dispatcher), `worker` (RestClient to worker), `storage` (`StorageService` over `media/`), `events` (SSE), `system`, `config`.

## Job flow

1. Upload finishes → `asset` row (PENDING) + `job` ANALYZE (priority 1).
2. Dispatcher sees worker idle → `POST /jobs/analyze`.
3. Worker → `/internal/asset-analyzed` → asset DONE → SSE to the UI.
4. User clicks Render → `render_job` QUEUED + `job` RENDER (priority 2). If any asset is not analyzed yet, its analysis runs first.
5. Worker posts progress → backend updates `render_job` and pushes SSE.
6. Preview ready → SSE `preview-ready` → UI plays it.
7. Complete → SSE `done` → download button.

## Angular screens

| Screen | Contents |
| --- | --- |
| Projects | Project cards, New project button, system status (GPU temp, worker, Ollama) |
| Project | Drag-and-drop upload with progress; asset grid with 360 / slow-mo / D-Log badges; music waveform with beats and sections |
| Render settings | Ratio, quality, fps, style, mode, length, cool mode, prompt box, "subject to follow" picker |
| Progress | Stage list with live percent, preview player as soon as ready, cancel |
| Result | Player, download, plan summary (style, cuts, effects), skipped-prompt log, "Make another version" |
