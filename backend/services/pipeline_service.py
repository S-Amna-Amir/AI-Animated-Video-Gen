"""
Pipeline service.
Orchestrates a full Phase 1 → Phase 2 → Phase 3 run as a single
async background task.

Phase 1 is not yet integrated: the service checks that the required
manifest file exists and skips directly to Phase 2 if it does.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from backend.websocket.manager import ws_manager
from backend.services import phase2_service, phase3_service
from backend.services.state_service import PHASE1_DIR

logger = logging.getLogger(__name__)

# ── in-memory state ───────────────────────────────────────────────────────────
_pipeline_status: dict[str, dict[str, Any]] = {}
_cancel_flags: dict[str, bool] = {}

_MANIFEST = "scene_manifest_auto.json"


# ── status helpers ────────────────────────────────────────────────────────────

def get_pipeline_status(run_id: str) -> dict[str, Any] | None:
    return _pipeline_status.get(run_id)


def cancel_pipeline(run_id: str) -> None:
    """Signal a running pipeline to stop between phases."""
    _cancel_flags[run_id] = True


def _init_status(run_id: str, prompt: str) -> None:
    _pipeline_status[run_id] = {
        "run_id": run_id,
        "prompt": prompt,
        "current_phase": None,
        "overall_pct": 0,
        "phase2_status": "pending",
        "phase3_status": "pending",
        "status": "running",
        "errors": [],
    }
    _cancel_flags[run_id] = False


def _update(run_id: str, **kwargs: Any) -> None:
    if run_id in _pipeline_status:
        _pipeline_status[run_id].update(kwargs)


def _is_cancelled(run_id: str) -> bool:
    return _cancel_flags.get(run_id, False)


# ── main orchestrator ─────────────────────────────────────────────────────────

async def run_full_pipeline(
    run_id: str,
    prompt: str,
    scene_count: int = 4,
    art_style: str = "cinematic",
    enable_bgm: bool = True,
    enable_subtitles: bool = True,
    mock_mode: bool = False,
    llm_provider: str = "claude",
    voice_engine: str = "edge-tts",
) -> None:
    """
    Full pipeline orchestrator.  Intended to be run as a background task.

    Phase 1 — skipped (not yet integrated).  Checks that the manifest exists.
    Phase 2 — audio generation via EnhancedAudioAgent.
    Phase 3 — video generation via VideoAgent.

    Overall progress accounting:
        Phase 2 maps to  0 – 50 %
        Phase 3 maps to 50 – 100 %
    """
    _init_status(run_id, prompt)
    await ws_manager.info(run_id, f"Pipeline started — run_id={run_id}")

    # ── Phase 1 (skipped) ────────────────────────────────────────────────────
    await ws_manager.warn(
        run_id,
        "Phase 1 skipped — using existing data/outputs/Phase1/ files",
    )
    _update(run_id, current_phase="phase1_skip", overall_pct=0)

    manifest = PHASE1_DIR / _MANIFEST
    if not manifest.exists():
        msg = (
            f"Phase 1 manifest not found at {manifest}. "
            "Please place scene_manifest_auto.json in data/outputs/Phase1/ "
            "before running the pipeline."
        )
        await ws_manager.error(run_id, f"✗ {msg}")
        _update(run_id, status="error", errors=[msg])
        return

    await ws_manager.info(run_id, f"✓ Found {manifest} — proceeding to Phase 2")

    # ── cancellation check ───────────────────────────────────────────────────
    if _is_cancelled(run_id):
        await ws_manager.warn(run_id, "Pipeline cancelled before Phase 2")
        _update(run_id, status="cancelled")
        return

    # ── Phase 2 ──────────────────────────────────────────────────────────────
    _update(run_id, current_phase="phase2", overall_pct=0, phase2_status="running")
    await ws_manager.info(run_id, "▶ Starting Phase 2 — Audio generation...")

    try:
        p2_result = await phase2_service.run_phase2(run_id=run_id)
    except Exception as exc:
        msg = f"Pipeline error in Phase 2 — {exc}"
        await ws_manager.error(run_id, msg)
        _update(run_id, status="error", phase2_status="error", errors=[msg])
        return

    if p2_result.get("status") != "success":
        err = p2_result.get("error", "Phase 2 failed")
        _update(run_id, status="error", phase2_status="error", errors=[err])
        return

    _update(run_id, overall_pct=50, phase2_status="complete")

    # ── cancellation check ───────────────────────────────────────────────────
    if _is_cancelled(run_id):
        await ws_manager.warn(run_id, "Pipeline cancelled after Phase 2")
        _update(run_id, status="cancelled")
        return

    # ── Phase 3 ──────────────────────────────────────────────────────────────
    _update(run_id, current_phase="phase3", phase3_status="running")
    await ws_manager.info(run_id, "▶ Starting Phase 3 — Video generation...")

    try:
        p3_result = await phase3_service.run_phase3(
            run_id=run_id,
            mock=mock_mode,
            use_subtitles=enable_subtitles,
        )
    except Exception as exc:
        msg = f"Pipeline error in Phase 3 — {exc}"
        await ws_manager.error(run_id, msg)
        _update(run_id, status="error", phase3_status="error", errors=[msg])
        return

    if p3_result.get("status") != "success":
        err = p3_result.get("error", "Phase 3 failed")
        _update(run_id, status="error", phase3_status="error", errors=[err])
        return

    _update(run_id, overall_pct=100, phase3_status="complete", status="complete", current_phase="done")
    await ws_manager.success(run_id, f"🎬 Pipeline complete — run_id={run_id}")