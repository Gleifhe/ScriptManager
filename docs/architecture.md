# ScriptManager — Architecture

## Overview

ScriptManager is a **single-machine workstation orchestration service** for running, scheduling, and chaining Python/PowerShell/Batch/Go/Exe scripts. It exposes a full web UI (HTMX), a REST API (FastAPI), and a CLI. It runs as a Windows service and requires no external infrastructure (no Redis, no message broker) in its default configuration.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Windows Service (NSSM)                        │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  ScriptManager Process                       │    │
│  │                                                              │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │    │
│  │  │  FastAPI App │   │  APScheduler │   │ ThreadPoolExec │  │    │
│  │  │  (Uvicorn)   │   │  (Background)│   │  (Script runs) │  │    │
│  │  │  port 8765   │   │              │   │  max_workers=4 │  │    │
│  │  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘  │    │
│  │         │                  │                    │           │    │
│  │         └──────────────────┴────────────────────┘           │    │
│  │                            │                                │    │
│  │                     ┌──────▼──────┐                         │    │
│  │                     │  SQLite DB  │                         │    │
│  │                     │ scriptmgr   │  (WAL mode)             │    │
│  │                     │    .db      │                         │    │
│  │                     └─────────────┘                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer Map

```
scriptmgr/
├── api/                  ← HTTP + WebSocket surface
│   ├── __init__.py       ← FastAPI app factory + lifespan hooks
│   ├── ui.py             ← HTMX web UI routes (all pages)
│   ├── websocket.py      ← WS /ws/runs/{id}/logs (live log streaming)
│   └── routers/          ← REST API (JSON)
│       ├── groups.py
│       ├── scripts.py
│       ├── schedules.py
│       ├── workflows.py
│       ├── runs.py
│       ├── services.py
│       └── browse.py     ← File browser (script path picker)
│
├── core/                 ← Shared infrastructure
│   ├── config.py         ← Settings (env vars, .env file, portable paths)
│   ├── db.py             ← SQLAlchemy engine + session + WAL pragmas
│   ├── models.py         ← ORM models (all tables)
│   └── schemas.py        ← Pydantic I/O schemas
│
├── executor/             ← Script execution engine
│   ├── runner.py         ← Subprocess launcher + batched log writer
│   ├── runtime.py        ← In-process ThreadPoolExecutor wrapper
│   ├── tasks.py          ← Task proxy (routes to inproc or Celery)
│   ├── log_hub.py        ← In-process pub/sub for live log broadcast
│   └── celery_app.py     ← Optional Celery app (distributed mode)
│
├── workflows/            ← DAG orchestration
│   ├── dag.py            ← DAG model (nodes, edges, traversal)
│   └── engine.py         ← Wave-by-wave DAG executor
│
├── scheduler/            ← Trigger management
│   └── apscheduler.py    ← APScheduler setup + schedule CRUD + retention
│
├── notifications/        ← Alerting
│   ├── dispatcher.py     ← Decides what to send and when
│   ├── email.py          ← SMTP sender
│   └── webhooks.py       ← Teams / Slack webhook sender
│
├── service/              ← Windows service integration
│   ├── installer.py      ← NSSM install/uninstall/start/stop/status
│   ├── main_service.py   ← Service entry point (uvicorn + scheduler)
│   └── always_on.py      ← Generates per-script service wrappers
│
└── cli/
    └── main.py           ← Typer CLI (serve, group, script, schedule,
                             workflow, run, service, always-on)
```

---

## Component Details

### 1. FastAPI Application (`api/__init__.py`)

The app factory registers all routers and wires up a lifespan handler that:
1. Initialises the database (creates tables if missing)
2. Registers the running asyncio event loop with `log_hub` (needed so worker threads can push into WebSocket queues)
3. Starts APScheduler
4. On shutdown: stops the scheduler and shuts down the thread pool

**URL map:**

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/` | `ui.py` | HTMX web pages |
| `/api/groups` | `routers/groups.py` | Groups CRUD |
| `/api/scripts` | `routers/scripts.py` | Scripts CRUD + run |
| `/api/schedules` | `routers/schedules.py` | Schedule CRUD |
| `/api/workflows` | `routers/workflows.py` | Workflow CRUD + run |
| `/api/runs` | `routers/runs.py` | Run history + logs |
| `/api/services` | `routers/services.py` | Always-on services |
| `/api/browse` | `routers/browse.py` | File system browser |
| `/ws/runs/{id}/logs` | `websocket.py` | Live log stream |
| `/docs` | FastAPI auto | Swagger UI |

---

### 2. Data Model (`core/models.py`)

```
Group (folders)
  └── Script (registered scripts)
        └── Schedule (triggers for scripts)
        └── Run* (execution records)
              └── RunLog (stdout/stderr/system lines)
        └── AlwaysOnService (service wrapper registration)

