"""
state_manager/history.py
--------------------------
Version history queries and diff summaries.
"""
import logging
from typing import Any, Dict, List, Optional

from state_manager import storage

logger = logging.getLogger(__name__)


def list_history() -> List[Dict[str, Any]]:
    """Return all versions newest-first with human-readable summary."""
    versions = storage.list_versions()
    result = []
    for v in versions:
        result.append({
            "version":     v["version"],
            "timestamp":   v["timestamp"],
            "description": v.get("description") or "(no description)",
            "edit_query":  v.get("edit_query", ""),
            "asset_count": v.get("asset_count", 0),
            "filename":    v.get("filename", ""),
        })
    return result


def get_version_detail(version: int) -> Optional[Dict[str, Any]]:
    """Return full snapshot payload for a version, or None."""
    return storage.read_version(version)


def diff_versions(v1: int, v2: int) -> Dict[str, Any]:
    """
    Produce a simple diff summary between two versions.
    Compares top-level state keys and asset counts.
    """
    snap1 = storage.read_version(v1)
    snap2 = storage.read_version(v2)

    if not snap1 or not snap2:
        return {"error": f"Version {v1 if not snap1 else v2} not found"}

    state1 = snap1.get("state", {})
    state2 = snap2.get("state", {})

    keys1, keys2 = set(state1.keys()), set(state2.keys())

    added   = list(keys2 - keys1)
    removed = list(keys1 - keys2)
    changed = [
        k for k in keys1 & keys2
        if str(state1[k])[:200] != str(state2[k])[:200]
    ]

    assets1 = set(snap1.get("asset_paths", []))
    assets2 = set(snap2.get("asset_paths", []))

    return {
        "v1": v1, "v2": v2,
        "state_keys_added":   added,
        "state_keys_removed": removed,
        "state_keys_changed": changed,
        "assets_added":   len(assets2 - assets1),
        "assets_removed": len(assets1 - assets2),
        "asset_count_v1": len(assets1),
        "asset_count_v2": len(assets2),
    }


def latest_version() -> Optional[Dict[str, Any]]:
    """Return the most recent version's index entry."""
    versions = storage.list_versions()
    return versions[0] if versions else None
