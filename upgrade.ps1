<#
.SYNOPSIS
    Upgrades an existing ScriptManager installation to the latest version.

.DESCRIPTION
    Handles both dev (editable) and production installs:
      1. Optionally pulls latest source from git
      2. Upgrades the Python package in-place
      3. Runs any pending Alembic database migrations
      4. Restarts the Windows service (if installed)
      5. Verifies the service came back healthy

    Safe to run repeatedly — all steps are idempotent.

.PARAMETER Production
    Use the production install layout.
    Venv at -InstallDir\.venv, data at -DataDir.

.PARAMETER InstallDir
    Root directory of the production venv.
    Default: C:\Program Files\ScriptManager

.PARAMETER DataDir
    Directory containing the database and .env.
    Default: C:\ProgramData\ScriptManager

.PARAMETER ServiceName
    Windows service name to restart. Default: "ScriptManager"

.PARAMETER SkipGitPull
    Skip the 'git pull' step (useful if you manage source separately
    or the repo is on a different machine).

.PARAMETER SkipServiceRestart
    Upgrade the package and DB but do NOT restart the service.
    Useful when you want to restart at a specific maintenance window.

.PARAMETER SkipMigrations
    Skip Alembic migration step.

.EXAMPLE
    .\upgrade.ps1
    Dev mode upgrade: git pull, pip install -e ., migrate, restart service.

.EXAMPLE
    .\upgrade.ps1 -Production
    Production upgrade using default dirs (C:\Program Files & C:\ProgramData).

.EXAMPLE
    .\upgrade.ps1 -Production -InstallDir "D:\Apps\ScriptMgr" -DataDir "D:\ScriptMgrData"
    Production upgrade with custom directories.

.EXAMPLE
    .\upgrade.ps1 -SkipGitPull -SkipServiceRestart
    Just reinstall the package and run migrations — no git, no service bounce.
#>
[CmdletBinding()]
param(
    [switch]$Production,
    [string]$InstallDir        = "C:\Program Files\ScriptManager",
    [string]$DataDir           = "C:\ProgramData\ScriptManager",
    [string]$ServiceName       = "ScriptManager",
    [switch]$SkipGitPull,
    [switch]$SkipServiceRestart,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}
function Write-OK($msg)   { Write-Host "    OK: $msg"    -ForegroundColor Green  }
function Write-Warn($msg) { Write-Host "    WARN: $msg"  -ForegroundColor Yellow }
function Fail($msg)       { Write-Host "ERROR: $msg"     -ForegroundColor Red; exit 1 }

# ── Resolve layout ────────────────────────────────────────────────────────────
if ($Production) {
    $VenvDir = Join-Path $InstallDir ".venv"
    Write-Host "Mode       : Production" -ForegroundColor Magenta
    Write-Host "Install dir: $InstallDir"
    Write-Host "Data dir   : $DataDir"
} else {
    $VenvDir = Join-Path $RepoRoot ".venv"
    $DataDir = Join-Path $RepoRoot "data"
    Write-Host "Mode       : Development (editable)" -ForegroundColor Magenta
    Write-Host "Repo root  : $RepoRoot"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Fail "Virtual environment not found at $VenvDir.`nRun .\bootstrap.ps1$(if ($Production){' -Production'}) first."
}
Write-Host "Python     : $VenvPython"

# ── Step 1: git pull ──────────────────────────────────────────────────────────
if ($SkipGitPull) {
    Write-Step "Skipping git pull (-SkipGitPull)"
} else {
    Write-Step "Pulling latest source..."
    $gitExe = (Get-Command git -ErrorAction SilentlyContinue).Source
    if (-not $gitExe) {
        Write-Warn "git not found on PATH — skipping git pull. Install git or use -SkipGitPull."
    } else {
        $isGitRepo = Test-Path (Join-Path $RepoRoot ".git")
        if (-not $isGitRepo) {
            Write-Warn "$RepoRoot is not a git repository — skipping git pull."
        } else {
            Push-Location $RepoRoot
            try {
                $before = & git rev-parse HEAD 2>&1
                & git pull --ff-only
                if ($LASTEXITCODE -ne 0) { Fail "git pull failed. Resolve conflicts manually then re-run." }
                $after = & git rev-parse HEAD 2>&1
                if ($before -eq $after) {
                    Write-OK "Already up to date ($($after.Substring(0,8)))"
                } else {
                    Write-OK "Updated $($before.Substring(0,8)) → $($after.Substring(0,8))"
                }
            } finally {
                Pop-Location
            }
        }
    }
}

