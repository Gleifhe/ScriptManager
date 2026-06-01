"""Scripts CRUD + manual trigger router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Run, RunStatus, Script
from scriptmgr.core.schemas import RunOut, ScriptIn, ScriptOut, ScriptPatch

router = APIRouter()


@router.get("/", response_model=list[ScriptOut])
def list_scripts(group_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Script)
    if group_id:
        q = q.filter(Script.group_id == group_id)
    return q.order_by(Script.name).all()


@router.post("/", response_model=ScriptOut, status_code=201)
def create_script(body: ScriptIn, db: Session = Depends(get_db)):
    script = Script(**body.model_dump())
    db.add(script)
    db.flush()
    return script


@router.get("/{script_id}", response_model=ScriptOut)
def get_script(script_id: int, db: Session = Depends(get_db)):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script not found")
    return s


@router.patch("/{script_id}", response_model=ScriptOut)
def update_script(script_id: int, body: ScriptPatch, db: Session = Depends(get_db)):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.add(s)
    return s


@router.delete("/{script_id}", status_code=204)
def delete_script(script_id: int, db: Session = Depends(get_db)):
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script not found")
    db.delete(s)


@router.post("/{script_id}/run", response_model=RunOut, status_code=202)
def trigger_script(script_id: int, db: Session = Depends(get_db)):
    """Manually trigger an immediate run of a script."""
    s = db.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script not found")

    run = Run(script_id=script_id, trigger_source="manual", status=RunStatus.QUEUED)
    db.add(run)
    db.flush()
    run_id = run.id

    from scriptmgr.executor.tasks import run_script_task
    run_script_task.delay(run_id)
    return run
