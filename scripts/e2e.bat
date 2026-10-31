@echo off
rem Browser end-to-end run against the real backend and worker. Spec: specs/11-coding-standards.md#5
rem Starts its own worker (18090), backend (18080) and UI (4300) so a running app is never touched.
rem Needs backend\target\editographer.jar (setup.bat builds it) and Chromium (first run downloads it
rem into tools\playwright). Screenshots land in frontend\e2e-screenshots.
setlocal EnableExtensions
call "%~dp0env.bat"
set "PLAYWRIGHT_BROWSERS_PATH=%ROOT%\tools\playwright"
cd /d "%ROOT%\frontend"
call npx playwright install chromium
if errorlevel 1 exit /b 1
call npx playwright test %*
exit /b %errorlevel%
