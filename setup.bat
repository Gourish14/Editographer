@echo off
rem One-time install, safe to re-run. Spec: specs/09-local-setup.md#setupbat-run-once
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0scripts\env.bat"
cd /d "%ROOT%"

set "MIN_JAVA_MAJOR=25"
set "MIN_NODE_MAJOR=24"
set "MIN_NODE_MINOR=15"
set "UV_VERSION=0.13.6"

echo [1/9] Checking Java, Node and the NVIDIA driver
where java >nul 2>nul || call :fail "Java not found. Install Java %MIN_JAVA_MAJOR% or newer."
if errorlevel 1 exit /b 1
set "JAVA_MAJOR="
for /f "tokens=3" %%V in ('java -version 2^>^&1 ^| findstr /i "version"') do if not defined JAVA_MAJOR set "JAVA_MAJOR=%%~V"
for /f "tokens=1 delims=." %%M in ("%JAVA_MAJOR%") do set "JAVA_MAJOR=%%M"
if %JAVA_MAJOR% LSS %MIN_JAVA_MAJOR% (
    call :fail "Java %JAVA_MAJOR% found, but Java %MIN_JAVA_MAJOR% or newer is required."
    exit /b 1
)

where node >nul 2>nul || call :fail "Node.js not found. Install Node %MIN_NODE_MAJOR%.%MIN_NODE_MINOR% or newer."
if errorlevel 1 exit /b 1
for /f "tokens=1,2 delims=v." %%A in ('node -v') do (
    set "NODE_MAJOR=%%A"
    set "NODE_MINOR=%%B"
)
set "NODE_OK="
if %NODE_MAJOR% GTR %MIN_NODE_MAJOR% set "NODE_OK=1"
if %NODE_MAJOR% EQU %MIN_NODE_MAJOR% if %NODE_MINOR% GEQ %MIN_NODE_MINOR% set "NODE_OK=1"
if not defined NODE_OK (
    call :fail "Node %NODE_MAJOR%.%NODE_MINOR% found, but Node %MIN_NODE_MAJOR%.%MIN_NODE_MINOR% or newer is required."
    exit /b 1
)

where nvidia-smi >nul 2>nul || call :fail "nvidia-smi not found. Install the NVIDIA driver."
if errorlevel 1 exit /b 1
nvidia-smi -L >nul 2>nul || call :fail "nvidia-smi could not reach a GPU. Check the NVIDIA driver."
if errorlevel 1 exit /b 1

echo [2/9] Checking FFmpeg
call :ensure_tool ffmpeg Gyan.FFmpeg
if errorlevel 1 exit /b 1
ffmpeg -hide_banner -encoders 2>nul | findstr /c:"hevc_nvenc" >nul
if errorlevel 1 (
    call :fail "This FFmpeg build has no hevc_nvenc. Remove it from PATH and run setup.bat again."
    exit /b 1
)
ffmpeg -hide_banner -loglevel error -f lavfi -i color=black:s=1280x720:d=0.1 -pix_fmt p010le -c:v hevc_nvenc -f null - >nul 2>nul
if errorlevel 1 (
    call :fail "FFmpeg cannot open hevc_nvenc in 10-bit. Update the NVIDIA driver."
    exit /b 1
)

echo [3/9] Checking Ollama
call :ensure_tool ollama Ollama.Ollama
if errorlevel 1 exit /b 1

echo [4/9] Installing uv and Python 3.12 into tools\
if not exist "%UV_DIR%\uv.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_UNMANAGED_INSTALL='%UV_DIR%'; irm https://astral.sh/uv/%UV_VERSION%/install.ps1 | iex"
    if errorlevel 1 (
        call :fail "uv installation failed."
        exit /b 1
    )
)
uv python install 3.12
if errorlevel 1 (
    call :fail "Python 3.12 installation failed."
    exit /b 1
)

echo [5/9] Installing the worker's Python packages
if exist "worker\pyproject.toml" (
    pushd worker
    uv sync
    set "SYNC_RESULT=!errorlevel!"
    popd
    if not "!SYNC_RESULT!"=="0" (
        call :fail "uv sync failed in worker\."
        exit /b 1
    )
)

echo [6/9] Downloading model weights
uv run --no-project python scripts\download_models.py
if errorlevel 1 (
    call :fail "Model download failed. Run setup.bat again to resume."
    exit /b 1
)

echo Making free LUTs and SFX
uv run --no-project python scripts\make_look_assets.py
if errorlevel 1 (
    call :fail "LUT and SFX generation failed. Run setup.bat again."
    exit /b 1
)

echo [7/9] Building the web app
if exist "frontend\package.json" (
    pushd frontend
    call npm ci --no-fund --no-audit
    set "BUILD_RESULT=!errorlevel!"
    if "!BUILD_RESULT!"=="0" (
        call npx ng build
        set "BUILD_RESULT=!errorlevel!"
    )
    popd
    if not "!BUILD_RESULT!"=="0" (
        call :fail "The web app did not build."
        exit /b 1
    )
    if exist "backend\src\main\resources\static" rmdir /s /q "backend\src\main\resources\static"
    xcopy /e /i /q /y "frontend\dist\editographer\browser" "backend\src\main\resources\static" >nul
)

echo [8/9] Building the backend
pushd backend
call .\mvnw.cmd -B -ntp -q -DskipTests package
set "BUILD_RESULT=!errorlevel!"
popd
if not "!BUILD_RESULT!"=="0" (
    call :fail "The backend did not build."
    exit /b 1
)

echo [9/9] Creating config\local.env and data folders
if not exist "media" mkdir "media"
if not exist "data" mkdir "data"
if not exist "logs" mkdir "logs"
if not exist "config\local.env" (
    set "TOKEN="
    for /f %%T in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do set "TOKEN=%%T"
    if not defined TOKEN (
        call :fail "Could not generate a worker token."
        exit /b 1
    )
    powershell -NoProfile -Command "(Get-Content 'config\local.env.example') -replace '^WORKER_TOKEN=.*', 'WORKER_TOKEN=!TOKEN!' | Set-Content -Encoding ascii 'config\local.env'"
    if errorlevel 1 (
        call :fail "Could not write config\local.env."
        exit /b 1
    )
)

echo.
echo Setup finished.
exit /b 0

:ensure_tool
rem Judged by finding the tool: winget's exit codes are negative, which errorlevel checks miss.
where %~1 >nul 2>nul
if not errorlevel 1 exit /b 0
echo Installing %~2 with winget
winget install --id %~2 --exact --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
call "%ROOT%\scripts\env.bat"
where %~1 >nul 2>nul
if not errorlevel 1 exit /b 0
call :fail "%~2 was installed, but %~1 could not be found."
exit /b 1

:fail
echo.
echo SETUP FAILED: %~1
exit /b 1
