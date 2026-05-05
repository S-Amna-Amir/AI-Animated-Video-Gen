"""
Run metadata routes.
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/versions
POST /runs/{run_id}/revert/{version}
GET  /runs/{run_id}/manifest
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.services import state_service

router = APIRouter(tags=["runs"])


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    return state_service.list_runs()


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    return state_service.get_run(run_id)


@router.get("/runs/{run_id}/versions")
async def list_versions(run_id: str) -> list[dict[str, Any]]:
    return state_service.list_versions(run_id)


@router.post("/runs/{run_id}/revert/{version}")
async def revert_version(run_id: str, version: int) -> dict[str, Any]:
    try:
        return state_service.revert_version(run_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/runs/{run_id}/manifest")
async def get_manifest(run_id: str) -> list[dict[str, Any]]:
    manifest = state_service.get_timing_manifest(run_id)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=f"Timing manifest not found for run_id={run_id}",
        )
    return manifest