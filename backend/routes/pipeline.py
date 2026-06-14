"""
backend/routes/pipeline.py
----------------------------
Pipeline execution endpoints.
Each phase runs as a FastAPI BackgroundTask and streams progress
back to the client over a WebSocket connection.

Endpoints:
  POST /api/pipeline/phase1       — start Phase 1
  POST /api/pipeline/phase2       — start Phase 2
  POST /api/pipeline/phase3       — start Phase 3
  POST /api/pipeline/phase3/short — start Phase 3 (1 scene, 3 lines)
  GET  /api/pipeline/status/{job_id} — poll job status
  WS   /api/pipeline/ws/{job_id}  — stream live log lines
"""
import asyncio
from http.client import HTTPException
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.services.job_store import JobStore

logger = logging.getLogger(__name__)
router = APIRouter()
jobs   = JobStore()   # in-process job registry

class _JobLogHandler(logging.Handler):
    """
    Attaches to the root logger during a pipeline run and forwards
    every log record into the job store so the WebSocket picks it up.
    Only records at INFO level and above are forwarded.
    """
    def __init__(self, job_id: str, job_store: JobStore):
        super().__init__(level=logging.INFO)
        self._job_id    = job_id
        self._job_store = job_store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._job_store.log(self._job_id, msg)
        except Exception:
            pass   # never let logging errors crash the pipeline


# ── Request / Response models ─────────────────────────────────────────────────

class Phase1Request(BaseModel):
    mode:      str = "auto"    # "auto" | "manual"
    raw_input: str             # prompt or screenplay text
    hitl_decision: Optional[str] = None
    hitl_edit: Optional[dict] = None


class Phase2Request(BaseModel):
    phase1_dir: str = "data/outputs"
    phase2_dir: str = "data/outputs/Phase2"
    freesound_api_key: Optional[str] = None


class Phase3Request(BaseModel):
    phase1_dir:    str  = "data/outputs"
    phase2_run:    Optional[str] = None   # auto-detect latest if None
    mock:          bool = False
    use_subtitles: bool = False
    short_mode:    bool = False           # limit to 1 scene / 3 lines


class JobResponse(BaseModel):
    job_id:    str
    status:    str
    message:   str

class Phase1ResumeRequest(BaseModel):
    job_id: str
    hitl_decision: str          # "yes" | "no" | "edit"
    hitl_edit: Optional[dict] = None



# ── Phase 1 — two-step ────────────────────────────────────────────────────────

@router.post("/phase1/generate", response_model=JobResponse)
async def start_phase1_generate(req: Phase1Request, background_tasks: BackgroundTasks):
    """Step 1: Run up to (but not including) HITL, park the script for review."""
    job_id = str(uuid.uuid4())
    jobs.create(job_id, phase=1, params=req.dict())
    background_tasks.add_task(_run_phase1_generate, job_id, req)
    return JobResponse(job_id=job_id, status="queued", message="Phase 1 generation started")


