@echo off
rem Starts or stops Editographer's own Ollama on its own port (OLLAMA_PORT in env.bat).
rem   ollama_server.bat start   starts it if nothing answers there, waits until it does; exit 1 on timeout
rem   ollama_server.bat stop    stops only the process listening on OLLAMA_PORT, never another Ollama
rem Spec: specs/09-local-setup.md#ollama-server
setlocal EnableExtensions
call "%~dp0env.bat"
if /i "%~1"=="start" goto start
if /i "%~1"=="stop" goto stop
echo Usage: ollama_server.bat start^|stop
exit /b 2

:start
curl -s -o nul -m 2 %OLLAMA_URL%/api/version
if not errorlevel 1 exit /b 0
start "Editographer Ollama" /min ollama serve
set /a "TRIES=0"
:wait
curl -s -o nul -m 2 %OLLAMA_URL%/api/version
if not errorlevel 1 exit /b 0
set /a "TRIES+=1"
if %TRIES% GEQ 30 (
    echo Ollama did not start on port %OLLAMA_PORT%.
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto wait

:stop
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"127.0.0.1:%OLLAMA_PORT% .*LISTENING"') do (
    taskkill /f /t /pid %%P >nul 2>nul
)
exit /b 0
