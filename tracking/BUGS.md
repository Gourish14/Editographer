# Bug log

Status: New → Confirmed → In progress → Fixed → Verified (or Won't fix). Severity rules and template: `specs/12-spec-driven-development.md` §7–8. Claude logs bugs found during development automatically.

## Open

| ID | Title | Severity | Status | Found in |
| --- | --- | --- | --- | --- |
| BUG-008 | A worker callback that fails is not retried, so a render can stay unfinished forever | High | New | T-118 |

## Closed

| ID | Title | Severity | Fixed in |
| --- | --- | --- | --- |
| BUG-007 | BPM misread 118 as 120, across the B3 style boundary | Medium | 79edabd |
| BUG-006 | Zoom punches landed off-centre | High | 79edabd |
| BUG-005 | Database writes failed after about 25 minutes on a fresh install | Critical | 79edabd |
| BUG-004 | Final mix could end early, and `-shortest` cut video frames | High | 79edabd |
| BUG-003 | Two GPU guards after merging T-201 and T-202 broke the one-model rule | High | 8e8596e |
| BUG-002 | createdAt differs between create and read-back | Low | T-106 commit |
| BUG-001 | setup.bat exits with code 255 right after winget installs FFmpeg | High | ef2569b |

## Details

<!-- Add one section per bug using the template, newest first. -->

### BUG-005 — Database writes failed after about 25 minutes on a fresh install
- Status: Fixed
- Severity: Critical
- Found: 2026-10-31, by Claude during T-118
- Spec: 07-api-and-data.md
- Steps to reproduce: Run the app for about 25 minutes after a first migration.
- Expected: Renders reach DONE.
- Actual: H2 ties CHECK constraints to the session that created them, and Hikari retired Flyway's connection, so every update on `render_job` and `job` failed until restart.
- Fix: 79edabd, `hikari.max-lifetime: 0`. The test only asserts the setting.

### BUG-004 — Final mix can end early when audio is shorter than the edit
- Status: Fixed
- Severity: High
- Found: 2026-10-31, by Claude during T-404
- Spec: 04-pipeline.md#stages (8)
- Steps to reproduce: Render an edit from a clip whose kept audio is shorter than the segment window.
- Expected: Audio and video both last the whole edit.
- Actual: About 4 s of audio in a 6 s edit, seen once. `ffmpeg_audio_finisher.py` uses `-shortest`, so it may also be the cause of the 3 frames lost in the T-118 rehearsal; unconfirmed.
- Fix: 79edabd, removed `-shortest` and made the mix exactly the edit's length. It also caused the rehearsal's 3 lost frames.

### BUG-002 — createdAt differs between create and read-back
- Status: Fixed
- Severity: Low
- Found: 2026-10-31, by Claude during T-106 smoke test
- Spec: 07-api-and-data.md
- Steps to reproduce: POST a project, then GET it.
- Expected: The same `createdAt`.
- Actual: 7 decimal places on create, 6 on read, because the database stores microseconds.
- Fix: `ClockConfig` ticks in microseconds. Test: `ClockConfigTest.ticksInDatabasePrecision`.

### BUG-001 — setup.bat exits with code 255 right after winget installs FFmpeg
- Status: Fixed
- Severity: High
- Found: 2026-10-30, by Claude during T-102
- Spec: 09-local-setup.md#setupbat-run-once
- Steps to reproduce: On a machine without FFmpeg, run `C:\Editographer\setup.bat`.
- Expected: Steps 3 to 7 run after FFmpeg installs.
- Actual: The script stops after step 2 with exit code 255 and no error message. uv, `config/local.env` and the models are not installed.
- Cause: winget adds FFmpeg to the user PATH only, so the running script could not find it. `ffmpeg ... | findstr` with an unknown command ended the batch silently, and `2>nul` hid the error. winget's exit codes are also negative, which `if errorlevel 1` never sees.
- Logs: winget reports "Successfully installed".
- Fix: ef2569b. `env.bat` finds winget's real install folders and `:ensure_tool` judges success by finding the tool. Test: `test_bug_001_finds_ffmpeg_in_the_winget_package_folder`. Verified with two full `setup.bat` runs.
