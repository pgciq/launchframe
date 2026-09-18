[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = "Stop"
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot "ffmpeg-config.json" }
$config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
$projectRoot = Split-Path $PSScriptRoot -Parent
$installDir = Join-Path $projectRoot ".tools\ffmpeg"
$tempRoot = Join-Path $env:TEMP ("launchframe-ffmpeg-" + [guid]::NewGuid().ToString("N"))
$archive = Join-Path $tempRoot "ffmpeg.zip"
$checksumFile = Join-Path $tempRoot "ffmpeg.sha256"
$extractDir = Join-Path $tempRoot "extract"
New-Item -ItemType Directory -Force -Path $tempRoot, $extractDir | Out-Null
try {
    Write-Host "Downloading public FFmpeg build $($config.version)..."
    Invoke-WebRequest -Uri $config.packageUrl -OutFile $archive -UseBasicParsing
    Invoke-WebRequest -Uri $config.sha256Url -OutFile $checksumFile -UseBasicParsing
    $expectedHash = (Get-Content -Raw -Encoding UTF8 $checksumFile) -match "(?i)([0-9a-f]{64})"
    if (-not $expectedHash) { throw "FFmpeg checksum was not found at $($config.sha256Url)." }
    $expected = $Matches[1].ToLowerInvariant()
    $hashLines = certutil.exe -hashfile $archive SHA256
    $actual = ($hashLines | Where-Object { $_ -match "^[0-9A-Fa-f]{64}$" } | Select-Object -First 1).Trim().ToLowerInvariant()
    if ($actual -ne $expected) { throw "FFmpeg SHA-256 mismatch. Expected $expected, got $actual." }
    Expand-Archive -Path $archive -DestinationPath $extractDir -Force
    $executable = Get-ChildItem -Path $extractDir -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
    if (-not $executable) { throw "ffmpeg.exe was not found in the downloaded archive." }
    if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    Copy-Item (Join-Path $executable.Directory.FullName "*") $installDir -Force
    $installed = Join-Path $installDir "ffmpeg.exe"
    & $installed -version *> $null
    if ($LASTEXITCODE -ne 0) { throw "The installed FFmpeg executable failed its version check." }
    Write-Host "Installed FFmpeg at $installed"
} finally {
    if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
