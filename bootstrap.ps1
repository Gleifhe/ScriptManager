<#
.SYNOPSIS
    One-click installer for ScriptManager (workstation / inproc mode).

.DESCRIPTION
    - Verifies Python 3.10+ is available.
    - Creates a virtual environment.
    - Installs ScriptManager (editable in dev mode, or as a proper package
      in production mode with -Production).
    - Writes a .env file to the data directory.
    - Initializes the SQLite database.
    - Prints next-step instructions.

.PARAMETER Celery
    Install the optional celery extra (celery + redis). Required only for
    distributed/multi-host deployments.

.PARAMETER Service
    Also install pywin32 (the [windows] extra) needed for the Windows
    service installer (scriptmgr service install).

.PARAMETER Python
    Path to the Python interpreter to use. Defaults to "python".

.PARAMETER Production
    Install as a standalone production system (not editable/dev mode).
    Uses -InstallDir for the venv and -DataDir for data/config.

.PARAMETER InstallDir
    Where to create the virtual environment in production mode.
    Default: C:\Program Files\ScriptManager

.PARAMETER DataDir
    Where to store the database, logs, and .env in production mode.
    Default: C:\ProgramData\ScriptManager

.EXAMPLE
    .\bootstrap.ps1
    Installs in workstation (dev/editable) mode — ideal for a single PC
    where you also want to edit the source.

.EXAMPLE
    .\bootstrap.ps1 -Production
    Installs as a standalone production system into C:\Program Files\ScriptManager.
    Data stored in C:\ProgramData\ScriptManager.

.EXAMPLE
    .\bootstrap.ps1 -Production -InstallDir "D:\Apps\ScriptManager" -DataDir "D:\ScriptManagerData"
    Installs to custom directories.

.EXAMPLE
    .\bootstrap.ps1 -Celery
    Installs with Celery + Redis support for distributed mode.
#>
[CmdletBinding()]
param(
    [switch]$Celery,
    [switch]$Service,
    [string]$Python = "python",
    [switch]$Production,
    [string]$InstallDir = "C:\Program Files\ScriptManager",
    [string]$DataDir    = "C:\ProgramData\ScriptManager"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Check Python
# ---------------------------------------------------------------------------
Write-Step "Checking Python..."
try {
    $pyVersion = & $Python --version 2>&1
} catch {
    Fail "Python not found. Install Python 3.10+ from https://python.org and re-run."
}

# Reject Microsoft Store Python — venvs from it cannot be used by Windows services
$pyCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($pyCommand -and $pyCommand.Source -match "WindowsApps") {
    Fail "The 'python' command points to Microsoft Store Python. Install CPython from python.org or winget and re-run with -Python pointing to that python.exe."
}

if ($pyVersion -notmatch "Python (\d+)\.(\d+)") {
    Fail "Unexpected Python version string: $pyVersion"
}
$major = [int]$Matches[1]; $minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Fail "Python 3.10+ required, found $pyVersion."
}
Write-Host "    Found $pyVersion" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Determine install layout
# ---------------------------------------------------------------------------
if ($Production) {
    Write-Step "Production install mode"
    Write-Host "    Install dir : $InstallDir" -ForegroundColor Yellow
    Write-Host "    Data dir    : $DataDir"    -ForegroundColor Yellow
    $VenvPath = Join-Path $InstallDir ".venv"
} else {
    Write-Step "Development (editable) install mode"
    $VenvPath = Join-Path $RepoRoot ".venv"
}

# ---------------------------------------------------------------------------
# 3. Virtual environment
# ---------------------------------------------------------------------------
if (Test-Path $VenvPath) {
    Write-Step "Reusing existing virtual environment at $VenvPath"
} else {
    Write-Step "Creating virtual environment at $VenvPath"
    if ($Production) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    }
    & $Python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { Fail "venv creation failed." }
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Fail "Virtual environment is missing $VenvPython"
}

# ---------------------------------------------------------------------------
# 4. Install dependencies
# ---------------------------------------------------------------------------
Write-Step "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }

$extras = @()
if ($Celery)  { $extras += "celery" }
if ($Service) { $extras += "windows" }

if ($Production) {
    # Non-editable install from source directory (or could be 'scriptmgr' from PyPI)
    $installSpec = if ($extras.Count -gt 0) {
        "`"$RepoRoot[$($extras -join ',')]`""
    } else {
        "`"$RepoRoot`""
    }
    $displayMode = "production (non-editable)"
} else {
    $installSpec = if ($extras.Count -gt 0) {
        "-e `"$RepoRoot[$($extras -join ',')]`""
    } else {
        "-e `"$RepoRoot`""
    }
    $displayMode = "development (editable)"
}

