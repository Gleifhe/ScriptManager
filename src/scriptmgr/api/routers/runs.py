"""Runs list, detail, logs, cancel, and stats router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Run, RunLog, RunStatus
from scriptmgr.core.schemas import RunLogOut, RunOut

router = APIRouter()


@router.get("/", response_model=list[RunOut])
def list_runs(
    status: str | None = None,
    script_id: int | None = None,
    workflow_id: int | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Run).order_by(Run.created_at.desc())
    if status:
        q = q.filter(Run.status == status)
    if script_id:
        q = q.filter(Run.script_id == script_id)
    if workflow_id:
        q = q.filter(Run.workflow_id == workflow_id)
    return q.offset(offset).limit(limit).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@router.get("/{run_id}/logs", response_model=list[RunLogOut])
def get_run_logs(
    run_id: int,
    stream: str | None = None,
    offset: int = 0,
    limit: int = Query(default=1000, le=10000),
    db: Session = Depends(get_db),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "Run not found")
    q = db.query(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.id)
    if stream:
        q = q.filter(RunLog.stream == stream)
    return q.offset(offset).limit(limit).all()


@router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    if r.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        raise HTTPException(409, f"Run is already {r.status.value}")
    r.status = RunStatus.CANCELLED
    db.add(r)
    return r


@router.get("/{run_id}/stats")
def run_stats(script_id: int, db: Session = Depends(get_db)):
    """Per-script run history stats: success rate, p50/p95 duration."""
    from sqlalchemy import func

    rows = (
        db.query(Run)
        .filter(Run.script_id == script_id, Run.finished_at.isnot(None))
        .all()
    )
    if not rows:
        return {"count": 0}

    durations = sorted(
        int((r.finished_at - r.started_at).total_seconds())
        for r in rows
        if r.started_at and r.finished_at
    )
    success = sum(1 for r in rows if r.status == RunStatus.SUCCESS)

    def _pct(lst, p):
        idx = int(len(lst) * p / 100)
        return lst[min(idx, len(lst) - 1)]

    return {
        "count": len(rows),
        "success_rate": round(success / len(rows) * 100, 1),
        "p50_sec": _pct(durations, 50) if durations else None,
        "p95_sec": _pct(durations, 95) if durations else None,
        "last_status": rows[-1].status.value,
    }
