"""
Phase 3 service.
Thin async wrapper around VideoAgent that:
  - Auto-detects the latest Phase 2 run directory when none is specified
  - Streams log lines to the WebSocket manager
  - Persists a state snapshot after completion
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from backend.websocket.manager import ws_manager
from backend.services.state_service import (
    save_snapshot,
    PHASE1_DIR,
    PHASE2_DIR,
    PHASE3_DIR,
)

logger = logging.getLogger(__name__)

# ── in-memory run status registry ────────────────────────────────────────────
_status: dict[str, dict[str, Any]] = {}


def get_status(run_id: str) -> dict[str, Any] | None:
    return _status.get(run_id)


def _set_status(run_id: str, **kwargs: Any) -> None:
    if run_id not in _status:
        _status[run_id] = {
            "run_id": run_id,
            "phase": "phase3",
            "pct": 0,
            "status": "starting",
            "errors": [],
        }
    _status[run_id].update(kwargs)


# ── helpers ───────────────────────────────────────────────────────────────────

def _latest_phase2_run() -> str | None:
    """Return path of the most-recently-modified Phase 2 sub-directory."""
    if not PHASE2_DIR.exists():
        return None
    dirs = [d for d in PHASE2_DIR.iterdir() if d.is_dir()]
    if not dirs:
        return None
    return str(max(dirs, key=lambda p: p.stat().st_mtime))


# ── main entry point ──────────────────────────────────────────────────────────

async def run_phase3(
    run_id: str,
    phase1_dir: str | None = None,
    phase2_run_dir: str | None = None,
    mock: bool = False,
    use_subtitles: bool = False,
) -> dict[str, Any]:
    """
    Run Phase 3 (VideoAgent) and return its result dict.
    Broadcasts log lines to WebSocket subscribers for run_id.
    """
    _set_status(run_id, status="running", pct=0)

    p1_dir = phase1_dir or str(PHASE1_DIR)
    p2_run = phase2_run_dir or _latest_phase2_run()

    if p2_run is None:
        msg = "Phase 3 error — no Phase 2 output directory found"
        await ws_manager.error(run_id, msg)
        _set_status(run_id, status="error", errors=[msg])
        return {"status": "failure", "error": msg}

    await ws_manager.info(run_id, f"Phase 3 starting — using Phase 2 dir: {p2_run}")
    _set_status(run_id, pct=5)

    try:
        from agents.video_agent.agent import VideoAgent  # type: ignore

        agent = VideoAgent(
            phase1_data_dir=p1_dir,
            phase2_run_dir=p2_run,
            phase3_output_dir=str(PHASE3_DIR),
            mock=mock,
            use_subtitles=use_subtitles,
            run_id=run_id,
        )

        await ws_manager.info(run_id, "Phase 3 agent initialised — generating images & compositing video...")
        _set_status(run_id, pct=10)

        result: dict[str, Any] = await agent.process()

    except ImportError as exc:
        msg = f"Phase 3 import error — {exc}"
        await ws_manager.error(run_id, msg)
        _set_status(run_id, status="error", errors=[msg])
        return {"status": "failure", "error": msg}
    except Exception as exc:
        msg = f"Phase 3 error — {exc}"
        await ws_manager.error(run_id, msg)
        _set_status(run_id, status="error", errors=[msg])
        return {"status": "failure", "error": msg}

    if result.get("status") == "success":
        _set_status(run_id, pct=100, status="complete")
        images = result.get("images_generated", 0)
        clips = result.get("clips_animated", 0)
        await ws_manager.success(
            run_id,
            f"✓ Phase 3 complete — {images} images, {clips} clips animated, final_output.mp4 saved",
        )

        save_snapshot(
            run_id=run_id,
            phase="phase3",
            summary_path=result.get("summary"),
            asset_paths=[result.get("video_path", "")],
            description=f"Phase 3 complete — {images} images, {clips} clips",
        )
    else:
        err = result.get("error", "Unknown Phase 3 error")
        _set_status(run_id, status="error", errors=[err])
        await ws_manager.error(run_id, f"✗ Phase 3 failed — {err}")

    return result