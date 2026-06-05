# Installation Guide

ScriptManager supports two install modes:

| Mode | Use when | Data location |
|------|----------|---------------|
| **Development** (default) | You want to edit the source, or just run it on your workstation | Inside the repo (`data/`) |
| **Production** | Dedicated machine, clean separation of app code and runtime data | `C:\Program Files\ScriptManager` + `C:\ProgramData\ScriptManager` |

---

## Prerequisites

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **NSSM** *(optional — only for Windows service installation)* — `winget install NSSM.NSSM`
- **Redis / Memurai** *(optional — only for multi-machine distributed mode)* — [memurai.com](https://www.memurai.com/)

---

## Option 1 — Development / Workstation Install

This is the simplest path. Source code and data live together in the cloned repo.

```powershell
# 1. Clone
git clone https://github.com/Gleifhe/ScriptManager.git
cd ScriptManager

# 2. One-click install (creates .venv, installs deps, copies .env, inits DB)
.\bootstrap.ps1

# 3. Start the server
.\.venv\Scripts\scriptmgr.exe serve
```

Open the dashboard: **http://localhost:8765**

### Optional flags

```powershell
# Also install pywin32 (needed for 'scriptmgr service install')
.\bootstrap.ps1 -Service

# Also install Celery + Redis client (distributed mode)
.\bootstrap.ps1 -Celery

# Use a specific Python interpreter
.\bootstrap.ps1 -Python "C:\Python312\python.exe"
```

### Install as a Windows Service (dev mode)

Run as **Administrator**:

```powershell
.\install-service.ps1
```

The service auto-starts on boot, restarts on failure, and writes logs to `data\logs\`.

---

## Option 2 — Production Install

The package is installed into a dedicated directory. Source code, venv, and data are all in separate locations — nothing lives inside the git repo at runtime.

**Default layout:**

```
C:\Program Files\ScriptManager\   ← venv lives here
C:\ProgramData\ScriptManager\     ← database, logs, .env live here
```

### Step 1: Install

Run from the cloned source directory:

```powershell
.\bootstrap.ps1 -Production
```

Or with custom paths:

```powershell
.\bootstrap.ps1 -Production `
    -InstallDir "D:\Apps\ScriptManager" `
    -DataDir    "D:\ScriptManagerData"
```

This will:
- Create a venv at `<InstallDir>\.venv`
- Run a non-editable `pip install` (clean package, no source dependency)
- Create `<DataDir>\.env` with `SCRIPTMGR_DATA_DIR` set
- Initialise the SQLite database at `<DataDir>\scriptmgr.db`

### Step 2: Configure

Edit `<DataDir>\.env` (e.g. `C:\ProgramData\ScriptManager\.env`):

```env
SCRIPTMGR_DATA_DIR=C:\ProgramData\ScriptManager
SCRIPTMGR_HOST=127.0.0.1
SCRIPTMGR_PORT=8765
SCRIPTMGR_LOG_LEVEL=INFO
SCRIPTMGR_LOG_RETENTION_DAYS=30
```

### Step 3: Install as a Windows Service

Run as **Administrator**:

```powershell
.\install-service.ps1 `
    -VenvDir "C:\Program Files\ScriptManager\.venv" `
    -DataDir "C:\ProgramData\ScriptManager"
```

Or with custom paths:

```powershell
.\install-service.ps1 `
    -VenvDir    "D:\Apps\ScriptManager\.venv" `
    -DataDir    "D:\ScriptManagerData" `
    -ServiceName "ScriptManager" `
    -Port        8765
```

The service will:
- Start automatically on boot
- Restart on failure (5 second delay)
- Write stdout/stderr to `<DataDir>\logs\service-stdout.log` / `service-stderr.log`
- Rotate logs at 10 MB

### Step 4: Verify

```powershell
Get-Service ScriptManager
# Status should be: Running

# Open the dashboard
Start-Process "http://localhost:8765"
```

---

## Manual Install (any platform)

```powershell
# 1. Clone
git clone https://github.com/Gleifhe/ScriptManager.git
cd ScriptManager

# 2. Create and activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows
# source .venv/bin/activate        # Linux/macOS

# 3. Install
pip install -e .

# 4. Configure
Copy-Item .env.example .env
# Edit .env as needed

# 5. Init database
scriptmgr db init

# 6. Start
scriptmgr serve
```

---

## Distributed Mode (Multi-Host)

Only needed if you want workers running on separate machines.

```powershell
# Install with Celery support
.\bootstrap.ps1 -Celery

# Set in .env:
SCRIPTMGR_EXECUTOR_MODE=celery
SCRIPTMGR_BROKER_URL=redis://your-redis-host:6379/0
SCRIPTMGR_RESULT_BACKEND=redis://your-redis-host:6379/1

# Start the API server (includes scheduler)
scriptmgr serve

# Start a worker on each machine
scriptmgr worker
```

Install Redis / [Memurai](https://www.memurai.com/) (Windows Redis) separately.

---

## Configuration Reference

All settings use the `SCRIPTMGR_` prefix and can be set in `.env` or as environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRIPTMGR_DATA_DIR` | Auto-detected | Where DB, logs, artifacts are stored |
| `SCRIPTMGR_DB_URL` | `sqlite:///<data_dir>/scriptmgr.db` | SQLAlchemy database URL |
| `SCRIPTMGR_HOST` | `127.0.0.1` | Server bind address |
| `SCRIPTMGR_PORT` | `8765` | Server port |
| `SCRIPTMGR_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |
| `SCRIPTMGR_EXECUTOR_MODE` | `inproc` | `inproc` (default) or `celery` |
| `SCRIPTMGR_WORKER_CONCURRENCY` | `4` | Number of concurrent script runner threads |
| `SCRIPTMGR_LOG_RETENTION_DAYS` | `30` | Days before old run logs are auto-purged |
| `SCRIPTMGR_SMTP_HOST` | *(blank)* | SMTP host for email alerts |
| `SCRIPTMGR_SMTP_PORT` | `587` | SMTP port |
| `SCRIPTMGR_SMTP_USER` | *(blank)* | SMTP username |
| `SCRIPTMGR_SMTP_PASSWORD` | *(blank)* | SMTP password |
| `SCRIPTMGR_TEAMS_WEBHOOK` | *(blank)* | Microsoft Teams webhook URL |
| `SCRIPTMGR_SLACK_WEBHOOK` | *(blank)* | Slack webhook URL |
| `SCRIPTMGR_BROKER_URL` | `redis://localhost:6379/0` | Celery broker (distributed mode only) |
| `SCRIPTMGR_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend (distributed mode only) |

---

## Data Directory Layout

```
<DataDir>\
    scriptmgr.db          ← main SQLite database (runs, scripts, schedules, logs)
    apscheduler.db        ← APScheduler job store (separate to avoid lock contention)
    .env                  ← configuration (production installs)
    logs\
        service-stdout.log
        service-stderr.log
    runs\                 ← reserved for future run artifacts
    artifacts\            ← reserved for script output files
```

---

## Troubleshooting

**Service won't start**
Check `<DataDir>\logs\service-stderr.log` for Python tracebacks.

**Port already in use**
Change `SCRIPTMGR_PORT` in `.env` and re-run `install-service.ps1 -Port <new-port>`.

**Database locked errors**
ScriptManager uses SQLite WAL mode which handles concurrent access. If you still see lock errors, check that only one instance is running.

**Templates not found (TemplateNotFound error)**
Run `pip install -e .` (dev) or `pip install . --upgrade` (production) to ensure templates are installed.

**Access denied stopping/restarting the service**
The service was installed by Administrator — management commands also require Administrator.
Right-click PowerShell → "Run as Administrator".
