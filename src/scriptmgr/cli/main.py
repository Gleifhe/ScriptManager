"""ScriptManager CLI — entry point: ``scriptmgr``."""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(
    name="scriptmgr",
    help="ScriptManager: orchestrate, schedule and report on Python scripts.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Sub-command groups
# ---------------------------------------------------------------------------
group_app = typer.Typer(help="Manage script groups/folders.", no_args_is_help=True)
script_app = typer.Typer(help="Manage scripts.", no_args_is_help=True)
schedule_app = typer.Typer(help="Manage schedules.", no_args_is_help=True)
workflow_app = typer.Typer(help="Manage DAG workflows.", no_args_is_help=True)
run_app = typer.Typer(help="View and manage runs.", no_args_is_help=True)
service_app = typer.Typer(help="Windows service management.", no_args_is_help=True)
always_on_app = typer.Typer(help="Per-script always-on service wrappers.", no_args_is_help=True)

app.add_typer(group_app, name="group")
app.add_typer(script_app, name="script")
app.add_typer(schedule_app, name="schedule")
app.add_typer(workflow_app, name="workflow")
app.add_typer(run_app, name="run")
app.add_typer(service_app, name="service")
app.add_typer(always_on_app, name="always-on")


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("", help="Override SCRIPTMGR_HOST"),
    port: int = typer.Option(0, help="Override SCRIPTMGR_PORT"),
    reload: bool = typer.Option(False, "--reload", help="Hot-reload on code changes (dev mode)"),
):
    """Start the API server + scheduler (foreground)."""
    import uvicorn
    from scriptmgr.core.config import get_settings
    from scriptmgr.core.db import init_db
    from scriptmgr.scheduler.apscheduler import start_scheduler

    settings = get_settings()
    init_db()
    if not reload:
        start_scheduler()
    uvicorn.run(
        "scriptmgr.api.app:app",
        host=host or settings.host,
        port=port or settings.port,
        log_level=settings.log_level.lower(),
        reload=reload,
    )


