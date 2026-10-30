# Changelog

All notable changes to Editographer. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
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
