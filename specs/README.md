# Editographer — Specs

AI auto video editor: raw clips + photos + music (+ optional prompt) in → a beat-synced, effect-heavy edit out, in any ratio at 4K, 6K or 8K. Built for DJI Osmo 360 footage. Runs 100% locally and free on a Windows laptop with an RTX 3050 6 GB.

## How to use these files

These files are the single source of truth for the app. When building or changing any part of the app, read the matching spec first and keep the code consistent with it. If the code and a spec disagree, update the spec in the same change.

| File | What it defines |
| --- | --- |
| [00-overview.md](00-overview.md) | What the app does, inputs, outputs, ratios and resolutions |
| [01-features.md](01-features.md) | Research on the best auto-edit apps and the full feature list |
| [02-architecture.md](02-architecture.md) | Local architecture, processes, ports, folder layout, data flow |
| [03-tech-stack.md](03-tech-stack.md) | Every library and model, with versions and licenses |
| [04-pipeline.md](04-pipeline.md) | The processing pipeline from upload to final file |
| [05-editing-brain.md](05-editing-brain.md) | **The core logic**: music map, shot scoring, pacing, assignment, effects, validation |
| [06-edit-plan-schema.md](06-edit-plan-schema.md) | The edit plan JSON and the prompt constraint JSON |
| [07-api-and-data.md](07-api-and-data.md) | Spring Boot REST API, worker API, database entities, job flow |
| [08-osmo360.md](08-osmo360.md) | DJI Osmo 360 support: modes, stitching, 360 reframing and effects |
| [09-local-setup.md](09-local-setup.md) | RTX 3050 6 GB profile, render modes, cool mode, setup and start scripts |
| [10-roadmap.md](10-roadmap.md) | Build phases, gates and acceptance criteria |
| [11-coding-standards.md](11-coding-standards.md) | SOLID, hexagonal structure per app, testing, logging, error codes, git, review checklist |
| [12-spec-driven-development.md](12-spec-driven-development.md) | The development process, the commands ("lets start development", "bug:", "feature:", "change:") and templates |

Outside `specs/`:

| Path | What it is |
| --- | --- |
| `../CLAUDE.md` | Instructions Claude reads first in every session |
| `../tracking/TASKS.md` | Task board: what to build next |
| `../tracking/FEATURES.md`, `BUGS.md`, `CHANGE_REQUESTS.md`, `DECISIONS.md`, `DEV_LOG.md` | Logs for features, bugs, changes, decisions and sessions |
| `../CHANGELOG.md`, `../VERSION` | Release notes and version |

## Starting development

Connect the `Editographer` folder in the Claude desktop app and type **lets start development**. Claude follows `12-spec-driven-development.md` §5: picks the next task from `tracking/TASKS.md`, builds it with tests, records everything and continues until the phase gate.

## Hard rules

1. **Free only.** No paid APIs, no subscriptions. Every dependency is free and open source or free from DJI.
2. **Local only.** No PostgreSQL, RabbitMQ, MinIO or Docker. H2 file database, local folders, direct HTTP between processes.
3. **One project folder.** Everything (code, models, media, database) lives inside `Editographer/`.
4. **6 GB VRAM budget.** Only one AI model on the GPU at a time.
5. **Beat is law.** Every cut and every effect lands on the music's beat grid.
