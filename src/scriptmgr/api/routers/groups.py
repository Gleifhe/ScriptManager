"""Groups CRUD router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Group
from scriptmgr.core.schemas import GroupIn, GroupOut

router = APIRouter()


@router.get("/", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(Group).order_by(Group.name).all()


@router.post("/", response_model=GroupOut, status_code=201)
def create_group(body: GroupIn, db: Session = Depends(get_db)):
    group = Group(**body.model_dump())
    db.add(group)
    db.flush()
    return group


@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    return g


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(group_id: int, body: GroupIn, db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.add(g)
    return g


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    db.delete(g)
