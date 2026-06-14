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
        run_dir = Path(r["run_dir"])
        summary  = _load_json(run_dir / "phase3_output.json")
        manifest = _load_json(run_dir / "version_manifest.json")
        r["summary"]          = summary or {}
        r["version_manifest"] = manifest or {}
    return {"runs": runs, "total": len(runs)}


@router.get("/phase3/latest")
async def latest_phase3_run():
    runs = _sorted_runs(PHASE3_DIR)
    if not runs:
        raise HTTPException(status_code=404, detail="No Phase 3 runs found")
    run = runs[0]
    run_dir = Path(run["run_dir"])
    return {
        "run_id":           run["run_id"],
        "run_dir":          run["run_dir"],
        "output":           _load_json(run_dir / "phase3_output.json"),
        "handoff":          _load_json(run_dir / "phase3_video_handoff.json"),
        "version_manifest": _load_json(run_dir / "version_manifest.json"),
    }


@router.get("/phase3/{run_id}")
async def get_phase3_run(run_id: str):
    run_dir = PHASE3_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Phase 3 run '{run_id}' not found")
    return {
        "run_id":           run_id,
        "run_dir":          str(run_dir),
        "output":           _load_json(run_dir / "phase3_output.json"),
        "handoff":          _load_json(run_dir / "phase3_video_handoff.json"),
        "version_manifest": _load_json(run_dir / "version_manifest.json"),
    }


@router.get("/phase3/{run_id}/lineage")
async def get_phase3_lineage(run_id: str):
    """
    Walk the version_manifest chain for a Phase 3 run and return the full
    ancestor tree: run_id → parent_run_id → grandparent ... back to the root.
    """
    chain = []
    current_id = run_id
    visited: set = set()

    while current_id and current_id not in visited:
        visited.add(current_id)
        run_dir = PHASE3_DIR / current_id
        if not run_dir.exists():
            break

        vm = _load_json(run_dir / "version_manifest.json")
        p3_out = _load_json(run_dir / "phase3_output.json")

        entry = {
            "run_id":              current_id,
            "edit_query":          vm.get("edit_query", "") if vm else "",
            "intent_label":        vm.get("intent_label", "") if vm else "",
            "intent_target":       vm.get("intent_target", "") if vm else "",
            "edit_timestamp":      vm.get("edit_timestamp", "") if vm else (p3_out or {}).get("timestamp", ""),
            "source_phase2_run_id": vm.get("source_phase2_run_id", "") if vm else (p3_out or {}).get("input", {}).get("phase2_run_dir", "").split("\\")[-1].split("/")[-1],
            "snapshot_before":     vm.get("snapshot_before", None) if vm else None,
            "snapshot_after":      vm.get("snapshot_after", None) if vm else None,
            "final_video":         (p3_out or {}).get("final_video", ""),
        }
        chain.append(entry)

        parent_id = vm.get("source_phase3_run_id", "") if vm else ""
        current_id = parent_id if parent_id != current_id else ""

    return {"run_id": run_id, "lineage": chain, "depth": len(chain)}


# ── Project (named run) endpoints ─────────────────────────────────────────────
# These expose the unified data/runs/<slug>/ project folders.
#
# GET /api/runs/projects              — list all projects
# GET /api/runs/projects/latest       — latest project session
# GET /api/runs/projects/{slug}       — single project session + edit list
# GET /api/runs/projects/{slug}/edits — list all edits for a project

@router.get("/projects")
async def list_projects():
    from agents.pipeline_run_manager import PipelineRunManager
    return {"projects": PipelineRunManager.list_all()}


@router.get("/projects/latest")
async def latest_project():
    from agents.pipeline_run_manager import PipelineRunManager
    pm = PipelineRunManager.latest()
    if not pm:
        raise HTTPException(status_code=404, detail="No projects found")
    return pm.get_manifest()


@router.get("/projects/{run_id}")
async def get_project(run_id: str):
    from agents.pipeline_run_manager import PipelineRunManager
    pm = PipelineRunManager.load(run_id)
    if not pm:
        raise HTTPException(status_code=404, detail=f"Project '{run_id}' not found")
    manifest = pm.get_manifest()
    # Enrich with quick file existence flags
    manifest["has_phase3_video"] = (pm.phase3_dir / "run_01" / "final_output.mp4").exists() or \
                                    any(pm.phase3_dir.rglob("final_output.mp4")) if pm.phase3_dir.exists() else False
    manifest["phase1_files"] = [p.name for p in pm.phase1_dir.iterdir() if p.is_file()] \
                                if pm.phase1_dir.exists() else []
    return manifest


@router.get("/projects/{run_id}/edits")
async def get_project_edits(run_id: str):
    from agents.pipeline_run_manager import PipelineRunManager
    pm = PipelineRunManager.load(run_id)
    if not pm:
        raise HTTPException(status_code=404, detail=f"Project '{run_id}' not found")

    edits = []
    if pm.phase5_dir.exists():
        for edit_dir in sorted(pm.phase5_dir.iterdir()):
            if not edit_dir.is_dir():
                continue
            manifest = _load_json(edit_dir / "edit_manifest.json") or {}
            output_file = manifest.get("output_file", "")
            edits.append({
                "edit_dir":    str(edit_dir),
                "edit_index":  manifest.get("edit_index"),
                "edit_query":  manifest.get("edit_query", ""),
                "intent":      manifest.get("intent", {}),
                "timestamp":   manifest.get("timestamp", ""),
                "completed_at": manifest.get("completed_at", ""),
                "output_file": output_file,
                "has_video":   bool(output_file and Path(output_file).exists()),
            })
    return {"run_id": run_id, "edits": edits, "count": len(edits)}
