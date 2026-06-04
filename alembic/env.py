"""Alembic environment configuration."""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from scriptmgr.core.config import get_settings, _find_repo_root
from scriptmgr.core.db import Base
import scriptmgr.core.models  # noqa: F401 — register all models with Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migrations_dir() -> str:
    """
    Return the absolute path to the alembic versions directory.

    - Dev/editable install: repo-root/alembic/versions (pyproject.toml present)
    - Production pip install: bundled inside the package at scriptmgr/alembic/versions
    """
    repo = _find_repo_root()
    if repo is not None:
        return str(repo / "alembic")
    # Production: migrations are bundled inside the installed package
    import importlib.resources as _ir
    try:
        # Python 3.9+
        pkg_path = _ir.files("scriptmgr").joinpath("alembic")
        return str(pkg_path)
    except Exception:
        # Fallback: locate via __file__
        return str(Path(__file__).resolve().parent.parent / "src" / "scriptmgr" / "alembic")


# Override script_location so alembic finds migrations wherever the package is installed
config.set_main_option("script_location", _migrations_dir())


def get_url() -> str:
    return get_settings().db_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
