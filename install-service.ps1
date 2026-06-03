<#
.SYNOPSIS
    Installs ScriptManager as a Windows Service that auto-starts on boot.
    Must be run as Administrator.

.DESCRIPTION
    Fully portable — all paths are derived from the location of this script.
    Works from any install directory.

.PARAMETER ServiceName
    Name for the Windows service. Default: "ScriptManager"

.PARAMETER Port
    Port for the web UI / API. Default: 8765

.EXAMPLE
    .\install-service.ps1
    .\install-service.ps1 -Port 9000
    .\install-service.ps1 -ServiceName "ScriptManager-Dev" -Port 8766
#>
[CmdletBinding()]
param(
    [string]$ServiceName = "ScriptManager",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

# ── Resolve paths relative to this script's location ──────────────────────────
$RepoRoot  = $PSScriptRoot
$VenvDir   = Join-Path $RepoRoot ".venv"
$Python    = Join-Path $VenvDir "Scripts\python.exe"
$LogDir    = Join-Path $RepoRoot "data\logs"
$AppArgs   = "-m scriptmgr.cli.main serve --port $Port"

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
    Write-Host "       Run .\bootstrap.ps1 first to create it."
    exit 1
}

# ── Find NSSM ─────────────────────────────────────────────────────────────────
$NssmPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $NssmPath) {
    # Common WinGet install location (version-agnostic search)
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
Write-Host "Using NSSM : $NssmPath" -ForegroundColor Cyan
Write-Host "Repo root  : $RepoRoot" -ForegroundColor Cyan
Write-Host "Python     : $Python" -ForegroundColor Cyan

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
& $NssmPath set      $ServiceName AppDirectory       $RepoRoot
& $NssmPath set      $ServiceName DisplayName        "ScriptManager Orchestration Service"
& $NssmPath set      $ServiceName Description        "Manages and schedules Python/PowerShell/Batch/Go scripts. UI at http://localhost:$Port"
& $NssmPath set      $ServiceName Start              SERVICE_AUTO_START
& $NssmPath set      $ServiceName AppStdout          "$LogDir\service-stdout.log"
& $NssmPath set      $ServiceName AppStderr          "$LogDir\service-stderr.log"
& $NssmPath set      $ServiceName AppRotateFiles     1
& $NssmPath set      $ServiceName AppRotateBytes     10485760
& $NssmPath set      $ServiceName AppRestartDelay    5000

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


