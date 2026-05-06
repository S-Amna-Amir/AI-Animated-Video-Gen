"""
Edit Agent routes — stub implementation.
Intent classification is keyword-based (no LLM call).
Execution delegates to the appropriate phase service.

POST /edit
POST /edit/{edit_id}/confirm
GET  /edit/history/{run_id}
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.services import phase2_service, phase3_service, state_service

router = APIRouter(tags=["edit"])

from agents.edit_agent.intent_classifier import IntentClassifier

# ── in-memory store of unconfirmed edits ──────────────────────────────────────
_pending_edits: dict[str, dict[str, Any]] = {}
classifier = IntentClassifier()

def _classify(query: str) -> dict[str, Any]:
    return classifier.classify(query)


# ── request models ────────────────────────────────────────────────────────────

class EditRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    query: str


# ── background task helpers ───────────────────────────────────────────────────

def _spawn_phase2_rerun(run_id: str) -> None:
    asyncio.create_task(
        phase2_service.rerun_phase2_steps(run_id=run_id, steps=["full"])
    )


def _spawn_phase3_rerun(run_id: str) -> None:
    asyncio.create_task(phase3_service.run_phase3(run_id=run_id))


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/edit")
async def classify_edit(req: EditRequest) -> dict[str, Any]:
    """
    Classify the edit intent and store it pending confirmation.
    No pipeline steps are triggered yet.
    """
    detected = _classify(req.query)
    edit_id = f"edit_{uuid4().hex[:8]}"

    _pending_edits[edit_id] = {
        "edit_id": edit_id,
        "run_id": req.run_id,
        **detected,
    }

    return {
        "edit_id": edit_id,
        "run_id": req.run_id,
        "intent": detected["intent"],
        "target": detected["target"],
        "scope": detected["scope"],
        "parameters": detected["parameters"],
        "status": "classified",
        "message": "Review and confirm",
    }


@router.post("/edit/{edit_id}/confirm")
async def confirm_edit(
    edit_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Execute the previously classified edit.
    Triggers the appropriate phase re-run as a background task.
    """
    edit = _pending_edits.get(edit_id)
    if edit is None:
        raise HTTPException(status_code=404, detail=f"No pending edit found for edit_id={edit_id}")

    run_id: str = edit["run_id"]
    target: str = edit["target"]
    intent: str = edit["intent"]

    # Script target → Phase 1 not integrated
    if target == "script":
        # Clean up but return error — don't leave it pending
        del _pending_edits[edit_id]
        return {
            "edit_id": edit_id,
            "status": "error",
            "message": "Phase 1 (script regeneration) is not yet integrated.",
        }

    # Dispatch based on target
    if target == "audio":
        background_tasks.add_task(_spawn_phase2_rerun, run_id)
    elif target in ("video_frame", "video"):
        background_tasks.add_task(_spawn_phase3_rerun, run_id)
    else:
        # Unknown target — default to Phase 3 re-run
        background_tasks.add_task(_spawn_phase3_rerun, run_id)

    # Persist a version snapshot
    state_service.save_snapshot(
        run_id=run_id,
        phase="edit",
        description=intent,
    )

    del _pending_edits[edit_id]

    return {"edit_id": edit_id, "status": "executing", "run_id": run_id}


@router.get("/edit/history/{run_id}")
async def edit_history(run_id: str) -> list[dict[str, Any]]:
    return state_service.list_versions(run_id)