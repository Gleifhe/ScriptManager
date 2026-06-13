"""Web UI router serving HTMX dashboard pages."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func as sqlfunc
from sqlalchemy.orm import Session, joinedload, selectinload

from scriptmgr.core.db import get_db
from scriptmgr.core.models import Group, Run, RunStatus, Schedule, Script, TriggerType, Workflow

router = APIRouter()

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))

# P8: 2-second cache for the dashboard JSON endpoint (polled every 3-5 s)
_dashboard_cache: dict = {}
_dashboard_cache_ts: float = 0.0
_DASHBOARD_TTL = 2.0


def _tmpl(request, name, **ctx):
    return _templates.TemplateResponse(request=request, name=name, context=ctx)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request, db: Session = Depends(get_db)):
    recent_runs = db.query(Run).order_by(Run.created_at.desc()).limit(20).all()
    groups = db.query(Group).order_by(Group.name).all()
    scripts = db.query(Script).order_by(Script.name).all()
    running = db.query(Run).filter(Run.status == RunStatus.RUNNING).count()
    return _tmpl(request, "dashboard.html", runs=recent_runs, groups=groups, scripts=scripts, running=running)


from fastapi.responses import JSONResponse

@router.get("/_api/dashboard", include_in_schema=False)
def dashboard_stats(db: Session = Depends(get_db)):
    """JSON endpoint polled by dashboard auto-refresh. P8: 2-second cache."""
    global _dashboard_cache, _dashboard_cache_ts
    now = time.monotonic()
    if now - _dashboard_cache_ts < _DASHBOARD_TTL and _dashboard_cache:
        return JSONResponse(_dashboard_cache)

    running  = db.query(Run).filter(Run.status == RunStatus.RUNNING).count()
    queued   = db.query(Run).filter(Run.status == RunStatus.QUEUED).count()
    # P3: joinedload prevents N+1 queries — 1 query vs 1 per run
    recent   = (
        db.query(Run)
        .options(joinedload(Run.script), joinedload(Run.workflow))
        .order_by(Run.created_at.desc())
        .limit(20)
        .all()
    )
    finished = [r for r in recent if r.finished_at]
    ok       = [r for r in finished if r.status == RunStatus.SUCCESS]
    rate     = round(len(ok) / len(finished) * 100) if finished else None
    rows = []
    for r in recent:
        name = r.script.name if r.script else (f"🔀 {r.workflow.name}" if r.workflow else "—")
        dur  = None
        if r.started_at and r.finished_at:
            dur = round((r.finished_at - r.started_at).total_seconds(), 1)
        rows.append({
            "id": r.id,
            "name": name,
            "status": r.status.value if r.status else "unknown",
            "trigger": r.trigger_source or "—",
            "started": r.started_at.strftime("%m/%d %H:%M") if r.started_at else "—",
            "duration": f"{dur}s" if dur is not None else "—",
        })
    payload = {"running": running, "queued": queued, "rate": rate,
               "total": len(recent), "rows": rows}
    _dashboard_cache = payload
    _dashboard_cache_ts = now
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@router.get("/help", response_class=HTMLResponse, include_in_schema=False)
def help_page(request: Request):
    return _tmpl(request, "help.html")


@router.get("/reports", response_class=HTMLResponse, include_in_schema=False)
def reports_page(request: Request, db: Session = Depends(get_db)):
    """P2: Use SQL aggregation instead of loading all rows into Python."""
    from datetime import datetime, timedelta, timezone

    # ── Global summary ────────────────────────────────────────────────────────
    summary_row = db.query(
        sqlfunc.count(Run.id).label("total"),
        sqlfunc.sum(case((Run.status == RunStatus.SUCCESS, 1), else_=0)).label("success"),
        sqlfunc.sum(case((Run.status == RunStatus.FAILED,  1), else_=0)).label("failed"),
        sqlfunc.sum(case((Run.status == RunStatus.CANCELLED, 1), else_=0)).label("cancelled"),
        sqlfunc.avg(
            (sqlfunc.julianday(Run.finished_at) - sqlfunc.julianday(Run.started_at)) * 86400
        ).label("avg_sec"),
    ).filter(Run.finished_at.isnot(None)).one()

    total     = summary_row.total or 0
    success   = summary_row.success or 0
    failed    = summary_row.failed or 0
    cancelled = summary_row.cancelled or 0
    avg_dur   = round(summary_row.avg_sec or 0, 1)

    # ── Per-script stats ──────────────────────────────────────────────────────
    # P3: joinedload groups to avoid N+1
    scripts = (
        db.query(Script)
        .options(joinedload(Script.group))
        .order_by(Script.name)
        .all()
    )

    per_script = db.query(
        Run.script_id,
        sqlfunc.count(Run.id).label("total"),
        sqlfunc.sum(case((Run.status == RunStatus.SUCCESS, 1), else_=0)).label("ok"),
        sqlfunc.avg(
            (sqlfunc.julianday(Run.finished_at) - sqlfunc.julianday(Run.started_at)) * 86400
        ).label("avg_sec"),
    ).filter(
        Run.script_id.isnot(None),
        Run.finished_at.isnot(None),
    ).group_by(Run.script_id).all()

    # Last-run status per script via MAX(id) subquery
    from sqlalchemy import select as _select
    last_id_sub = (
        _select(sqlfunc.max(Run.id))
        .where(Run.script_id == Run.script_id)
        .correlate(Run)
    )
    last_runs_raw = (
        db.query(Run.script_id, Run.status)
        .filter(
            Run.id.in_(
                db.query(sqlfunc.max(Run.id)).filter(Run.script_id.isnot(None)).group_by(Run.script_id)
            )
        )
        .all()
    )
    last_status_map = {row.script_id: row.status.value for row in last_runs_raw}
    stats_map = {row.script_id: row for row in per_script}
    script_name = {s.id: s for s in scripts}

    script_stats = []
    for sid, row in stats_map.items():
        s = script_name.get(sid)
        if s is None:
            continue
        script_stats.append({
            "name": s.name,
            "group": s.group.name if s.group else "—",
            "total": row.total,
            "success": row.ok or 0,
            "failed": (row.total or 0) - (row.ok or 0),
            "avg_sec": round(row.avg_sec or 0, 1),
            "last_status": last_status_map.get(sid, "—"),
        })
    script_stats.sort(key=lambda x: x["total"], reverse=True)

    # ── Last 14 days daily counts ─────────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    day_labels = [(today - timedelta(days=i)) for i in range(13, -1, -1)]

    day_rows = db.query(
        sqlfunc.strftime("%Y-%m-%d", Run.created_at).label("day"),
        sqlfunc.count(Run.id).label("cnt"),
    ).filter(Run.created_at >= (today - timedelta(days=13))).group_by("day").all()
    day_map = {row.day: row.cnt for row in day_rows}
    daily = [{"date": str(d), "count": day_map.get(str(d), 0)} for d in day_labels]

    running_now = db.query(Run).filter(Run.status == RunStatus.RUNNING).count()
    queued_now  = db.query(Run).filter(Run.status == RunStatus.QUEUED).count()

    return _tmpl(request, "reports.html",
                 total=total, success=success, failed=failed, cancelled=cancelled,
                 avg_dur=avg_dur, script_stats=script_stats, daily=daily,
                 running_now=running_now, queued_now=queued_now)


@router.get("/services", response_class=HTMLResponse, include_in_schema=False)
def services_page(request: Request, db: Session = Depends(get_db)):
    from scriptmgr.core.models import AlwaysOnService
    services = db.query(AlwaysOnService).all()
    scripts = db.query(Script).order_by(Script.name).all()
    return _tmpl(request, "services.html", services=services, scripts=scripts)


@router.post("/services", include_in_schema=False)
def services_create(
    script_id: int = Form(...),
    service_name: str = Form(...),
    db: Session = Depends(get_db),
):
    from scriptmgr.core.models import AlwaysOnService
    svc = AlwaysOnService(script_id=script_id, service_name=service_name, status="registered")
    db.add(svc); db.commit()
    return RedirectResponse("/services", status_code=303)


@router.post("/services/{svc_id}/delete", include_in_schema=False)
def services_delete(svc_id: int, db: Session = Depends(get_db)):
    from scriptmgr.core.models import AlwaysOnService
    s = db.get(AlwaysOnService, svc_id)
    if s:
        db.delete(s); db.commit()
    return RedirectResponse("/services", status_code=303)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@router.get("/groups", response_class=HTMLResponse, include_in_schema=False)
def groups_list(request: Request, db: Session = Depends(get_db)):
    groups = db.query(Group).order_by(Group.name).all()
    return _tmpl(request, "groups.html", groups=groups)


@router.post("/groups", include_in_schema=False)
def groups_create(request: Request, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    g = Group(name=name, description=description)
    db.add(g); db.commit()
    return RedirectResponse("/groups", status_code=303)


@router.post("/groups/{group_id}/delete", include_in_schema=False)
def groups_delete(group_id: int, db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if g:
        db.delete(g); db.commit()
    return RedirectResponse("/groups", status_code=303)


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

@router.get("/scripts", response_class=HTMLResponse, include_in_schema=False)
def scripts_list(request: Request, db: Session = Depends(get_db)):
    # P3: selectinload avoids N+1 for group association
    scripts = (
        db.query(Script)
        .options(selectinload(Script.group))
        .order_by(Script.name)
        .all()
    )
    groups = db.query(Group).order_by(Group.name).all()
    # P5: single COUNT query instead of lazy-loading all runs per script
    run_count_rows = (
        db.query(Run.script_id, sqlfunc.count(Run.id).label("cnt"))
        .group_by(Run.script_id)
        .all()
    )
    run_counts = {row.script_id: row.cnt for row in run_count_rows}
    return _tmpl(request, "scripts.html", scripts=scripts, groups=groups, run_counts=run_counts)


@router.post("/scripts", include_in_schema=False)
def scripts_create(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    group_id: int = Form(...),
    description: str = Form(""),
    interpreter: str = Form("auto"),
    args_str: str = Form(""),
    timeout_sec: int = Form(0),
    db: Session = Depends(get_db),
):
    import shlex
    # "auto" means blank — let the runner detect from extension
    interp = "" if interpreter == "auto" else interpreter
    args = shlex.split(args_str) if args_str.strip() else []
    s = Script(name=name, path=path, group_id=group_id, description=description,
               interpreter=interp, args=args, timeout_sec=timeout_sec)
    db.add(s); db.commit()
    return RedirectResponse("/scripts", status_code=303)


@router.post("/scripts/{script_id}/run", include_in_schema=False)
def scripts_run(
    script_id: int,
    params: str = Form(""),
    db: Session = Depends(get_db),
):
    import shlex
    from scriptmgr.executor.tasks import run_script_task
    # Parse params string into a list (supports quoted args)
    param_list = shlex.split(params) if params.strip() else []
    run = Run(script_id=script_id, trigger_source="ui", status=RunStatus.QUEUED, params=param_list)
    db.add(run); db.commit(); db.refresh(run)
    run_script_task.delay(run.id)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@router.post("/scripts/{script_id}/delete", include_in_schema=False)
def scripts_delete(script_id: int, db: Session = Depends(get_db)):
    s = db.get(Script, script_id)
    if s:
        db.delete(s); db.commit()
    return RedirectResponse("/scripts", status_code=303)


@router.post("/scripts/{script_id}/edit", include_in_schema=False)
def scripts_edit(
    script_id: int,
    name: str = Form(...),
    path: str = Form(...),
    group_id: int = Form(...),
    description: str = Form(""),
    interpreter: str = Form("auto"),
    args_str: str = Form(""),
    timeout_sec: int = Form(0),
    db: Session = Depends(get_db),
):
    import shlex
    s = db.get(Script, script_id)
    if s:
        s.name = name
        s.path = path
        s.group_id = group_id
        s.description = description
        s.interpreter = "" if interpreter == "auto" else interpreter
        s.args = shlex.split(args_str) if args_str.strip() else []
        s.timeout_sec = timeout_sec
        db.commit()
    return RedirectResponse("/scripts", status_code=303)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@router.get("/runs", response_class=HTMLResponse, include_in_schema=False)
def runs_list(request: Request, db: Session = Depends(get_db)):
    status_filter = request.query_params.get("status", "")
    script_filter = request.query_params.get("script_id", "")
    page = int(request.query_params.get("page", "1"))
    per_page = 50
    q = db.query(Run).order_by(Run.created_at.desc())
    if status_filter:
        q = q.filter(Run.status == status_filter)
    if script_filter:
        q = q.filter(Run.script_id == int(script_filter))
    total = q.count()
    # P3: joinedload prevents N+1 on script/workflow name access in template
    runs = (
        q.options(joinedload(Run.script), joinedload(Run.workflow))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    scripts = db.query(Script).order_by(Script.name).all()
    statuses = [s.value for s in RunStatus]
    return _tmpl(request, "runs.html", runs=runs, scripts=scripts, statuses=statuses,
                 status_filter=status_filter, script_filter=script_filter,
                 page=page, per_page=per_page, total=total)


@router.get("/runs/{run_id}", response_class=HTMLResponse, include_in_schema=False)
def run_detail(run_id: int, request: Request, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    logs = run.logs if run else []
    return _tmpl(request, "run_detail.html", run=run, logs=logs)


@router.post("/runs/{run_id}/cancel", include_in_schema=False)
def runs_cancel(run_id: int, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    r = db.get(Run, run_id)
    if r and r.status in (RunStatus.QUEUED, RunStatus.RUNNING):
        r.status = RunStatus.CANCELLED
        # Always stamp finished_at so the run appears in Reports
        if r.finished_at is None:
            r.finished_at = datetime.now(timezone.utc)
        db.commit()
        # Also kill the subprocess if it is still running
        from scriptmgr.executor.runner import kill_run
        kill_run(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

@router.get("/schedules", response_class=HTMLResponse, include_in_schema=False)
def schedules_list(request: Request, db: Session = Depends(get_db)):
    schedules = db.query(Schedule).order_by(Schedule.id.desc()).all()
    scripts = db.query(Script).order_by(Script.name).all()
    workflows = db.query(Workflow).order_by(Workflow.name).all()
    trigger_types = [t.value for t in TriggerType]
    return _tmpl(request, "schedules.html", schedules=schedules, scripts=scripts,
                 workflows=workflows, trigger_types=trigger_types)


@router.post("/schedules", include_in_schema=False)
def schedules_create(
    request: Request,
    trigger_type: str = Form(...),
    expression: str = Form(...),
    script_id: str = Form(""),
    workflow_id: str = Form(""),
    rerun_delay_sec: int = Form(5),
    db: Session = Depends(get_db),
):
    sched = Schedule(
        trigger_type=TriggerType(trigger_type),
        expression=expression,
        script_id=int(script_id) if script_id else None,
        workflow_id=int(workflow_id) if workflow_id else None,
        rerun_delay_sec=rerun_delay_sec,
    )
    db.add(sched); db.commit()

    from scriptmgr.scheduler.apscheduler import add_schedule
    db.refresh(sched)
    add_schedule(sched)

    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{sched_id}/edit", include_in_schema=False)
def schedules_edit(
    sched_id: int,
    trigger_type: str = Form(...),
    expression: str = Form(...),
    script_id: str = Form(""),
    workflow_id: str = Form(""),
    rerun_delay_sec: int = Form(5),
    db: Session = Depends(get_db),
):
    s = db.get(Schedule, sched_id)
    if s:
        s.trigger_type     = TriggerType(trigger_type)
        s.expression       = expression
        s.script_id        = int(script_id)   if script_id   else None
        s.workflow_id      = int(workflow_id) if workflow_id else None
        s.rerun_delay_sec  = rerun_delay_sec
        db.commit()
        db.refresh(s)
        from scriptmgr.scheduler.apscheduler import add_schedule, remove_schedule
        remove_schedule(sched_id)
        if s.enabled:
            add_schedule(s)
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{sched_id}/toggle", include_in_schema=False)
def schedules_toggle(sched_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, sched_id)
    if s:
        s.enabled = not s.enabled; db.commit()
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{sched_id}/delete", include_in_schema=False)
def schedules_delete(sched_id: int, db: Session = Depends(get_db)):
    s = db.get(Schedule, sched_id)
    if s:
        db.delete(s); db.commit()
    return RedirectResponse("/schedules", status_code=303)


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

@router.get("/workflows", response_class=HTMLResponse, include_in_schema=False)
def workflows_list(request: Request, db: Session = Depends(get_db)):
    workflows = db.query(Workflow).order_by(Workflow.name).all()
    groups = db.query(Group).order_by(Group.name).all()
    return _tmpl(request, "workflows.html", workflows=workflows, groups=groups)


@router.post("/workflows", include_in_schema=False)
def workflows_create(
    name: str = Form(...),
    description: str = Form(""),
    group_id: int = Form(...),
    db: Session = Depends(get_db),
):
    w = Workflow(name=name, description=description, group_id=group_id, dag={"nodes": [], "edges": []})
    db.add(w); db.commit()
    return RedirectResponse("/workflows", status_code=303)


@router.get("/workflows/{wf_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def workflows_edit_page(wf_id: int, request: Request, db: Session = Depends(get_db)):
    w = db.get(Workflow, wf_id)
    if not w:
        return RedirectResponse("/workflows", status_code=303)
    scripts = db.query(Script).order_by(Script.name).all()
    return _tmpl(request, "workflow_edit.html", workflow=w, scripts=scripts)


@router.post("/workflows/{wf_id}/save", include_in_schema=False)
def workflows_save(wf_id: int, dag_json: str = Form(...), db: Session = Depends(get_db)):
    import json as _json
    w = db.get(Workflow, wf_id)
    if w:
        try:
            w.dag = _json.loads(dag_json)
        except Exception:
            pass
        db.commit()
    return RedirectResponse(f"/workflows/{wf_id}/edit", status_code=303)


@router.post("/workflows/{wf_id}/run", include_in_schema=False)
def workflows_run(wf_id: int, db: Session = Depends(get_db)):
    from scriptmgr.executor.tasks import run_workflow_task
    run = Run(workflow_id=wf_id, trigger_source="ui", status=RunStatus.QUEUED)
    db.add(run); db.commit(); db.refresh(run)
    run_workflow_task.delay(run.id)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@router.post("/workflows/{wf_id}/delete", include_in_schema=False)
def workflows_delete(wf_id: int, db: Session = Depends(get_db)):
    w = db.get(Workflow, wf_id)
    if w:
        db.delete(w); db.commit()
    return RedirectResponse("/workflows", status_code=303)

