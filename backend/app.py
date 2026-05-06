"""
CineForge API — FastAPI application entry point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import pipeline, phases, files, run, edit
from backend.websocket import routes as ws_routes


# ── required output directories ───────────────────────────────────────────────
_REQUIRED_DIRS: list[str] = [
    "data/outputs/Phase1",
    "data/outputs/Phase2",
    "data/outputs/Phase3",
    "data/state_versions",
    "data/bgm_library",
    "frontend",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    for d in _REQUIRED_DIRS:
        Path(d).mkdir(parents=True, exist_ok=True)
    yield
    # shutdown (nothing to clean up for now)


# ── app ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CineForge API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── health ────────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(pipeline.router, prefix="/api")
app.include_router(phases.router,   prefix="/api")
app.include_router(files.router,    prefix="/api")
app.include_router(run.router,     prefix="/api")
app.include_router(edit.router,     prefix="/api")

# ── WebSocket router (no /api prefix) ────────────────────────────────────────
app.include_router(ws_routes.router)

# ── Static files — MUST be last ───────────────────────────────────────────────
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)