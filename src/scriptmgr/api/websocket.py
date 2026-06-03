"""WebSocket endpoint for live run log streaming.

Mode-aware:
- In ``inproc`` mode (default): subscribes to the in-process log hub.
- In ``celery`` mode:           subscribes to Redis pub/sub.
Both modes fall back to short-polling the DB if the primary channel is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from scriptmgr.core.config import get_settings
from scriptmgr.executor.log_hub import log_hub

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/runs/{run_id}/logs")
async def run_logs_ws(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()
    mode = (get_settings().executor_mode or "inproc").lower()

    if mode == "celery":
        await _stream_via_redis(websocket, run_id)
    else:
        await _stream_via_loghub(websocket, run_id)


# ---------------------------------------------------------------------------
# In-process log hub (inproc mode)
# ---------------------------------------------------------------------------

async def _stream_via_loghub(websocket: WebSocket, run_id: int) -> None:
    log_hub.set_loop(asyncio.get_running_loop())
    q = log_hub.subscribe(run_id)
    try:
        # Send any backlog from DB first so the user sees the run-so-far
        await _send_backlog(websocket, run_id)
        while True:
            data = await q.get()
            await websocket.send_json(data)
            if data.get("line") == "__done__":
                break
    except WebSocketDisconnect:
        pass
    finally:
        log_hub.unsubscribe(run_id, q)


# ---------------------------------------------------------------------------
# Redis pub/sub (celery mode)
# ---------------------------------------------------------------------------

async def _stream_via_redis(websocket: WebSocket, run_id: int) -> None:
    settings = get_settings()
    try:
        import redis.asyncio as aioredis
    except ImportError:
        await _stream_via_polling(websocket, run_id)
        return

    client = aioredis.from_url(settings.broker_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(f"run:{run_id}:logs")
    try:
        await _send_backlog(websocket, run_id)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            await websocket.send_json(data)
            if data.get("line") == "__done__":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe()
        await client.aclose()


# ---------------------------------------------------------------------------
# DB polling fallback
# ---------------------------------------------------------------------------

async def _stream_via_polling(websocket: WebSocket, run_id: int) -> None:
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Run, RunLog, RunStatus

    seen_id = 0
    try:
        while True:
            with session_scope() as db:
                rows = (
                    db.query(RunLog)
                    .filter(RunLog.run_id == run_id, RunLog.id > seen_id)
                    .order_by(RunLog.id)
                    .all()
                )
                for row in rows:
                    await websocket.send_json({"stream": row.stream, "line": row.line})
                    seen_id = row.id
                run = db.get(Run, run_id)
                if run and run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                    await websocket.send_json({"stream": "system", "line": "__done__"})
                    break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


async def _send_backlog(websocket: WebSocket, run_id: int) -> None:
    """Send log lines already written before this connection subscribed.
    P9: Capped at BACKLOG_LIMIT lines — informs the client if older lines exist.
    """
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import RunLog

    BACKLOG_LIMIT = 1000

    with session_scope() as db:
        total = db.query(RunLog).filter(RunLog.run_id == run_id).count()

        if total > BACKLOG_LIMIT:
            skipped = total - BACKLOG_LIMIT
            await websocket.send_json({
                "stream": "system",
                "line": f"[scriptmgr] {skipped} earlier line(s) omitted — showing last {BACKLOG_LIMIT}",
            })
            rows = (
                db.query(RunLog)
                .filter(RunLog.run_id == run_id)
                .order_by(RunLog.id.desc())
                .limit(BACKLOG_LIMIT)
                .all()
            )
            rows = list(reversed(rows))
        else:
            rows = (
                db.query(RunLog)
                .filter(RunLog.run_id == run_id)
                .order_by(RunLog.id)
                .all()
            )

        for row in rows:
            await websocket.send_json({"stream": row.stream, "line": row.line})
