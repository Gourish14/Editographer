# Decision log (ADRs)

Template: `specs/12-spec-driven-development.md` §8. Newest first.

| ID | Decision | Status |
| --- | --- | --- |
| ADR-028 | Editographer's Ollama runs on its own port | Accepted |
| ADR-027 | The first slot of a drop prefers the followed clip | Accepted |
| ADR-026 | Split B1 parts over 32 bars at a change above 0.15 | Accepted |
| ADR-025 | 360 follow: plan, measure with SAM 2, plan again | Accepted |
| ADR-024 | Per-camera stitch profiles fitted on real clips | Accepted |
| ADR-023 | Stitch at ingest, raise frame rate only for a big gap | Accepted |
| ADR-022 | End-to-end test ports, folders and browser | Accepted |
| ADR-021 | Caption budget and SAM 2 memory | Accepted |
| ADR-020 | Sections use a rank-scaled intensity, and half-tempo correction | Accepted |
| ADR-019 | Callback retry and stuck-job limits | Accepted |
| ADR-018 | How the gate judges cuts | Accepted |
| ADR-017 | Ramp eligibility, reframe path and transition mix | Accepted |
| ADR-016 | Choices made in T-201, T-202, T-301 and T-303 | Accepted |
| ADR-015 | 360 views render with FFmpeg v360 | Accepted |
| ADR-014 | Photo parallax and speech defaults | Accepted |
| ADR-013 | Phase 2 starts before the real-footage Phase 1 gate | Accepted |
| ADR-012 | Phase 1 composites with FFmpeg filters | Accepted |
| ADR-011 | The beat grid includes midpoints, and energy is scaled against the peak | Accepted |
| ADR-010 | Osmo camera modes are detected from width and DJI metadata | Accepted |
| ADR-009 | SpotBugs EI_EXPOSE_REP2 is off outside domain | Accepted |
| ADR-008 | uv, its Python and its cache live in tools/ | Accepted |
| ADR-007 | Hexagonal architecture, packaged by feature, in all three apps | Accepted |
| ADR-006 | Brain = deterministic rules engine guided by an LLM | Accepted |
| ADR-005 | Qwen3 4B and Qwen2.5-VL 3B via Ollama for the 6 GB GPU | Accepted |
| ADR-004 | Worker on private Python 3.12 via uv | Accepted |
| ADR-003 | Spring Boot 4 on Java 25 | Accepted |
| ADR-002 | Job queue as an H2 table with a polling dispatcher | Accepted |
| ADR-001 | H2 file database and local media folder | Accepted |

### ADR-028 — Editographer's Ollama runs on its own port
- Date / Status: 2026-11-01 / Accepted
- Context: With another Ollama on 11434, pulls landed in the user profile, the worker reached a server without our models, and the director quietly fell back.
- Options considered: Detect and warn; a dedicated port.
- Decision: Port 11500, named only in `scripts/env.bat`. `scripts/ollama_server.bat` starts and stops our server, by the PID on that port.
- Consequences: The real `config/local.env` loses its old `OLLAMA_URL` the next time `setup.bat` or `start.bat` runs. Gate scripts keep their own port 18434.

### ADR-027 — The first slot of a drop prefers the followed clip
- Date / Status: 2026-11-01 / Accepted
- Context: The gate's beat spin landed on a clip with no follow point, so it did not turn around the tapped subject.
- Options considered: Leave it to scoring; force the slot.
- Decision: When a follow point resolves, the first slot of a drop takes a shot from that clip, ignoring the neighbour-clip rule for that slot only. Slots and cuts do not change.
- Consequences: One slot can sit next to the same clip. A follow point with no asset id still means the first 360 clip.

### ADR-026 — Split B1 parts over 32 bars at a change above 0.15
- Date / Status: 2026-11-01 / Accepted
- Context: The gate song's drop ran 135 s, because a step in brightness at 110 s scored 0.16, under the 0.3 boundary.
- Options considered: Lower the boundary for all songs; split only long parts.
- Decision: A part over 32 bars also gets its biggest 4-bar change over 0.15, repeated until none is left. Lowering 0.3 everywhere split songs too heavily. `ANALYSIS_VERSION` 7.
- Consequences: The drop is now 45 to 111 s, followed by a build. AcidJazz gained two short drops, seen only with stand-in beats, so unconfirmed.

