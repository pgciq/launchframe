@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%run.ps1" -Debug
if errorlevel 1 pause
endlocal
