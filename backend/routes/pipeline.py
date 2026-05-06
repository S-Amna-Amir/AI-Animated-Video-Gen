"""
Pipeline routes.
POST /pipeline/run   — kick off a full Phase 1→2→3 run
GET  /pipeline/status/{run_id}
POST /pipeline/cancel/{run_id}
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.services import pipeline_service

router = APIRouter(tags=["pipeline"])


# ── request model ─────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str
    scene_count: int = 4
    art_style: str = "cinematic"
    enable_bgm: bool = True
    enable_subtitles: bool = True
    mock_mode: bool = False
    llm_provider: str = "claude"
    voice_engine: str = "edge-tts"


# ── background task wrapper ───────────────────────────────────────────────────

def _spawn_pipeline(run_id: str, req: PipelineRunRequest) -> None:
    """
    BackgroundTasks expects a plain (non-async) callable.
    We create an asyncio Task so the coroutine runs on the event loop.
    """
    asyncio.create_task(
        pipeline_service.run_full_pipeline(
            run_id=run_id,
            prompt=req.prompt,
            scene_count=req.scene_count,
            art_style=req.art_style,
            enable_bgm=req.enable_bgm,
            enable_subtitles=req.enable_subtitles,
            mock_mode=req.mock_mode,
            llm_provider=req.llm_provider,
            voice_engine=req.voice_engine,
        )
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/pipeline/run")
async def run_pipeline(
    req: PipelineRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(_spawn_pipeline, run_id, req)
    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Full pipeline queued — connect to /ws/logs/{run_id} for live logs",
    }


@router.get("/pipeline/status/{run_id}")
async def pipeline_status(run_id: str) -> dict[str, Any]:
    status = pipeline_service.get_pipeline_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No pipeline found for run_id={run_id}")
    return status


@router.post("/pipeline/cancel/{run_id}")
async def cancel_pipeline(run_id: str) -> dict[str, Any]:
    pipeline_service.cancel_pipeline(run_id)
    return {"run_id": run_id, "status": "cancelling"}