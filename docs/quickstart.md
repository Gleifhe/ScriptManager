# Quick Start Guide

## Prerequisites

- Python 3.10+
- *(Optional)* NSSM for Windows service features: https://nssm.cc — install via `winget install NSSM.NSSM`
- *(Optional)* Redis — only required for **distributed/multi-host** mode. Use [Memurai](https://www.memurai.com/) on Windows.

---

## One-Click Install (Recommended)

Open PowerShell **in the folder where you cloned ScriptManager** and run:

```powershell
.\bootstrap.ps1
```

This creates `.venv\`, installs all dependencies, copies `.env.example` → `.env`, and initialises the database. **No Redis needed** for single-machine use.

Then start the server:

```powershell
.\.venv\Scripts\scriptmgr.exe serve
```

Open the dashboard: **http://localhost:8765**

---

## Manual Install

```powershell
# 1. Clone (or unzip) ScriptManager to any folder, then cd into it
cd <your-install-dir>

# 2. Create virtual environment and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3. Configure (defaults work out of the box)
Copy-Item .env.example .env

# 4. Initialise the database
scriptmgr db init

# 5. Start the server
scriptmgr serve
```

---

## Register Your First Script

```powershell
# Create a group
scriptmgr group add "AI Workflows" --description "My AI pipeline scripts"

# Register a script (group ID from step above — usually 1)
scriptmgr script add .\samples\hello.py --group 1 --name hello --description "Demo script"

# Run it immediately
scriptmgr script run hello --watch
```

## Schedule It (cron — every hour)

```powershell
scriptmgr schedule add --type cron --expr "0 * * * *" --script 1
scriptmgr schedule list
```

## Schedule Continuous Re-run (restart 10s after finish)

```powershell
scriptmgr schedule add --type continuous --expr "10" --script 1
```

## Create a DAG Workflow

Use the visual **Workflow Builder** in the web UI (`/workflows`), or load a JSON definition:

```powershell
scriptmgr workflow add .\samples\sample_workflow.json --group 1 --name "My Pipeline"
scriptmgr workflow run 1
```

## View Run History and Logs

```powershell
scriptmgr run list
scriptmgr run logs 1
```

---

## Install as a Windows Service (Always-On Orchestrator)

Run as **Administrator**:

```powershell
.\install-service.ps1
```

Works from any install directory — all paths are self-relative.

Logs: `data\logs\service-stdout.log` and `data\logs\service-stderr.log`

---

## Distributed Mode (Multi-Host, Optional)

Only needed if you want workers on separate machines:

```powershell
# Install with Celery support
.\bootstrap.ps1 -Celery

# Set in .env:
# SCRIPTMGR_EXECUTOR_MODE=celery
# SCRIPTMGR_BROKER_URL=redis://your-redis-host:6379/0

# Start a worker on each host
scriptmgr worker
```

---

## Notifications

Edit `.env`:

```
SCRIPTMGR_SMTP_HOST=smtp.yourcompany.com
SCRIPTMGR_SMTP_USER=you@company.com
SCRIPTMGR_SMTP_PASSWORD=...
SCRIPTMGR_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...
SCRIPTMGR_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

Notifications fire automatically on failed/timed-out runs.

---

## Running Tests

```powershell
pip install -e .[dev]
pytest tests/ -v
```


## 2. Configure

```powershell
Copy-Item .env.example .env
# Edit .env — at minimum set your Redis URL if not on default localhost:6379
notepad .env
```

## 3. Initialise the database

```powershell
scriptmgr db init
```

## 4. Start Redis, then the API + scheduler

```powershell
# Terminal 1 — API server (includes scheduler)
scriptmgr serve

# Terminal 2 — Celery worker
scriptmgr worker
```

Open the dashboard: http://localhost:8765

API docs: http://localhost:8765/api/docs

---

## 5. Register your first script

```powershell
# Create a group
scriptmgr group add "AI Workflows" --description "My AI pipeline scripts"

# Register a script (group ID from step above — usually 1)
scriptmgr script add .\samples\hello.py --group 1 --name hello --description "Demo script"

# Run it immediately
scriptmgr script run hello --watch
```

## 6. Schedule it (cron — every hour)

```powershell
scriptmgr schedule add --type cron --expr "0 * * * *" --script 1
scriptmgr schedule list
```

## 7. Schedule continuous re-run (restart 10s after finish)

```powershell
scriptmgr schedule add --type continuous --expr "10" --script 1
```

## 8. Create a DAG workflow

Edit `samples/sample_workflow.json` to use your real script IDs, then:

```powershell
scriptmgr workflow add .\samples\sample_workflow.json --group 1 --name "My Pipeline"
scriptmgr workflow run 1
```

## 9. View run history and logs

```powershell
scriptmgr run list
scriptmgr run logs 1
```

---

## Install as a Windows Service (always-on orchestrator)

Run as **Administrator**:

```powershell
scriptmgr service install
scriptmgr service start
```

Logs: `data\logs\service-stdout.log`

---

## Wrap a script as an always-on Windows service

```powershell
scriptmgr always-on install my-watcher `
  --script .\watchers\my_watcher.py `
  --heartbeat 30 `
  --output-dir .\services

# Then run as Administrator:
pwsh .\services\install_my-watcher.ps1
```

The service auto-restarts on failure and sends a heartbeat every 30 seconds to
`/api/services/heartbeat` so you can monitor it in the dashboard.

---

## Notifications

Edit `.env`:

```
SCRIPTMGR_SMTP_HOST=smtp.yourcompany.com
SCRIPTMGR_SMTP_USER=you@company.com
SCRIPTMGR_SMTP_PASSWORD=...
SCRIPTMGR_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...
SCRIPTMGR_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

Notifications fire automatically on failed/timed-out runs.

---

## Running Tests

```powershell
pip install -e .[dev]
pytest tests/ -v
```
