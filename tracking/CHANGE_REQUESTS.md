# Change requests

Status: Proposed → Approved → Specs updated → Implemented → Closed (or Rejected). Template: `specs/12-spec-driven-development.md` §8.

| ID | Title | Status |
| --- | --- | --- |
| CR-001 | Local no-install stack instead of PostgreSQL, RabbitMQ, MinIO, Docker | Specs updated |
| CR-002 | RTX 3050 6 GB laptop profile, render modes, cool mode | Specs updated |
| CR-003 | DJI Osmo 360 as primary camera | Specs updated |
| CR-004 | Enterprise coding standards and spec-driven development process | Specs updated |
| CR-005 | Raise setup version checks to what the stack needs | Implemented |
| CR-006 | setup.bat installs models and assets per phase | Implemented |
| CR-007 | Define where asset thumbnails come from | Proposed |
| CR-008 | Define how .LRF proxies link to their .OSV, and which photo formats count | Proposed |
| CR-009 | Add fileHash and logProfile to the asset-analyzed callback | Implemented |

## Details

### CR-009 — Add fileHash and logProfile to the asset-analyzed callback
- Status: Implemented
- Requested: 2026-10-31, by Claude during T-106
- Reason: The `asset` table has `file_hash` and `log_profile`, but the callback in spec 07 did not carry them, so the backend could never fill them in.
- Impact: specs `07-api-and-data.md`; backend worker callback; T-109 must send both.
- Decision: auto-approved, does not touch a hard rule or the architecture.

### CR-008 — Define how .LRF proxies link to their .OSV, and which photo formats count
- Status: Proposed
- Requested: 2026-10-31, by Claude during T-105
- Reason: Spec 04 matches an `.LRF` by name, but uploads are stored as `{assetId}.{ext}`, so the stored name no longer matches. An `.LRF` also should not appear as a separate clip in an edit. Separately, spec 00 lists "DJI panoramic photos" without a format.
- Impact: specs `00`, `04`, `08`; T-109 ingest; asset model. Risk: duplicate shots if `.LRF` files are analyzed as clips.
- Assumption meanwhile: `.lrf` is accepted as VIDEO and `.dng` as PHOTO; the original filename is kept on the asset, so T-109 can match by name within a project.
- Decision: pending, to settle in T-109.

### CR-007 — Define where asset thumbnails come from
- Status: Proposed
- Requested: 2026-10-31, by Claude during T-105
- Reason: Spec 07 has `GET /api/assets/{id}/thumbnail`, but no spec or task says who creates the image.
- Impact: specs `02`, `04`, `07`; T-109 must write it.
- Assumption meanwhile: the worker writes `media/cache/{fileHash}/thumbnail.jpg` during ingest; the backend serves it and answers 404 until it exists.
- Decision: pending, to settle in T-109.

### CR-006 — setup.bat installs models and assets per phase
- Status: Implemented
- Requested: 2026-10-30, by Claude during T-102
- Reason: Spec 09 lists every model, LLM pull, LUT and SFX in `setup.bat`, but T-102 asks for Phase 1 weights only. Pulling about 5 GB of Ollama models that no Phase 1 code uses slows setup for nothing.
- Impact: specs `09-local-setup.md`; code `setup.bat`, `scripts/models.json`; Phase 2 must add the `ollama pull` step and its weights; Phase 3 and 4 add theirs. No risk to Phase 1.
- Decision: auto-approved, does not touch a hard rule or the architecture.

### CR-005 — Raise setup version checks to what the stack needs
- Status: Implemented
- Requested: 2026-10-30, by Claude during T-102
- Reason: T-102 said Java ≥ 17 and Node ≥ 20.19, but the backend compiles for Java 25 (ADR-003) and Angular 22 requires Node `^22.22.3 || ^24.15.0`. A machine passing the old checks would fail later with a confusing build error. The target machine already has Java 25.0.1 and Node 24.19.0.
- Impact: specs `09-local-setup.md`; task T-102 criteria; code `setup.bat`. No risk on the target machine.
- Decision: auto-approved, does not touch a hard rule or the architecture.

### CR-004 — Enterprise coding standards and spec-driven development process
- Status: Specs updated
- Requested: 2026-10-30, by user
- Reason: The code must follow SOLID and a proper structure, and all bugs, features and changes must be logged, so development can run from the single command "lets start development".
- Impact: specs `11-coding-standards.md`, `12-spec-driven-development.md`, `README.md`, `02-architecture.md`; new `CLAUDE.md` and `tracking/` files; all tasks follow the new checklist.
- Decision: approved by user.

### CR-003 — DJI Osmo 360 as primary camera
- Status: Specs updated
- Requested: 2026-10-30, by user
- Reason: Raw footage comes from a DJI Osmo 360 (single-lens 4K and 360 at 4K/6K/8K).
- Impact: spec `08-osmo360.md`; pipeline ingest, brain B7, render; Phase 3 and 4 tasks.
- Decision: approved by user.

### CR-002 — RTX 3050 6 GB laptop profile
- Status: Specs updated
- Requested: 2026-10-30, by user
- Reason: The app must run on the user's laptop with an RTX 3050 6 GB, fast enough and without overheating.
- Impact: spec `09-local-setup.md`; smaller models, GPU guard, render modes, cool mode.
- Decision: approved by user.

### CR-001 — Local no-install stack
- Status: Specs updated
- Requested: 2026-10-30, by user
- Reason: The user does not want to install PostgreSQL, RabbitMQ or MinIO; everything should live in one folder.
- Impact: specs `02-architecture.md`, `03-tech-stack.md`, `07-api-and-data.md`; H2, local `media/`, HTTP job dispatch.
- Decision: approved by user.
