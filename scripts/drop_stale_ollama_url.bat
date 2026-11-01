@echo off
rem Removes an old OLLAMA_URL line from config\local.env: the address now comes from scripts\env.bat.
rem Spec: specs/09-local-setup.md#ollama-server
setlocal EnableExtensions
call "%~dp0env.bat"
if not exist "%ROOT%\config\local.env" exit /b 0
powershell -NoProfile -Command "$p='%ROOT%\config\local.env'; $t=[IO.File]::ReadAllText($p); $n=[regex]::Replace($t,'(?m)^OLLAMA_URL=[^\r\n]*(\r?\n)?',''); if ($n -ne $t) { [IO.File]::WriteAllText($p,$n) }"
exit /b 0
