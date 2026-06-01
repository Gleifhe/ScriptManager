"""SMTP email notifications."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run

logger = logging.getLogger(__name__)


def _duration(run: Run) -> str:
    if run.started_at and run.finished_at:
        return f"{int((run.finished_at - run.started_at).total_seconds())}s"
    return "—"


def send_email_notification(run_id: int, recipients: list[str] | None = None) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        return

    with session_scope() as db:
        run = db.get(Run, run_id)
        if not run:
            return
        script_name = run.script.name if run.script else f"workflow:{run.workflow_id}"
        subject = f"[ScriptManager] {script_name} — Run #{run_id} {run.status.value.upper()}"
        body = (
            f"Run ID  : {run_id}\n"
            f"Target  : {script_name}\n"
            f"Status  : {run.status.value}\n"
            f"Exit    : {run.exit_code}\n"
            f"Started : {run.started_at}\n"
            f"Finished: {run.finished_at}\n"
            f"Duration: {_duration(run)}\n"
            f"Host    : {run.host}\n"
        )
        to = recipients or ([settings.smtp_user] if settings.smtp_user else [])

    if not to:
        logger.debug("No recipients configured; skipping email for run %s", run_id)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_user:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("Email sent for run %s to %s", run_id, to)
    except Exception as exc:
        logger.error("Email send failed for run %s: %s", run_id, exc)
        raise
