@echo off
rem Starts everything and opens the app. Spec: specs/09-local-setup.md#startbat
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0scripts\env.bat"
cd /d "%ROOT%"

if not exist "config\local.env" (
    echo Run setup.bat first: config\local.env is missing.
    exit /b 1
)
if not exist "backend\target\editographer.jar" (
    echo Run setup.bat first: the backend has not been built.
    exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("config\local.env") do set "%%A=%%B"

where ollama >nul 2>nul
if not errorlevel 1 (
    tasklist /fi "imagename eq ollama.exe" | findstr /i "ollama.exe" >nul
    if errorlevel 1 start "Editographer Ollama" /min ollama serve
)

start "Editographer worker" /min cmd /c "cd /d "%ROOT%\worker" && uv run uvicorn app.main:app --host %WORKER_HOST% --port %WORKER_PORT%"
start "Editographer backend" /min java -jar "%ROOT%\backend\target\editographer.jar"

echo Waiting for Editographer to start
set /a "TRIES=0"
:wait
curl -s -o nul -m 2 http://127.0.0.1:%BACKEND_PORT%/api/system
if not errorlevel 1 goto ready
set /a "TRIES+=1"
if %TRIES% GEQ 90 (
    echo Editographer did not start in time. See logs\backend.log and logs\worker.log.
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto wait

:ready
echo Editographer is running at http://localhost:%BACKEND_PORT%
if not defined EDITOGRAPHER_NO_BROWSER start "" "http://localhost:%BACKEND_PORT%"
exit /b 0
