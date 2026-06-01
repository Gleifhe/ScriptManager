"""Pydantic v2 schemas for request/response serialisation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

class GroupIn(BaseModel):
    name: str
    description: str = ""
    parent_id: int | None = None


class GroupOut(GroupIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

class ScriptIn(BaseModel):
    group_id: int
    name: str
    path: str
    interpreter: str = "python"
    venv: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str = ""
    timeout_sec: int = 0
    tags: list[str] = []
    description: str = ""


class ScriptOut(ScriptIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class ScriptPatch(BaseModel):
    name: str | None = None
    path: str | None = None
    interpreter: str | None = None
    venv: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout_sec: int | None = None
    tags: list[str] | None = None
    description: str | None = None
    group_id: int | None = None


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

class ScheduleIn(BaseModel):
    script_id: int | None = None
    workflow_id: int | None = None
    trigger_type: str
    expression: str
    enabled: bool = True
    rerun_delay_sec: int = 5


class ScheduleOut(ScheduleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

class WorkflowIn(BaseModel):
    group_id: int
    name: str
    description: str = ""
    dag: dict[str, Any]


class WorkflowOut(WorkflowIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    script_id: int | None
    workflow_id: int | None
    parent_run_id: int | None
    status: str
    trigger_source: str
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    host: str
    worker: str
    created_at: datetime


class RunLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    ts: datetime
    stream: str
    line: str


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    script_id: int
    service_name: str
    status: str
    last_heartbeat: datetime | None
    heartbeat_interval_sec: int
    pid: int | None


class HeartbeatIn(BaseModel):
    service_name: str
    status: str = "running"
    pid: int | None = None
