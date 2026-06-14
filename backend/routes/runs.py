"""
backend/routes/runs.py
-----------------------
Read-only endpoints for browsing completed phase runs.

GET /api/runs/phase2           — list all Phase 2 run directories
GET /api/runs/phase2/latest    — get latest Phase 2 run
GET /api/runs/phase2/{run_id}  — get specific Phase 2 run manifest
GET /api/runs/phase3           — list all Phase 3 run directories
GET /api/runs/phase3/latest    — get latest Phase 3 run
GET /api/runs/phase3/{run_id}  — get specific Phase 3 run summary
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()

PHASE2_DIR = Path("data/outputs/Phase2")
PHASE3_DIR = Path("data/outputs/Phase3")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sorted_runs(base: Path) -> List[Dict[str, Any]]:
    if not base.exists():
        return []
    dirs = sorted(
        [p for p in base.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [{"run_id": d.name, "run_dir": str(d)} for d in dirs]


def _load_json(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Phase 2 ───────────────────────────────────────────────────────────────────

@router.get("/phase2")
async def list_phase2_runs():
    runs = _sorted_runs(PHASE2_DIR)
    for r in runs:
        summary = _load_json(Path(r["run_dir"]) / "phase2_summary.json")
        r["summary"] = summary or {}
    return {"runs": runs, "total": len(runs)}


@router.get("/phase2/latest")
async def latest_phase2_run():
    runs = _sorted_runs(PHASE2_DIR)
    if not runs:
        raise HTTPException(status_code=404, detail="No Phase 2 runs found")
    run = runs[0]
    run_dir = Path(run["run_dir"])
    return {
        "run_id":          run["run_id"],
        "run_dir":         run["run_dir"],
        "summary":         _load_json(run_dir / "phase2_summary.json"),
        "timing_manifest": _load_json(run_dir / "timing_manifest.json"),
        "bgm_metadata":    _load_json(run_dir / "bgm_metadata.json"),
    }


@router.get("/phase2/{run_id}")
async def get_phase2_run(run_id: str):
    run_dir = PHASE2_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Phase 2 run '{run_id}' not found")
    return {
        "run_id":          run_id,
        "run_dir":         str(run_dir),
        "summary":         _load_json(run_dir / "phase2_summary.json"),
        "timing_manifest": _load_json(run_dir / "timing_manifest.json"),
        "bgm_metadata":    _load_json(run_dir / "bgm_metadata.json"),
        "config":          _load_json(run_dir / "phase2_config.json"),
    }


# ── Phase 3 ───────────────────────────────────────────────────────────────────

@router.get("/phase3")
async def list_phase3_runs():
    runs = _sorted_runs(PHASE3_DIR)
    for r in runs:
        summary = _load_json(Path(r["run_dir"]) / "phase3_output.json")
        r["summary"] = summary or {}
    return {"runs": runs, "total": len(runs)}


@router.get("/phase3/latest")
async def latest_phase3_run():
    runs = _sorted_runs(PHASE3_DIR)
    if not runs:
        raise HTTPException(status_code=404, detail="No Phase 3 runs found")
    run = runs[0]
    run_dir = Path(run["run_dir"])
    return {
        "run_id":  run["run_id"],
        "run_dir": run["run_dir"],
        "output":  _load_json(run_dir / "phase3_output.json"),
        "handoff": _load_json(run_dir / "phase3_video_handoff.json"),
    }


@router.get("/phase3/{run_id}")
async def get_phase3_run(run_id: str):
    run_dir = PHASE3_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Phase 3 run '{run_id}' not found")
    return {
        "run_id":  run_id,
        "run_dir": str(run_dir),
        "output":  _load_json(run_dir / "phase3_output.json"),
        "handoff": _load_json(run_dir / "phase3_video_handoff.json"),
    }
