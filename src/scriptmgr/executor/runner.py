"""Subprocess runner: executes a script, streams logs to DB.

Log destinations:
- DB (``run_logs`` table) — always
- In-process log hub — always (cheap; powers WebSocket when in inproc mode)
- Redis pub/sub          — only when ``executor_mode == "celery"``
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run, RunLog, RunStatus
from scriptmgr.executor.log_hub import log_hub

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P1: Batched log writer — reduces per-line DB session overhead dramatically
# ---------------------------------------------------------------------------

class _RunLogBuffer:
    """
    Buffers RunLog rows and flushes to DB in batches.

    Flush triggers:
      - Buffer reaches FLUSH_LINES entries (synchronous, called from reader thread)
      - FLUSH_SECS elapses with lines pending   (timer thread)
      - close() is called at run end            (final flush, synchronous)
    """

    FLUSH_LINES = 50
    FLUSH_SECS  = 0.25

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self._buf: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def add(self, stream: str, line: str) -> None:
        to_write: list[tuple[str, str]] | None = None
        with self._lock:
            self._buf.append((stream, line))
            if len(self._buf) >= self.FLUSH_LINES:
                to_write = self._drain_locked()
            elif self._timer is None:
                self._timer = threading.Timer(self.FLUSH_SECS, self._timed_flush)
                self._timer.daemon = True
                self._timer.start()
        if to_write:
            self._write(to_write)

    def close(self) -> None:
        """Cancel pending timer and flush all remaining lines."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            to_write = self._drain_locked()
        if to_write:
            self._write(to_write)

    # ── internals ────────────────────────────────────────────────────────────

    def _timed_flush(self) -> None:
        with self._lock:
            self._timer = None
            to_write = self._drain_locked()
        if to_write:
            self._write(to_write)

    def _drain_locked(self) -> list[tuple[str, str]]:
        rows, self._buf = self._buf, []
        return rows

    def _write(self, rows: list[tuple[str, str]]) -> None:
        try:
            with session_scope() as db:
                db.bulk_save_objects([
                    RunLog(run_id=self.run_id, stream=s, line=ln)
                    for s, ln in rows
                ])
        except Exception as exc:
            logger.warning("Log flush failed for run %s: %s", self.run_id, exc)

_REDIS_CLIENT = None
_REDIS_CHECKED = False


def _get_redis():
    global _REDIS_CLIENT, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _REDIS_CLIENT
    _REDIS_CHECKED = True
    if (get_settings().executor_mode or "inproc").lower() != "celery":
        return None
    try:
        import redis as redis_lib
        _REDIS_CLIENT = redis_lib.from_url(get_settings().broker_url, decode_responses=True)
    except Exception as exc:
        logger.warning("Redis client unavailable, falling back to in-proc log hub only: %s", exc)
    return _REDIS_CLIENT



def _build_command(script, extra_params: list[str] | None = None) -> list[str]:
    """
    Build the subprocess command list for any script type.

    Detection order:
      1. If ``interpreter`` is set and non-empty, honour it.
      2. Otherwise auto-detect from file extension.

    Supported types (auto-detected):
      .py            → python  (or venv python if script.venv is set)
      .ps1           → powershell.exe -ExecutionPolicy Bypass -File
      .bat / .cmd    → cmd.exe /c
      .exe           → direct execution (no wrapper)
      .go            → go run
      (no ext / any) → direct execution
    """
    path = str(script.path)
    ext = Path(path).suffix.lower()
    static_args = list(script.args or [])
    runtime_args = list(extra_params or [])
    all_args = static_args + runtime_args

    interp = (script.interpreter or "").strip()

    # --- Explicit interpreter set ---
    if interp:
        interp_lower = interp.lower()
        # PowerShell shorthand
        if interp_lower in ("powershell", "pwsh", "powershell.exe", "pwsh.exe"):
            exe = "pwsh.exe" if interp_lower.startswith("pwsh") else "powershell.exe"
            return [exe, "-ExecutionPolicy", "Bypass", "-File", path] + all_args
        # CMD shorthand
        if interp_lower in ("cmd", "cmd.exe", "batch"):
            return ["cmd.exe", "/c", path] + all_args
        # Python with venv support
        if interp_lower in ("python", "python3", "python.exe"):
            resolved = _resolve_python(script)
            return [resolved, path] + all_args
        # Go
        if interp_lower in ("go", "go run"):
            return ["go", "run", path] + all_args
        # Anything else (e.g. full path to interpreter)
        if ext in (".py",):
            return [interp, path] + all_args
        return [interp, path] + all_args

    # --- Auto-detect by extension ---
    if ext == ".py":
        return [_resolve_python(script), path] + all_args
    if ext == ".ps1":
        return ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path] + all_args
    if ext in (".bat", ".cmd"):
        return ["cmd.exe", "/c", path] + all_args
    if ext == ".go":
        return ["go", "run", path] + all_args
    # .exe or no extension — run directly
    return [path] + all_args


