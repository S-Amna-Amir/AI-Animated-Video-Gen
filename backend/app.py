"""
backend/app.py
---------------
FastAPI application factory.
Mounts all routers and configures CORS + static file serving.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import pipeline, runs, files, edit

logger = logging.getLogger(__name__)

DATA_DIR    = Path("data/outputs")
STATIC_DIR  = Path("frontend/dist")   # built React app


def create_app() -> FastAPI:
    app = FastAPI(
        title="Project Montage API",
        version="1.0.0",
        description="AI-powered animated video generation pipeline",
    )

    # ── CORS (dev: allow all; tighten in production) ──────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API routers ────────────────────────────────────────────────────────
    app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
    app.include_router(runs.router,     prefix="/api/runs",     tags=["runs"])
    app.include_router(files.router,    prefix="/api/files",    tags=["files"])
    app.include_router(edit.router,     prefix="/api/edit",     tags=["edit"])

    # ── Serve built frontend (production) ─────────────────────────────────
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
        logger.info("Serving frontend from %s", STATIC_DIR)
    else:
        logger.info("Frontend not built — API-only mode")

    return app


app = create_app()
