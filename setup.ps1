[CmdletBinding()]
param(
    [switch]$InstallMissing,
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $PSScriptRoot).Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$manifestPath = Join-Path $root ".install-manifest.json"
$venvExistedBefore = Test-Path (Join-Path $root ".venv")
$ffmpegExistedBefore = Test-Path (Join-Path $root ".tools\ffmpeg")
$installedWinget = [System.Collections.Generic.List[string]]::new()
$installedNpm = [System.Collections.Generic.List[string]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()
$minimumNodeVersion = [version]"22.19.0"
$minimumPiVersion = [version]"0.85.1"

function Find-Command([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Get-PythonCandidates {
    # The Windows Python launcher can exist without a registered interpreter
    # (for example, the Scoop launcher). Try it, but do not let that shadow a
    # working python.exe later on PATH.
    $launcher = Find-Command @("py")
    if ($launcher) {
        [pscustomobject]@{ Path = $launcher; Arguments = @("-3.12") }
        # -3 selects the newest installed Python 3.x, so a working 3.13+
        # installation is preferred instead of installing the 3.12 fallback.
        [pscustomobject]@{ Path = $launcher; Arguments = @("-3") }
        [pscustomobject]@{ Path = $launcher; Arguments = @() }
    }
    $pythonExe = Find-Command @("python")
    if ($pythonExe) {
        [pscustomobject]@{ Path = $pythonExe; Arguments = @() }
    }
}

function Select-Python {
    foreach ($candidate in @(Get-PythonCandidates)) {
        # A stale py.exe launcher writes "No suitable Python runtime found"
        # to stderr and PowerShell 7 promotes that native stderr to a
        # NativeCommandError when $ErrorActionPreference is Stop. Treat a
        # failed probe as a normal candidate miss so setup can try the next
        # candidate or install Python through winget.
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $candidate.Path @($candidate.Arguments) -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" *> $null
            $exitCode = $LASTEXITCODE
        } catch {
            $exitCode = 1
        } finally {
            $ErrorActionPreference = $previousPreference
        }
        if ($exitCode -eq 0) { return $candidate }
    }
    return $null
}

function Get-ToolVersion([string]$Path) {
    if (-not $Path) { return $null }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = (& $Path --version 2>$null | Out-String)
        $exitCode = $LASTEXITCODE
    } catch {
        $output = ""
        $exitCode = 1
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) { return $null }
    $match = [regex]::Match($output, "(?<!\d)v?(\d+\.\d+\.\d+)")
    if (-not $match.Success) { return $null }
    try { return [version]$match.Groups[1].Value } catch { return $null }
}

function Find-OfficeExecutable([string]$Name) {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Microsoft Office\root\Office16\$Name"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Office\root\Office16\$Name"),
        (Join-Path $env:ProgramFiles "Microsoft Office\Office16\$Name"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Office\Office16\$Name")
    )
    foreach ($candidate in $candidates) { if ($candidate -and (Test-Path $candidate)) { return $candidate } }
    return (Find-Command @($Name))
}

function Check-Command([string]$Label, [string[]]$Names, [bool]$Required = $true) {
    $path = Find-Command $Names
    if ($path) { Write-Host "[OK] ${Label}: $path" -ForegroundColor Green; return $path }
    $message = "$Label was not found."
    if ($Required) { $errors.Add($message) } else { $warnings.Add($message) }
    Write-Host "[WARN] $message" -ForegroundColor Yellow
    return $null
}

Write-Host "LaunchFrame setup" -ForegroundColor Cyan
Write-Host "Project root: $root"

# Python is the only bootstrap prerequisite. Install it before checking the
# remaining tools so setup can create the virtual environment on a clean machine
# without requiring the user to answer a generic missing-software prompt.
$pythonSpec = Select-Python
if (-not $pythonSpec) {
    Write-Host "Python 3.10+ was not found. Installing Python 3.12 as the fallback with winget..." -ForegroundColor Cyan
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3.10 or newer is required, but winget was not found. Install Python manually from https://www.python.org/downloads/windows/ and rerun setup.ps1."
    }
    & $winget.Source install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Python fallback installation through winget failed. Install Python 3.10+ manually and rerun setup.ps1."
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $pythonSpec = Select-Python
    if (-not $pythonSpec) {
        throw "Python installation completed, but no working Python 3.10+ interpreter was found in PATH. Restart PowerShell and rerun setup.ps1."
    }
    Write-Host "[OK] Python installed: $($pythonSpec.Path)" -ForegroundColor Green
}

