@echo off
rem Shared environment for setup.bat, start.bat and check.bat.
rem Keeps uv, its Python and its cache inside the project folder (specs/README.md rule 3).
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "UV_DIR=%ROOT%\tools\uv"
set "UV_PYTHON_INSTALL_DIR=%ROOT%\tools\python"
set "UV_PYTHON_BIN_DIR=%ROOT%\tools\python\bin"
set "UV_CACHE_DIR=%ROOT%\tools\uv-cache"
set "UV_PROJECT_ENVIRONMENT=%ROOT%\worker\.venv"
set "UV_PYTHON=3.12"
set "OLLAMA_MODELS=%ROOT%\models\ollama"

rem winget adds these folders to the user PATH only, which a running shell never sees.
set "FFMPEG_DIR=%ROOT%\tools\ffmpeg\bin"
for /d %%P in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*") do (
    for /d %%V in ("%%P\ffmpeg-*") do set "FFMPEG_DIR=%%V\bin"
)
set "OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama"

set "PATH=%UV_DIR%;%FFMPEG_DIR%;%ROOT%\tools\ffmpeg\bin;%OLLAMA_DIR%;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
