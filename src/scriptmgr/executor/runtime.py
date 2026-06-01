"""In-process task runner — replaces Celery for workstation use.

A simple thread-pool that mimics Celery's `.delay()` interface so the rest of
the codebase doesn't need to change.  Scripts run as subprocesses (each script
gets its own OS process), but the *orchestration* of those subprocesses happens
inside the API server's process via a ThreadPoolExecutor.

This is plenty for a workstation: tens of scripts, a handful running concurrently.
If you ever need distributed workers, you can swap this module for Celery.
"""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from scriptmgr.core.config import get_settings

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        settings = get_settings()
        _executor = ThreadPoolExecutor(
            max_workers=settings.worker_concurrency,
            thread_name_prefix="scriptmgr-runner",
        )
    return _executor


def shutdown_executor() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=False)
        _executor = None


class _Task:
    """Wraps a callable so callers can use the familiar `.delay(...)` pattern."""

    def __init__(self, fn: Callable[..., Any], name: str):
        self._fn = fn
        self.name = name

    def delay(self, *args: Any, **kwargs: Any) -> Future:
        """Submit the task to the worker pool — returns a concurrent.futures.Future."""
        logger.debug("Submitting task %s args=%s", self.name, args)
        return get_executor().submit(self._run_safe, *args, **kwargs)

    def _run_safe(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._fn(*args, **kwargs)
        except Exception:
            logger.exception("Task %s raised", self.name)
            raise


def task(name: str) -> Callable[[Callable[..., Any]], _Task]:
    """Decorator that turns a plain function into a `_Task` with `.delay()`."""

    def decorator(fn: Callable[..., Any]) -> _Task:
        return _Task(fn, name=name)

    return decorator
