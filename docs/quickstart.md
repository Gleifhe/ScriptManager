# Quick Start Guide

## Prerequisites

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **NSSM** *(optional — only for Windows service installation)* — `winget install NSSM.NSSM`
- **Redis / Memurai** *(optional — only for distributed/multi-host mode)* — [memurai.com](https://www.memurai.com/)

---

## One-Click Install (Recommended)

Open PowerShell in the folder where you cloned ScriptManager:

```powershell
.\bootstrap.ps1
```

Then start the server:

```powershell
.\.venv\Scripts\scriptmgr.exe serve
```

Open the dashboard: **http://localhost:8765**

> No Redis required. Default `inproc` mode runs everything in a single process.

For full installation options (production install, custom directories, Windows service):
→ **[docs/installation.md](installation.md)**

---

## Register Your First Script

```powershell
# Create a group
scriptmgr group add "AI Workflows" --description "My AI pipeline scripts"

# Register a script (group ID 1 from above)
scriptmgr script add .\samples\hello.py --group 1 --name hello

# Run it and watch the output
scriptmgr script run hello --watch
```

---

## Schedule a Script

```powershell
# Every hour (cron)
scriptmgr schedule add --type cron --expr "0 * * * *" --script 1

# Every 5 minutes (interval)
scriptmgr schedule add --type interval --expr "300" --script 1

# Continuous — restart 10 seconds after it finishes
scriptmgr schedule add --type continuous --expr "10" --script 1

# View schedules
scriptmgr schedule list
```

---

## Create a Workflow (DAG)

Use the visual **Workflow Builder** in the web UI at `/workflows`, or load a JSON file:

```powershell
scriptmgr workflow add .\samples\sample_workflow.json --group 1 --name "My Pipeline"
scriptmgr workflow run 1
```

---

## View Runs and Logs

```powershell
scriptmgr run list
scriptmgr run logs 1
```

Or open the **Runs** page in the dashboard for live log streaming.

---

## Install as a Windows Service

Run as **Administrator**:

```powershell
.\install-service.ps1
```

The service auto-starts on boot and restarts on failure.
Logs: `data\logs\service-stdout.log` and `data\logs\service-stderr.log`

→ **[Full installation guide](installation.md)**

---

## Upgrading

```powershell
.\upgrade.ps1
```

→ **[Full upgrade guide](upgrading.md)**

---

## Notifications

Edit `.env`:

```env
SCRIPTMGR_SMTP_HOST=smtp.yourcompany.com
SCRIPTMGR_SMTP_USER=you@company.com
SCRIPTMGR_SMTP_PASSWORD=...
SCRIPTMGR_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...
SCRIPTMGR_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

Notifications fire automatically on failed, timed-out, or cancelled runs.

---

## Distributed Mode (Multi-Host)

Only needed for workers on separate machines:

```powershell
# Install with Celery support
.\bootstrap.ps1 -Celery

# In .env:
SCRIPTMGR_EXECUTOR_MODE=celery
SCRIPTMGR_BROKER_URL=redis://your-redis-host:6379/0

# Start a worker on each machine
scriptmgr worker
```

---

## Running Tests

```powershell
pip install -e .[dev]
pytest tests/ -v
```
