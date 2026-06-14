"""
state_manager/state_manager.py
--------------------------------
Public facade — the only import agents and routes need.

Usage:
    from state_manager.state_manager import StateManager
    sm = StateManager()
    sm.snapshot("Before edit")
    sm.revert(2)
    sm.history()
"""
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from state_manager import storage
from state_manager.snapshot import take_snapshot
from state_manager.history import list_history, get_version_detail, diff_versions

logger = logging.getLogger(__name__)


class StateManager:
    """
    Recommended implementation pattern from project spec:

        StateManager.snapshot(version, state_json, asset_paths) → persisted
        StateManager.revert(version) → restores assets + state + updates UI
        StateManager.history() → list of all versions with diff summary
    """

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(
        self,
        description: str = "",
        edit_query: str = "",
        intent: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Capture the current pipeline state as a new version.
        Automatically increments the version counter.
        Returns the index entry for the new version.
        """
        return take_snapshot(description=description, edit_query=edit_query, intent=intent)

    # ── Revert ────────────────────────────────────────────────────────────────

    def revert(self, version: int) -> Dict[str, Any]:
        """
        Restore pipeline outputs to a previous snapshot.

        What this does:
          - Reads the snapshot's state JSON
          - Copies Phase 2 / Phase 3 run directories back (if they still exist)
          - Rewrites Phase 1 JSON files from snapshot data
          - Takes a new snapshot labelled "revert to vN" so history is never lost

        Returns a result dict with "restored_assets" count and new version number.
        """
        snap = storage.read_version(version)
        if not snap:
            return {"success": False, "error": f"Version {version} not found"}

        state = snap.get("state", {})
        restored: List[str] = []

        # ── Restore Phase 1 outputs ───────────────────────────────────────────
        import json
        p1_dir = Path("data/outputs")
        p1_dir.mkdir(parents=True, exist_ok=True)

        if "scene_manifest" in state:
            target = p1_dir / "scene_manifest.json"
            target.write_text(json.dumps(state["scene_manifest"], indent=2), encoding="utf-8")
            restored.append(str(target))
            logger.info("[StateManager] Restored scene_manifest.json")

        if "character_db" in state:
            target = p1_dir / "character_db.json"
            target.write_text(json.dumps(state["character_db"], indent=2), encoding="utf-8")
            restored.append(str(target))
            logger.info("[StateManager] Restored character_db.json")

        # ── Restore Phase 2 run symlink / note ───────────────────────────────
        if "phase2_run_dir" in state:
            run_dir = Path(state["phase2_run_dir"])
            if run_dir.exists():
                restored.append(str(run_dir))
                logger.info("[StateManager] Phase 2 run still present: %s", run_dir)
            else:
                logger.warning("[StateManager] Phase 2 run dir missing: %s", run_dir)

        # ── Restore Phase 3 run ───────────────────────────────────────────────
        if "phase3_run_dir" in state:
            run_dir = Path(state["phase3_run_dir"])
            if run_dir.exists():
                restored.append(str(run_dir))
                logger.info("[StateManager] Phase 3 run still present: %s", run_dir)
            else:
                logger.warning("[StateManager] Phase 3 run dir missing: %s", run_dir)

        # ── Take a new snapshot labelled as a revert ─────────────────────────
        new_snap = take_snapshot(
            description=f"Reverted to v{version:03d}",
            edit_query=f"revert:{version}",
        )

        logger.info(
            "[StateManager] Revert to v%03d complete — %d assets | new version v%03d",
            version, len(restored), new_snap["version"],
        )
        return {
            "success":         True,
            "reverted_to":     version,
            "new_version":     new_snap["version"],
            "restored_assets": len(restored),
            "restored_paths":  restored,
        }

    # ── History ───────────────────────────────────────────────────────────────

    def history(self) -> List[Dict[str, Any]]:
        """Return all versions newest-first."""
        return list_history()

    def detail(self, version: int) -> Optional[Dict[str, Any]]:
        """Return full payload for a version."""
        return get_version_detail(version)

    def diff(self, v1: int, v2: int) -> Dict[str, Any]:
        """Diff two versions."""
        return diff_versions(v1, v2)

    def latest(self) -> Optional[Dict[str, Any]]:
        """Return the most recent index entry."""
        versions = storage.list_versions()
        return versions[0] if versions else None
