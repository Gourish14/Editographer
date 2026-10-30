# Bug log

Status: New → Confirmed → In progress → Fixed → Verified (or Won't fix). Severity rules and template: `specs/12-spec-driven-development.md` §7–8. Claude logs bugs found during development automatically.

## Open

| ID | Title | Severity | Status | Found in |
| --- | --- | --- | --- | --- |
| — | No open bugs | — | — | — |

## Closed

| ID | Title | Severity | Fixed in |
| --- | --- | --- | --- |
| BUG-002 | createdAt differs between create and read-back | Low | T-106 commit |
| BUG-001 | setup.bat exits with code 255 right after winget installs FFmpeg | High | ef2569b |

## Details

<!-- Add one section per bug using the template, newest first. -->

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
