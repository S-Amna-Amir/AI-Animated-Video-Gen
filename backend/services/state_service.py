"""
State service.
Reads run metadata from Phase2/Phase3 output dirs and writes version
snapshots to data/state_versions/{run_id}/v{N}.json.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── directory roots (relative to project root) ──────────────────────────────
PHASE1_DIR = Path("data/outputs/Phase1")
PHASE2_DIR = Path("data/outputs/Phase2")
PHASE3_DIR = Path("data/outputs/Phase3")
STATE_DIR = Path("data/state_versions")
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _latest_run(base: Path) -> str | None:
    """Return name of most-recently-modified sub-directory."""
    dirs = [d for d in base.iterdir() if d.is_dir()] if base.exists() else []
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime).name


# ── public API ────────────────────────────────────────────────────────────────

def list_runs() -> list[dict[str, Any]]:
    """Return summary list of all known runs across Phase2 and Phase3."""
    runs: dict[str, dict[str, Any]] = {}

    for phase_dir, phase_key in [(PHASE2_DIR, "phase2"), (PHASE3_DIR, "phase3")]:
        if not phase_dir.exists():
            continue
        for run_dir in sorted(phase_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            if run_id not in runs:
                runs[run_id] = {
                    "run_id": run_id,
                    "phase2_dir": None,
                    "phase3_dir": None,
                    "status": "unknown",
                    "timestamp": None,
                }
            runs[run_id][f"{phase_key}_dir"] = str(run_dir)

            # pick up timestamp from summary file
            summary_file = run_dir / f"{phase_key}_summary.json"
            if not summary_file.exists():
                # phase3 names it differently
                summary_file = run_dir / "phase3_output.json"
            if summary_file.exists():
                data = _load_json(summary_file)
                ts = data.get("timestamp")
                if ts:
                    runs[run_id]["timestamp"] = ts

    # derive status
    for info in runs.values():
        if info["phase3_dir"]:
            p3_dir = Path(info["phase3_dir"])
            if (p3_dir / "final_output.mp4").exists():
                info["status"] = "complete"
            else:
                info["status"] = "phase3_partial"
        elif info["phase2_dir"]:
            p2_dir = Path(info["phase2_dir"])
            if (p2_dir / "master_audio_track.mp3").exists():
                info["status"] = "phase2_complete"
            else:
                info["status"] = "phase2_partial"

    return sorted(runs.values(), key=lambda x: x.get("timestamp") or "", reverse=True)


def get_run(run_id: str) -> dict[str, Any]:
    """Return merged summary for a single run_id."""
    result: dict[str, Any] = {"run_id": run_id}

    p2_dir = PHASE2_DIR / run_id
    p3_dir = PHASE3_DIR / run_id

    if p2_dir.exists():
        result["phase2_summary"] = _load_json(p2_dir / "phase2_summary.json")
        result["phase2_config"] = _load_json(p2_dir / "phase2_config.json")
        result["phase2_dir"] = str(p2_dir)

    if p3_dir.exists():
        result["phase3_output"] = _load_json(p3_dir / "phase3_output.json")
        result["phase3_dir"] = str(p3_dir)
        result["has_video"] = (p3_dir / "final_output.mp4").exists()

    return result


def get_timing_manifest(run_id: str) -> list[dict[str, Any]] | None:
    p2_dir = PHASE2_DIR / run_id
    manifest_path = p2_dir / "timing_manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    return None


def list_files(run_id: str) -> list[dict[str, Any]]:
    """Return metadata for every output file belonging to run_id."""
    files: list[dict[str, Any]] = []

    def _walk(base: Path, phase: str) -> None:
        if not base.exists():
            return
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(base)
                files.append({
                    "filename": str(rel),
                    "phase": phase,
                    "size_bytes": path.stat().st_size,
                    "abs_path": str(path),
                    "modified": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })

    _walk(PHASE2_DIR / run_id, "phase2")
    _walk(PHASE3_DIR / run_id, "phase3")
    return files


def resolve_file(run_id: str, filename: str) -> Path | None:
    """Find a file by relative filename within a run's output dirs."""
    for base in (PHASE2_DIR / run_id, PHASE3_DIR / run_id):
        candidate = base / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def get_video_path(run_id: str) -> Path | None:
    candidate = PHASE3_DIR / run_id / "final_output.mp4"
    return candidate if candidate.exists() else None


# ── version snapshots ─────────────────────────────────────────────────────────

def _run_state_dir(run_id: str) -> Path:
    d = STATE_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_version(run_id: str) -> int:
    d = _run_state_dir(run_id)
    existing = [int(f.stem[1:]) for f in d.glob("v*.json") if f.stem[1:].isdigit()]
    return max(existing, default=0) + 1


def save_snapshot(
    run_id: str,
    phase: str,
    summary_path: str | None = None,
    asset_paths: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    version = _next_version(run_id)
    snapshot: dict[str, Any] = {
        "version": version,
        "run_id": run_id,
        "phase": phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "summary_path": summary_path,
        "asset_paths": asset_paths or [],
    }
    path = _run_state_dir(run_id) / f"v{version}.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot


def list_versions(run_id: str) -> list[dict[str, Any]]:
    d = _run_state_dir(run_id)
    versions = []
    for f in sorted(d.glob("v*.json")):
        try:
            versions.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return sorted(versions, key=lambda x: x.get("version", 0), reverse=True)


def revert_version(run_id: str, version: int) -> dict[str, Any]:
    """
    Restore state snapshot for a given version.
    Currently returns the snapshot metadata; actual asset restoration
    is a no-op stub (assets are already on disk from that run).
    """
    path = _run_state_dir(run_id) / f"v{version}.json"
    if not path.exists():
        raise FileNotFoundError(f"Version v{version} not found for run {run_id}")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    # Mark as the active version by bumping a pointer file
    pointer = _run_state_dir(run_id) / "current.json"
    pointer.write_text(json.dumps({"current_version": version}), encoding="utf-8")
    return snapshot


def get_current_version(run_id: str) -> int | None:
    pointer = _run_state_dir(run_id) / "current.json"
    if pointer.exists():
        data = _load_json(pointer)
        return data.get("current_version")
    versions = list_versions(run_id)
    return versions[0]["version"] if versions else None