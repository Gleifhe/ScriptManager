<#
.SYNOPSIS
    Installs ScriptManager as a Windows Service that auto-starts on boot.
    Must be run as Administrator.

.DESCRIPTION
    Fully portable — works for both dev (editable) and production installs.
    All paths are derived from the parameters or the script's own location.

.PARAMETER ServiceName
    Name for the Windows service. Default: "ScriptManager"

.PARAMETER Port
    Port for the web UI / API. Default: 8765

.PARAMETER VenvDir
    Path to the virtual environment. 
    Default (dev mode): <script-dir>\.venv
    Override for production: e.g. "C:\Program Files\ScriptManager\.venv"

.PARAMETER DataDir
    Path where the database, logs, and .env are stored.
    Default (dev mode): <script-dir>\data
    Override for production: e.g. "C:\ProgramData\ScriptManager"

.EXAMPLE
    .\install-service.ps1
    Dev mode — venv and data inside the repo.

.EXAMPLE
    .\install-service.ps1 -VenvDir "C:\Program Files\ScriptManager\.venv" -DataDir "C:\ProgramData\ScriptManager"
    Production mode — installed via bootstrap.ps1 -Production.

.EXAMPLE
    .\install-service.ps1 -Port 9000 -ServiceName "ScriptManager-Prod"
#>
[CmdletBinding()]
param(
    [string]$ServiceName = "ScriptManager",
    [int]$Port           = 8765,
    [string]$VenvDir     = "",
    [string]$DataDir     = ""
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ─────────────────────────────────────────────────────────────
$RepoRoot  = $PSScriptRoot

# VenvDir: explicit param > dev default (<repo>\.venv)
if (-not $VenvDir) { $VenvDir = Join-Path $RepoRoot ".venv" }

# DataDir: explicit param > dev default (<repo>\data)
if (-not $DataDir) { $DataDir = Join-Path $RepoRoot "data" }

$Python  = Join-Path $VenvDir "Scripts\python.exe"
$LogDir  = Join-Path $DataDir "logs"
$AppArgs = "-m scriptmgr.cli.main serve --port $Port"

# AppDirectory: for a production install use DataDir (no source tree);
# for a dev install use RepoRoot so relative imports still work.
$AppDir = if (Test-Path (Join-Path $RepoRoot "pyproject.toml")) { $RepoRoot } else { $DataDir }

# ── Admin check ───────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Run this script as Administrator." -ForegroundColor Red
    Write-Host "       Right-click PowerShell → 'Run as Administrator', then try again."
    exit 1
}

# ── Check venv exists ─────────────────────────────────────────────────────────
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Virtual environment not found at: $VenvDir" -ForegroundColor Red
    Write-Host "       Run .\bootstrap.ps1 (or .\bootstrap.ps1 -Production) first."
    exit 1
}

# ── Find NSSM ─────────────────────────────────────────────────────────────────
$NssmPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $NssmPath) {
    $wingetBase = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $nssmExe = Get-ChildItem -Path $wingetBase -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } |
        Select-Object -First 1
    if ($nssmExe) { $NssmPath = $nssmExe.FullName }
}
if (-not $NssmPath) {
    Write-Host "ERROR: nssm.exe not found on PATH." -ForegroundColor Red
    Write-Host "       Install it: winget install NSSM.NSSM"
    Write-Host "       Or download from https://nssm.cc/download and add to PATH."
    exit 1
}

Write-Host "Using NSSM  : $NssmPath"   -ForegroundColor Cyan
Write-Host "Python      : $Python"      -ForegroundColor Cyan
Write-Host "AppDirectory: $AppDir"      -ForegroundColor Cyan
Write-Host "Data dir    : $DataDir"     -ForegroundColor Cyan
Write-Host "Log dir     : $LogDir"      -ForegroundColor Cyan

# ── Ensure log dir exists ─────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ── Remove existing service ───────────────────────────────────────────────────
$existing = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service '$ServiceName'..." -ForegroundColor Yellow
    & $NssmPath stop $ServiceName 2>$null | Out-Null
    Start-Sleep 2
    & $NssmPath remove $ServiceName confirm | Out-Null
    Start-Sleep 2
}

# ── Install ───────────────────────────────────────────────────────────────────
Write-Host "Installing service '$ServiceName'..." -ForegroundColor Cyan
& $NssmPath install  $ServiceName $Python $AppArgs
& $NssmPath set      $ServiceName AppDirectory       $AppDir
& $NssmPath set      $ServiceName DisplayName        "ScriptManager Orchestration Service"
& $NssmPath set      $ServiceName Description        "Manages and schedules Python/PowerShell/Batch/Go scripts. UI at http://localhost:$Port"
& $NssmPath set      $ServiceName Start              SERVICE_AUTO_START
& $NssmPath set      $ServiceName AppStdout          "$LogDir\service-stdout.log"
& $NssmPath set      $ServiceName AppStderr          "$LogDir\service-stderr.log"
& $NssmPath set      $ServiceName AppRotateFiles     1
& $NssmPath set      $ServiceName AppRotateBytes     10485760
& $NssmPath set      $ServiceName AppRestartDelay    5000
# Pass the data directory to the service process so it finds the DB and .env
& $NssmPath set      $ServiceName AppEnvironmentExtra "SCRIPTMGR_DATA_DIR=$DataDir"

# ── Start ─────────────────────────────────────────────────────────────────────
Write-Host "Starting service..." -ForegroundColor Cyan
& $NssmPath start $ServiceName
Start-Sleep 5

$svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "SUCCESS — $ServiceName is running!" -ForegroundColor Green
    Write-Host "  Status  : $($svc.Status)"
    Write-Host "  UI      : http://localhost:$Port"
    Write-Host "  Data    : $DataDir"
    Write-Host "  Logs    : $LogDir"
    Write-Host ""
    Write-Host "Management commands:" -ForegroundColor Yellow
    Write-Host "  Stop    : Stop-Service $ServiceName"
    Write-Host "  Start   : Start-Service $ServiceName"
    Write-Host "  Restart : .\restart-service.ps1   (as Administrator)"
    Write-Host "  Remove  : & '$NssmPath' remove $ServiceName confirm"
} else {
    $status = if ($svc) { $svc.Status } else { "not found" }
    Write-Host "Service status: $status" -ForegroundColor Red
    Write-Host "Check logs: $LogDir\service-stderr.log"
    exit 1
}

