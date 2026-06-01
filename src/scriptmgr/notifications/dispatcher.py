"""Dispatch failure/completion notifications for a run."""
from __future__ import annotations

import logging

from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run, RunStatus

logger = logging.getLogger(__name__)


def dispatch_run_notification(run_id: int) -> None:
    """Send email + webhook alerts for non-success runs."""
    with session_scope() as db:
        run = db.get(Run, run_id)
        if not run:
            return
        if run.status == RunStatus.SUCCESS:
            return  # Only alert on non-success by default

    from scriptmgr.notifications.email import send_email_notification
    from scriptmgr.notifications.webhooks import send_webhook_notification

    for fn, label in ((send_email_notification, "email"), (send_webhook_notification, "webhook")):
        try:
            fn(run_id)
        except Exception as exc:
            logger.warning("%s notification failed for run %s: %s", label, run_id, exc)
