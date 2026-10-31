# Development log

Newest first. One entry per working session (template in `specs/12-spec-driven-development.md` §8).

## 2026-10-31 — Session 4 (overnight, multi-agent)
- Done: T-118, T-406, T-408, T-410, T-201, T-202, T-301, T-302, T-303, T-401, T-402, T-403, T-404, T-405.
- Done since: T-411. All 4 lines passed on real clips, plans from the LLM: car shots 36% to 100%, 17 of 17 drop slots ramped, shakes 6 to 0, render DONE with Ollama on a closed port. The car numbers were re-scored from saved plans after a script fix, not re-rendered. The baseline already chose Cinematic, so that prompt changed shakes, not style. `qwen3:4b` was only in the user profile, so it was copied into `models/ollama`.
- Real Osmo files found: two public review samples in `media/gate-inputs/osmo`, no stated licence, local only (`SOURCES.json`).
- Done since: T-412. 60 s 8K 9:16 Max with cool mode, 4 h 29 min, 1799 of 1799 frames, peak 79.84 C, 4.19 GB VRAM. Chrome played the 8K file with 0 dropped frames. The 83 C pause never triggered. d3d11va decode was 0.47x, CUDA 1.28x. T-413, T-415 and BUG-009 merged. The GPU run caught a stitch that never ended.
- In progress: T-414 Phase 3 gate. T-409 in review, needs a real `.OSV`. T-409 8K and 6K checks ran on a shared GPU, so times are upper bounds; 8K 16:9 Max reached 6.0 GB system-wide against the 6.1 GB limit. Cool mode was only tried on a 2 s render, peak 78 C, so the full-length claim is unproven.
- Found: BUG-003, ADR-014, ADR-015, ADR-016, CR-013.
- Next: T-412. Phase 1 gate passed on real media, slowest 11.5 min at 1:1, drop found. Phase 3 gate can run on those files once T-414 and T-415 merge.
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
