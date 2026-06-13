<#
.SYNOPSIS
    Reset ScriptManager to a clean state for testing.

.DESCRIPTION
    Stops the ScriptManager Windows service (or any foreground process on port 8765),
    deletes all SQLite databases, run logs, artifacts, and APScheduler jobs, then
    re-initialises an empty database and optionally restarts the service.

.PARAMETER DataDir
    Path to the ScriptManager data directory.
    Defaults to .\data (the dev layout inside the repo).

.PARAMETER KeepScripts
    If set, preserves the scripts/groups/schedules/workflows rows — only wipes
    run history, logs, and the APScheduler job store.

.PARAMETER NoStart
    Skip restarting the service / server after the reset.

.EXAMPLE
    .\reset-db.ps1
    Full wipe and restart.

.EXAMPLE
    .\reset-db.ps1 -KeepScripts
    Clear run history only; keep all script definitions.

.EXAMPLE
    .\reset-db.ps1 -NoStart
    Wipe everything but do not restart (useful before running automated tests).
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$DataDir  = "",
    [switch]$KeepScripts,
    [switch]$NoStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot

# ── Resolve data directory ────────────────────────────────────────────────────
if (-not $DataDir) {
    $DataDir = Join-Path $RepoRoot "data"
}
if (-not (Test-Path $DataDir)) {
    Write-Host "Data directory not found: $DataDir" -ForegroundColor Yellow
    Write-Host "Nothing to reset." -ForegroundColor Yellow
    exit 0
}

$MainDb       = Join-Path $DataDir "scriptmgr.db"
$SchedulerDb  = Join-Path $DataDir "apscheduler.db"
$LogsDir      = Join-Path $DataDir "logs"
$RunsDir      = Join-Path $DataDir "runs"
$ArtifactsDir = Join-Path $DataDir "artifacts"

# ── Helper ────────────────────────────────────────────────────────────────────
function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Confirm-Action([string]$prompt) {
    $ans = Read-Host "$prompt [y/N]"
    return $ans -match '^[Yy]'
}

# ── Warn user ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ScriptManager Database Reset" -ForegroundColor Yellow
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
if ($KeepScripts) {
    Write-Host "  Mode : Run history + logs only (scripts/schedules kept)" -ForegroundColor White
} else {
    Write-Host "  Mode : FULL WIPE — all data will be deleted" -ForegroundColor Red
}
Write-Host "  DataDir : $DataDir" -ForegroundColor White
Write-Host ""

if (-not (Confirm-Action "  Proceed with reset?")) {
    Write-Host "Aborted." -ForegroundColor DarkGray
    exit 0
}

# ── Stop the service / server ─────────────────────────────────────────────────
Write-Step "Stopping ScriptManager..."

$svc = Get-Service -Name "ScriptManager" -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -in @("Running","Paused")) {
    Write-Host "    Stopping Windows service..."
    Stop-Service -Name "ScriptManager" -Force
    $svc.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(15))
    Write-Host "    Service stopped." -ForegroundColor Green
} else {
    # Kill any foreground process holding port 8765
    $conns = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
    if ($conns) {
        $conns | ForEach-Object {
            Write-Host "    Killing PID $($_.OwningProcess) on port 8765..."
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        Write-Host "    Foreground server stopped." -ForegroundColor Green
    } else {
        Write-Host "    No running instance found." -ForegroundColor DarkGray
    }
}

# ── Always wipe APScheduler job store ─────────────────────────────────────────
Write-Step "Removing APScheduler job store..."
if (Test-Path $SchedulerDb) {
    Remove-Item $SchedulerDb -Force
    Write-Host "    Deleted: $SchedulerDb" -ForegroundColor Green
} else {
    Write-Host "    Not found (already clean)." -ForegroundColor DarkGray
}

# ── Wipe logs and run artifacts ───────────────────────────────────────────────
Write-Step "Clearing logs and artifacts..."
foreach ($dir in @($LogsDir, $RunsDir, $ArtifactsDir)) {
    if (Test-Path $dir) {
        $files = Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue
        if ($files) {
            $files | Remove-Item -Force
            Write-Host "    Cleared: $dir ($($files.Count) file(s))" -ForegroundColor Green
        } else {
            Write-Host "    Already empty: $dir" -ForegroundColor DarkGray
        }
    }
}

# ── Database wipe ─────────────────────────────────────────────────────────────
if ($KeepScripts) {
    # Surgical: delete only run-related rows, leave scripts/groups/schedules/workflows
    Write-Step "Clearing run history (keeping script definitions)..."
    if (Test-Path $MainDb) {
        $venv    = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path $venv)) { $venv = "python" }
        & $venv -c @"
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute('DELETE FROM run_log')
cur.execute('DELETE FROM run')
cur.execute("UPDATE sqlite_sequence SET seq=0 WHERE name IN ('run','run_log')")
con.commit()
rows = cur.execute('SELECT changes()').fetchone()[0]
con.close()
print(f'    Deleted run rows. Auto-increment counters reset.')
"@ $MainDb
    } else {
        Write-Host "    Main DB not found — nothing to clear." -ForegroundColor DarkGray
    }
} else {
    # Full wipe: delete the whole main DB; init_db will recreate it on next start
    Write-Step "Deleting main database..."
    if (Test-Path $MainDb) {
        Remove-Item $MainDb -Force
        # Also delete WAL/SHM sidecar files if present
        Remove-Item "$MainDb-wal" -Force -ErrorAction SilentlyContinue
        Remove-Item "$MainDb-shm" -Force -ErrorAction SilentlyContinue
        Write-Host "    Deleted: $MainDb" -ForegroundColor Green
    } else {
        Write-Host "    Not found (already clean)." -ForegroundColor DarkGray
    }

    # Re-initialise an empty schema so the server starts without running migrations
    Write-Step "Initialising empty database schema..."
    $venv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venv) {
        & $venv -c "from scriptmgr.core.db import init_db; init_db(); print('    Database initialised.')"
    } else {
        Write-Host "    .venv not found — DB will be created on first server start." -ForegroundColor Yellow
    }
}

# ── Optionally restart ────────────────────────────────────────────────────────
if (-not $NoStart) {
    Write-Step "Restarting ScriptManager..."
    $svc = Get-Service -Name "ScriptManager" -ErrorAction SilentlyContinue
    if ($svc) {
        Start-Service -Name "ScriptManager"
        Write-Host "    Windows service started." -ForegroundColor Green
    } else {
        Write-Host "    (No Windows service — start manually with: .\.venv\Scripts\scriptmgr.exe serve)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Reset complete!" -ForegroundColor Green
Write-Host "  Open http://localhost:8765 to start fresh." -ForegroundColor Cyan
Write-Host ""