### ADR-025 — 360 follow: plan, measure with SAM 2, plan again
- Date / Status: 2026-11-01 / Accepted
- Context: The planner is pure and the source windows are known only after planning, but following a subject needs SAM 2. A person is under 1% of an equirect frame.
- Options considered: Track whole clips at analysis; track after a first plan.
- Decision: Plan once, measure, then plan again with the same seed, so only framing changes. SAM 2 runs on a 100 degree view centred on the subject, in 2 s chunks at 4 samples a second, capped at 90 s. A follow point applies to the first 360 clip. Tracking moves yaw only.
- Consequences: One SAM 2 load per chunk is slow on long windows. The constants are guesses until the GPU run.

### ADR-024 — Per-camera stitch profiles fitted on real clips
- Date / Status: 2026-11-01 / Accepted
- Context: The assumed 195 degrees left visible seams on real files. A fit gave about 194 degrees, plus lens rotations that differ by camera model.
- Options considered: One FOV; per-model profiles; decoding DJI's factory calibration.
- Decision: Profiles chosen by the file's `encoder` tag, each lens mapped separately and feathered 4 degrees either side of the seam, 10-bit kept. The `djmd` metadata is not decoded.
- Consequences: About 5 times the CPU cost, roughly 12 minutes for a 23 s 8K clip. Each profile comes from one camera, so unit variation is unmeasured. Near objects keep a soft parallax ghost.

### ADR-023 — Stitch at ingest, raise frame rate only for a big gap
- Date / Status: 2026-10-31 / Accepted
- Context: Raw `.OSV` must become equirect before analysis, and RIFE per frame is costly.
- Options considered: Stitch at render; stitch once at ingest.
- Decision: Stitch once to `media/stitched/{assetId}.mp4`, 10-bit HEVC at cq 14. In Max mode, RIFE raises the frame rate only when output fps is at least 1.5x native, so 50 into 60 is conformed. 360 clips are conformed, not interpolated. Working size stays per plan, not per segment.
- Consequences: One re-encode and extra disk per clip. Lens FOV of 195 degrees is assumed and unproven on real files. A 16:9 8K Max edit always runs ESRGAN at 4x, about 10 to 13 s per frame on a shared GPU.

### ADR-022 — End-to-end test ports, folders and browser
- Date / Status: 2026-10-31 / Accepted
- Context: The browser test runs the real apps and must not touch a running install.
- Options considered: Reuse the normal ports; separate ports and data.
- Decision: Ports 18080, 18090 and 4300, with data under `data/e2e`, `media/e2e` and `logs/e2e`. `E2E_BROWSER_CHANNEL=chrome` uses the installed Chrome.
- Consequences: With the channel set, `scripts\e2e.bat` skips `playwright install chromium`. The bundled Chromium path has not been run here.

### ADR-021 — Caption budget and SAM 2 memory
- Date / Status: 2026-10-31 / Accepted
- Context: Captions are slow and spec 05 sends only the top 40 shots to the director. SAM 2.1 small measured about 2.5 GB, above the 1 to 2 GB the spec planned.
- Options considered: Caption every shot; caption the top 40 per clip.
- Decision: Caption the top 40 shots per clip. Accept SAM 2.1 small at about 2.5 GB, since one model at a time still fits in 6 GB.
- Consequences: Lower-ranked shots have no caption.

### ADR-020 — Sections use a rank-scaled intensity, and half-tempo correction
- Date / Status: 2026-10-31 / Accepted
- Context: Real songs never reached the old drop threshold, so no drop was found, and a fast song could be read at double time (170 for 84.96 BPM).
- Options considered: Lower the raw threshold; a new rank-scaled curve.
- Decision: Add an `intensity` curve and make section `mean_energy` rank-scaled. A drop needs mean intensity of at least 0.6 and 0.1 above the section before. B10's drop test moves to 0.6 on the same scale. Apply the half-tempo rule.
- Consequences: Drops were found in 3 of 5 test songs. Cached analyses rerun (`ANALYSIS_VERSION` 6). B10's second rule now fires for almost any song at 120 BPM or more with a drop.

### ADR-019 — Callback retry and stuck-job limits
- Date / Status: 2026-10-31 / Accepted
- Context: A lost `/internal/complete` left a render unfinished forever, and a worker restart left jobs RUNNING.
- Options considered: Retry only; retry plus recovery from `/health`.
- Decision: Terminal callbacks retry 6 times over about 25 s, on connection errors and 5xx. A RUNNING job older than 30 s that the worker does not report is requeued, up to 3 attempts, then failed along with its render or asset. Repeat completions are ignored.
- Consequences: If a job is requeued and runs a second time, a late callback from the first run marks it DONE and the second run's callback is ignored. A late DONE for a job already given up on is ignored, so the user sees a failure.

