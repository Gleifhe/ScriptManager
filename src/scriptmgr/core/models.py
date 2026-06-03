"""SQLAlchemy ORM models."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TriggerType(str, enum.Enum):
    MANUAL = "manual"
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"
    CONTINUOUS = "continuous"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    parent: Mapped["Group | None"] = relationship(
        "Group", remote_side="Group.id", back_populates="children"
    )
    children: Mapped[list["Group"]] = relationship("Group", back_populates="parent")
    scripts: Mapped[list["Script"]] = relationship(
        "Script", back_populates="group", cascade="all, delete-orphan"
    )
    workflows: Mapped[list["Workflow"]] = relationship("Workflow", back_populates="group")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    path: Mapped[str] = mapped_column(String(1000))
    interpreter: Mapped[str] = mapped_column(String(500), default="python")
    venv: Mapped[str] = mapped_column(String(500), default="")
    args: Mapped[list] = mapped_column(JSON, default=list)
    env: Mapped[dict] = mapped_column(JSON, default=dict)
    cwd: Mapped[str] = mapped_column(String(1000), default="")
    timeout_sec: Mapped[int] = mapped_column(Integer, default=0)  # 0 = no timeout
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped[Group] = relationship("Group", back_populates="scripts")
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="script", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="script")
    service: Mapped["AlwaysOnService | None"] = relationship("AlwaysOnService", back_populates="script")

    __table_args__ = (Index("ix_scripts_group_name", "group_id", "name", unique=True),)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("scripts.id"), nullable=True, index=True)
    workflow_id: Mapped[int | None] = mapped_column(ForeignKey("workflows.id"), nullable=True, index=True)
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType))
    expression: Mapped[str] = mapped_column(String(500))  # cron / seconds / ISO-date
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rerun_delay_sec: Mapped[int] = mapped_column(Integer, default=5)  # for CONTINUOUS
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    script: Mapped["Script | None"] = relationship("Script", back_populates="schedules")
    workflow: Mapped["Workflow | None"] = relationship("Workflow", back_populates="schedules")


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # dag JSON structure:
    # {
    #   "nodes": [{"id": "n1", "script_id": 1, "retry": 0, "timeout_sec": 0, "label": ""}],
    #   "edges": [{"from": "n1", "to": "n2", "on": "success|failure|always"}]
    # }
    dag: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped[Group] = relationship("Group", back_populates="workflows")
    schedules: Mapped[list[Schedule]] = relationship("Schedule", back_populates="workflow")
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="workflow")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("scripts.id"), nullable=True, index=True)
    workflow_id: Mapped[int | None] = mapped_column(ForeignKey("workflows.id"), nullable=True, index=True)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(50), default="manual")
    params: Mapped[list] = mapped_column(JSON, default=list)  # per-run extra args
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.QUEUED, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    host: Mapped[str] = mapped_column(String(200), default="")
    worker: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    script: Mapped["Script | None"] = relationship("Script", back_populates="runs")
    workflow: Mapped["Workflow | None"] = relationship("Workflow", back_populates="runs")
    logs: Mapped[list["RunLog"]] = relationship("RunLog", back_populates="run", cascade="all, delete-orphan")


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    stream: Mapped[str] = mapped_column(String(10), default="stdout")  # stdout | stderr | system
    line: Mapped[str] = mapped_column(Text)

    run: Mapped[Run] = relationship("Run", back_populates="logs")

    # P10: composite index speeds up log fetches (filter run_id, order by id)
    __table_args__ = (Index("ix_run_logs_run_id_id", "run_id", "id"),)


class AlwaysOnService(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), unique=True)
    service_name: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_interval_sec: Mapped[int] = mapped_column(Integer, default=60)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    script: Mapped[Script] = relationship("Script", back_populates="service")