def _resolve_python(script) -> str:
    """Return python interpreter path, preferring the script's venv."""
    if script.venv:
        venv = Path(script.venv)
        interp = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if interp.exists():
            return str(interp)
    return script.interpreter if (script.interpreter or "").strip() not in ("", "python", "python3") else sys.executable


def execute_script(run_id: int) -> int:
    """
    Run the script referenced by *run_id*.
    Streams stdout/stderr to DB (run_logs) and the in-process log hub.
    Per-run parameters are read from ``run.params`` (JSON list).
    Returns the process exit code.
    """
    with session_scope() as db:
        run = db.get(Run, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        script = run.script
        if not script:
            raise ValueError(f"Run {run_id} has no associated script")

        extra_params = list(run.params or [])
        cmd = _build_command(script, extra_params)
        cwd = script.cwd or str(Path(str(script.path)).parent)
        env = {**os.environ, **{k: str(v) for k, v in (script.env or {}).items()}}
        timeout = script.timeout_sec or None

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.host = socket.gethostname()
        run.worker = threading.current_thread().name
        db.add(run)

    buf = _RunLogBuffer(run_id)

    def _log(stream: str, line: str) -> None:
        line = line.rstrip("\n")
        buf.add(stream, line)               # batched DB write
        log_hub.publish(run_id, stream, line)  # immediate in-process broadcast
        r = _get_redis()
        if r:
            try:
                r.publish(f"run:{run_id}:logs", json.dumps({"stream": stream, "line": line}))
            except Exception:
                pass

    exit_code = -1
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )

        def _reader(pipe, stream: str) -> None:
            for line in iter(pipe.readline, ""):
                _log(stream, line)
            pipe.close()

        t_out = threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            _log("system", f"[scriptmgr] Timed out after {timeout}s")
            buf.close()
            _finish_run(run_id, RunStatus.TIMED_OUT, -9)
            return -9

        t_out.join()
        t_err.join()
        exit_code = proc.returncode

    except Exception as exc:
        logger.exception("Error executing run %s", run_id)
        _log("system", f"[scriptmgr] Execution error: {exc}")
        exit_code = -1

    # Flush any remaining buffered log lines before finalising the run
    buf.close()

    status = RunStatus.SUCCESS if exit_code == 0 else RunStatus.FAILED
    _finish_run(run_id, status, exit_code)

    # Signal log consumers that the run is done
    log_hub.publish(run_id, "system", "__done__")
    r = _get_redis()
    if r:
        try:
            r.publish(f"run:{run_id}:logs", json.dumps({"stream": "system", "line": "__done__"}))
        except Exception:
            pass

    return exit_code


def _finish_run(run_id: int, status: RunStatus, exit_code: int) -> None:
    with session_scope() as db:
        run = db.get(Run, run_id)
        if run:
            run.status = status
            run.finished_at = datetime.now(timezone.utc)
            run.exit_code = exit_code
            db.add(run)
    _dispatch_notification(run_id)


def _dispatch_notification(run_id: int) -> None:
    try:
        from scriptmgr.notifications.dispatcher import dispatch_run_notification
        dispatch_run_notification(run_id)
    except Exception as exc:
        logger.warning("Notification dispatch failed for run %s: %s", run_id, exc)
