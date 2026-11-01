# Development log

Newest first. One entry per working session (template in `specs/12-spec-driven-development.md` §8).

## 2026-10-31 — Session 4 (overnight, multi-agent)
- Done: T-118, T-406, T-408, T-410, T-201, T-202, T-301, T-302, T-303, T-401, T-402, T-403, T-404, T-405.
- Done since: T-411. All 4 lines passed on real clips, plans from the LLM: car shots 36% to 100%, 17 of 17 drop slots ramped, shakes 6 to 0, render DONE with Ollama on a closed port. The car numbers were re-scored from saved plans after a script fix, not re-rendered. The baseline already chose Cinematic, so that prompt changed shakes, not style. `qwen3:4b` was only in the user profile, so it was copied into `models/ollama`.
- Real Osmo files found: two public review samples in `media/gate-inputs/osmo`, no stated licence, local only (`SOURCES.json`).
- Done since: T-412. 60 s 8K 9:16 Max with cool mode, 4 h 29 min, 1799 of 1799 frames, peak 79.84 C, 4.19 GB VRAM. Chrome played the 8K file with 0 dropped frames. The 83 C pause never triggered. d3d11va decode was 0.47x, CUDA 1.28x. T-413, T-415 and BUG-009 merged. The GPU run caught a stitch that never ended.
- Done since: Phase 3 gate on two real Osmo files, run 20261101-051742, 9:16 and 16:9, 40 s Fast at 4K. SAM 2 tracked the real rider, 79 samples, none lost, about 3.5 min. Rider visible in 36 of 36 samples from the tapped clip by eye (YOLO found 27). Spin on the drop at 0 ms off the beat, a full turn seen frame by frame in frames 466 to 471, half under the flash (BUG-010), on the untapped clip (CR-014). Tiny planet ends on the section change. 1186 of 1186 frames, worst cut 13.3 ms, 10-bit HEVC. 32% of source repeated. The run's private Ollama returned 404, so this run used the rule director. Only one road ride and a 10 s clip, so no other light, motion or subject was tested.
- T-418: 16 GiB tus upload through a client kill and a backend restart, 8.1 MiB resent, SHA-256 equal, heap at most 107 MB, RSS 404 MB, 210 MB/s. Uses a Python tus client, not the browser's.
- T-419: real `setup.bat` run in a worktree, 9 of 9 steps, with two other Ollama servers running. Both models landed in `models/ollama`, about 5.4 GB, and the user profile store did not change. `start.bat` and `stop.bat` ran, and a real director reply came back. uv, Python and non-Ollama models were reused, not downloaded.
- Phase 3 re-run on `main`, run 20261101-073725, fresh stitch and analysis, both ratios: real director (no fallback), SAM 2 85 samples none lost, spin on the drop at 0 ms off the beat, on the followed clip, flash over 3 frames and a full turn visible around the rider. Rider in 40 of 40 sampled 9:16 frames. 1186 of 1186 frames, worst cut 13.3 ms, 28% of source repeated.
- `qwen3:4b` was re-pulled through port 11500: the hand copy sat in the old `manifests` folder, which listed it but gave a 404 on chat. The first Phase 3 run's fallback came from that, not from the product.
- Before: T-409 in review, needs a real `.OSV`. T-409 8K and 6K checks ran on a shared GPU, so times are upper bounds; 8K 16:9 Max reached 6.0 GB system-wide against the 6.1 GB limit. Cool mode was only tried on a 2 s render, peak 78 C, so the full-length claim is unproven.
- Found: BUG-003, ADR-014, ADR-015, ADR-016, CR-013.
- Next: final full check on `main`, BUG-010, CR-014, a 16 GB upload, a full `setup.bat` run, the DJI LUT licence. Phase 1 gate passed on real media, slowest 11.5 min at 1:1, drop found. Phase 3 gate can run on those files once T-414 and T-415 merge.
- Needs user: real footage for the gate; push from GitHub Desktop.

## 2026-10-31 — Session 3
- Done: T-109, T-110, T-111, T-112, T-113.
- In progress: T-114 (frontend).
- Found: ADR-010, ADR-011, ADR-012, CR-012.
- Next: T-114, T-115, T-116, T-117, then the T-118 gate.
- Needs user: nothing.

## 2026-10-31 — Session 2
- Done: BUG-001, BUG-002, T-102, T-105, T-106, T-107, T-108.
- In progress: —
- Found: BUG-002, CR-007, CR-008, CR-009, CR-010, CR-011.
- Next: T-109, then T-110 and T-111 (worker analysis).
- Needs user: nothing.

## 2026-10-30 — Session 1
- Done: T-101, T-103, T-104.
- In progress: T-102 (scripts written, downloader tested; `setup.bat` stops after installing FFmpeg).
- Found: BUG-001, CR-005, CR-006, ADR-008, ADR-009.
- Next: fix BUG-001, finish T-102, then T-105.
- Needs user: nothing.
- Note: T-103 and T-104 were committed together with T-102 work and merged to `main` at the user's request, not on separate task branches. GitHub Desktop can switch branches and stash uncommitted files during a session, so check `git reflog` and `git stash list` if files vanish.

## 2026-10-30 — Session 0 (planning)
- Done: specs 00–12, CLAUDE.md, tracking files, Phase 1 task board.
- In progress: —
- Found: —
- Next: T-101 Repository scaffold and conventions.
- Needs user: connect the project folder from the Claude desktop app, then type "lets start development".
