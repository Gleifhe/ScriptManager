"""Windows service installer for the main ScriptManager orchestrator.

Uses NSSM (Non-Sucking Service Manager) to wrap the FastAPI/uvicorn process.
Download NSSM from https://nssm.cc and place nssm.exe on PATH (or set NSSM_PATH).

Usage (run as Administrator):
    scriptmgr service install
    scriptmgr service start
    scriptmgr service stop
    scriptmgr service uninstall
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "ScriptManager"
SERVICE_DISPLAY = "ScriptManager Orchestration Service"
SERVICE_DESCRIPTION = (
    "Manages, schedules, and reports on Python AI/automation scripts. "
    "Hosts FastAPI API, APScheduler, and a local Celery worker."
)


def _nssm() -> str:
    """Return the path to nssm.exe, checking PATH and a local bin/ directory."""
    env_path = os.environ.get("NSSM_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    local = Path(__file__).parent / "bin" / "nssm.exe"
    if local.exists():
        return str(local)
    return "nssm"  # assume it's on PATH


def _python() -> str:
    return sys.executable


def _app_dir() -> str:
    """Root of the installed package / project."""
    return str(Path(__file__).resolve().parents[3])


def install_service(data_dir: str = "") -> None:
    """Install ScriptManager as a Windows service via NSSM."""
    nssm = _nssm()
    python = _python()
    app_dir = _app_dir()
    log_dir = Path(data_dir or os.path.join(app_dir, "data", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    # Build the command: python -m scriptmgr.service.main_service
    cmds = [
        [nssm, "install", SERVICE_NAME, python, "-m", "scriptmgr.service.main_service"],
        [nssm, "set", SERVICE_NAME, "DisplayName", SERVICE_DISPLAY],
        [nssm, "set", SERVICE_NAME, "Description", SERVICE_DESCRIPTION],
        [nssm, "set", SERVICE_NAME, "AppDirectory", app_dir],
        [nssm, "set", SERVICE_NAME, "AppStdout", str(log_dir / "service-stdout.log")],
        [nssm, "set", SERVICE_NAME, "AppStderr", str(log_dir / "service-stderr.log")],
        [nssm, "set", SERVICE_NAME, "AppRotateFiles", "1"],
        [nssm, "set", SERVICE_NAME, "AppRotateBytes", "10485760"],  # 10 MB
        [nssm, "set", SERVICE_NAME, "Start", "SERVICE_AUTO_START"],
    ]
    for cmd in cmds:
        _run(cmd)
    print(f"[ScriptManager] Service '{SERVICE_NAME}' installed. Run: scriptmgr service start")


def start_service() -> None:
    _run([_nssm(), "start", SERVICE_NAME])
    print(f"[ScriptManager] Service '{SERVICE_NAME}' started.")


def stop_service() -> None:
    _run([_nssm(), "stop", SERVICE_NAME])
    print(f"[ScriptManager] Service '{SERVICE_NAME}' stopped.")


def uninstall_service() -> None:
    stop_service()
    _run([_nssm(), "remove", SERVICE_NAME, "confirm"])
    print(f"[ScriptManager] Service '{SERVICE_NAME}' removed.")


def status_service() -> None:
    _run([_nssm(), "status", SERVICE_NAME])


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
