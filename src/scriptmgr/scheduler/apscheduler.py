"""APScheduler integration: cron, interval, date, and continuous-rerun triggers.

Jobs are persisted in the same SQLite DB via SQLAlchemyJobStore so they survive
restarts without re-registration.
"""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run, RunStatus, Schedule, TriggerType

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        _scheduler = BackgroundScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=settings.db_url)},
            executors={"default": ThreadPoolExecutor(max_workers=settings.worker_concurrency)},
            timezone="UTC",
        )
    return _scheduler


def start_scheduler() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        _reload_all_schedules()
        logger.info("APScheduler started")


def stop_scheduler() -> None:
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("APScheduler stopped")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _reload_all_schedules() -> None:
    """Register all enabled schedules from the DB into APScheduler."""
    with session_scope() as db:
        schedules = db.query(Schedule).filter(Schedule.enabled.is_(True)).all()
        for s in schedules:
            _register(s)
    logger.info("Reloaded %d schedule(s)", len(schedules))


def _build_trigger(schedule: Schedule):
    tt = schedule.trigger_type
    expr = schedule.expression
    if tt == TriggerType.CRON:
        return CronTrigger.from_crontab(expr, timezone="UTC")
    if tt == TriggerType.INTERVAL:
        return IntervalTrigger(seconds=int(expr))
    if tt == TriggerType.DATE:
        return DateTrigger(run_date=datetime.fromisoformat(expr))
    if tt == TriggerType.CONTINUOUS:
        delay = max(schedule.rerun_delay_sec, 1)
        return IntervalTrigger(seconds=delay)
    return None


def _fire(schedule_id: int) -> None:
    """Called by APScheduler when a trigger fires — creates a Run and enqueues a Celery task."""
    from scriptmgr.executor.tasks import run_script_task, run_workflow_task

    with session_scope() as db:
        schedule = db.get(Schedule, schedule_id)
        if not schedule or not schedule.enabled:
            return
        run = Run(
            script_id=schedule.script_id,
            workflow_id=schedule.workflow_id,
            trigger_source="schedule",
            status=RunStatus.QUEUED,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        is_script = schedule.script_id is not None

    if is_script:
        run_script_task.delay(run_id)
    else:
        run_workflow_task.delay(run_id)
    logger.debug("Fired schedule %s → run %s", schedule_id, run_id)


def _register(schedule: Schedule) -> None:
    trigger = _build_trigger(schedule)
    if trigger is None:
        return
    get_scheduler().add_job(
        _fire,
        trigger=trigger,
        id=f"schedule_{schedule.id}",
        args=[schedule.id],
        replace_existing=True,
        misfire_grace_time=300,
    )


# ---------------------------------------------------------------------------
# Public API (called by API routers / CLI)
# ---------------------------------------------------------------------------

def add_schedule(schedule: Schedule) -> None:
    _register(schedule)


def remove_schedule(schedule_id: int) -> None:
    job_id = f"schedule_{schedule_id}"
    sched = get_scheduler()
    if sched.get_job(job_id):
        sched.remove_job(job_id)
        logger.info("Removed job %s", job_id)


def pause_schedule(schedule_id: int) -> None:
    sched = get_scheduler()
    job_id = f"schedule_{schedule_id}"
    if sched.get_job(job_id):
        sched.pause_job(job_id)


def resume_schedule(schedule_id: int) -> None:
    sched = get_scheduler()
    job_id = f"schedule_{schedule_id}"
    if sched.get_job(job_id):
        sched.resume_job(job_id)