$nodeCandidate = Find-Command @("node")
$nodeVersion = Get-ToolVersion $nodeCandidate
$piCandidate = Find-Command @("pi", "pi.cmd")
$piVersion = Get-ToolVersion $piCandidate

if (-not $InstallMissing -and -not $env:CI) {
    $missing = @()
    if (-not $nodeVersion -or $nodeVersion -lt $minimumNodeVersion) { $missing += "Node.js >= $minimumNodeVersion" }
    if (-not (Find-Command @("git"))) { $missing += "Git" }
    if (-not (Find-Command @("az.cmd", "az"))) { $missing += "Azure CLI" }
    if (-not $piVersion -or $piVersion -lt $minimumPiVersion) { $missing += "Pi CLI >= $minimumPiVersion" }
    $officeAvailable = (Find-OfficeExecutable "POWERPNT.EXE") -and (Find-OfficeExecutable "WINWORD.EXE")
    if (-not $officeAvailable -and -not (Find-Command @("soffice", "soffice.exe"))) { $missing += "LibreOffice fallback" }
    if (-not $officeAvailable -and -not (Find-Command @("pdftoppm", "pdftoppm.exe"))) { $missing += "Poppler fallback" }
    $ffmpegAvailable = @($env:FFMPEG_PATH, (Join-Path $root ".tools\ffmpeg\ffmpeg.exe"), (Find-Command @("ffmpeg.exe", "ffmpeg"))) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $ffmpegAvailable) { $missing += "FFmpeg" }
    if ($missing.Count -gt 0) {
        Write-Host "Missing software detected: $($missing -join ', ')" -ForegroundColor Yellow
        $answer = Read-Host "Install missing software automatically using Winget/public download? [y/N]"
        if ($answer -match "^(y|yes)$") { $InstallMissing = $true }
        else { Write-Host "Skipping automatic installation. The setup will continue with detection and report required items." -ForegroundColor Yellow }
    }
}
if ($InstallMissing) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { $warnings.Add("winget was not found; automatic installation was skipped.") }
    else {
        $packages = @(
            @{ Name = "Node.js LTS"; Id = "OpenJS.NodeJS.LTS"; Commands = @("node") },
            @{ Name = "Git"; Id = "Git.Git"; Commands = @("git") },
            @{ Name = "Azure CLI"; Id = "Microsoft.AzureCLI"; Commands = @("az.cmd", "az") },
            @{ Name = "LibreOffice"; Id = "TheDocumentFoundation.LibreOffice"; Commands = @("soffice", "soffice.exe") },
            @{ Name = "Poppler"; Id = "oschwartz10612.Poppler"; Commands = @("pdftoppm", "pdftoppm.exe") },
            @{ Name = "FFmpeg"; Id = "Gyan.FFmpeg.Shared"; Commands = @("ffmpeg.exe", "ffmpeg") }
        )
        $officeAvailable = (Find-OfficeExecutable "POWERPNT.EXE") -and (Find-OfficeExecutable "WINWORD.EXE")
        foreach ($package in $packages) {
            if ($officeAvailable -and $package.Name -in @("LibreOffice", "Poppler")) { continue }
            $packagePath = Find-Command $package.Commands
            $packageVersion = if ($package.Name -eq "Node.js LTS") { Get-ToolVersion $packagePath } else { $null }
            $packageNeedsInstall = -not $packagePath
            if ($package.Name -eq "Node.js LTS" -and (-not $packageVersion -or $packageVersion -lt $minimumNodeVersion)) { $packageNeedsInstall = $true }
            if ($packageNeedsInstall) {
                Write-Host "Installing $($package.Name)..." -ForegroundColor Cyan
                winget install --id $package.Id --exact --silent --accept-package-agreements --accept-source-agreements
                if ($LASTEXITCODE -ne 0) { $errors.Add("Could not install $($package.Name) through winget.") }
                else { $installedWinget.Add($package.Id) }
            }
        }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }
}

