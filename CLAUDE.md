# CLAUDE.md — Editographer

You are the developer of **Editographer**, an AI auto video editor. This project uses **spec-driven development**. Read this file first in every session.

## Golden rules

1. The specs in `specs/` are the source of truth. Never build anything that is not in a spec; if something is missing, log a `CR-` and use the smallest reasonable assumption.
2. Follow `specs/11-coding-standards.md` (SOLID, hexagonal layers, tests, logging) for every line of code.
3. Follow `specs/12-spec-driven-development.md` for every piece of work: trace → spec → criteria → code → verify → record → commit.
4. Respect the hard rules in `specs/README.md`: free only, local only (H2 + local folders + HTTP, no Docker/PostgreSQL/RabbitMQ/MinIO), one project folder, 6 GB VRAM budget, beat is law.
5. Keep the tracking files in `tracking/` and `CHANGELOG.md` up to date at all times. Log bugs, spec gaps and decisions automatically.

## Commands the user will type

| User types | You do |
| --- | --- |
| **lets start development** / **continue development** / **start** | Run the loop in `specs/12-spec-driven-development.md` §5: read specs + tracking, pick the next task from `tracking/TASKS.md`, implement it fully with tests, record it, move to the next task, and continue until the phase gate, a real blocker, or a clean stopping point. |
| **status** | Summary of phase, tasks, open bugs, open CRs, next task. |
| **bug: …** | Log `BUG-`, reproduce, failing test, fix, verify, record. |
| **feature: …** | Log `FEAT-` + `CR-`, impact analysis, update specs, add tasks, continue (ask first only if a hard rule or the architecture changes). |
| **change: …** | Log `CR-`, impact analysis, update specs and tasks, implement. |
| **decide: …** | Write an `ADR-` in `tracking/DECISIONS.md`. |

## Environment facts

- Target machine: Windows 11, RTX 3050 Laptop 6 GB, Java 25.0.1, Node 24.19.0, system Python 3.13.9 (the worker uses a private Python 3.12 via uv).
- If you cannot run a command in your current environment (for example GPU tests or Windows `.bat` scripts), still write the code and tests, mark the task `In review` with "needs local verification", and give the user the exact command to run.

## Where things are

| Path | What |
| --- | --- |
| `specs/` | All specs, start with `specs/README.md` |
| `tracking/TASKS.md` | Task board (what to build next) |
| `tracking/BUGS.md`, `FEATURES.md`, `CHANGE_REQUESTS.md`, `DECISIONS.md`, `DEV_LOG.md` | Logs |
| `CHANGELOG.md`, `VERSION` | Release notes and version |
| `frontend/`, `backend/`, `worker/` | The three apps (created in Phase 1) |
| `scripts/check.bat` | Runs every test, lint and architecture check |
