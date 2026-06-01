# ScriptManager

A Python-based orchestration service for managing, scheduling, chaining, and monitoring AI/automation scripts on a Windows workstation — all from a web browser, with zero external dependencies in the default configuration.

[![GitHub](https://img.shields.io/badge/repo-Gleifhe%2FScriptManager-blue?logo=github)](https://github.com/Gleifhe/ScriptManager)

---

## What It Does

ScriptManager is your local control panel for Python (and PowerShell, Batch, Go, EXE) scripts. You register scripts once, then run them on-demand, on a schedule, as part of a pipeline, or as always-running Windows services — all with full live log streaming and run history.

---

## Features

| Category | Capability |
|---|---|
| **Organisation** | Groups/folders for scripts; per-script description, tags, env vars, venv, cwd |
| **Languages** | Auto-detects Python, PowerShell, Batch/CMD, Go, EXE from file extension |
| **Run modes** | One-shot, scheduled (cron/interval/date), continuous re-run, always-on service |
| **Workflows** | Visual DAG builder — chain scripts with `on success / on failure / always` conditions, per-step retry & timeout |
| **Live logs** | WebSocket streaming — watch script output in real time as it runs |
| **Dashboard** | Auto-refreshing overview (5s polling) — running count, queue, success rate, recent runs |
| **Reports** | 14-day activity chart, per-script success rate, avg duration, last status |
| **Alerts** | Email (SMTP), Microsoft Teams, Slack webhooks — fires on failure/timeout/cancel |
| **REST API** | Full JSON API with Swagger UI at `/docs` |
| **Web UI** | Dark-themed dashboard; live search on all pages |
| **Windows Service** | ScriptManager itself runs as a Windows Service (NSSM-backed, auto-starts on boot) |
| **Always-On** | Register long-running scripts as Windows Services with heartbeat monitoring |

---

## Architecture

```
Browser
  └── FastAPI (port 8765)
        ├── Web UI (Jinja2 templates)
        ├── REST API  (/api/...)
        ├── WebSocket (/ws/runs/{id}/logs)
        └── APScheduler (background thread)
              └── ThreadPoolExecutor → subprocess runner
                    └── SQLite (data/scriptmgr.db)
```

**Default mode (`inproc`):** Everything runs in a single Python process. No Redis, no Celery, no external services required.

**Optional distributed mode (`celery`):** Set `SCRIPTMGR_EXECUTOR_MODE=celery` + Redis for multi-machine/multi-worker setups.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| API / UI | **FastAPI** + Jinja2 | Async, type-safe, auto-docs |
| Scheduler | **APScheduler 3** (SQLAlchemy jobstore) | Pure Python, cron + interval + date + continuous |
| Workers | **ThreadPoolExecutor** (default) / **Celery** (optional) | No Redis needed for workstation use |
| Database | **SQLite** (Alembic-managed) | Zero-ops; schema migrations built-in |
| Executor host | **NSSM** | Reliable Windows service wrapping |
| CLI | **Typer** | Type-driven, ergonomic |

See [`docs/scheduler-review.md`](docs/scheduler-review.md) for the full best-in-breed comparison (ArcanaDev JAMS, Prefect, Airflow, Dagster, Rundeck, Temporal, etc.).

---

## Quick Start

```powershell
# 1. Clone and create virtualenv
git clone https://github.com/Gleifhe/ScriptManager.git
cd ScriptManager
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install (editable)
pip install -e .[dev]

# 3. Initialise the database
scriptmgr db init

# 4. Start the server
scriptmgr serve

# 5. Open the dashboard
start http://localhost:8765
```

> **No Redis required.** The default `inproc` mode runs everything in-process.

### Optional: run with auto-reload (development)
```powershell
scriptmgr serve --port 8766 --reload
```

---

## Install as a Windows Service (auto-start on boot)

```powershell
# Run as Administrator:
.\install-service.ps1

# Verify
Get-Service ScriptManager

# Restart after code changes (also as Administrator):
.\restart-service.ps1
```

The service runs on port 8765 and restarts automatically on failure or reboot.

---

## Wrap a Script as an Always-On Service

1. Register the script in the **Always-On** page of the UI
2. Install with NSSM (as Administrator):

```powershell
nssm install MyWatcherSvc "C:\scripts\my_watcher.py"
nssm set MyWatcherSvc AppRestartDelay 5000
nssm start MyWatcherSvc
```

3. Add heartbeat calls to your script:

```python
import requests, time
while True:
    requests.post("http://localhost:8765/api/services/heartbeat",
        json={"service_name": "MyWatcherSvc", "status": "running"})
    time.sleep(60)
    # ... your actual work
```

---

## Notifications

Configure in `.env` (copy from `.env.example`):

```env
# Email
SCRIPTMGR_SMTP_HOST=smtp.gmail.com
SCRIPTMGR_SMTP_PORT=587
SCRIPTMGR_SMTP_USER=you@gmail.com
SCRIPTMGR_SMTP_PASSWORD=your-app-password

# Microsoft Teams
SCRIPTMGR_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...

# Slack
SCRIPTMGR_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

Alerts fire on failed, timed-out, or cancelled runs.

---

## REST API

Interactive docs at **http://localhost:8765/docs**

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/scripts/{id}/run` | Trigger a script run |
| `GET` | `/api/runs` | List runs (filter by status, script) |
| `GET` | `/api/runs/{id}/logs` | Get log lines for a run |
| `POST` | `/api/schedules` | Create a schedule |
| `POST` | `/api/workflows/{id}/run` | Run a workflow |
| `POST` | `/api/services/heartbeat` | Post always-on service heartbeat |
| `GET` | `/_api/dashboard` | Dashboard stats JSON |

WebSocket log streaming: `ws://localhost:8765/ws/runs/{run_id}/logs`

---

## Project Layout

```
ScriptManager/
├── src/scriptmgr/
│   ├── api/
│   │   ├── routers/        # REST API endpoints (groups, scripts, runs, schedules, workflows, services)
│   │   ├── web/templates/  # Jinja2 HTML templates (12 pages)
│   │   ├── ui.py           # Web UI routes
│   │   └── websocket.py    # WebSocket log streaming
│   ├── cli/                # Typer CLI (serve, db init, worker)
│   ├── core/               # Config, DB, ORM models, Pydantic schemas
│   ├── executor/           # Subprocess runner, task dispatcher, log hub
│   ├── scheduler/          # APScheduler integration (cron/interval/date/continuous)
│   ├── workflows/          # DAG engine (parallel fan-out, conditional edges, retry)
│   ├── notifications/      # Email + Teams/Slack adapters
│   └── service/            # Windows service installer + always-on heartbeat
├── alembic/                # DB migrations
├── docs/                   # HTML docs (served at /help), scheduler comparison
├── samples/                # Sample scripts and a sample DAG JSON
├── tests/
│   └── unit/               # DAG engine + runner unit tests
├── install-service.ps1     # NSSM Windows service installer (run as Admin)
├── restart-service.ps1     # Restart service and verify (run as Admin)
├── bootstrap.ps1           # First-time setup helper
├── setup_dirs.ps1          # Create data directory structure
├── pyproject.toml
└── .env.example            # All configuration options with defaults
```

---

## Configuration

All settings use the `SCRIPTMGR_` prefix and can be set in `.env`:

| Setting | Default | Description |
|---|---|---|
| `SCRIPTMGR_HOST` | `127.0.0.1` | Bind address |
| `SCRIPTMGR_PORT` | `8765` | HTTP port |
| `SCRIPTMGR_DB_URL` | `sqlite:///./data/scriptmgr.db` | Database URL |
| `SCRIPTMGR_EXECUTOR_MODE` | `inproc` | `inproc` or `celery` |
| `SCRIPTMGR_WORKER_CONCURRENCY` | `4` | Max concurrent script runs |
| `SCRIPTMGR_LOG_RETENTION_DAYS` | `30` | Days to keep run logs |
| `SCRIPTMGR_SMTP_HOST` | _(empty)_ | SMTP server for email alerts |
| `SCRIPTMGR_TEAMS_WEBHOOK` | _(empty)_ | Teams webhook URL |
| `SCRIPTMGR_SLACK_WEBHOOK` | _(empty)_ | Slack webhook URL |

---

## Known Gaps / Roadmap

- [ ] Cancel actually kills the subprocess (currently marks DB status only)
- [ ] Group rename/edit UI
- [ ] Schedule "Next Run" time displayed in UI
- [ ] Workflow run step breakdown in Run History
- [ ] Log retention purge job
- [ ] CSV/JSON export from Reports page
- [ ] Notifications config page in UI (currently `.env` only)

See [`CONTRIBUTING.md`](CONTRIBUTING.md) or open an issue to help.

---

## License

MIT
