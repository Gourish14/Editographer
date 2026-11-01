# Bug log

Status: New → Confirmed → In progress → Fixed → Verified (or Won't fix). Severity rules and template: `specs/12-spec-driven-development.md` §7–8. Claude logs bugs found during development automatically.

## Open

| ID | Title | Severity | Status | Found in |
| --- | --- | --- | --- | --- |
| BUG-016 | Uploads from the user's Chrome crawl at about 0.03 MB/s, cause unknown | High | Open | First real upload, 2026-11-01 |
| BUG-015 | Removing a clip deletes its file at one click, with no confirmation and no log line | High | Open | First real upload, 2026-11-01 |
| BUG-012 | A VS Code build with an old classpath can put crash stubs in `editographer.jar` | Medium | Open | Running the app, 2026-11-01 |

## Closed

| ID | Title | Severity | Fixed in |
| --- | --- | --- | --- |
| BUG-014 | A stopped `.OSV` stitch left a partial file that analysis would reuse as finished | High | This commit |
| BUG-013 | The `.OSV` stitch used 17.9 GB of memory on a 36 s clip and starved the machine | High | This commit |
| BUG-010 | The white flash on a drop hid the first half of a beat spin | Low | T-417 |
| BUG-011 | `setup.bat` and `start.bat` used any Ollama on 11434, and `stop.bat` killed every Ollama by name | High | T-419 |
| BUG-009 | A join could end a frame 0.33 ms early, so timestamps drifted | Low | 50fa6db |
| BUG-008 | A worker callback that fails was not retried, so a render could stay unfinished forever | High | T-407 |
| BUG-007 | BPM misread 118 as 120, across the B3 style boundary | Medium | 79edabd |
| BUG-006 | Zoom punches landed off-centre | High | 79edabd |
| BUG-005 | Database writes failed after about 25 minutes on a fresh install | Critical | 79edabd |
| BUG-004 | Final mix could end early, and `-shortest` cut video frames | High | 79edabd |
| BUG-003 | Two GPU guards after merging T-201 and T-202 broke the one-model rule | High | 8e8596e |
| BUG-002 | createdAt differs between create and read-back | Low | T-106 commit |
| BUG-001 | setup.bat exits with code 255 right after winget installs FFmpeg | High | ef2569b |

## Details

<!-- Add one section per bug using the template, newest first. -->

### BUG-016 — Uploads from the user's Chrome crawl at about 0.03 MB/s, cause unknown
- Status: Open
- Severity: High
- Found: 2026-11-01, by Claude on the first real upload
- Spec: 02-architecture.md
- Steps to reproduce: Drop `.OSV` clips from `C:\DJI OSMO Videos` on the project page in the user's Chrome. An Incognito window is just as slow.
- Expected: About 95 MB/s, as measured on the same page and file in a clean headless Chrome driven by Playwright. A Python tus client reached 98.8 MB/s.
- Actual: 0.01 to 0.05 MB/s per clip. Tomcat upload threads wait on the socket, so the backend is not the limit. Two uploads were running at the same time.
- Not yet compared: a visible window against headless, one upload against two, and a hidden or covered window.
- Workaround: Clips 1 and 2 were sent by a Python tus client (1977 MB in 19.6 s, 2448 MB in 87.8 s).
- Fix: Not done.

### BUG-015 — Removing a clip deletes its file at one click, with no confirmation and no log line
- Status: Open
- Severity: High
- Found: 2026-11-01, by Claude after a real upload disappeared
- Spec: 07-api-and-data.md
- Steps to reproduce: Click remove on a clip in `asset-grid.ts`.
- Expected: A confirmation first, and a log line naming the asset.
- Actual: `AssetService.deleteAsset` deletes the row and the file at once and logs nothing. Two `.OSV` clips of project `Bike_Vlogging` went this way at 08:01:24 UTC, 21 s after a backend start. The folder time and the first `job.orphaned` line match to the second. What sent the requests cannot be told from the logs. No other code path deletes an asset.
- Fix: Not done.

### BUG-013 — The `.OSV` stitch used 17.9 GB of memory on a 36 s clip and starved the machine
- Status: Fixed
- Severity: High
- Found: 2026-11-01, by Claude on the first real upload
- Spec: 08-osmo360.md
- Steps to reproduce: Upload `CAM_20261025215451_0004_D.OSV` (618 MB, 36 s) on the 15.7 GB laptop and let analysis run.
- Expected: The stitch stays within what the machine has and takes about as long as the Phase 3 run (18.6 min of analysis for 594 MB).
- Actual: 23 minutes in, ffmpeg held 17.9 GB of private memory, 0.35 GB of RAM was free and 2 GB of the 40.9 GB commit limit remained. The stitched file was 62 MB and growing about 3.6 MB a minute. Port 11500 was listening but gave no reply within 5 s. Docker's WSL distros were stopped.
- Cause: Not a leak, memory rises and stays flat. `v360` builds per-pixel tables, and `interp=cubic` at 8K twice costs about 5.5 GB more than `linear`. Default decode threads queue about 3 GB more frames.
- Measured, 60 frames of that clip: cubic 17.1 GB at 0.17 fps, cubic with 2 threads 14.6 GB at 0.33 fps, linear 11.7 GB at 0.78 fps, linear with 2 threads 8.5 GB at 2.94 fps. A daylight clip with linear and 2 threads gave 8.6 GB at 0.73 fps, against 0.23 fps for cubic with 2 threads.
- Fix: `interp=linear` and `-threads 2` on the input. Cost: linear keeps 78.6% of cubic's detail by Laplacian variance on a daylight frame. Seam geometry was not refitted, the profile values are unchanged.

### BUG-014 — A stopped `.OSV` stitch left a partial file that analysis would reuse as finished
- Status: Fixed
- Severity: High
- Found: 2026-11-01, by Claude while stopping the job for BUG-013
- Spec: 08-osmo360.md
- Steps to reproduce: Stop the worker during a stitch, then analyze the asset again.
- Expected: The stitch starts over.
- Actual: `_stitched` checks only that `media/stitched/{assetId}.mp4` exists, and ffmpeg was writing to that name, so a 75 MB file with no index was left to be reused.
- Fix: The stitch writes `{assetId}.part.mp4` and renames it when finished.

### BUG-012 — A VS Code build with an old classpath can put crash stubs in `editographer.jar`
- Status: Open
- Severity: Medium
- Found: 2026-11-01, by Claude while starting the app
- Spec: 09-local-setup.md
- Steps to reproduce: Open `backend` in VS Code with a classpath saved before a dependency was added, then run `mvnw package` without a separate build folder.
- Expected: The jar holds classes that Maven compiled.
- Actual: The Java extension also writes to `backend/target/classes`. `TusConfig` and `TusUploadAdapter` became "Unresolved compilation problems" stubs, Maven packaged them as up to date, and the backend failed at startup. 2 of 115 classes were affected.
- Workaround: Run **Java: Reload Projects** in VS Code. The running jar was built in a separate folder and scanned, 0 stubs.
- Fix: Not done. `setup.bat` still builds in `backend/target`.

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
