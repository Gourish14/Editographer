# Development log

Newest first. One entry per working session (template in `specs/12-spec-driven-development.md` §8).

## 2026-10-31 — Session 4 (overnight, multi-agent)
- Done: T-118 in review, T-201, T-202, T-301, T-302, T-303, T-401, T-402, T-403, T-404, T-405.
- In progress: T-406 in review, gate re-run due; T-409.
- Found: BUG-003, ADR-014, ADR-015, ADR-016, CR-013.
- Next: merge the T-40x agents. Gate on 10 real clips and a real song passed beats, frames and time, slowest 13.8 min at 1:1, but found no drop.
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
