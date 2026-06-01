<#
.SYNOPSIS
    Installs ScriptManager as a Windows Service that auto-starts on boot.
    Must be run as Administrator.
#>

$ErrorActionPreference = "Stop"

$NssmPath   = "C:\Users\glennle\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$Python     = "d:\repos\Test\.venv\Scripts\python.exe"
$Args       = "-m scriptmgr.cli.main serve"
$WorkDir    = "d:\repos\Test"
$LogDir     = "d:\repos\Test\data\logs"
$SvcName    = "ScriptManager"

# Check admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Run this script as Administrator." -ForegroundColor Red
    exit 1
}

# Find NSSM if path moved
if (-not (Test-Path $NssmPath)) {
    $NssmPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source
    if (-not $NssmPath) {
        Write-Host "ERROR: nssm.exe not found. Run: winget install NSSM.NSSM" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Using NSSM: $NssmPath" -ForegroundColor Cyan

# Remove existing service cleanly
$existing = Get-Service $SvcName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service..." -ForegroundColor Yellow
    & $NssmPath stop $SvcName | Out-Null
    & $NssmPath remove $SvcName confirm | Out-Null
    Start-Sleep 2
}

# Install
Write-Host "Installing service '$SvcName'..." -ForegroundColor Cyan
& $NssmPath install $SvcName $Python $Args
& $NssmPath set $SvcName AppDirectory $WorkDir
& $NssmPath set $SvcName DisplayName "ScriptManager Orchestration Service"
& $NssmPath set $SvcName Description "Manages and schedules Python/PowerShell/Batch/Go scripts. UI at http://localhost:8765"
& $NssmPath set $SvcName Start SERVICE_AUTO_START
& $NssmPath set $SvcName AppStdout "$LogDir\service-stdout.log"
& $NssmPath set $SvcName AppStderr "$LogDir\service-stderr.log"
& $NssmPath set $SvcName AppRotateFiles 1
& $NssmPath set $SvcName AppRotateBytes 10485760
& $NssmPath set $SvcName AppRestartDelay 5000   # restart 5s after crash

Write-Host "Starting service..." -ForegroundColor Cyan
& $NssmPath start $SvcName
Start-Sleep 5

$svc = Get-Service $SvcName -ErrorAction SilentlyContinue
if ($svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "SUCCESS - ScriptManager is running as a Windows Service!" -ForegroundColor Green
    Write-Host "  Status : $($svc.Status)"
    Write-Host "  UI     : http://localhost:8765"
    Write-Host "  Logs   : $LogDir\service-stdout.log"
    Write-Host ""
    Write-Host "Useful commands:" -ForegroundColor Yellow
    Write-Host "  Stop    : Stop-Service ScriptManager"
    Write-Host "  Start   : Start-Service ScriptManager"
    Write-Host "  Restart : Restart-Service ScriptManager"
    Write-Host "  Remove  : & '$NssmPath' remove ScriptManager confirm"
} else {
    Write-Host "Service status: $($svc.Status)" -ForegroundColor Red
    Write-Host "Check logs at: $LogDir\service-stderr.log"
}
