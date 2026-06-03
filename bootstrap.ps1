<#
.SYNOPSIS
    One-click installer for ScriptManager (workstation / inproc mode).

.DESCRIPTION
    - Verifies Python 3.10+ is available.
    - Creates a local virtual environment in .venv\
    - Installs ScriptManager in editable mode (core deps only - no Celery/Redis).
    - Initializes the SQLite database.
    - Prints next-step instructions.

    For distributed mode (multiple worker hosts), pass -Celery to also install
    celery + redis. You'll still need to install Redis/Memurai separately.

.PARAMETER Celery
    Install the optional celery extra (celery + redis). Required only for
    distributed/multi-host deployments.

.PARAMETER Service
    Also install pywin32 (the [windows] extra) needed for the Windows service
    installer (scriptmgr service install). Not required for plain workstation use.

.PARAMETER Python
    Path to the Python interpreter to use. Defaults to "python".

.EXAMPLE
    .\bootstrap.ps1
    Installs in workstation (inproc) mode. Sufficient for a single PC.

.EXAMPLE
    .\bootstrap.ps1 -Celery
    Installs with Celery + Redis support for distributed mode.
#>
[CmdletBinding()]
param(
    [switch]$Celery,
    [switch]$Service,
    [string]$Python = "python"
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

if ($pyVersion -notmatch "Python (\d+)\.(\d+)") {
    Fail "Unexpected Python version string: $pyVersion"
}
$major = [int]$Matches[1]; $minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Fail "Python 3.10+ required, found $pyVersion."
}
Write-Host "    Found $pyVersion" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
$VenvPath = Join-Path $RepoRoot ".venv"
if (Test-Path $VenvPath) {
    Write-Step "Reusing existing virtual environment at .venv\"
} else {
    Write-Step "Creating virtual environment at .venv\"
    & $Python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { Fail "venv creation failed." }
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Fail "Virtual environment is missing $VenvPython"
}

# ---------------------------------------------------------------------------
# 3. Install dependencies
# ---------------------------------------------------------------------------
Write-Step "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }

$extras = @()
if ($Celery)  { $extras += "celery" }
if ($Service) { $extras += "windows" }  # pywin32 — only needed for Windows service installer

$installSpec = if ($extras.Count -gt 0) { "-e `".[$($extras -join ',')]`"" } else { "-e ." }
$displayExtras = if ($extras.Count -gt 0) { $extras -join "," } else { "core only" }

Write-Step "Installing ScriptManager (extras: $displayExtras)..."
Push-Location $RepoRoot
try {
    $cmd = "& `$VenvPython -m pip install $installSpec"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 4. .env file
# ---------------------------------------------------------------------------
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Write-Step "Creating .env from .env.example"
    Copy-Item $EnvExample $EnvFile
}

# ---------------------------------------------------------------------------
# 5. Initialize DB
# ---------------------------------------------------------------------------
Write-Step "Initializing database..."
& $VenvPython -m scriptmgr.cli.main db init
if ($LASTEXITCODE -ne 0) {
    Write-Host "    DB init returned non-zero - this is OK if already initialized." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 6. Done
# ---------------------------------------------------------------------------
Write-Step "All set!"
Write-Host ""
Write-Host "Activate the environment:" -ForegroundColor Yellow
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Then start the server (inproc mode - no separate worker needed):" -ForegroundColor Yellow
Write-Host "    scriptmgr serve"
Write-Host ""
Write-Host "Open the UI:" -ForegroundColor Yellow
Write-Host "    http://localhost:8765"
Write-Host ""
if ($Celery) {
    Write-Host "You installed the [celery] extra. To use distributed mode:" -ForegroundColor Yellow
    Write-Host "    1. Install Redis (https://www.memurai.com on Windows)"
    Write-Host "    2. Set SCRIPTMGR_EXECUTOR_MODE=celery in .env"
    Write-Host "    3. Start a worker on each host: scriptmgr worker"
    Write-Host ""
}
Write-Host "For Windows service installation, re-run with -Service flag:" -ForegroundColor Gray
Write-Host "    .\bootstrap.ps1 -Service" -ForegroundColor Gray
Write-Host "Then run as Administrator: .\install-service.ps1" -ForegroundColor Gray
