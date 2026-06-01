# restart-service.ps1
# Run as Administrator to restart the ScriptManager Windows service
# This picks up all code changes from d:\repos\Test

param(
    [switch]$Stop,
    [switch]$Start
)

$SvcName = "ScriptManager"

function Check-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = [System.Security.Principal.WindowsPrincipal]$id
    return $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Check-Admin)) {
    Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "Right-click PowerShell -> 'Run as Administrator', then run this script again."
    exit 1
}

if ($Stop) {
    Stop-Service $SvcName -Force
    Write-Host "Service stopped." -ForegroundColor Yellow
    exit 0
}

if ($Start) {
    Start-Service $SvcName
    Write-Host "Service started." -ForegroundColor Green
    exit 0
}

# Default: restart
Write-Host "Restarting $SvcName..." -ForegroundColor Cyan
Restart-Service $SvcName -Force
Start-Sleep 5
$status = (Get-Service $SvcName).Status
Write-Host "Service status: $status" -ForegroundColor $(if ($status -eq 'Running') { 'Green' } else { 'Red' })

# Quick verify
try {
    $r = [System.Net.WebRequest]::Create("http://localhost:8765/")
    $r.Timeout = 5000
    $resp = $r.GetResponse()
    Write-Host "Web server responding: HTTP $([int]$resp.StatusCode)" -ForegroundColor Green
    $resp.Close()
} catch {
    Write-Host "Web server not yet responding - wait a few seconds and try http://localhost:8765" -ForegroundColor Yellow
}