Workflow (DAG)
  └── Schedule (triggers for workflows)
  └── Run* (parent run for the whole workflow)
        └── Run* (child runs, one per DAG node)
              └── RunLog

* Run.parent_run_id links workflow child runs back to the parent
```

**Run statuses:** `queued → running → success | failed | cancelled | timed_out`

**Schedule trigger types:** `cron` · `interval` · `date` · `continuous`

---

### 3. Script Execution (`executor/`)

```
UI / Scheduler / CLI
       │
       ▼
  run_script_task.delay(run_id)           ← TaskProxy
       │
       ├─ inproc mode (default) ──────→  ThreadPoolExecutor.submit(_run_script)
       └─ celery mode ─────────────────→  Celery worker via Redis broker
                │
                ▼
         execute_script(run_id)           ← runner.py
                │
         subprocess.Popen(cmd)            ← actual OS process
                │
         Reader threads (stdout + stderr)
                │
         _RunLogBuffer (50-line / 250ms batches)
                │
         ┌──────┴──────┐
         │             │
      DB bulk        log_hub.publish()    ← in-process broadcast
      save                │
                    WebSocket clients
                    (via asyncio queue)
```

**Supported script types** (auto-detected from extension):

| Extension | Interpreter |
|-----------|-------------|
| `.py` | `python` (or venv python) |
| `.ps1` | `powershell -File` |
| `.bat` / `.cmd` | `cmd /c` |
| `.go` | `go run` |
| `.exe` | direct |
| `.sh` | `bash` |

---

### 4. Workflow Engine (`workflows/`)

Workflows are stored as a DAG JSON structure and executed wave-by-wave:

```
DAG JSON  →  Dag.from_dict()  →  execute_workflow()
                                       │
                              find root nodes (no predecessors)
                                       │
                              ┌────── wave loop ──────┐
                              │                       │
                         run nodes in           collect outcomes
                         parallel               (success/failure)
                         (ThreadPool)                 │
                                             check outgoing edges
                                             ("on": success|failure|always)
                                                      │
                                             queue next wave
                                             (when ALL predecessors done)
                                       │
                              └────── until no more ready ──────┘
                                       │
                              set parent Run status
```

Each node gets its own `Run` row with `parent_run_id` linking back to the workflow run. Retry logic re-creates a new `Run` for each attempt.

---

### 5. Scheduler (`scheduler/apscheduler.py`)

APScheduler runs in a background thread inside the server process:

- **Job store:** `data/apscheduler.db` (separate SQLite — avoids lock contention with run logs)
- **Executor:** Fixed `ThreadPoolExecutor(4)` — isolated from script runner threads
- **Trigger types:**

| Type | Expression | Behaviour |
|------|-----------|-----------|
| `cron` | `"0 9 * * 1-5"` | Standard cron syntax |
| `interval` | `"300"` (seconds) | Repeating every N seconds |
| `date` | ISO datetime string | One-shot at a specific time |
| `continuous` | delay seconds | Re-queues immediately after completion |

- **Retention job:** Daily at 03:00 UTC — deletes `RunLog` and `Run` rows older than `log_retention_days` (default 30)

---

### 6. Live Log Streaming (`websocket.py` + `log_hub.py`)

```
Script subprocess (OS thread)
       │  stdout/stderr lines
       ▼
_RunLogBuffer.add(stream, line)
       │
       ├──→ bulk DB write (every 50 lines or 250ms)
       │
       └──→ log_hub.publish(run_id, stream, line)
                   │
            asyncio.Queue per subscriber
                   │
            WebSocket.send_json()  ──→  Browser