$displayExtras = if ($extras.Count -gt 0) { $extras -join "," } else { "core only" }
Write-Step "Installing ScriptManager — $displayMode (extras: $displayExtras)..."
& $VenvPython -m pip install $installSpec.Split(" ")
if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }

# ---------------------------------------------------------------------------
# 5. .env file
# ---------------------------------------------------------------------------
if ($Production) {
    $EnvDest = Join-Path $DataDir ".env"
    $EnvExample = Join-Path $RepoRoot ".env.example"
    if (-not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    }
    if (-not (Test-Path $EnvDest)) {
        Write-Step "Creating .env in $DataDir"
        if (Test-Path $EnvExample) {
            Copy-Item $EnvExample $EnvDest
        } else {
            # Minimal production .env
            @"
SCRIPTMGR_DATA_DIR=$DataDir
SCRIPTMGR_HOST=127.0.0.1
SCRIPTMGR_PORT=8765
SCRIPTMGR_LOG_LEVEL=INFO
SCRIPTMGR_EXECUTOR_MODE=inproc
SCRIPTMGR_WORKER_CONCURRENCY=4
SCRIPTMGR_LOG_RETENTION_DAYS=30
"@ | Set-Content $EnvDest
        }
        # Ensure SCRIPTMGR_DATA_DIR is set (uncommented) in the production .env
        $envContent = Get-Content $EnvDest
        $envContent = $envContent -replace '^#?\s*SCRIPTMGR_DATA_DIR=.*', "SCRIPTMGR_DATA_DIR=$DataDir"
        if ($envContent -notmatch 'SCRIPTMGR_DATA_DIR=') {
            $envContent += "SCRIPTMGR_DATA_DIR=$DataDir"
        }
        $envContent | Set-Content $EnvDest
        Write-Host "    .env written to $EnvDest" -ForegroundColor Green
    } else {
        Write-Host "    .env already exists at $EnvDest — skipping" -ForegroundColor Yellow
    }
} else {
    $EnvFile    = Join-Path $RepoRoot ".env"
    $EnvExample = Join-Path $RepoRoot ".env.example"
    if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
        Write-Step "Creating .env from .env.example"
        Copy-Item $EnvExample $EnvFile
    }
}

# ---------------------------------------------------------------------------
# 6. Initialize DB
# ---------------------------------------------------------------------------
Write-Step "Initializing database..."
$env:SCRIPTMGR_DATA_DIR = if ($Production) { $DataDir } else { "" }
& $VenvPython -m scriptmgr.cli.main db init
if ($LASTEXITCODE -ne 0) {
    Write-Host "    DB init returned non-zero — OK if already initialized." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 7. Done
# ---------------------------------------------------------------------------
Write-Step "All set!"
Write-Host ""

if ($Production) {
    $ScriptMgrExe = Join-Path $VenvPath "Scripts\scriptmgr.exe"
    Write-Host "Production install complete." -ForegroundColor Green
    Write-Host ""
    Write-Host "Install dir : $InstallDir"    -ForegroundColor Yellow
    Write-Host "Data dir    : $DataDir"        -ForegroundColor Yellow
    Write-Host "CLI         : $ScriptMgrExe"   -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To start the server:" -ForegroundColor Yellow
    Write-Host "    & `"$ScriptMgrExe`" serve"
    Write-Host ""
    Write-Host "To install as a Windows service (run as Administrator):" -ForegroundColor Yellow
    Write-Host "    .\install-service.ps1 -VenvDir `"$VenvPath`" -DataDir `"$DataDir`""
    Write-Host ""
} else {
    Write-Host "Activate the environment:" -ForegroundColor Yellow
    Write-Host "    .\.venv\Scripts\Activate.ps1"
    Write-Host ""
    Write-Host "Then start the server:" -ForegroundColor Yellow
    Write-Host "    scriptmgr serve"
    Write-Host ""
    Write-Host "Open the UI:" -ForegroundColor Yellow
    Write-Host "    http://localhost:8765"
    Write-Host ""
}

if ($Celery) {
    Write-Host "You installed the [celery] extra. To use distributed mode:" -ForegroundColor Yellow
    Write-Host "    1. Install Redis (https://www.memurai.com on Windows)"
    Write-Host "    2. Set SCRIPTMGR_EXECUTOR_MODE=celery in .env"
    Write-Host "    3. Start a worker on each host: scriptmgr worker"
    Write-Host ""
}
if (-not $Production) {
    Write-Host "For Windows service installation, re-run with -Service flag:" -ForegroundColor Gray
    Write-Host "    .\bootstrap.ps1 -Service" -ForegroundColor Gray
    Write-Host "Then run as Administrator: .\install-service.ps1" -ForegroundColor Gray
}

