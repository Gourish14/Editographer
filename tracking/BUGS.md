# Bug log

Status: New → Confirmed → In progress → Fixed → Verified (or Won't fix). Severity rules and template: `specs/12-spec-driven-development.md` §7–8. Claude logs bugs found during development automatically.

## Open

| ID | Title | Severity | Status | Found in |
| --- | --- | --- | --- | --- |
| BUG-001 | setup.bat exits with code 255 right after winget installs FFmpeg | High | New | T-102 |

## Closed

| ID | Title | Severity | Fixed in |
| --- | --- | --- | --- |
| — | — | — | — |

## Details

<!-- Add one section per bug using the template, newest first. -->

### BUG-001 — setup.bat exits with code 255 right after winget installs FFmpeg
- Status: New
- Severity: High
- Found: 2026-10-30, by Claude during T-102
- Spec: 09-local-setup.md#setupbat-run-once
- Steps to reproduce: On a machine without FFmpeg, run `C:\Editographer\setup.bat`.
- Expected: Steps 3 to 7 run after FFmpeg installs.
- Actual: The script stops after step 2 with exit code 255 and no error message. uv, `config/local.env` and the models are not installed. Cause not yet known.
- Logs: winget reports "Successfully installed".
- Fix: pending.
