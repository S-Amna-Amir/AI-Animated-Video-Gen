"""
Edit Agent routes — full implementation with EditAgent and StateManager.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.edit_agent.agent import EditAgent
from state_manager.state_manager import StateManager
from backend.websocket.manager import ws_manager

router = APIRouter(tags=["edit"])

# Initialize services
edit_agent = EditAgent()
state_manager = StateManager()

# ── request models ────────────────────────────────────────────────────────────

class EditRequest(BaseModel):
    run_id: str
    command: str
    current_state_json: Dict[str, Any]

class UndoRequest(BaseModel):
    run_id: str
    version: int

# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/edit")
async def process_edit(req: EditRequest) -> Dict[str, Any]:
    """
    Process an edit command through the full EditAgent pipeline.
    Returns the result with new version, intent, plan, and execution result.
    """
    try:
        # Emit progress event
        await ws_manager.info(req.run_id, "Starting edit processing...")
        
        # Run the full pipeline
        result = await edit_agent.process_edit(req.run_id, req.command, req.current_state_json)
        
        # Emit completion
        await ws_manager.success(req.run_id, f"Edit completed: {result['intent'].intent}")
        
        return {
            "new_version": result["new_version"],
            "intent": result["intent"].model_dump(),
            "plan": result["plan"].model_dump(),
            "result": result["result"],
            "success": True
        }
    except Exception as e:
        await ws_manager.error(req.run_id, f"Edit failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/undo")
async def undo_edit(req: UndoRequest) -> Dict[str, Any]:
    """
    Revert to a specific version.
    Returns the restored state and new version number.
    """
    try:
        # Revert to the specified version
        reverted_snapshot = state_manager.revert(req.run_id, req.version)
        
        await ws_manager.success(req.run_id, f"Reverted to version {req.version}")
        
        return {
            "restored_state": reverted_snapshot.state_json,
            "new_version": reverted_snapshot.version,
            "success": True
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await ws_manager.error(req.run_id, f"Undo failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{run_id}")
async def get_edit_history(run_id: str) -> list[Dict[str, Any]]:
    """
    Get the full version history for a run.
    Returns list of snapshots with version, timestamp, edit_command, state_json, asset_paths.
    """
    try:
        history = state_manager.history(run_id)
        return [
            {
                "version": snap.version,
                "timestamp": snap.timestamp,
                "edit_command": snap.edit_command,
                "state_json": snap.state_json,
                "asset_paths": snap.asset_paths
            }
            for snap in history
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))