@router.websocket("/ws/{job_id}")
async def ws_job_logs(websocket: WebSocket, job_id: str):
    """Stream live log lines for a job as they are appended."""
    await websocket.accept()
    sent = 0
    hitl_notified = False   # ← send pending_hitl event only once
    try:
        while True:
            job = jobs.get(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                break

            logs = job.get("logs", [])
            while sent < len(logs):
                await websocket.send_json({"log": logs[sent]})
                sent += 1

            status = job["status"]

            if status == "pending_hitl" and not hitl_notified:
                await websocket.send_json({
                    "status": "pending_hitl",
                    "script": job.get("script"),
                    "result": None,
                })
                hitl_notified = True
                # Don't break — stay connected for resume logs

            elif status in ("complete", "failed"):
                await websocket.send_json({
                    "status": status,
                    "result": job.get("result"),
                })
                break

            await asyncio.sleep(0.3)

    except WebSocketDisconnect:
        pass


async def _run_phase1_generate(job_id: str, req: Phase1Request):
    jobs.set_running(job_id)
    try:
        jobs.log(job_id, f"Phase 1 generation starting | mode={req.mode}")

        from agents.orchestrator.workflow import run_phase1_generate
        state = await asyncio.get_event_loop().run_in_executor(
            None, run_phase1_generate, req.mode, req.raw_input
        )

        if state.get("status") == "failed":
            jobs.set_failed(job_id, state.get("error_message", "Unknown error"))
            jobs.log(job_id, f"FAILED: {state.get('error_message')}")
            return

        script = state.get("script", {})
        jobs.log(job_id, f"Script ready: {script.get('title','?')} | {script.get('total_scenes',0)} scenes")

        # Park state so /resume can pick it up
        jobs.set_pending_hitl(job_id, state=state, script=script)
        jobs.log(job_id, "Awaiting HITL review…")

    except Exception as e:
        jobs.set_failed(job_id, str(e))
        jobs.log(job_id, f"ERROR: {e}\n{traceback.format_exc()}")


@router.post("/phase1/resume", response_model=JobResponse)
async def resume_phase1(req: Phase1ResumeRequest, background_tasks: BackgroundTasks):
    """Step 2: Apply the user's HITL decision and run the rest of the pipeline."""
    job = jobs.get(req.job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "pending_hitl":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Job is not awaiting review (status: {job['status']})")

    background_tasks.add_task(_run_phase1_resume, req.job_id, req)
    return JobResponse(job_id=req.job_id, status="running", message="Resuming after HITL")


async def _run_phase1_resume(job_id: str, req: Phase1ResumeRequest):
    jobs.set_running(job_id)

    # ── Bridge Python logging → job store for this run ────────────────────
    handler = _JobLogHandler(job_id, jobs)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        jobs.log(job_id, f"HITL decision received: {req.hitl_decision}")

        parked_state = jobs.get_parked_state(job_id)
        if not parked_state:
            jobs.set_failed(job_id, "Parked state not found — cannot resume.")
            return

        from agents.orchestrator.workflow import run_phase1_resume

        # ── Step: apply HITL decision ──────────────────────────────────────
        decision = (req.hitl_decision or "").strip().lower()
        if decision in ("yes", "approve"):
            jobs.log(job_id, "Script approved — starting character design…")
        elif decision in ("no", "reject"):
            jobs.log(job_id, "Script rejected.")
            jobs.set_failed(job_id, "Script rejected by operator.")
            return
        elif decision == "edit":
            jobs.log(job_id, "Applying script edits — starting character design…")

        # ── Step: run the rest of the graph (blocks in thread pool) ───────
        jobs.log(job_id, "Building character profiles…")
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None,
            run_phase1_resume,
            parked_state,
            req.hitl_decision,
            req.hitl_edit,
        )

        if state.get("status") == "failed":
            jobs.set_failed(job_id, state.get("error_message", "Unknown error"))
            jobs.log(job_id, f"FAILED: {state.get('error_message')}")
            return

        # ── Done ───────────────────────────────────────────────────────────
        script = state.get("script", {})
        chars  = state.get("characters", [])
        jobs.log(job_id, f"Characters built : {len(chars)}")
        jobs.set_complete(job_id, result={
            "title":        script.get("title"),
            "total_scenes": script.get("total_scenes"),
            "characters":   len(chars),
            "output_dir":   "data/outputs",
        })
        jobs.log(job_id, "Phase 1 complete ✓")

    except asyncio.CancelledError:
        # Server is shutting down mid-run — mark failed so the UI doesn't
        # stay stuck on "running" forever after a reload.
        jobs.set_failed(job_id, "Server restarted while job was running.")
        jobs.log(job_id, "Job cancelled — server was restarted.")

    except Exception as e:
        jobs.set_failed(job_id, str(e))
        jobs.log(job_id, f"ERROR: {e}\n{traceback.format_exc()}")

    finally:
        # Always remove the handler — don't leak it into subsequent requests
        root_logger.removeHandler(handler)


# ── Phase 2 ───────────────────────────────────────────────────────────────────

@router.post("/phase2", response_model=JobResponse)
async def start_phase2(req: Phase2Request, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs.create(job_id, phase=2, params=req.dict())
    background_tasks.add_task(_run_phase2, job_id, req)
    return JobResponse(job_id=job_id, status="queued", message="Phase 2 started")


async def _run_phase2(job_id: str, req: Phase2Request):
    jobs.set_running(job_id)
    try:
        jobs.log(job_id, "Phase 2 starting | TTS + BGM synthesis")
        from agents.audio_agent.enhanced_agent import EnhancedAudioAgent

        agent = EnhancedAudioAgent(
            phase1_data_dir=req.phase1_dir,
            phase2_output_dir=req.phase2_dir,
            freesound_api_key=req.freesound_api_key,
        )
        jobs.log(job_id, f"Agent ready | run={agent.run_manager.current_run_id}")

        result = await agent.process()

        if result.get("status") != "success":
            jobs.set_failed(job_id, result.get("error", "Unknown error"))
            jobs.log(job_id, f"FAILED: {result.get('error')}")
            return

        jobs.log(job_id, f"Scenes processed : {result['scenes_processed']}/{result['total_scenes']}")
        jobs.log(job_id, f"Scenes with BGM  : {result['scenes_with_bgm']}")
        jobs.log(job_id, f"Duration         : {result['total_duration_ms']/1000:.1f}s")
        jobs.set_complete(job_id, result={
            "run_id":          result["run_id"],
            "timing_manifest": result["timing_manifest_path"],
            "master_audio":    result.get("master_audio_track"),
            "output_dir":      result["output_directory"],
            "duration_ms":     result["total_duration_ms"],
        })
        jobs.log(job_id, "Phase 2 complete ✓")

    except Exception as e:
        tb = traceback.format_exc()
        jobs.set_failed(job_id, str(e))
        jobs.log(job_id, f"ERROR: {e}\n{tb}")


# ── Phase 3 ───────────────────────────────────────────────────────────────────

@router.post("/phase3", response_model=JobResponse)
async def start_phase3(req: Phase3Request, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs.create(job_id, phase=3, params=req.dict())
    background_tasks.add_task(_run_phase3, job_id, req)
    return JobResponse(job_id=job_id, status="queued", message="Phase 3 started")


@router.post("/phase3/short", response_model=JobResponse)
async def start_phase3_short(req: Phase3Request, background_tasks: BackgroundTasks):
    req.short_mode = True
    job_id = str(uuid.uuid4())
    jobs.create(job_id, phase=3, params=req.dict())
    background_tasks.add_task(_run_phase3, job_id, req)
    return JobResponse(job_id=job_id, status="queued", message="Phase 3 (short) started")


async def _run_phase3(job_id: str, req: Phase3Request):
    jobs.set_running(job_id)
    try:
        mode_label = "SHORT" if req.short_mode else "FULL"
        jobs.log(job_id, f"Phase 3 starting | mode={mode_label} mock={req.mock}")

        # Resolve Phase 2 run dir
        phase2_run = req.phase2_run or _latest_run("data/outputs/Phase2")
        jobs.log(job_id, f"Phase 2 run: {phase2_run}")

        if req.short_mode:
            from agents.video_agent.agent import VideoAgent as _VA
            class AgentClass(_VA):
                def load_phase1_output(self, phase1_dir='data/outputs'):
                    data = super().load_phase1_output(phase1_dir)
                    if data.get('scenes'):
                        data['scenes'] = [data['scenes'][0]]
                    return data
                def load_phase2_manifest(self, phase2_run_dir):
                    m = super().load_phase2_manifest(phase2_run_dir)
                    if m:
                        first_sid = m[0].get('scene_id')
                        m = [e for e in m if e.get('scene_id') == first_sid][:3]
                    return m
        else:
            from agents.video_agent.agent import VideoAgent as AgentClass

        agent  = AgentClass()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: agent.run(
                phase1_dir=req.phase1_dir,
                phase2_run_dir=phase2_run,
                mock=req.mock,
                use_subtitles=req.use_subtitles,
            ),
        )

        if result.get("status") == "failed":
            jobs.set_failed(job_id, "; ".join(result.get("errors", ["Unknown"])))
            jobs.log(job_id, f"FAILED: {result.get('errors')}")
            return

        imgs  = result.get("scene_images", {})
        clips = result.get("scene_clips", {})
        jobs.log(job_id, f"Images  : {sum(1 for p in imgs.values() if p)}/{len(imgs)}")
        jobs.log(job_id, f"Clips   : {sum(1 for p in clips.values() if p)}/{len(clips)}")
        jobs.log(job_id, f"Video   : {result.get('final_video')}")
        jobs.set_complete(job_id, result={
            "run_id":        result["run_id"],
            "final_video":   result.get("final_video"),
            "use_subtitles": result.get("use_subtitles", False),
            "status":        result["status"],
            "run_dir":       str(Path("data/outputs/Phase3") / result["run_id"]),
        })
        jobs.log(job_id, f"Phase 3 {result['status']} ✓")

    except Exception as e:
        tb = traceback.format_exc()
        jobs.set_failed(job_id, str(e))
        jobs.log(job_id, f"ERROR: {e}\n{tb}")


# ── Status polling ────────────────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Don't send the full parked state to the client
    return {k: v for k, v in job.items() if not k.startswith("_")}



# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_run(base: str) -> str:
    root = Path(base)
    if not root.exists():
        return ""
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return str(max(dirs, key=lambda p: p.stat().st_mtime)) if dirs else ""