@app.command()
def worker(
    concurrency: int = typer.Option(0, help="Worker concurrency (default from settings)"),
):
    """Start a Celery worker (distributed mode only)."""
    from scriptmgr.core.config import get_settings

    settings = get_settings()
    mode = (settings.executor_mode or "inproc").lower()
    if mode != "celery":
        typer.secho(
            f"Executor mode is '{mode}'. The 'worker' command is only used in 'celery' mode.\n"
            "In 'inproc' mode the API server runs scripts itself — no separate worker needed.\n"
            "Set SCRIPTMGR_EXECUTOR_MODE=celery in your .env to enable distributed mode.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    try:
        from scriptmgr.executor.celery_app import celery_app
    except ImportError:
        typer.secho(
            "Celery is not installed. Install with: pip install -e .[celery]",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    c = concurrency or settings.worker_concurrency
    celery_app.worker_main(
        argv=["worker", "--loglevel=info", f"--concurrency={c}"]
    )


@app.command("db")
def db_cmd(
    action: str = typer.Argument(..., help="init | reset"),
):
    """Database management (init, reset)."""
    from scriptmgr.core.db import get_engine, init_db

    if action == "init":
        init_db()
        rprint("[green]Database initialised.[/green]")
    elif action == "reset":
        typer.confirm("This will DROP and recreate all tables. Continue?", abort=True)
        from scriptmgr.core.db import Base
        Base.metadata.drop_all(bind=get_engine())
        init_db()
        rprint("[green]Database reset.[/green]")
    else:
        rprint(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# group commands
# ---------------------------------------------------------------------------

@group_app.command("list")
def group_list():
    """List all groups."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Group

    with session_scope() as db:
        groups = db.query(Group).order_by(Group.name).all()

    t = Table("ID", "Name", "Description", "Parent")
    for g in groups:
        t.add_row(str(g.id), g.name, g.description or "—", str(g.parent_id or "—"))
    rprint(t)


@group_app.command("add")
def group_add(
    name: str = typer.Argument(...),
    description: str = typer.Option("", "-d", "--description"),
    parent_id: Optional[int] = typer.Option(None, "-p", "--parent"),
):
    """Add a group."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Group

    with session_scope() as db:
        g = Group(name=name, description=description, parent_id=parent_id)
        db.add(g)
        db.flush()
        rprint(f"[green]Created group #{g.id}: {g.name}[/green]")


@group_app.command("delete")
def group_delete(group_id: int):
    """Delete a group."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Group

    typer.confirm(f"Delete group {group_id}?", abort=True)
    with session_scope() as db:
        g = db.get(Group, group_id)
        if not g:
            rprint("[red]Group not found.[/red]")
            raise typer.Exit(1)
        db.delete(g)
    rprint("[green]Deleted.[/green]")


# ---------------------------------------------------------------------------
# script commands
# ---------------------------------------------------------------------------

@script_app.command("list")
def script_list(group_id: Optional[int] = typer.Option(None, "-g")):
    """List scripts."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Script

    with session_scope() as db:
        q = db.query(Script)
        if group_id:
            q = q.filter(Script.group_id == group_id)
        scripts = q.order_by(Script.name).all()

    t = Table("ID", "Group", "Name", "Path", "Interpreter", "Tags")
    for s in scripts:
        t.add_row(str(s.id), str(s.group_id), s.name, s.path, s.interpreter, ", ".join(s.tags or []))
    rprint(t)


@script_app.command("add")
def script_add(
    path: str = typer.Argument(..., help="Path to the .py script"),
    group: int = typer.Option(..., "-g", "--group", help="Group ID"),
    name: str = typer.Option("", "-n", "--name", help="Script name (default: filename)"),
    interpreter: str = typer.Option("python", "--interpreter"),
    venv: str = typer.Option("", "--venv", help="Path to virtualenv"),
    timeout: int = typer.Option(0, "--timeout", help="Timeout in seconds (0=none)"),
    description: str = typer.Option("", "-d", "--description"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
):
    """Register a script."""
    from pathlib import Path as P

    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Script

    script_name = name or P(path).stem
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    with session_scope() as db:
        s = Script(
            group_id=group,
            name=script_name,
            path=path,
            interpreter=interpreter,
            venv=venv,
            timeout_sec=timeout,
            description=description,
            tags=tag_list,
        )
        db.add(s)
        db.flush()
        rprint(f"[green]Registered script #{s.id}: {s.name}[/green]")


@script_app.command("run")
def script_run(
    name_or_id: str = typer.Argument(..., help="Script name or ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Tail logs until completion"),
):
    """Manually trigger a script run."""
    import time

    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Run, RunLog, RunStatus, Script

    with session_scope() as db:
        try:
            sid = int(name_or_id)
            script = db.get(Script, sid)
        except ValueError:
            script = db.query(Script).filter(Script.name == name_or_id).first()
        if not script:
            rprint(f"[red]Script '{name_or_id}' not found.[/red]")
            raise typer.Exit(1)
        run = Run(script_id=script.id, trigger_source="cli", status=RunStatus.QUEUED)
        db.add(run)
        db.flush()
        run_id = run.id

    from scriptmgr.executor.tasks import run_script_task
    run_script_task.delay(run_id)
    rprint(f"[blue]Queued run #{run_id} for '{name_or_id}'[/blue]")

    if watch:
        seen = 0
        rprint("[dim]--- live log ---[/dim]")
        while True:
            with session_scope() as db:
                rows = (
                    db.query(RunLog)
                    .filter(RunLog.run_id == run_id, RunLog.id > seen)
                    .order_by(RunLog.id)
                    .all()
                )
                for row in rows:
                    colour = "red" if row.stream == "stderr" else "white"
                    rprint(f"[{colour}]{row.line}[/{colour}]")
                    seen = row.id
                run_obj = db.get(Run, run_id)
                if run_obj and run_obj.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                    rprint(f"\n[bold]Run finished: {run_obj.status.value}[/bold]")
                    break
            time.sleep(0.5)


@script_app.command("delete")
def script_delete(script_id: int):
    """Delete a script registration."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Script

    typer.confirm(f"Delete script {script_id}?", abort=True)
    with session_scope() as db:
        s = db.get(Script, script_id)
        if not s:
            rprint("[red]Script not found.[/red]")
            raise typer.Exit(1)
        db.delete(s)
    rprint("[green]Deleted.[/green]")


# ---------------------------------------------------------------------------
# schedule commands
# ---------------------------------------------------------------------------

@schedule_app.command("list")
def schedule_list():
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Schedule

    with session_scope() as db:
        rows = db.query(Schedule).all()

    t = Table("ID", "Script", "Workflow", "Type", "Expression", "Enabled")
    for s in rows:
        t.add_row(
            str(s.id), str(s.script_id or "—"), str(s.workflow_id or "—"),
            s.trigger_type.value, s.expression, "✓" if s.enabled else "✗",
        )
    rprint(t)


@schedule_app.command("add")
def schedule_add(
    trigger_type: str = typer.Option(..., "--type", help="cron | interval | date | continuous"),
    expression: str = typer.Option(..., "--expr", help="Cron string / seconds / ISO date"),
    script_id: Optional[int] = typer.Option(None, "--script"),
    workflow_id: Optional[int] = typer.Option(None, "--workflow"),
    delay: int = typer.Option(5, "--rerun-delay", help="Continuous rerun delay (seconds)"),
):
    """Add a schedule."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Schedule, TriggerType
    from scriptmgr.scheduler.apscheduler import add_schedule

    with session_scope() as db:
        s = Schedule(
            script_id=script_id,
            workflow_id=workflow_id,
            trigger_type=TriggerType(trigger_type),
            expression=expression,
            rerun_delay_sec=delay,
        )
        db.add(s)
        db.flush()
        add_schedule(s)
        rprint(f"[green]Created schedule #{s.id}[/green]")


@schedule_app.command("delete")
def schedule_delete(schedule_id: int):
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Schedule
    from scriptmgr.scheduler.apscheduler import remove_schedule

    typer.confirm(f"Delete schedule {schedule_id}?", abort=True)
    with session_scope() as db:
        s = db.get(Schedule, schedule_id)
        if not s:
            rprint("[red]Not found.[/red]")
            raise typer.Exit(1)
        remove_schedule(schedule_id)
        db.delete(s)
    rprint("[green]Deleted.[/green]")


# ---------------------------------------------------------------------------
# run commands
# ---------------------------------------------------------------------------

@run_app.command("list")
def run_list(
    status: Optional[str] = typer.Option(None, "--status"),
    limit: int = typer.Option(20, "--limit"),
):
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Run

    with session_scope() as db:
        q = db.query(Run).order_by(Run.created_at.desc())
        if status:
            q = q.filter(Run.status == status)
        runs = q.limit(limit).all()

    t = Table("ID", "Script", "Trigger", "Status", "Started", "Exit")
    for r in runs:
        name = r.script.name if r.script else f"wf:{r.workflow_id}"
        t.add_row(
            str(r.id), name, r.trigger_source, r.status.value,
            str(r.started_at or "—"), str(r.exit_code if r.exit_code is not None else "—"),
        )
    rprint(t)


@run_app.command("logs")
def run_logs(
    run_id: int,
    stream: Optional[str] = typer.Option(None, "--stream", help="stdout | stderr | system"),
):
    """Print logs for a run."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import RunLog

    with session_scope() as db:
        q = db.query(RunLog).filter(RunLog.run_id == run_id).order_by(RunLog.id)
        if stream:
            q = q.filter(RunLog.stream == stream)
        for row in q.all():
            colour = "red" if row.stream == "stderr" else ("yellow" if row.stream == "system" else "white")
            rprint(f"[{colour}]{row.line}[/{colour}]")


@run_app.command("cancel")
def run_cancel(run_id: int):
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Run, RunStatus

    with session_scope() as db:
        r = db.get(Run, run_id)
        if not r:
            rprint("[red]Run not found.[/red]")
            raise typer.Exit(1)
        r.status = RunStatus.CANCELLED
        db.add(r)
    rprint(f"[green]Run #{run_id} marked cancelled.[/green]")


# ---------------------------------------------------------------------------
# workflow commands
# ---------------------------------------------------------------------------

@workflow_app.command("list")
def workflow_list():
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Workflow

    with session_scope() as db:
        rows = db.query(Workflow).order_by(Workflow.name).all()

    t = Table("ID", "Group", "Name", "Description")
    for w in rows:
        t.add_row(str(w.id), str(w.group_id), w.name, w.description or "—")
    rprint(t)


@workflow_app.command("add")
def workflow_add(
    json_file: str = typer.Argument(..., help="Path to workflow DAG JSON file"),
    group: int = typer.Option(..., "-g", "--group"),
    name: str = typer.Option(..., "-n", "--name"),
    description: str = typer.Option("", "-d"),
):
    """Register a workflow from a DAG JSON file."""
    import json
    from pathlib import Path as P

    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Workflow

    dag = json.loads(P(json_file).read_text())
    with session_scope() as db:
        wf = Workflow(group_id=group, name=name, description=description, dag=dag)
        db.add(wf)
        db.flush()
        rprint(f"[green]Created workflow #{wf.id}: {wf.name}[/green]")


@workflow_app.command("run")
def workflow_run(workflow_id: int):
    """Manually trigger a workflow."""
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Run, RunStatus
    from scriptmgr.executor.tasks import run_workflow_task

    with session_scope() as db:
        run = Run(workflow_id=workflow_id, trigger_source="cli", status=RunStatus.QUEUED)
        db.add(run)
        db.flush()
        run_id = run.id
    run_workflow_task.delay(run_id)
    rprint(f"[blue]Queued workflow run #{run_id}[/blue]")


# ---------------------------------------------------------------------------
# service commands
# ---------------------------------------------------------------------------

@service_app.command("install")
def service_install(data_dir: str = typer.Option("", "--data-dir")):
    """Install ScriptManager as a Windows service (requires Administrator)."""
    from scriptmgr.service.installer import install_service
    install_service(data_dir=data_dir)


@service_app.command("start")
def service_start():
    from scriptmgr.service.installer import start_service
    start_service()


@service_app.command("stop")
def service_stop():
    from scriptmgr.service.installer import stop_service
    stop_service()


@service_app.command("uninstall")
def service_uninstall():
    typer.confirm("Uninstall ScriptManager Windows service?", abort=True)
    from scriptmgr.service.installer import uninstall_service
    uninstall_service()


@service_app.command("status")
def service_status():
    from scriptmgr.service.installer import status_service
    status_service()


# ---------------------------------------------------------------------------
# always-on commands
# ---------------------------------------------------------------------------

@always_on_app.command("install")
def always_on_install(
    service_name: str = typer.Argument(..., help="Windows service name"),
    script: str = typer.Option(..., "--script", help="Path to the Python script"),
    interpreter: str = typer.Option("python", "--interpreter"),
    heartbeat: int = typer.Option(60, "--heartbeat", help="Heartbeat interval (seconds)"),
    heartbeat_url: str = typer.Option(
        "http://localhost:8765/api/services/heartbeat", "--heartbeat-url"
    ),
    output_dir: str = typer.Option(".", "--output-dir", help="Where to write generated files"),
    nssm: str = typer.Option("nssm", "--nssm"),
    log_dir: str = typer.Option(r"C:\ProgramData\ScriptManager\logs", "--log-dir"),
):
    """Generate and install an always-on Windows service wrapper for a script."""
    from pathlib import Path as P

    from scriptmgr.service.always_on import generate_always_on_service

    files = generate_always_on_service(
        service_name=service_name,
        script_path=script,
        interpreter=interpreter,
        heartbeat_url=heartbeat_url,
        heartbeat_interval=heartbeat,
        output_dir=output_dir,
        nssm_path=nssm,
        log_dir=log_dir,
    )
    out = P(output_dir)
    for filename, content in files.items():
        fpath = out / filename
        fpath.write_text(content, encoding="utf-8")
        rprint(f"[green]Generated {fpath}[/green]")

    ps1 = out / [k for k in files if k.endswith(".ps1")][0]
    rprint(f"\n[bold]Run as Administrator:[/bold]\n  pwsh {ps1}")


if __name__ == "__main__":
    app()
