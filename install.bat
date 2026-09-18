@echo off
setlocal
set "ROOT=%~dp0"
set "PROJECT_ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

echo ================================================
echo LaunchFrame installer
echo ================================================
echo.

echo [1/4] Removing downloaded-file blocks...
call "%ROOT%unblock-scripts.bat"
if errorlevel 1 (
  echo.
  echo Installation stopped because scripts could not be unblocked.
  exit /b 1
)

echo.
echo [2/4] Running setup...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%setup.ps1" -InstallMissing
if errorlevel 1 (
  echo.
  echo Installation stopped because setup failed.
  exit /b 1
)
if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo.
  echo Installation stopped: .venv was not created.
  exit /b 1
)

echo.
echo [3/4] Creating desktop shortcut...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\create-shortcut.ps1" -ProjectRoot "%PROJECT_ROOT%"
if errorlevel 1 (
  echo.
  echo Installation stopped because the desktop shortcut could not be created.
  exit /b 1
)

echo.
echo Installation completed successfully.
set /p "START_NOW=Start LaunchFrame now? [Y/n]: "
if /I "%START_NOW%"=="" set "START_NOW=Y"
if /I "%START_NOW%"=="Y" (
  echo.
  echo Starting LaunchFrame in hidden mode...
  start "LaunchFrame" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT%run.ps1"
) else (
  echo You can start it from the desktop shortcut.
)
endlocal
exit /b 0
