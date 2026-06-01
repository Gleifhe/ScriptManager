"""Entry point run by the Windows service: starts API server + scheduler + local worker subprocess."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading

import uvicorn

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import init_db
from scriptmgr.scheduler.apscheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_worker_proc: subprocess.Popen | None = None


def _start_worker() -> None:
    global _worker_proc
    settings = get_settings()
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "scriptmgr.executor.celery_app:celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={settings.worker_concurrency}",
    ]
    logger.info("Starting local Celery worker: %s", " ".join(cmd))
    _worker_proc = subprocess.Popen(cmd)


def _stop_worker() -> None:
    global _worker_proc
    if _worker_proc and _worker_proc.poll() is None:
        _worker_proc.terminate()
        _worker_proc.wait(timeout=15)
        _worker_proc = None


def run() -> None:
    settings = get_settings()
    logger.info("ScriptManager service starting (executor=%s)…", settings.executor_mode)
    init_db()
    start_scheduler()

    # Only spawn an external Celery worker when running in distributed mode.
    # In ``inproc`` mode the API server runs scripts itself via a thread pool.
    if (settings.executor_mode or "inproc").lower() == "celery":
        threading.Thread(target=_start_worker, daemon=True).start()
    else:
        logger.info("Executor mode is 'inproc' — skipping Celery worker subprocess.")

    try:
        uvicorn.run(
            "scriptmgr.api.app:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
        )
    finally:
        logger.info("ScriptManager service shutting down…")
        stop_scheduler()
        _stop_worker()


if __name__ == "__main__":
    run()
