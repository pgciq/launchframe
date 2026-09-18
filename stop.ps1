[CmdletBinding()]
param(
    [int]$Port = 8875,
    [int]$WebSocketPort = 8876
)

$ErrorActionPreference = "Stop"
$portsFile = Join-Path $PSScriptRoot ".video-work\web-gui-ports.json"
if ($Port -eq 8875 -and $WebSocketPort -eq 8876 -and (Test-Path $portsFile)) {
    try {
        $savedPorts = Get-Content -Raw $portsFile | ConvertFrom-Json
        $Port = [int]$savedPorts.port
        $WebSocketPort = [int]$savedPorts.websocket_port
    } catch { }
}
$ports = @($Port, $WebSocketPort) | Select-Object -Unique
$processIds = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $ports -contains $_.LocalPort } |
        Select-Object -ExpandProperty OwningProcess -Unique
) | Where-Object { $_ -and $_ -ne $PID }

if (-not $processIds) {
    Write-Host "LaunchFrame Web GUI is not running on ports $($ports -join ', ')." -ForegroundColor Yellow
    exit 0
}

foreach ($processId in $processIds) {
    Write-Host "Stopping LaunchFrame Web GUI process tree (PID $processId)..." -ForegroundColor Cyan
    & taskkill.exe /PID $processId /T /F | Out-Null
}

Remove-Item $portsFile -Force -ErrorAction SilentlyContinue
Write-Host "LaunchFrame Web GUI stopped." -ForegroundColor Green
