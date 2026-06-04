"""Application configuration loaded from env / .env file."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path | None:
    """
    Walk up from this file to find the repo root (identified by pyproject.toml).
    Returns None when running from a proper pip install (no pyproject.toml present).
    """
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _default_data_dir() -> Path:
    """
    Resolve the default data directory:
      - Dev / editable install   → <repo-root>/data
      - Production pip install   → %PROGRAMDATA%\\ScriptManager  (Windows)
                                   /var/lib/scriptmgr             (Linux/macOS)
    Can always be overridden with SCRIPTMGR_DATA_DIR.
    """
    repo = _find_repo_root()
    if repo is not None:
        # Editable / development install — keep data inside the repo
        return repo / "data"
    # Production install — use the OS-standard application data location
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / "ScriptManager"
    return Path("/var/lib/scriptmgr")


def _default_env_file() -> str:
    """
    Look for .env next to pyproject.toml (dev) or in the data dir (production).
    The data-dir location is resolved early so the env file can itself override
    SCRIPTMGR_DATA_DIR if needed.
    """
    repo = _find_repo_root()
    if repo is not None:
        return str(repo / ".env")
    # Production: env file lives alongside the database
    return str(_default_data_dir() / ".env")


_DEFAULT_DATA_DIR = _default_data_dir()
_DEFAULT_DB_URL = f"sqlite:///{(_DEFAULT_DATA_DIR / 'scriptmgr.db').as_posix()}"
_DEFAULT_ENV_FILE = _default_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCRIPTMGR_",
        env_file=_DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=_DEFAULT_DATA_DIR)
    db_url: str = _DEFAULT_DB_URL
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"

    # Executor mode: "inproc" (default — workstation, no Redis needed)
    #                "celery" (distributed — requires Redis + worker process)
    executor_mode: str = "inproc"

    # Celery / Redis (only used when executor_mode == "celery")
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    worker_concurrency: int = 4

    # Notifications
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "scriptmgr@localhost"
    teams_webhook: str = ""
    slack_webhook: str = ""

    log_retention_days: int = 30

    def ensure_dirs(self) -> None:
        for sub in ("", "logs", "runs", "artifacts"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
