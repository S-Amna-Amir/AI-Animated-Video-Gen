"""
state_manager/snapshot.py
---------------------------
High-level snapshot API used by StateManager.
Collects all current asset paths from the data/outputs tree
and delegates persistence to storage.py.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from state_manager import storage

logger = logging.getLogger(__name__)

PHASE1_OUTPUTS = Path("data/outputs")
PHASE2_OUTPUTS = Path("data/outputs/Phase2")
PHASE3_OUTPUTS = Path("data/outputs/Phase3")


def _collect_asset_paths() -> List[str]:
    """
    Walk the outputs tree and return all significant generated files:
    JSONs, images, audio files, and the final MP4.
    """
    extensions = {".json", ".png", ".jpg", ".mp3", ".wav", ".mp4"}
    paths: List[str] = []

    for base in (PHASE1_OUTPUTS, PHASE2_OUTPUTS, PHASE3_OUTPUTS):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in extensions:
                paths.append(str(p))

    return sorted(paths)


def _load_current_state() -> Dict[str, Any]:
    """
    Build a lightweight state snapshot from whatever JSON outputs exist.
    Does not import any agent — purely reads files.
    """
    state: Dict[str, Any] = {}

    # Phase 1: scene manifest + character DB
    for name in ("scene_manifest.json", "scene_manifest_auto.json", "scene_manifest_manual.json"):
        p = PHASE1_OUTPUTS / name
        if p.exists():
            try:
                state["scene_manifest"] = json.loads(p.read_text(encoding="utf-8"))
                state["scene_manifest_file"] = str(p)
                break
            except Exception:
                pass

    for name in ("character_db.json", "character_db_auto.json", "character_db_manual.json"):
        p = PHASE1_OUTPUTS / name
        if p.exists():
            try:
                state["character_db"] = json.loads(p.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    # Phase 2: latest run summary + timing manifest
    if PHASE2_OUTPUTS.exists():
        runs = sorted(
            [d for d in PHASE2_OUTPUTS.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        if runs:
            latest = runs[0]
            state["phase2_run_id"] = latest.name
            state["phase2_run_dir"] = str(latest)
            for fname in ("phase2_summary.json", "timing_manifest.json"):
                fp = latest / fname
                if fp.exists():
                    try:
                        state[fname.replace(".json", "")] = json.loads(fp.read_text(encoding="utf-8"))
                    except Exception:
                        pass

    # Phase 3: latest run output + handoff
    if PHASE3_OUTPUTS.exists():
        runs = sorted(
            [d for d in PHASE3_OUTPUTS.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        if runs:
            latest = runs[0]
            state["phase3_run_id"] = latest.name
            state["phase3_run_dir"] = str(latest)
            for fname in ("phase3_output.json", "phase3_video_handoff.json"):
                fp = latest / fname
                if fp.exists():
                    try:
                        state[fname.replace(".json", "")] = json.loads(fp.read_text(encoding="utf-8"))
                    except Exception:
                        pass

    return state


def take_snapshot(
    description: str = "",
    edit_query: str = "",
    intent: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Capture the current pipeline state and persist it as a new version.

    Returns the index entry dict: {version, timestamp, description, filename, ...}
    """
    version    = storage.latest_version_number() + 1
    state      = _load_current_state()
    asset_paths = _collect_asset_paths()

    filepath = storage.write_version(
        version=version,
        state_json=state,
        asset_paths=asset_paths,
        description=description,
        edit_query=edit_query,
        intent=intent,
    )

    logger.info("[Snapshot] v%03d saved (%d assets) -> %s", version, len(asset_paths), filepath)
    return {
        "version":     version,
        "timestamp":   state.get("timestamp", ""),
        "description": description,
        "edit_query":  edit_query,
        "asset_count": len(asset_paths),
        "filepath":    filepath,
    }
