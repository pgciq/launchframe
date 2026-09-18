@echo off
setlocal
set "ROOT=%~dp0"
 echo Removing Windows download blocks from LaunchFrame PowerShell scripts...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%ROOT%' -Recurse -File | Where-Object { $_.Extension -in '.ps1', '.bat' } | Unblock-File"
if errorlevel 1 (
  echo Failed to unblock scripts. Check PowerShell policy or contact IT Security.
  exit /b 1
)
echo Scripts unblocked. You can now run setup.ps1 or run.ps1.
echo If PowerShell still reports that script execution is disabled, run:
echo powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\setup.ps1" -InstallMissing
endlocal