if ($pythonSpec) {
    Write-Host "[OK] Python: $($pythonSpec.Path)" -ForegroundColor Green
} else {
    $errors.Add("Python 3.10 or newer was not found.")
    Write-Host "[ERROR] Python 3.10 or newer was not found." -ForegroundColor Red
}
if (-not (Test-Path $venvPython)) {
    if (-not $pythonSpec) { throw "Python 3.10 or newer is required to create .venv." }
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    & $pythonSpec.Path @($pythonSpec.Arguments) -m venv (Join-Path $root ".venv")
}
if (-not (Test-Path $venvPython)) { $errors.Add("Python virtual environment could not be created. Check the Python error above and remove a partial .venv before retrying.") }
else {
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { $errors.Add("Could not upgrade pip.") }
    & $venvPython -m pip install -e $root
    if ($LASTEXITCODE -ne 0) { $errors.Add("Could not install the LaunchFrame project. Stop running launchframe processes and retry setup.ps1.") }
    $azureVendor = Join-Path $root "vendor\azure-mcp"
    if (Test-Path (Join-Path $azureVendor "pyproject.toml")) {
        & $venvPython -m pip install -e $azureVendor
        if ($LASTEXITCODE -ne 0) { $errors.Add("Could not install vendored azure-mcp.") }
    }
}

$node = Check-Command "Node.js" @("node") $true
$nodeVersion = Get-ToolVersion $node
if (-not $nodeVersion -or $nodeVersion -lt $minimumNodeVersion) {
    $found = if ($nodeVersion) { $nodeVersion } else { "unknown" }
    $errors.Add("Node.js $minimumNodeVersion or newer is required (found $found). Upgrade Node.js and rerun setup.ps1.")
    Write-Host "[ERROR] Node.js $minimumNodeVersion or newer is required (found $found)." -ForegroundColor Red
} else { Write-Host "[OK] Node.js version: $nodeVersion" -ForegroundColor Green }
$npm = Check-Command "npm" @("npm", "npm.cmd") $true
$pi = Find-Command @("pi", "pi.cmd")
$piVersion = Get-ToolVersion $pi
$piNeedsInstall = -not $pi -or -not $piVersion -or $piVersion -lt $minimumPiVersion
if ($piNeedsInstall -and $InstallMissing -and $npm) {
    Write-Host "Installing/updating Pi CLI..." -ForegroundColor Cyan
    & $npm install --global @earendil-works/pi-coding-agent@latest
    if ($LASTEXITCODE -ne 0) { $errors.Add("Could not install Pi CLI through npm.") }
    else { $installedNpm.Add("@earendil-works/pi-coding-agent@latest") }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $pi = Find-Command @("pi", "pi.cmd")
    $piVersion = Get-ToolVersion $pi
}
if (-not $piVersion -or $piVersion -lt $minimumPiVersion) {
    $found = if ($piVersion) { $piVersion } else { "not found" }
    $errors.Add("Pi CLI $minimumPiVersion or newer is required (found $found). Upgrade @earendil-works/pi-coding-agent and rerun setup.ps1.")
    Write-Host "[ERROR] Pi CLI $minimumPiVersion or newer is required (found $found)." -ForegroundColor Red
} else { Write-Host "[OK] Pi: $pi ($piVersion)" -ForegroundColor Green }
Check-Command "Git" @("git") $false | Out-Null
Check-Command "Azure CLI" @("az.cmd", "az") $false | Out-Null
$powerpoint = Find-OfficeExecutable "POWERPNT.EXE"
if ($powerpoint) { Write-Host "[OK] PowerPoint: $powerpoint" -ForegroundColor Green } else { $warnings.Add("PowerPoint was not found."); Write-Host "[WARN] PowerPoint was not found." -ForegroundColor Yellow }
$word = Find-OfficeExecutable "WINWORD.EXE"
if ($word) { Write-Host "[OK] Microsoft Word: $word" -ForegroundColor Green } else { $warnings.Add("Microsoft Word was not found."); Write-Host "[WARN] Microsoft Word was not found." -ForegroundColor Yellow }
$libreOffice = Find-Command @("soffice", "soffice.exe")
if ($libreOffice) { Write-Host "[OK] LibreOffice fallback: $libreOffice" -ForegroundColor Green } else { Write-Host "[INFO] LibreOffice not found; optional when Microsoft Office is available." -ForegroundColor DarkGray }
$poppler = Find-Command @("pdftoppm", "pdftoppm.exe")
if ($poppler) { Write-Host "[OK] Poppler fallback: $poppler" -ForegroundColor Green } else { Write-Host "[INFO] Poppler not found; optional because PDF pages use PyMuPDF." -ForegroundColor DarkGray }

