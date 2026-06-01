"""Unit tests for the subprocess runner (no Redis / Celery required)."""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap

import pytest

# Patch out Redis so runner doesn't error without it
import unittest.mock as mock


def _write_script(content: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8")
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """Suppress Redis pub/sub calls."""
    monkeypatch.setattr("scriptmgr.executor.runner._get_redis", lambda: None)


@pytest.fixture()
def db(tmp_path):
    """In-memory SQLite DB with all tables created."""
    import os
    os.environ.setdefault("SCRIPTMGR_DATA_DIR", str(tmp_path))
    os.environ["SCRIPTMGR_DB_URL"] = "sqlite://"  # in-memory

    from scriptmgr.core import db as db_module
    db_module._engine = None
    db_module._SessionLocal = None

    from scriptmgr.core.config import get_settings
    import scriptmgr.core.config as cfg_mod
    cfg_mod._settings = None

    from scriptmgr.core.db import init_db
    init_db()
    yield
    db_module._engine = None
    db_module._SessionLocal = None


def _make_run(script_path: str):
    from scriptmgr.core.db import session_scope
    from scriptmgr.core.models import Group, Run, RunStatus, Script

    with session_scope() as s:
        g = Group(name="test")
        s.add(g)
        s.flush()
        sc = Script(
            group_id=g.id,
            name="test-script",
            path=script_path,
            interpreter=sys.executable,
        )
        s.add(sc)
        s.flush()
        run = Run(script_id=sc.id, trigger_source="test", status=RunStatus.QUEUED)
        s.add(run)
        s.flush()
        return run.id


def test_success(db):
    path = _write_script("print('hello')\n")
    try:
        run_id = _make_run(path)
        from scriptmgr.executor.runner import execute_script
        exit_code = execute_script(run_id)
        assert exit_code == 0

        from scriptmgr.core.db import session_scope
        from scriptmgr.core.models import Run, RunLog, RunStatus
        with session_scope() as s:
            run = s.get(Run, run_id)
            assert run.status == RunStatus.SUCCESS
            logs = s.query(RunLog).filter(RunLog.run_id == run_id).all()
            assert any("hello" in l.line for l in logs)
    finally:
        os.unlink(path)


def test_failure(db):
    path = _write_script("import sys; sys.exit(1)\n")
    try:
        run_id = _make_run(path)
        from scriptmgr.executor.runner import execute_script
        exit_code = execute_script(run_id)
        assert exit_code == 1

        from scriptmgr.core.db import session_scope
        from scriptmgr.core.models import Run, RunStatus
        with session_scope() as s:
            run = s.get(Run, run_id)
            assert run.status == RunStatus.FAILED
    finally:
        os.unlink(path)
