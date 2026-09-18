[CmdletBinding()]
param(
    [switch]$Purge,
    [switch]$RemoveInstallationDirectory
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$manifestPath = Join-Path $root ".install-manifest.json"
$runtimePath = Join-Path $root ".video-work\web-gui-runtime.json"
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "LaunchFrame.lnk"

function Read-Manifest {
    if (-not (Test-Path $manifestPath)) { return $null }
    try { return Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json } catch { return $null }
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try { return (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").CommandLine } catch { return $null }
}

function Get-RunningInstance($Runtime) {
    if (-not $Runtime -or -not $Runtime.pid) { return $null }
    try { $process = Get-Process -Id ([int]$Runtime.pid) -ErrorAction Stop } catch { return $null }
    $commandLine = Get-ProcessCommandLine ([int]$Runtime.pid)
    if ($commandLine -and $commandLine -notmatch "web_gui") { return $null }
    return $process
}

function Confirm-Action([string]$Message) {
    $answer = Read-Host "$Message [y/N]"
    return $answer -match "^(y|yes)$"
}

$manifest = Read-Manifest
$runtime = $null
if (Test-Path $runtimePath) {
    try { $runtime = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json } catch { $runtime = $null }
}
$running = Get-RunningInstance $runtime
if ($running) {
    if (-not (Confirm-Action "LaunchFrame is running (PID $($running.Id)). Close it before uninstalling?")) {
        Write-Host "Uninstall cancelled." -ForegroundColor Yellow
        exit 1
    }
    try { & taskkill.exe /PID $running.Id /T /F | Out-Null } catch { Stop-Process -Id $running.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
}

Write-Host "This removes LaunchFrame application files and its desktop shortcut." -ForegroundColor Cyan
Write-Host "Product resource folders, generated outputs, and shared system tools are preserved." -ForegroundColor Yellow
if (-not (Confirm-Action "Continue with uninstall?")) {
    Write-Host "Uninstall cancelled." -ForegroundColor Yellow
    exit 1
}

$removed = [System.Collections.Generic.List[string]]::new()
$preserved = [System.Collections.Generic.List[string]]::new()
$failed = [System.Collections.Generic.List[string]]::new()

function Remove-PathIfPresent([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) { return }
    try { Remove-Item -LiteralPath $Path -Recurse -Force; $removed.Add($Label) } catch { $failed.Add("${Label}: $($_.Exception.Message)") }
}

if (Test-Path $shortcutPath) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $target = "$($shortcut.TargetPath) $($shortcut.Arguments)"
        if ($target -match [regex]::Escape($root)) {
            Remove-Item -LiteralPath $shortcutPath -Force
            $removed.Add("Desktop shortcut")
        } else { $preserved.Add("Desktop shortcut (points to another installation)") }
    } catch { $failed.Add("Desktop shortcut: $($_.Exception.Message)") }
}

$created = @($manifest.created)
if ($created -contains ".venv") { Remove-PathIfPresent (Join-Path $root ".venv") ".venv" } else { $preserved.Add(".venv (not recorded as created by this installer)") }
if ($created -contains ".tools\ffmpeg") { Remove-PathIfPresent (Join-Path $root ".tools\ffmpeg") ".tools\ffmpeg" } else { $preserved.Add(".tools\ffmpeg (not recorded as created by this installer)") }
Remove-PathIfPresent $runtimePath "Web GUI runtime file"
Remove-PathIfPresent (Join-Path $root ".video-work\web-gui-ports.json") "Web GUI ports file"

if ($Purge) {
    Remove-PathIfPresent (Join-Path $root ".install-manifest.json") "Installation manifest"
} else {
    Remove-PathIfPresent $manifestPath "Installation manifest"
}

$manifestRoot = if ($manifest) { [string]$manifest.root } else { $root }
$recordedProjectRoot = if ($manifest -and $manifest.environment_variables) { [string]$manifest.environment_variables.VIDEO_PROJECT_ROOT } else { "" }
$currentProjectRoot = [Environment]::GetEnvironmentVariable("VIDEO_PROJECT_ROOT", "User")
if ($recordedProjectRoot -and $currentProjectRoot -eq $recordedProjectRoot) {
    if (Confirm-Action "Remove the user VIDEO_PROJECT_ROOT environment variable? (value: $currentProjectRoot)") {
        [Environment]::SetEnvironmentVariable("VIDEO_PROJECT_ROOT", $null, "User")
        $removed.Add("VIDEO_PROJECT_ROOT user environment variable")
    } else { $preserved.Add("VIDEO_PROJECT_ROOT user environment variable") }
} elseif ($currentProjectRoot) {
    $preserved.Add("VIDEO_PROJECT_ROOT (value was not created by this installation)")
}

if ($manifest -and $manifest.winget_installed) {
    $preserved.Add("Shared Winget tools: " + (@($manifest.winget_installed) -join ", "))
}
if ($manifest -and $manifest.npm_installed) {
    $preserved.Add("Shared npm packages: " + (@($manifest.npm_installed) -join ", "))
}

if ($RemoveInstallationDirectory) {
    $confirmation = Read-Host "Type DELETE to remove the entire installation directory '$root'"
    if ($confirmation -ne "DELETE") {
        Write-Host "Installation directory removal skipped." -ForegroundColor Yellow
    } else {
        $cleanup = Join-Path $env:TEMP ("pvf-cleanup-" + [guid]::NewGuid().ToString("N") + ".ps1")
        @"
Start-Sleep -Seconds 2
Remove-Item -LiteralPath '$($root.Replace("'", "''"))' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$($cleanup.Replace("'", "''"))' -Force -ErrorAction SilentlyContinue
"@ | Set-Content -LiteralPath $cleanup -Encoding UTF8
        Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanup) -WindowStyle Hidden
        Write-Host "Installation directory removal scheduled." -ForegroundColor Green
        exit 0
    }
}

Write-Host "`nUninstall summary" -ForegroundColor Cyan
Write-Host "Removed:"
if ($removed.Count) { $removed | ForEach-Object { Write-Host " - $_" } } else { Write-Host " - Nothing" }
Write-Host "Preserved:"
if ($preserved.Count) { $preserved | ForEach-Object { Write-Host " - $_" } } else { Write-Host " - Nothing" }
if ($failed.Count) {
    Write-Host "Could not remove:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host " - $_" }
    exit 1
}
Write-Host "Uninstall completed." -ForegroundColor Green