### ADR-018 — How the gate judges cuts
- Date / Status: 2026-10-31 / Accepted
- Context: Measuring cuts in the final file is fooled by jumps inside clips and by look-alike frames across a cut.
- Options considered: every cut measured; a share of visible cuts.
- Decision: `scripts/phase1_gate.py` requires at least 95% of visible cuts within one frame, plus exact frame counts. Stress renders are judged on frames only. `--shared-gpu` reports time without failing on it.
- Consequences: This rule was set after seeing data, though the real run scored 100%, so it did not change the result. Cuts between look-alike frames are vouched for by frame counts alone.

### ADR-017 — Ramp eligibility, reframe path and transition mix
- Date / Status: 2026-10-31 / Accepted
- Context: T-405 needed choices the specs leave open.
- Options considered: Spec 06 `keyframes` or a new `reframe.path`; requiring B6's hold on a whole beat or on the grid.
- Decision: A slot ramps if it lasts at least 0.5 s and its middle is on the grid, half beats included. Flat tracking is stored as `reframe.path` crop centers. RIFE scale 0.5 starts at 4K. Section changes cycle zoom_through, spin and glitch; other cuts alternate hard cut and whip, capped at half of all cuts. 360 section changes use the tiny planet.
- Consequences: Velocity drop slots are often too short, so ramps there are rare unless a prompt asks. `motionBlur` is emitted even when the prompt turns other effects off.

### ADR-016 — Choices made in T-201, T-202, T-301 and T-303
- Date / Status: 2026-10-31 / Accepted
- Context: The agents made decisions the specs leave open.
- Options considered: recorded per item below.
- Decision: Scoring uses the full B2 formula with no renormalization. Ultralytics is forced offline, with telemetry and auto-install off. CLIP uses OpenAI weights, which the aesthetic head was trained on; YOLO is yolo11n; A uses object velocity only, no pose. `fxIntensity` replaces the style's value. Style precedence is prompt, UI setting, director, then B10 rules. Chronological order means asset order until capture time is stored. RIFE is 4.25 in fp16 with 24 px tile context. A transition plays inside the outgoing segment and ends on the beat, so join stays a copy. `tmix` was replaced because it silently dropped 2 frames. Ollama models live in `models/ollama`.
- Consequences: Scores sit lower than in Phase 1, so more shots may fall under 0.2 on real footage. Camera pans count as object speed. Temperature is checked only between segments, because a running FFmpeg cannot pause. RIFE at 4K with scale 1.0 reaches 3.6 GB, so scale 0.5 should probably start at 4K, not above it. The qwen3:4b model downloaded earlier sits in the user profile and is unused now.

### ADR-015 — 360 views render with FFmpeg v360
- Date / Status: 2026-10-31 / Accepted
- Context: Spec 08 named a ModernGL shader for reframing. `v360` proved able to animate per frame, and a projection change fits in one graph through split, trim and concat.
- Options considered: ModernGL; `v360` commands.
- Decision: Use `v360` with `reset_rot=1`. Plan FOV is a horizontal lens FOV, converted for stereographic output so 160 gives a real globe. Dead zone is ±10% of the crop; the subject sits on the third behind its motion, above 2% of frame width of travel; 1€ uses `min_cutoff` 1 Hz and `beta` 1.5. A drop spin in a slot under a beat is compressed so the full 360° still happens.
- Consequences: No shader code for reframing. 8K is CPU heavy: 5.5 s per 30 frames at native view width and 48 s at full 8K, so Max mode should render at view size and upscale.

### ADR-014 — Photo parallax and speech defaults
- Date / Status: 2026-10-31 / Accepted
- Context: T-402 and T-403 needed choices the specs leave open.
- Options considered: FFmpeg `displace` needs x and y maps, so a true parallax was costly; Whisper can run on CPU or GPU.
- Decision: Parallax is two layers, a depth-masked near layer over the photo, used when depth contrast is at least 0.8. Whisper defaults to the CPU, with CUDA opt-in through `GpuGuard`. `av` is pinned to 16.x because faster-whisper 1.2.1 fails on av 19.
- Consequences: The 0.8 threshold comes from two generated images and needs tuning on real photos. The `av` pin must be revisited when faster-whisper updates.

