"""Task handles for running scripts and workflows.

Supports two executor modes (selected via SCRIPTMGR_EXECUTOR_MODE):

  - ``inproc`` (default for workstation) — in-process ThreadPoolExecutor, no Redis
  - ``celery``                            — distributed Celery + Redis

Public surface stays the same in both modes: callers do ``run_script_task.delay(run_id)``.
The router below picks the underlying implementation lazily on first call.
"""
from __future__ import annotations

import logging
from typing import Any

from scriptmgr.core.config import get_settings
from scriptmgr.executor.runtime import task as inproc_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The actual work functions — these are mode-agnostic.
# ---------------------------------------------------------------------------

def _run_script(run_id: int) -> dict:
    from scriptmgr.executor.runner import execute_script
    exit_code = execute_script(run_id)
    return {"run_id": run_id, "exit_code": exit_code}


def _run_workflow(run_id: int) -> dict:
    from scriptmgr.workflows.engine import execute_workflow
    execute_workflow(run_id)
    return {"run_id": run_id}


# ---------------------------------------------------------------------------
# Pre-built in-process task handles
# ---------------------------------------------------------------------------

_inproc_run_script = inproc_task("scriptmgr.run_script")(_run_script)
_inproc_run_workflow = inproc_task("scriptmgr.run_workflow")(_run_workflow)


# ---------------------------------------------------------------------------
# Celery task handles (built lazily, only if mode == "celery")
# ---------------------------------------------------------------------------

_celery_handles: dict[str, Any] = {}


def _get_celery_handles() -> dict[str, Any]:
    if _celery_handles:
        return _celery_handles
    from scriptmgr.executor.celery_app import celery_app

    @celery_app.task(name="scriptmgr.run_script", bind=True)
    def celery_run_script(self, run_id: int) -> dict:
        return _run_script(run_id)

    @celery_app.task(name="scriptmgr.run_workflow", bind=True)
    def celery_run_workflow(self, run_id: int) -> dict:
        return _run_workflow(run_id)

    _celery_handles["run_script"] = celery_run_script
    _celery_handles["run_workflow"] = celery_run_workflow
    return _celery_handles


# ---------------------------------------------------------------------------
# Public proxy objects with `.delay(...)`
# ---------------------------------------------------------------------------

class _TaskProxy:
    """Routes ``.delay(...)`` to the right backend based on current mode."""

    def __init__(self, name: str):
        self._name = name

    def delay(self, *args, **kwargs):
        mode = (get_settings().executor_mode or "inproc").lower()
        if mode == "celery":
            handles = _get_celery_handles()
            return handles[self._name].delay(*args, **kwargs)
        # default: in-process
        if self._name == "run_script":
            return _inproc_run_script.delay(*args, **kwargs)
        return _inproc_run_workflow.delay(*args, **kwargs)


run_script_task = _TaskProxy("run_script")
run_workflow_task = _TaskProxy("run_workflow")
