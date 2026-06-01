"""Celery application factory."""
from __future__ import annotations

from celery import Celery

from scriptmgr.core.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery("scriptmgr", broker=settings.broker_url, backend=settings.result_backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        worker_concurrency=settings.worker_concurrency,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # Auto-discover tasks in this package
        include=["scriptmgr.executor.tasks"],
    )
    return app


celery_app = make_celery()