```

On new WebSocket connection, `_send_backlog()` replays up to the last **1,000** stored log lines before switching to live streaming.

---

### 7. Windows Service Integration (`service/`)

**ScriptManager service** (NSSM-managed):
- Entry point: `main_service.py` → starts Uvicorn + APScheduler
- Installed via `install-service.ps1` or `scriptmgr service install`
- Logs written to `data/logs/service-stdout.log` and `service-stderr.log`

**Always-On service wrappers:**
- For scripts that should run continuously as their own service (not scheduled)
- `always_on.py` generates a Python wrapper + PS1 installer for any script
- Wrapper sends heartbeats to `/api/services/heartbeat` so the UI shows liveness
- Managed via `scriptmgr always-on install`

---

### 8. Notifications (`notifications/`)

Triggered automatically after any non-SUCCESS run completes:

| Channel | Config key | |
|---------|-----------|--|
| Email (SMTP) | `SCRIPTMGR_SMTP_HOST` etc. | Skipped if host is blank |
| Slack | `SCRIPTMGR_SLACK_WEBHOOK` | Skipped if URL is blank |
| MS Teams | `SCRIPTMGR_TEAMS_WEBHOOK` | Skipped if URL is blank |

---

### 9. Configuration (`core/config.py`)

All settings use the `SCRIPTMGR_` prefix and can be set in `.env` or environment variables:

| Key | Default | Description |
|-----|---------|-------------|
| `SCRIPTMGR_DATA_DIR` | `<repo>/data` | Database + logs root |
| `SCRIPTMGR_DB_URL` | `sqlite:///<data>/scriptmgr.db` | SQLAlchemy URL |
| `SCRIPTMGR_HOST` | `127.0.0.1` | Bind address |
| `SCRIPTMGR_PORT` | `8765` | HTTP port |
| `SCRIPTMGR_EXECUTOR_MODE` | `inproc` | `inproc` or `celery` |
| `SCRIPTMGR_WORKER_CONCURRENCY` | `4` | Script runner thread count |
| `SCRIPTMGR_LOG_RETENTION_DAYS` | `30` | Days before logs are purged |

Paths are resolved relative to the repo root (found by walking up to `pyproject.toml`), making the installation portable to any directory.

---

## Execution Modes

### Workstation Mode (default — `inproc`)

```
┌──────────────────────────────────┐
│        Single Process            │
│  FastAPI + APScheduler + Runner  │
│  All in one — no Redis needed    │
└──────────────────────────────────┘
```

Best for: personal workstation, single machine, tens of scripts.

### Distributed Mode (`celery`)

```
┌─────────────┐     Redis      ┌──────────────┐
│  API Server │ ─── broker ──→ │ Celery Worker│
│  + Scheduler│ ←── results ── │  (separate   │
└─────────────┘                │   process)   │
                                └──────────────┘
```

Best for: multiple machines, high script volume, isolated worker processes.
Enable with `SCRIPTMGR_EXECUTOR_MODE=celery` and install with `bootstrap.ps1 -Celery`.

---

## Data Flow: Script Run (End to End)

```
1. Trigger          UI button / Schedule fires / CLI / API POST
        │
2. Create Run       Run row inserted (status=QUEUED)
        │
3. Dispatch         run_script_task.delay(run_id)
        │
4. Execute          execute_script(run_id) in worker thread
                    → subprocess.Popen([interpreter, script_path, ...args])
        │
5. Stream           stdout/stderr reader threads
                    → _RunLogBuffer batches to DB
                    → log_hub broadcasts to WebSocket subscribers
        │
6. Finish           exit_code captured
                    → Run.status = SUCCESS | FAILED | TIMED_OUT
                    → Run.finished_at set
        │
7. Notify           dispatch_run_notification(run_id)
                    → email / Slack / Teams (if configured, on non-success)
```

---

## Database Schema Summary

```sql
groups          id, name, description, parent_id
scripts         id, group_id, name, path, interpreter, venv, args,
                timeout_sec, description, tags
schedules       id, script_id, workflow_id, trigger_type, expression,
                enabled, rerun_delay_sec
workflows       id, group_id, name, description, dag (JSON)
runs            id, script_id, workflow_id, parent_run_id,
                trigger_source, params, status, started_at,
                finished_at, exit_code, host, worker, created_at
run_logs        id, run_id, ts, stream, line
                INDEX (run_id, id)          ← composite for fast fetch
services        id, script_id, service_name, status, last_heartbeat,
                heartbeat_interval_sec, pid
```

SQLite is run in **WAL mode** with a 16 MB page cache and 128 MB mmap for concurrent read/write performance.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite (not Postgres) | Zero-infrastructure for workstation use; WAL mode handles concurrency adequately for local load |
| In-process thread pool (not Celery default) | No Redis dependency; simpler installation; adequate for workstation concurrency |
| HTMX (not React/Vue) | Server-rendered UI — no JS build step, simpler deployment, works without a CDN |
| APScheduler (not cron/Task Scheduler) | Pure Python, portable, survives reboots as part of the Windows service, supports all trigger types in one library |
| NSSM for Windows service | Handles stdout/stderr redirection and automatic restart; avoids `pywin32` complexity |
| Batched log writes (50 lines/250ms) | Eliminates the primary DB bottleneck — verbose scripts were causing 1000+ single-row commits/sec |
| Separate APScheduler DB | Prevents job-store lock contention when run-log writes are heavy |
