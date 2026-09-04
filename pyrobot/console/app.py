"""FastAPI application factory and static web console server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pyrobot.console.api import create_api_router
from pyrobot.console.settings import DEFAULT_SETTINGS_PATH, SettingsManager
from pyrobot.console.supervisor import ConsoleConfig, RuntimeSupervisor
from pyrobot.logging_config import get_logger

logger = get_logger("console_app")

STATIC_DIR = Path(__file__).parent / "static"


def create_app(supervisor: Optional[RuntimeSupervisor] = None, settings_path: Optional[str | Path] = None) -> FastAPI:
    """Build and configure the FastAPI web console application.

    Args:
        supervisor: Active runtime supervisor (created fresh if omitted).
        settings_path: Optional path for the settings store; defaults to
            data/console_settings.json. Injectable so callers/tests can isolate.
    """
    active_supervisor = supervisor or RuntimeSupervisor()

    app = FastAPI(
        title="PyRobot Management Console",
        description="Production command and control dashboard for the PyRobot quantitative trading engine.",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Mount API routes
    settings_manager = SettingsManager(settings_path if settings_path is not None else DEFAULT_SETTINGS_PATH)
    api_router = create_api_router(active_supervisor, settings_manager=settings_manager)
    app.include_router(api_router)

    # Mount static assets directory
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Root route serves index.html
    @app.get("/")
    async def serve_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({"message": "PyRobot Management Console API is running."})

    # Health check endpoint
    @app.get("/health")
    def health_check():
        return {
            "status": "healthy",
            "supervisor_state": active_supervisor.state.value,
        }

    # Store supervisor on app state for access if needed
    app.state.supervisor = active_supervisor

    return app


def main() -> None:
    """Console entrypoint: parses host/port, starts loop, and launches Uvicorn server."""
    import uvicorn

    host = os.environ.get("PYROBOT_CONSOLE_HOST", "127.0.0.1")
    port = int(os.environ.get("PYROBOT_CONSOLE_PORT", "8080"))
    auto_start = os.environ.get("PYROBOT_AUTO_START", "true").lower() == "true"

    supervisor = RuntimeSupervisor(ConsoleConfig.from_env())

    if auto_start:
        logger.info("Auto-starting trading loop in background thread...")
        supervisor.start()

    app = create_app(supervisor)

    logger.info("Starting PyRobot Management Console on http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
