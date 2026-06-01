# ScriptManager

A Python orchestration service for managing, scheduling, chaining, and supervising
Python scripts that power AI and automation workflows.

## Features

- **Groups / folders** to organize scripts by purpose (nested)
- **Run modes**: one-shot, scheduled (cron / interval / date), continuous re-run, always-on Windows service
- **DAG workflows** with sequential, parallel, and conditional (`on_success` / `on_failure`) edges
- **Detailed reports**: live log streaming, per-script history, success rates, p50/p95 duration
- **Alerts** via email (SMTP) and Microsoft Teams / Slack webhooks
- **Web UI** + **CLI** + REST API
- **Windows service wrapper** for the orchestrator itself, plus a generator for per-script always-on services (NSSM-based) with heartbeats

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| API / UI | **FastAPI** + HTMX | Async, simple, great docs |
| Scheduler | **APScheduler** (SQLAlchemy jobstore) | Pure-Python, cron + interval + date |
| Workers | **Celery** + **Redis** | Mature, scales to remote workers later |
| DB | **SQLite** (Alembic-managed) | Zero-ops; portable to PostgreSQL |
| Service host | **NSSM** (or `pywin32`) | Reliable Windows service wrapping |
| CLI | **Typer** | Type-driven, ergonomic |

See `docs/scheduler-review.md` for the full best-in-breed comparison (ArcanaDev JAMS, Prefect, Airflow, Dagster, Rundeck, Temporal, etc.).

## Quick Start

```powershell
# 1. Create venv and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]

# 2. Initialize the database
scriptmgr db init

# 3. Start Redis (download from https://github.com/microsoftarchive/redis/releases or use Memurai/Docker)
#    e.g.: docker run -d -p 6379:6379 redis:7

# 4. Start the API + scheduler
scriptmgr serve

# 5. In another terminal, start a worker
scriptmgr worker

# 6. Register a script and run it
scriptmgr group add "AI/Pipelines" --description "AI prep scripts"
scriptmgr script add ./samples/hello.py --group "AI/Pipelines" --name "hello"
scriptmgr script run hello

# Open the dashboard
start http://localhost:8765
```

## Install as a Windows Service

```powershell
# After pip install, run as Administrator:
scriptmgr service install
scriptmgr service start
```

This installs `ScriptManager` as a Windows service (NSSM-backed) that hosts the
API, scheduler, and a local worker. Logs go to `%PROGRAMDATA%\ScriptManager\logs`.

## Wrap a Script as an Always-On Service

```powershell
scriptmgr always-on install my-watcher --script ./watchers/my_watcher.py --heartbeat 30
```

Generates and installs a Windows service that auto-restarts the script and
pings the orchestrator every 30 seconds.

## Project Layout

```
scriptmgr/
├── src/scriptmgr/
│   ├── api/            # FastAPI routes + WebSocket log streaming
│   ├── cli/            # Typer CLI
│   ├── core/           # config, db, models, schemas
│   ├── executor/       # Celery tasks, subprocess runner, log capture
│   ├── scheduler/      # APScheduler integration
│   ├── workflows/      # DAG engine
│   ├── notifications/  # email + Teams/Slack adapters
│   ├── service/        # Windows service installer + heartbeat
│   └── web/            # HTMX templates + static
├── alembic/            # DB migrations
├── samples/            # sample scripts and a sample DAG
├── docs/
└── tests/
```

## Status

This is the initial scaffold. Implementation phases are tracked in
`plan.md` (session state). See `docs/phases.md` for current progress.
