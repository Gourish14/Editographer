# Decision log (ADRs)

Template: `specs/12-spec-driven-development.md` §8. Newest first.

| ID | Decision | Status |
| --- | --- | --- |
| ADR-007 | Hexagonal architecture, packaged by feature, in all three apps | Accepted |
| ADR-006 | Brain = deterministic rules engine guided by an LLM | Accepted |
| ADR-005 | Qwen3 4B and Qwen2.5-VL 3B via Ollama for the 6 GB GPU | Accepted |
| ADR-004 | Worker on private Python 3.12 via uv | Accepted |
| ADR-003 | Spring Boot 4 on Java 25 | Accepted |
| ADR-002 | Job queue as an H2 table with a polling dispatcher | Accepted |
| ADR-001 | H2 file database and local media folder | Accepted |

### ADR-007 — Hexagonal architecture, packaged by feature
- Date / Status: 2026-10-30 / Accepted
- Context: The app must follow SOLID and stay easy to change (for example a later move to PostgreSQL or MinIO).
- Options considered: layered by technical type (controllers/, services/); hexagonal by feature.
- Decision: Hexagonal (api, application, domain, infrastructure) inside each feature; enforced by ArchUnit and import-linter.
- Consequences: More files per feature; infrastructure swaps become config changes; domain logic is testable without frameworks.

### ADR-006 — Rules engine guided by an LLM
- Date / Status: 2026-10-30 / Accepted
- Context: Edits must always land on the beat and look good, even when a small local LLM gives weak or invalid output.
- Options considered: LLM writes the whole plan; rules only; rules + LLM for intent.
- Decision: LLM decides style, story hints and prompt constraints; deterministic rules build the plan (spec 05).
- Consequences: Reliable rhythm and testable output; the LLM's creativity is limited to intent.

### ADR-005 — Small local models via Ollama
- Date / Status: 2026-10-30 / Accepted
- Context: 6 GB VRAM, no paid APIs.
- Options considered: Qwen3 8B (too tight in 6 GB), Qwen3 4B, cloud APIs (not free).
- Decision: Qwen3 4B (planner) and Qwen2.5-VL 3B (captions), 4-bit, `keep_alive: 0`.
- Consequences: Fits the GPU one model at a time; larger models possible later on a bigger GPU.

### ADR-004 — Private Python 3.12 via uv
- Date / Status: 2026-10-30 / Accepted
- Context: System Python is 3.13.9; some AI libraries are not yet stable on 3.13.
- Options considered: Downgrade system Python; conda; uv-managed 3.12.
- Decision: uv installs Python 3.12 into `worker/.venv`; the system Python is untouched.
- Consequences: One extra tool (uv), installed by setup.bat.

### ADR-003 — Spring Boot 4 on Java 25
- Date / Status: 2026-10-30 / Accepted
- Context: Java 25.0.1 LTS is installed.
- Decision: Spring Boot 4 with Java 25.
- Consequences: Modern Java features (records, pattern matching, virtual threads) available.

### ADR-002 — Job queue as a database table
- Date / Status: 2026-10-30 / Accepted
- Context: Single machine, single GPU worker; RabbitMQ not wanted.
- Decision: `job` table in H2 + `@Scheduled` dispatcher polling worker `/health` every 2 s.
- Consequences: Simple and durable across restarts; replaceable by RabbitMQ behind the `JobQueue` port.

### ADR-001 — H2 and local media folder
- Date / Status: 2026-10-30 / Accepted
- Context: No installs beyond Java, Node and Python; everything in one folder.
- Decision: H2 file mode in `data/`, media in `media/`, behind `StorageService` ports.
- Consequences: Zero setup; single-user only; swap to PostgreSQL / MinIO later via adapters.
