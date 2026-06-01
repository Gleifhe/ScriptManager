"""Microsoft Teams and Slack webhook notifications (no 3rd-party SDK required)."""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import session_scope
from scriptmgr.core.models import Run

logger = logging.getLogger(__name__)


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")


def _duration(run: Run) -> str:
    if run.started_at and run.finished_at:
        return f"{int((run.finished_at - run.started_at).total_seconds())}s"
    return "—"


def send_webhook_notification(run_id: int) -> None:
    settings = get_settings()
    if not settings.teams_webhook and not settings.slack_webhook:
        return

    with session_scope() as db:
        run = db.get(Run, run_id)
        if not run:
            return
        script_name = run.script.name if run.script else f"workflow:{run.workflow_id}"
        title = f"ScriptManager: {script_name} — Run #{run_id} {run.status.value.upper()}"
        body = (
            f"**Status:** {run.status.value}  \n"
            f"**Exit code:** {run.exit_code}  \n"
            f"**Duration:** {_duration(run)}  \n"
            f"**Host:** {run.host}"
        )

    if settings.teams_webhook:
        try:
            _post(
                settings.teams_webhook,
                {
                    "type": "message",
                    "attachments": [
                        {
                            "contentType": "application/vnd.microsoft.card.adaptive",
                            "content": {
                                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                "type": "AdaptiveCard",
                                "version": "1.3",
                                "body": [
                                    {"type": "TextBlock", "weight": "Bolder", "text": title},
                                    {"type": "TextBlock", "text": body, "wrap": True},
                                ],
                            },
                        }
                    ],
                },
            )
        except Exception as exc:
            logger.error("Teams webhook failed for run %s: %s", run_id, exc)

    if settings.slack_webhook:
        try:
            _post(settings.slack_webhook, {"text": f"*{title}*\n{body}"})
        except Exception as exc:
            logger.error("Slack webhook failed for run %s: %s", run_id, exc)
