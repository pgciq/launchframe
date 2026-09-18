[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8875,
    [int]$WebSocketPort = 8876,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $PSScriptRoot).Path
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$root;$env:PYTHONPATH" } else { $root }
$env:PVF_INSTALL_ROOT = $root
function Get-RegistryPathEntries {
    $entries = @()
    foreach ($scope in @("User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($value) { $entries += $value -split ';' }
    }
    return $entries | Where-Object { $_ } | ForEach-Object { [Environment]::ExpandEnvironmentVariables($_.Trim('"')) }
}

function Find-FfmpegExecutable {
    $candidates = @()
    if ($env:FFMPEG_PATH) { $candidates += $env:FFMPEG_PATH }
    $candidates += Join-Path $root ".tools\ffmpeg\ffmpeg.exe"
    $candidates += Get-RegistryPathEntries | ForEach-Object { Join-Path $_ "ffmpeg.exe" }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) { return (Resolve-Path $candidate).Path }
    }
    return $null
}

$ffmpegPath = Find-FfmpegExecutable
if ($ffmpegPath) { $env:FFMPEG_PATH = $ffmpegPath }
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$debugMode = $PSBoundParameters.ContainsKey("Debug") -and [bool]$PSBoundParameters["Debug"]
$runtimeDir = Join-Path $root ".video-work"
$runtimePath = Join-Path $runtimeDir "web-gui-runtime.json"
$logPath = Join-Path $runtimeDir "web-gui.log"
$errorLogPath = Join-Path $runtimeDir "web-gui-error.log"
if (-not (Test-Path $venvPython)) {
    throw "The Python environment is not configured. Run .\setup.ps1 first."
}

function Test-PortAvailable([int]$CandidatePort) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $CandidatePort)
    try { $listener.Start(); return $true } catch { return $false } finally { $listener.Stop() }
}

function Read-Runtime {
    if (-not (Test-Path $runtimePath)) { return $null }
    try { return Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json } catch { return $null }
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try { return (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").CommandLine } catch { return $null }
}

function Test-ExistingInstance($Runtime) {
    if (-not $Runtime -or -not $Runtime.pid) { return $null }
    try { $existing = Get-Process -Id ([int]$Runtime.pid) -ErrorAction Stop } catch { return $null }
    $commandLine = Get-ProcessCommandLine ([int]$Runtime.pid)
    if ($existing.Path -and ([IO.Path]::GetFullPath($existing.Path) -ne [IO.Path]::GetFullPath($venvPython))) { return $null }
    if ($commandLine -and $commandLine -notmatch "web_gui") { return $null }
    return $existing
}

function Confirm-ReplaceExisting {
    param([string]$Message)
    if ($debugMode) { return (Read-Host "$Message [y/N]") -match "^(y|yes)$" }
    try {
        Add-Type -AssemblyName PresentationFramework
        return [System.Windows.MessageBox]::Show($Message, "LaunchFrame", [System.Windows.MessageBoxButton]::YesNo, [System.Windows.MessageBoxImage]::Warning) -eq [System.Windows.MessageBoxResult]::Yes
    } catch {
        return (Read-Host "$Message [y/N]") -match "^(y|yes)$"
    }
}

function Stop-ExistingInstance($ProcessObject) {
    if (-not $ProcessObject) { return }
    try { & taskkill.exe /PID $ProcessObject.Id /T /F | Out-Null } catch { Stop-Process -Id $ProcessObject.Id -Force -ErrorAction SilentlyContinue }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if ($ProcessObject.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
}

$existingRuntime = Read-Runtime
$existingProcess = Test-ExistingInstance $existingRuntime
if ($existingProcess) {
    $existingUrl = if ($existingRuntime.port) { "http://$BindHost`:$($existingRuntime.port)/" } else { "http://$BindHost`:$Port/" }
    $replace = Confirm-ReplaceExisting "LaunchFrame is already running (PID $($existingProcess.Id)).`n`nClose the existing instance and start a new one?"
    if (-not $replace) {
        if (-not $NoBrowser) { Start-Process $existingUrl }
        exit 0
    }
    Stop-ExistingInstance $existingProcess
    Remove-Item -LiteralPath $runtimePath -Force -ErrorAction SilentlyContinue
}

$requestedPort = $Port
$requestedWebSocketPort = $WebSocketPort
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    if ((Test-PortAvailable $Port) -and (Test-PortAvailable $WebSocketPort)) { break }
    $Port = $requestedPort + (($attempt + 1) * 2)
    $WebSocketPort = $requestedWebSocketPort + (($attempt + 1) * 2)
}
if (-not (Test-PortAvailable $Port) -or -not (Test-PortAvailable $WebSocketPort)) {
    throw "Could not find two available localhost ports starting at $requestedPort/$requestedWebSocketPort."
}
if ($Port -ne $requestedPort) {
    Write-Host "Requested ports were occupied. Using HTTP $Port and WebSocket $WebSocketPort." -ForegroundColor Yellow
}

$url = "http://$BindHost`:$Port/"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$portsFile = Join-Path $runtimeDir "web-gui-ports.json"
@{ port = $Port; websocket_port = $WebSocketPort } | ConvertTo-Json | Set-Content -Encoding UTF8 $portsFile
$argumentList = @("-m", "web_gui", "--host", $BindHost, "--port", $Port, "--websocket-port", $WebSocketPort)
if ($debugMode) { $argumentList += "--debug" }
$startParameters = @{
    FilePath = $venvPython
    ArgumentList = $argumentList
    WorkingDirectory = $root
    PassThru = $true
}
if (-not $debugMode) {
    $startParameters.WindowStyle = "Hidden"
    Set-Content -LiteralPath $logPath -Value "" -Encoding UTF8
    Set-Content -LiteralPath $errorLogPath -Value "" -Encoding UTF8
    $startParameters.RedirectStandardOutput = $logPath
    $startParameters.RedirectStandardError = $errorLogPath
}
$process = Start-Process @startParameters
$runtime = @{
    pid = $process.Id
    port = $Port
    websocket_port = $WebSocketPort
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    debug = [bool]$debugMode
    log_path = $logPath
    error_log_path = $errorLogPath
    root = $root
    install_root = $root
    ffmpeg_path = $env:FFMPEG_PATH
}
$runtime | ConvertTo-Json | Set-Content -Encoding UTF8 $runtimePath
Write-Host "LaunchFrame Web GUI starting (PID $($process.Id))..." -ForegroundColor Cyan

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect($BindHost, $Port)
        $client.Dispose()
        $ready = $true
        break
    } catch {
        if ($process.HasExited) {
            Remove-Item -LiteralPath $runtimePath -Force -ErrorAction SilentlyContinue
            throw "Web GUI exited before it became ready."
        }
    }
}
if (-not $ready) {
    Remove-Item -LiteralPath $runtimePath -Force -ErrorAction SilentlyContinue
    throw "Web GUI did not become ready at $url"
}

Write-Host "Web GUI: $url" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $url }
