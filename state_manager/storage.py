"""
state_manager/storage.py
--------------------------
Append-only JSON file store for pipeline state snapshots.
Each version is a separate file: data/state_versions/v{N}_{timestamp}.json
Index file: data/state_versions/index.json

Design: simple file-based, no SQLite dependency, easy to inspect.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_VERSIONS_DIR = Path("data/state_versions")
INDEX_FILE = STATE_VERSIONS_DIR / "index.json"


def _ensure_dir() -> None:
    STATE_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> List[Dict]:
    _ensure_dir()
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(index: List[Dict]) -> None:
    _ensure_dir()
    INDEX_FILE.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_version(
    version: int,
    state_json: Dict[str, Any],
    asset_paths: List[str],
    description: str = "",
    edit_query: str = "",
    intent: Optional[Dict] = None,
) -> str:
    """
    Persist a state snapshot. Returns the path to the written file.
    """
    _ensure_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"v{version:03d}_{ts}.json"
    filepath = STATE_VERSIONS_DIR / filename

    payload = {
        "version":     version,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "description": description,
        "edit_query":  edit_query,
        "intent":      intent,
        "asset_paths": asset_paths,
        "state":       state_json,
    }
    filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update index
    index = _load_index()
    index.append({
        "version":     version,
        "timestamp":   payload["timestamp"],
        "description": description,
        "edit_query":  edit_query,
        "filename":    filename,
        "asset_count": len(asset_paths),
    })
    _save_index(index)

    logger.info("[Storage] Wrote version v%03d → %s", version, filename)
    return str(filepath)


def read_version(version: int) -> Optional[Dict[str, Any]]:
    """Load a specific snapshot by version number. Returns None if not found."""
    index = _load_index()
    entry = next((e for e in index if e["version"] == version), None)
    if not entry:
        return None
    filepath = STATE_VERSIONS_DIR / entry["filename"]
    if not filepath.exists():
        logger.warning("[Storage] Version file missing: %s", filepath)
        return None
    return json.loads(filepath.read_text(encoding="utf-8"))


def list_versions() -> List[Dict]:
    """Return all index entries, newest first."""
    return sorted(_load_index(), key=lambda e: e["version"], reverse=True)


def latest_version_number() -> int:
    """Return the highest version number stored, or 0 if none."""
    index = _load_index()
    return max((e["version"] for e in index), default=0)


def delete_version(version: int) -> bool:
    """Remove a version file and its index entry. Returns True on success."""
    index = _load_index()
    entry = next((e for e in index if e["version"] == version), None)
    if not entry:
        return False
    filepath = STATE_VERSIONS_DIR / entry["filename"]
    filepath.unlink(missing_ok=True)
    _save_index([e for e in index if e["version"] != version])
    logger.info("[Storage] Deleted version v%03d", version)
    return True
