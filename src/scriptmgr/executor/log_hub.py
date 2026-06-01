"""In-process log broadcaster — replaces Redis pub/sub for workstation use.

Each run has its own asyncio.Queue per WebSocket subscriber.  The runner posts
log lines to all subscribers; subscribers consume from their own queue.

This is in-memory only — log lines are also persisted to the `run_logs` DB
table so they survive process restarts (the WebSocket fallback in
api/websocket.py reads from the DB if no in-memory broadcaster is attached).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class _LogHub:
    """Thread-safe in-memory log broadcaster keyed by run_id."""

    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once by the FastAPI lifespan handler."""
        self._loop = loop

    def subscribe(self, run_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        with self._lock:
            self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: int, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs[run_id].discard(q)
            if not self._subs[run_id]:
                self._subs.pop(run_id, None)

    def publish(self, run_id: int, stream: str, line: str) -> None:
        """Called from worker threads — schedules delivery on the event loop."""
        with self._lock:
            queues = list(self._subs.get(run_id, ()))
        if not queues or self._loop is None:
            return
        payload: dict[str, Any] = {"stream": stream, "line": line}
        for q in queues:
            try:
                self._loop.call_soon_threadsafe(self._safe_put, q, payload)
            except RuntimeError:
                pass  # loop is closing

    @staticmethod
    def _safe_put(q: asyncio.Queue, payload: dict) -> None:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # drop log if subscriber can't keep up


log_hub = _LogHub()
