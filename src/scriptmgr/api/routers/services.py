"""Always-on services: heartbeat and status router."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import AlwaysOnService
from scriptmgr.core.schemas import HeartbeatIn, ServiceOut

router = APIRouter()


@router.get("/", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(AlwaysOnService).all()


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(service_id: int, db: Session = Depends(get_db)):
    s = db.get(AlwaysOnService, service_id)
    if not s:
        raise HTTPException(404, "Service not found")
    return s


@router.post("/heartbeat", status_code=204)
def heartbeat(body: HeartbeatIn, db: Session = Depends(get_db)):
    """Receive a heartbeat ping from an always-on service wrapper."""
    svc = db.query(AlwaysOnService).filter(AlwaysOnService.service_name == body.service_name).first()
    if not svc:
        raise HTTPException(404, f"Service '{body.service_name}' not registered")
    svc.last_heartbeat = datetime.now(timezone.utc)
    svc.status = body.status
    if body.pid is not None:
        svc.pid = body.pid
    db.add(svc)
