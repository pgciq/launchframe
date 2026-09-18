[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
# A Windows batch path ending in `\` can leave a literal closing quote in
# PowerShell's argument value. Normalize it defensively before Resolve-Path.
$ProjectRoot = $ProjectRoot.Trim().Trim('"')
$root = (Resolve-Path $ProjectRoot).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "LaunchFrame.lnk"
$powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$runScript = Join-Path $root "run.ps1"
$icon = Join-Path $root "assets\launchframe.ico"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShell
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runScript`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Start LaunchFrame"
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Save()
$manifestPath = Join-Path $root ".install-manifest.json"
if (Test-Path $manifestPath) {
    try {
        $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
        $created = @($manifest.created | Where-Object { $_ -ne "desktop-shortcut" })
        $created += "desktop-shortcut"
        $manifest.created = $created
        $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    } catch {
        Write-Warning "Desktop shortcut was created, but the install manifest could not be updated: $($_.Exception.Message)"
    }
}
Write-Host "Desktop shortcut created: $shortcutPath" -ForegroundColor Green
