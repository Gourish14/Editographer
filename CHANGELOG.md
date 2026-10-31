# Changelog

All notable changes to Editographer. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- One shared GPU guard, restoring the one-model-at-a-time rule [BUG-003].
- `setup.bat` no longer stops silently after installing FFmpeg [BUG-001].
- A project's `createdAt` is the same on create and read-back [BUG-002].

### Added
- Specs 00–12: overview, features, architecture, stack, pipeline, editing brain, edit plan schema, API and data, Osmo 360, local setup, roadmap, coding standards, spec-driven development process.
- `CLAUDE.md` with the development command protocol.
- Tracking files: tasks, features, bugs, change requests, decisions, dev log.
- Repository scaffold: folder layout, `.gitignore`, `.gitattributes`, `.editorconfig`, `config/local.env.example` [T-101].
- `setup.bat`, `scripts/env.bat` and a resumable, checksummed model downloader [T-102].
- Spring Boot 4 backend scaffold: H2 and Flyway schema, ProblemDetail errors, JSON logging, request ids, ArchUnit, JaCoCo, Spotless, Checkstyle, SpotBugs [T-103].
- Projects REST API [T-104].
- Resumable tus uploads, local media storage, asset list and delete, thumbnail endpoint, ANALYZE jobs queued on upload [T-105].
- Job queue, dispatcher, worker client, token-protected worker callbacks, restart recovery [T-106].
- Photos, speech ducking, captions and prompt text now reach real edits [T-404].
- Grades, D-Log M, transitions, motion blur, SFX, ducking and cool mode [T-303].
- RIFE and Real-ESRGAN adapters, not yet wired in [T-301].
- Prompt constraints, Ollama director with fallback, all 7 styles [T-202].
- YOLO, CLIP tags, aesthetics, duplicate rejection and shot search [T-201].
- Speed ramp curve, smart reframe rules and 360 projections with FFmpeg, not yet wired in [T-302].
- Render tonight, 360 preview and subject picker, skipped-prompt list, speed tips, live GPU temperature [T-401].
- Speech detection, text rules and text layers, not yet wired in [T-402].
- Photo analysis, Ken Burns and depth parallax, not yet wired in [T-403].
- Angular app: projects, uploads, asset grid, waveform, render settings, live progress and result; `start.bat`, `stop.bat`, `scripts/check.bat`, browser error reporting [T-114] [T-115] [T-116] [T-117].
- Video renderer: per-segment FFmpeg and NVENC, 1080p preview first, 10-bit HEVC final, all 6 ratios, zoom punch, shake, flash, -14 LUFS stereo music, `scripts/check_beats.py` [T-113].
- Brain: pacing, shot assignment, beat effects, validation and the edit plan, for Velocity and Cinematic [T-112].
- Shot detection, frame measurements, and scoring [T-111].
- Music map: beats, downbeats, energy, sections and edit window; waveform endpoint [T-110].
- Worker ingest: ffprobe, content hash, analysis cache, NVENC proxies, `.LRF` reuse, thumbnails, Osmo camera and D-Log M detection [T-109].
- Python worker scaffold: FastAPI API, one-job runner with cancellation, GPU guard, NVML status, JSON logs, backend reports [T-108].
- Render API with regenerate and cancel, live SSE events, video streaming with Range, style presets, system status [T-107].
