"""Application configuration loaded from env / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path:
    """
    Walk up from this file to find the repo root (identified by pyproject.toml).
    Falls back to the current working directory so the package works when
    installed via 'pip install' (non-editable) into any location.
    """
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


_REPO_ROOT = _find_repo_root()
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
_DEFAULT_DB_URL = f"sqlite:///{(_DEFAULT_DATA_DIR / 'scriptmgr.db').as_posix()}"
_DEFAULT_ENV_FILE = str(_REPO_ROOT / ".env")


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
