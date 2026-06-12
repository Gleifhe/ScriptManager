"""FastAPI application factory and lifespan handler."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scriptmgr.core.config import get_settings
from scriptmgr.core.db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    logger.info(
        "ScriptManager API starting on %s:%s (executor=%s)",
        settings.host, settings.port, settings.executor_mode,
    )
    init_db()

    # Register the running event loop so worker threads can publish into asyncio queues
    import asyncio
    from scriptmgr.executor.log_hub import log_hub
    log_hub.set_loop(asyncio.get_running_loop())

    from scriptmgr.scheduler.apscheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()

    # Shut down the in-process worker pool (no-op if unused)
    from scriptmgr.executor.runtime import shutdown_executor
    shutdown_executor()
    logger.info("ScriptManager API stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="ScriptManager",
        version="0.1.0",
        description="Orchestration service for Python AI/automation scripts.",
        lifespan=lifespan,
    )

    # Optional API key middleware — protects /api/* and /ws/* routes.
    # Web UI routes (/dashboard, /scripts, etc.) are always accessible.
    # Enabled only when SCRIPTMGR_API_KEY is set in .env / environment.
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next):
            settings = get_settings()
            key = settings.api_key
            if not key:
                return await call_next(request)  # disabled — no key configured
            path = request.url.path
            # Only guard /api/* and /ws/* — leave the web UI open
            if not (path.startswith("/api/") or path.startswith("/ws/")):
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            if auth == f"Bearer {key}":
                return await call_next(request)
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    application.add_middleware(ApiKeyMiddleware)

    # API routers
    from scriptmgr.api.routers import browse, groups, runs, schedules, scripts, services, workflows

    application.include_router(groups.router, prefix="/api/groups", tags=["Groups"])
    application.include_router(scripts.router, prefix="/api/scripts", tags=["Scripts"])
    application.include_router(schedules.router, prefix="/api/schedules", tags=["Schedules"])
    application.include_router(workflows.router, prefix="/api/workflows", tags=["Workflows"])
    application.include_router(runs.router, prefix="/api/runs", tags=["Runs"])
    application.include_router(services.router, prefix="/api/services", tags=["Services"])
    application.include_router(browse.router, prefix="/api/browse", tags=["Browse"])

    # WebSocket log streaming
    from scriptmgr.api.websocket import router as ws_router
    application.include_router(ws_router)

    # Web UI (HTMX)
    from scriptmgr.api.ui import router as ui_router
    application.include_router(ui_router)

    return application


app = create_app()
