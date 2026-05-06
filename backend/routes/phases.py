"""
Phase-level routes.
POST /phase/2/run
POST /phase/2/rerun
GET  /phase/2/status/{run_id}
POST /phase/3/run
GET  /phase/3/status/{run_id}
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.services import phase2_service, phase3_service

router = APIRouter(tags=["phases"])


# ── request models ────────────────────────────────────────────────────────────

class Phase2RunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    phase1_dir: str | None = None
    custom_voices: dict[str, str] | None = None


class Phase2RerunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    steps: list[str]


class Phase3RunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    phase1_dir: str | None = None
    phase2_run_dir: str | None = None
    mock: bool = False
    use_subtitles: bool = False


# ── background task helpers ───────────────────────────────────────────────────

def _spawn_phase2(
    run_id: str,
    phase1_dir: str | None,
    custom_voices: dict[str, str] | None,
) -> None:
    asyncio.create_task(
        phase2_service.run_phase2(
            run_id=run_id,
            phase1_dir=phase1_dir,
            custom_voices=custom_voices,
        )
    )


def _spawn_phase2_rerun(
    run_id: str,
    steps: list[str],
) -> None:
    asyncio.create_task(
        phase2_service.rerun_phase2_steps(run_id=run_id, steps=steps)
    )


def _spawn_phase3(
    run_id: str,
    phase1_dir: str | None,
    phase2_run_dir: str | None,
    mock: bool,
    use_subtitles: bool,
) -> None:
    asyncio.create_task(
        phase3_service.run_phase3(
            run_id=run_id,
            phase1_dir=phase1_dir,
            phase2_run_dir=phase2_run_dir,
            mock=mock,
            use_subtitles=use_subtitles,
        )
    )


# ── Phase 2 endpoints ─────────────────────────────────────────────────────────

@router.post("/phase/2/run")
async def run_phase2(
    req: Phase2RunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    run_id = req.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(
        _spawn_phase2,
        run_id,
        req.phase1_dir,
        req.custom_voices,
    )
    return {"run_id": run_id, "status": "started"}


@router.post("/phase/2/rerun")
async def rerun_phase2(
    req: Phase2RerunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    background_tasks.add_task(_spawn_phase2_rerun, req.run_id, req.steps)
    return {"run_id": req.run_id, "steps": req.steps, "status": "started"}


@router.get("/phase/2/status/{run_id}")
async def phase2_status(run_id: str) -> dict[str, Any]:
    status = phase2_service.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No Phase 2 run found for run_id={run_id}")
    return status


# ── Phase 3 endpoints ─────────────────────────────────────────────────────────

@router.post("/phase/3/run")
async def run_phase3(
    req: Phase3RunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    run_id = req.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(
        _spawn_phase3,
        run_id,
        req.phase1_dir,
        req.phase2_run_dir,
        req.mock,
        req.use_subtitles,
    )
    return {"run_id": run_id, "status": "started"}


@router.get("/phase/3/status/{run_id}")
async def phase3_status(run_id: str) -> dict[str, Any]:
    status = phase3_service.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No Phase 3 run found for run_id={run_id}")
    return status