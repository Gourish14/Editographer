# Changelog

All notable changes to Editographer. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Specs 00–12: overview, features, architecture, stack, pipeline, editing brain, edit plan schema, API and data, Osmo 360, local setup, roadmap, coding standards, spec-driven development process.
- `CLAUDE.md` with the development command protocol.
- Tracking files: tasks, features, bugs, change requests, decisions, dev log.
- Repository scaffold: folder layout, `.gitignore`, `.gitattributes`, `.editorconfig`, `config/local.env.example` [T-101].
- `setup.bat`, `scripts/env.bat` and a resumable, checksummed model downloader; `setup.bat` does not finish yet (BUG-001) [T-102].
- Spring Boot 4 backend scaffold: H2 and Flyway schema, ProblemDetail errors, JSON logging, request ids, ArchUnit, JaCoCo, Spotless, Checkstyle, SpotBugs [T-103].
- Projects REST API [T-104].