# ── Step 2: Stop service before upgrade ───────────────────────────────────────
$serviceExists = $null -ne (Get-Service $ServiceName -ErrorAction SilentlyContinue)
$wasRunning    = $false

if ($serviceExists -and -not $SkipServiceRestart) {
    $svc = Get-Service $ServiceName
    if ($svc.Status -eq "Running") {
        Write-Step "Stopping service '$ServiceName' for upgrade..."
        try {
            Stop-Service $ServiceName -Force
            Start-Sleep 3
            Write-OK "Service stopped"
            $wasRunning = $true
        } catch {
            Write-Warn "Could not stop service (may need Administrator). Upgrading while running — some files may be locked."
        }
    }
}

# ── Step 3: pip upgrade ───────────────────────────────────────────────────────
Write-Step "Upgrading Python package..."
& $VenvPython -m pip install --upgrade pip --quiet

if ($Production) {
    # Non-editable: reinstall from source tree
    & $VenvPython -m pip install "$RepoRoot" --upgrade
} else {
    # Editable: re-sync dependencies (code is already live via editable link)
    & $VenvPython -m pip install -e "$RepoRoot" --upgrade
}

if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
Write-OK "Package upgraded"

# Show installed version
$ver = & $VenvPython -c "import importlib.metadata; print(importlib.metadata.version('scriptmgr'))" 2>&1
Write-OK "Installed version: $ver"

# ── Step 4: Database migrations ───────────────────────────────────────────────
if ($SkipMigrations) {
    Write-Step "Skipping database migrations (-SkipMigrations)"
} else {
    Write-Step "Running database migrations..."

    # Set data dir env var so alembic/config.py finds the right DB
    $env:SCRIPTMGR_DATA_DIR = $DataDir

    # Try alembic upgrade head first (if migrations exist)
    $alembicResult = & $VenvPython -m alembic -c "$RepoRoot\alembic.ini" upgrade head 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Migrations applied"
    } else {
        # Fallback: init_db (create_all) for installs without migration files yet
        Write-Warn "Alembic returned non-zero — falling back to db init (create_all):"
        Write-Host "    $alembicResult" -ForegroundColor DarkGray
        & $VenvPython -m scriptmgr.cli.main db init
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "db init also failed — database may already be current. Check logs."
        } else {
            Write-OK "DB schema verified via create_all"
        }
    }
}

# ── Step 5: Restart service ───────────────────────────────────────────────────
if ($SkipServiceRestart) {
    Write-Step "Skipping service restart (-SkipServiceRestart)"
    if ($serviceExists) {
        Write-Warn "Remember to manually restart '$ServiceName' to apply the upgrade."
    }
} elseif (-not $serviceExists) {
    Write-Step "Service '$ServiceName' is not installed — skipping restart"
    Write-Host "    Start manually: & `"$VenvPython`" -m scriptmgr.cli.main serve" -ForegroundColor Yellow
} else {
    if ($wasRunning) {
        Write-Step "Starting service '$ServiceName'..."
        try {
            Start-Service $ServiceName
            Start-Sleep 5
            $svc = Get-Service $ServiceName
            if ($svc.Status -eq "Running") {
                Write-OK "Service is running"
            } else {
                Fail "Service failed to start (status: $($svc.Status)). Check logs in $DataDir\logs\"
            }
        } catch {
            Fail "Could not start service — run as Administrator or start manually: Start-Service $ServiceName"
        }
    } else {
        Write-Step "Service '$ServiceName' was not running — leaving it stopped"
    }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  ScriptManager upgrade complete!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Version : $ver"
if ($serviceExists -and -not $SkipServiceRestart -and $wasRunning) {
    $port = 8765
    # Try to read port from .env
    $envFile = Join-Path $DataDir ".env"
    if (-not (Test-Path $envFile)) { $envFile = Join-Path $RepoRoot ".env" }
    if (Test-Path $envFile) {
        $portLine = Get-Content $envFile | Where-Object { $_ -match "SCRIPTMGR_PORT\s*=" } | Select-Object -First 1
        if ($portLine -match "=\s*(\d+)") { $port = $Matches[1] }
    }
    Write-Host "  UI      : http://localhost:$port" -ForegroundColor Cyan
}
Write-Host "  Data    : $DataDir"
Write-Host ""
