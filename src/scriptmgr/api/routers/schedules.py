"""Schedules CRUD router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Schedule, TriggerType
from scriptmgr.core.schemas import ScheduleIn, ScheduleOut

router = APIRouter()


@router.get("/", response_model=list[ScheduleOut])
def list_schedules(script_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Schedule)
    if script_id:
        q = q.filter(Schedule.script_id == script_id)
    return q.all()


@router.post("/", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleIn, db: Session = Depends(get_db)):
    try:
        trigger_type = TriggerType(body.trigger_type)
    except ValueError:
        raise HTTPException(400, f"Invalid trigger_type: {body.trigger_type}")

    sched = Schedule(**{**body.model_dump(), "trigger_type": trigger_type})
    db.add(sched)
    db.flush()

    from scriptmgr.scheduler.apscheduler import add_schedule
    add_schedule(sched)
    return sched


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    return s


@router.patch("/{schedule_id}/enable", response_model=ScheduleOut)
def enable_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    s.enabled = True
    db.add(s)
    from scriptmgr.scheduler.apscheduler import add_schedule
    add_schedule(s)
    return s


@router.patch("/{schedule_id}/disable", response_model=ScheduleOut)
def disable_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    s.enabled = False
    db.add(s)
    from scriptmgr.scheduler.apscheduler import remove_schedule
    remove_schedule(schedule_id)
    return s


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    from scriptmgr.scheduler.apscheduler import remove_schedule
    remove_schedule(schedule_id)
    db.delete(s)
