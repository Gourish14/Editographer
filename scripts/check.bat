@echo off
rem Runs every test, lint, type and architecture check. Spec: specs/12-spec-driven-development.md#4
setlocal EnableExtensions
call "%~dp0env.bat"
set "FAILED="

echo === Scripts
cd /d "%ROOT%\scripts"
python -m unittest discover -s . -p "test_*.py"
if errorlevel 1 set "FAILED=%FAILED% scripts"

echo === Backend
cd /d "%ROOT%\backend"
call mvnw.cmd -B -ntp clean verify
if errorlevel 1 set "FAILED=%FAILED% backend"

echo === Worker
cd /d "%ROOT%\worker"
uv run ruff format --check .
if errorlevel 1 set "FAILED=%FAILED% worker-format"
uv run ruff check .
if errorlevel 1 set "FAILED=%FAILED% worker-lint"
uv run mypy
if errorlevel 1 set "FAILED=%FAILED% worker-types"
uv run lint-imports
if errorlevel 1 set "FAILED=%FAILED% worker-layers"
uv run pytest -q
if errorlevel 1 set "FAILED=%FAILED% worker-tests"

echo === Frontend
cd /d "%ROOT%\frontend"
call npx prettier --check "src/**/*.{ts,html,scss}"
if errorlevel 1 set "FAILED=%FAILED% frontend-format"
call npx ng lint
if errorlevel 1 set "FAILED=%FAILED% frontend-lint"
call npx ng test --watch=false
if errorlevel 1 set "FAILED=%FAILED% frontend-tests"

echo.
if defined FAILED (
    echo CHECKS FAILED:%FAILED%
    exit /b 1
)
echo ALL CHECKS PASSED
exit /b 0
