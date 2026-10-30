# 12 — Spec-driven development (SDD) process

Specs say **what** the app does, tracking files say **where we are**, code says **how**. Nothing is built that is not in a spec, and no spec changes without a tracked item.

## 1. Artifacts

| Artifact | Location | Purpose |
| --- | --- | --- |
| Specs | `specs/*.md` | Source of truth for behavior, architecture, rules |
| Task board | `tracking/TASKS.md` | Every unit of work, its status and dependencies |
| Feature log | `tracking/FEATURES.md` | Every feature with its spec reference and status |
| Bug log | `tracking/BUGS.md` | Every defect, found by the user or during development |
| Change requests | `tracking/CHANGE_REQUESTS.md` | Every change to agreed scope or specs |
| Decision log | `tracking/DECISIONS.md` | Architecture Decision Records (ADRs) |
| Changelog | `CHANGELOG.md` | What changed per version |
| Dev log | `tracking/DEV_LOG.md` | One entry per working session: what was done, what is next |

## 2. ID scheme

| Prefix | Example | Used for |
| --- | --- | --- |
| `T-` | T-113 | Task (first digit = phase) |
| `FEAT-` | FEAT-012 | Feature |
| `BUG-` | BUG-007 | Bug |
| `CR-` | CR-004 | Change request |
| `ADR-` | ADR-006 | Decision |

Every commit, branch, test file and log entry references one of these ids.

## 3. Lifecycles

**Task:** `Todo → In progress → In review → Done` (or `Blocked` with a reason).
**Feature:** `Planned → In progress → Done → Verified` (Verified = phase gate passed).
**Bug:** `New → Confirmed → In progress → Fixed → Verified` (or `Won't fix` with reason).
**Change request:** `Proposed → Approved → Specs updated → Implemented → Closed` (or `Rejected`).

## 4. The workflow for every piece of work

1. **Trace.** Find or create the item (task, bug, CR) and the spec sections it implements.
2. **Spec first.** If behavior changes, update the spec in the same change set before or with the code.
3. **Acceptance criteria.** Each task lists testable criteria; write them as tests first where practical.
4. **Implement** following `11-coding-standards.md`.
5. **Verify.** Run `scripts/check.bat` (tests, lint, types, architecture rules). If a check cannot run in the current environment, mark the task `In review` with "needs local verification" and the exact command.
6. **Record.** Update `TASKS.md`, `FEATURES.md` status, `CHANGELOG.md` (Unreleased), `DEV_LOG.md`. Log any bug found along the way in `BUGS.md`.
7. **Commit** with a Conventional Commit message referencing the id.

## 5. Command protocol (what the user types)

The user drives development with short commands. Claude follows these exactly.

### "lets start development" / "continue development" / "start"

1. Read `specs/README.md`, this file, `11-coding-standards.md`, `tracking/TASKS.md`, `tracking/BUGS.md` and the last entry of `tracking/DEV_LOG.md`.
2. Determine the **current phase** = lowest phase with tasks not `Done`.
3. Pick the next task: any `In progress` task first; otherwise the first `Todo` task whose dependencies are all `Done`. Open bugs with severity Critical/High in the current phase come before new tasks.
4. Post one line: which task, which spec sections.
5. Implement the task end to end (workflow §4), then immediately pick the next task. Keep going without asking, until one of:
   - the **phase gate** is reached → run the gate checks from `10-roadmap.md`, record results, report to the user and stop;
   - a **blocker** that only the user can resolve (missing hardware access, a decision that changes a hard rule, an unclear spec) → record it as `Blocked`, ask one clear question, stop;
   - the session is running long → write the `DEV_LOG.md` entry and stop at a clean task boundary.
6. End every session with a `DEV_LOG.md` entry and a short summary to the user: tasks done, bugs found, what is next.

### "status"

Summarize from tracking files: current phase, tasks done / remaining, open bugs by severity, open CRs, next task.

### "bug: <description>"

Create `BUG-xxx` (template below) with severity, steps, expected, actual, spec reference. Reproduce, add a failing test, fix, verify, set `Fixed`, record in CHANGELOG under "Fixed".

### "feature: <description>"

Create `FEAT-xxx` and a `CR-xxx`. Write the impact analysis and the proposed spec change. If it does not touch the hard rules in `README.md` or the architecture, approve it automatically, update specs, add tasks to the right phase, and continue. Otherwise ask the user to approve first.

### "change: <description>"

Create `CR-xxx` with impact analysis (specs, code, tasks, risks). Same approval rule as features. On approval: update specs, add/modify tasks, set CR `Specs updated`, implement, close.

### "decide: <question>" or any architecture choice made during work

Write an `ADR-xxx` in `DECISIONS.md`: context, options, decision, consequences.

## 6. Automatic logging during development

Claude logs without being asked:

- **Bugs** found while coding or testing (failing test unrelated to the current change, crash, wrong output) → `BUG-xxx` with status `New` and severity.
- **Spec gaps** (behavior the spec does not define) → a `CR-xxx` with status `Proposed`, plus the smallest reasonable assumption used meanwhile, noted in the task.
- **Decisions** (library choice, data format, algorithm parameter not in spec) → `ADR-xxx`.
- **Deviations** from coding standards → `ADR-xxx` explaining why.

## 7. Severity

| Severity | Meaning | Rule |
| --- | --- | --- |
| Critical | App unusable, data loss, crash on main flow | Fix before any new task |
| High | Main feature wrong (cuts off-beat, render fails for a ratio) | Fix within the current phase, before the gate |
| Medium | Feature works with a workaround | Fix before the next phase gate |
| Low | Cosmetic, minor | Backlog |

## 8. Templates

### Task (in `TASKS.md`)

```
### T-1xx — <title>
- Status: Todo | In progress | In review | Done | Blocked (<reason>)
- Spec: <file>#<section>, …
- Depends on: T-1xx, …
- Acceptance criteria:
  - [ ] <testable statement>
- Notes:
```

### Bug (in `BUGS.md`)

```
### BUG-xxx — <title>
- Status: New | Confirmed | In progress | Fixed | Verified | Won't fix
- Severity: Critical | High | Medium | Low
- Found: <date>, by <user | Claude during T-xxx>
- Spec: <file>#<section>
- Steps to reproduce:
- Expected:
- Actual:
- Logs: <jobId / requestId, relevant lines>
- Fix: <commit / task>, test: <test name>
```

### Change request (in `CHANGE_REQUESTS.md`)

```
### CR-xxx — <title>
- Status: Proposed | Approved | Specs updated | Implemented | Closed | Rejected
- Requested: <date>, by <user | Claude>
- Reason:
- Impact: specs <files>, code <modules>, tasks <ids>, risks
- Decision: <approved by / auto-approved because …>
```

### ADR (in `DECISIONS.md`)

```
### ADR-xxx — <title>
- Date / Status: Accepted | Superseded by ADR-yyy
- Context:
- Options considered:
- Decision:
- Consequences:
```

### Dev log entry (in `DEV_LOG.md`, newest first)

```
## <date> — Session <n>
- Done: T-…, BUG-…
- In progress: T-… (<where it stopped>)
- Found: BUG-…, CR-…
- Next: T-…
- Needs user: <nothing | question>
```
