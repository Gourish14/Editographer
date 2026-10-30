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

## Details

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
