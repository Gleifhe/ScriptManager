# Quick Start Guide

## Prerequisites

- Python 3.10+
- Redis (broker + result backend)
  - Windows: use [Memurai](https://www.memurai.com/) (Redis-compatible), or `docker run -d -p 6379:6379 redis:7`
- NSSM (for Windows service features): https://nssm.cc

---

## 1. Install

```powershell
cd d:\repos\Test
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
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
