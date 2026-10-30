@echo off
rem Stops the backend, the worker and Ollama. Spec: specs/09-local-setup.md#startbat
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0scripts\env.bat"
cd /d "%ROOT%"

set "BACKEND_PORT=8080"
set "WORKER_PORT=8090"
if exist "config\local.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("config\local.env") do set "%%A=%%B"
)

call :stop_port %BACKEND_PORT%
call :stop_port %WORKER_PORT%
taskkill /f /im "ollama app.exe" >nul 2>nul
taskkill /f /im ollama.exe >nul 2>nul
echo Editographer stopped.
exit /b 0

:stop_port
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%~1 .*LISTENING"') do (
    taskkill /f /t /pid %%P >nul 2>nul
)
exit /b 0
