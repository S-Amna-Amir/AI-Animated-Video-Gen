"""
backend/routes/edit.py
-----------------------
Phase 5 edit + undo API endpoints.

POST /api/edit/apply          — apply a free-text edit command
POST /api/edit/undo/{version} — revert to a previous snapshot
GET  /api/edit/history        — list all versions
GET  /api/edit/history/{v}    — detail for one version
GET  /api/edit/diff/{v1}/{v2} — diff two versions
WS   /api/edit/ws/{job_id}    — stream edit job logs
"""
import asyncio
import logging
import traceback
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.services.job_store import JobStore

logger = logging.getLogger(__name__)
router = APIRouter()
jobs   = JobStore()


# ── Request models ────────────────────────────────────────────────────────────

class EditRequest(BaseModel):
    query: str


class UndoRequest(BaseModel):
    version: int


# ── Apply edit ────────────────────────────────────────────────────────────────

@router.post("/apply")
async def apply_edit(req: EditRequest):
    job_id = str(uuid.uuid4())
    jobs.create(job_id, phase=5, params={"query": req.query})

    # Run in background so WS streaming works
    asyncio.create_task(_run_edit(job_id, req.query))

    return {"job_id": job_id, "status": "queued", "message": "Edit started"}


async def _run_edit(job_id: str, query: str):
    jobs.set_running(job_id)

    def _log(msg: str):
        jobs.log(job_id, msg)

    try:
        from agents.edit_agent.agent import EditAgent
        agent  = EditAgent(log_callback=_log)
        result = await agent.edit(query)

        if result["success"]:
            jobs.set_complete(job_id, result={
                "intent":          result["intent"],
                "snapshot_before": result["snapshot_before"],
                "snapshot_after":  result["snapshot_after"],
                "steps_completed": len([s for s in result["execution"]["steps"] if s["ok"]]),
            })
        else:
            jobs.set_failed(job_id, result.get("error", "Edit failed"))

    except Exception as e:
        tb = traceback.format_exc()
        jobs.set_failed(job_id, str(e))
        jobs.log(job_id, f"ERROR: {e}\n{tb}")


# ── Undo ──────────────────────────────────────────────────────────────────────

@router.post("/undo/{version}")
async def undo_edit(version: int):
    from agents.edit_agent.agent import EditAgent
    agent  = EditAgent()
    result = agent.undo(version)
    if result["success"]:
        return result
    from fastapi import HTTPException
    raise HTTPException(status_code=400, detail=result.get("error", "Revert failed"))


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history")
async def get_history():
    from state_manager.state_manager import StateManager
    return {"versions": StateManager().history()}


@router.get("/history/{version}")
async def get_version(version: int):
    from state_manager.state_manager import StateManager
    detail = StateManager().detail(version)
    if not detail:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return detail


@router.get("/diff/{v1}/{v2}")
async def diff_versions(v1: int, v2: int):
    from state_manager.state_manager import StateManager
    return StateManager().diff(v1, v2)


# ── Status + WebSocket ────────────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def edit_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.websocket("/ws/{job_id}")
async def ws_edit_logs(websocket: WebSocket, job_id: str):
    await websocket.accept()
    sent = 0
    try:
        while True:
            job  = jobs.get(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                break
            logs = job.get("logs", [])
            while sent < len(logs):
                await websocket.send_json({"log": logs[sent]})
                sent += 1
            if job["status"] in ("complete", "failed"):
                await websocket.send_json({"status": job["status"], "result": job.get("result")})
                break
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass
