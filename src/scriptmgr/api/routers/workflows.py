"""Workflows CRUD + trigger router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Run, RunStatus, Workflow
from scriptmgr.core.schemas import RunOut, WorkflowIn, WorkflowOut

router = APIRouter()


@router.get("/", response_model=list[WorkflowOut])
def list_workflows(group_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Workflow)
    if group_id:
        q = q.filter(Workflow.group_id == group_id)
    return q.order_by(Workflow.name).all()


@router.post("/", response_model=WorkflowOut, status_code=201)
def create_workflow(body: WorkflowIn, db: Session = Depends(get_db)):
    wf = Workflow(**body.model_dump())
    db.add(wf)
    db.flush()
    return wf


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(workflow_id: int, body: WorkflowIn, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(wf, k, v)
    db.add(wf)
    return wf


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    db.delete(wf)


@router.post("/{workflow_id}/run", response_model=RunOut, status_code=202)
def trigger_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    run = Run(workflow_id=workflow_id, trigger_source="manual", status=RunStatus.QUEUED)
    db.add(run)
    db.flush()

    from scriptmgr.executor.tasks import run_workflow_task
    run_workflow_task.delay(run.id)
    return run