### ADR-013 — Phase 2 starts before the real-footage Phase 1 gate
- Date / Status: 2026-10-31 / Accepted
- Context: Spec 10 says not to start a phase until the previous gate passes, but the T-118 gate needs real footage the user has not supplied, and the user asked to finish development rapidly with multiple agents and without check-ins.
- Options considered: stop at the gate; run the gate on generated media and continue.
- Decision: Run T-118 on generated media, continue to Phases 2 to 4, and keep the real-footage run open as a named blocker.
- Consequences: Later phases build on B1 and B2 thresholds not yet proven on real songs and clips, so they may need retuning at the real gate.

### ADR-012 — Phase 1 composites with FFmpeg filters
- Date / Status: 2026-10-31 / Accepted
- Context: Spec 03 names ModernGL for effects, but the Phase 1 effects are only crops, scales and a flash, and the gate needs 4K in 15 minutes.
- Options considered: ModernGL now; FFmpeg filters per segment.
- Decision: Each segment is rendered by one FFmpeg call behind the `Compositor` port. `crop` cannot resize per frame, so a zoom scales per frame and crops back.
- Consequences: Simple and fast, but compose and encode cannot be reported apart, so Phase 1 progress groups them. Shader transitions in Phase 3 add a second `Compositor`.

### ADR-011 — The beat grid includes midpoints, and energy is scaled against the peak
- Date / Status: 2026-10-31 / Accepted
- Context: B3 asks for half-beat cuts while B11 and the gate say every cut lands on a beat. B1 says energy is normalized 0 to 1 without saying how; min-max scaling made a steady song look dramatic.
- Options considered: drop half-beat cuts; treat midpoints as grid points. Min-max scaling; dividing by the peak.
- Decision: The grid is every beat plus each midpoint, used by pacing, B11 and `scripts/check_beats.py`. Energy is divided by the song's peak. Section labels check Drop first, then Intro and Outro, then Break, Build, and Verse. Boundaries within 4 bars of a bigger change are dropped.
- Consequences: Half-beat cuts count as on the beat. B1 thresholds (0.75, 0.4, 0.25) apply to peak-relative energy, so they need checking on real songs at the gate.

### ADR-010 — Osmo camera modes are detected from width and DJI metadata
- Date / Status: 2026-10-31 / Accepted
- Context: Spec 08 lists the modes but not how to tell them apart. Real Osmo 360 metadata has not been inspected yet, and Boost 4K frame sizes are unknown.
- Options considered: wait for real footage; detect by frame width plus any tag containing "dji".
- Decision: 2:1 frames or `.OSV` are 360, split at 7000 and 5000 px wide. A DJI tag means single-lens, split at 4800, 3800 and 2600 px wide.
- Consequences: Thresholds live in `domain/media.py` and must be checked against real clips at the Phase 3 gate. A wrong guess only changes the badge and reframe defaults, and Phase 1 treats every mode the same.

### ADR-009 — SpotBugs EI_EXPOSE_REP2 is off outside domain
- Date / Status: 2026-10-30 / Accepted
- Context: Spec 11 requires constructor injection and a clean SpotBugs run. EI_EXPOSE_REP2 flags every injected collaborator as exposed mutable state, a false positive for Spring beans.
- Options considered: annotate every class; drop to a High threshold, which hides real findings; exclude this one pattern in the layers that use injection.
- Decision: Exclude EI_EXPOSE_REP2 in `api`, `application` and `infrastructure` packages through `backend/spotbugs-exclude.xml`. `domain` keeps the check.
- Consequences: A real exposure of mutable state outside `domain` is not reported by this rule. Domain types are records, so the important boundary stays covered.

### ADR-008 — uv, its Python and its cache live in tools/
- Date / Status: 2026-10-30 / Accepted
- Context: uv defaults to user-profile folders for its binary, Python builds and package cache, which breaks hard rule 3 (one project folder). ADR-004 did not say where the interpreter lives; a venv only links to it.
- Options considered: uv defaults; a project-local install through `UV_UNMANAGED_INSTALL`, `UV_PYTHON_INSTALL_DIR` and `UV_CACHE_DIR`.
- Decision: Install into `tools/uv`, `tools/python` and `tools/uv-cache`, set once in `scripts/env.bat`. The uv version is pinned in `setup.bat`.
- Consequences: Deleting the project removes everything, and the user PATH is untouched. Every script must call `scripts/env.bat` first. PyTorch's cache lands in `tools/`, which is ignored by git.

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