$ffmpegCandidates = @(
    $env:FFMPEG_PATH,
    (Join-Path $root ".tools\ffmpeg\ffmpeg.exe"),
    (Find-Command @("ffmpeg.exe", "ffmpeg"))
) | Where-Object { $_ -and (Test-Path $_) }
if ($ffmpegCandidates) { Write-Host "[OK] FFmpeg: $($ffmpegCandidates[0])" -ForegroundColor Green }
else {
    if ($InstallMissing) {
        $errors.Add("FFmpeg could not be installed through Winget. Run 'winget install Gyan.FFmpeg.Shared' manually, or set FFMPEG_PATH.")
        Write-Host "[ERROR] FFmpeg was not found after Winget installation." -ForegroundColor Red
    } else {
        $warnings.Add("FFmpeg was not found. Run 'winget install Gyan.FFmpeg.Shared' or set FFMPEG_PATH.")
        Write-Host "[WARN] FFmpeg was not found." -ForegroundColor Yellow
        Write-Host "Install it with: winget install Gyan.FFmpeg.Shared" -ForegroundColor Yellow
    }
}

if ($ProjectRoot) {
    $resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
    [Environment]::SetEnvironmentVariable("VIDEO_PROJECT_ROOT", $resolvedProjectRoot, "User")
    $env:VIDEO_PROJECT_ROOT = $resolvedProjectRoot
    Write-Host "[OK] VIDEO_PROJECT_ROOT set to $resolvedProjectRoot" -ForegroundColor Green
} elseif ($env:VIDEO_PROJECT_ROOT) {
    Write-Host "[OK] VIDEO_PROJECT_ROOT: $env:VIDEO_PROJECT_ROOT" -ForegroundColor Green
} else {
    Write-Host "[INFO] VIDEO_PROJECT_ROOT is not set; using the LaunchFrame installation directory as the default workspace root." -ForegroundColor DarkGray
}

if ($warnings.Count -gt 0) {
    Write-Host "`nOptional or externally managed items:" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host " - $_" }
}
if ($errors.Count -gt 0) {
    Write-Host "`nSetup failed:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host " - $_" }
    exit 1
}
$created = @()
if (-not $venvExistedBefore -and (Test-Path (Join-Path $root ".venv"))) { $created += ".venv" }
if (-not $ffmpegExistedBefore -and (Test-Path (Join-Path $root ".tools\ffmpeg"))) { $created += ".tools\ffmpeg" }
$version = "unknown"
$pyproject = Join-Path $root "pyproject.toml"
if (Test-Path $pyproject) {
    $versionMatch = Select-String -LiteralPath $pyproject -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($versionMatch) { $version = $versionMatch.Matches[0].Groups[1].Value }
}
$manifest = @{
    version = $version
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    root = $root
    created = @($created)
    winget_installed = @($installedWinget)
    npm_installed = @($installedNpm)
    environment_variables = @{ VIDEO_PROJECT_ROOT = if ($ProjectRoot) { $resolvedProjectRoot } else { "" } }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Installation manifest: $manifestPath" -ForegroundColor DarkGray
Write-Host "`nSetup completed. Run .\run.ps1 to start the local Web GUI." -ForegroundColor Green
