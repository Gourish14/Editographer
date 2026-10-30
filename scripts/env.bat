@echo off
rem Shared environment for setup.bat, start.bat and check.bat.
rem Keeps uv, its Python and its cache inside the project folder (specs/README.md rule 3).
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "UV_DIR=%ROOT%\tools\uv"
set "UV_PYTHON_INSTALL_DIR=%ROOT%\tools\python"
set "UV_CACHE_DIR=%ROOT%\tools\uv-cache"
set "UV_PROJECT_ENVIRONMENT=%ROOT%\worker\.venv"
set "UV_PYTHON=3.12"

set "PATH=%UV_DIR%;%ROOT%\tools\ffmpeg\bin;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
