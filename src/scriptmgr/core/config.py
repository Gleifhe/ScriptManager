"""Application configuration loaded from env / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCRIPTMGR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("./data"))
    db_url: str = "sqlite:///./data/scriptmgr.db"
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
