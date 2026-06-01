# Scheduler Comparison — Best in Breed

## Summary

ScriptManager uses **APScheduler + Celery** as its core scheduling and execution engine.
This document explains the evaluation.

---

## Options Evaluated

### ✅ APScheduler + Celery (Chosen)
- **APScheduler**: Pure-Python, embeds directly into FastAPI via background thread.
  Supports cron, interval, date, and custom triggers. Persistent via SQLAlchemy jobstore
  (same DB as the rest of ScriptManager — zero extra infra for scheduling metadata).
- **Celery**: Mature, battle-tested distributed task queue. Works with Redis broker.
  Supports 25+ concurrent workers, retries, result backends, and fan-out to remote workers
  later without changing business logic.
- **Why chosen**: Same language as scripts, minimal ops surface, scales naturally.

### ArcanaDev JAMS
- Enterprise Windows-native job scheduler with excellent UI, SLA tracking, and audit.
- Licensed / commercial product.
- **Consider** if you outgrow APScheduler and need enterprise compliance, SLA alerting,
  calendar-aware blackout windows, or native AD integration.

### Prefect 2 / 3
- Modern Python orchestrator with first-class DAG support and excellent observability.
- Self-hosted or cloud. Great for data-engineering pipelines.
- **Consider** if DAG complexity grows significantly (complex dependencies, dynamic task
  generation, parametrised flows, data lineage).

### Apache Airflow
- DAG-first, widely adopted, strong ecosystem.
- Heavy: separate scheduler, webserver, workers, metadata DB (Postgres required).
- Linux-leaning; significant ops overhead.
- **Verdict**: Overkill for 50–500 scripts on a single Windows machine.

### Dagster
- Asset-centric pipeline orchestrator; excellent for data assets and lineage.
- More opinionated than we need for general script ops.

### Rundeck
- JVM-based operations job runner with ACLs and audit.
- Not Python-native; would require a separate JVM process.

### Windows Task Scheduler
- Free, built-in.
- No DAGs, no live logs, no grouping, weak reporting.
- Adequate for < 10 standalone scripts; not for this use case.

### Temporal / Cadence
- Workflow-as-code engines designed for long-running, durable workflows.
- Powerful but heavy and complex to operate.
- **Consider** if workflows need saga patterns, human-in-the-loop steps, or
  extremely long-lived executions (days/weeks).

### Quartz.NET
- .NET scheduler. Wrong ecosystem.

---

## Migration Path

The ScriptManager data model is scheduler-agnostic: schedules, runs, and workflows are
stored in SQLite. If you migrate to Prefect or JAMS:

1. Export schedules / workflows from the DB.
2. Swap out `scheduler/apscheduler.py` for a new adapter module.
3. Keep the API, CLI, and reporting layers unchanged.
