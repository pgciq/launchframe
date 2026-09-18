@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
echo LaunchFrame uninstaller
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\uninstall.ps1" %*
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo Uninstall did not complete successfully. Review the message above.
if not "%CODE%"=="0" pause
endlocal
exit /b %CODE%
