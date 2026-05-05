"""
Phase 2 service.
Thin async wrapper around EnhancedAudioAgent that:
  - Streams log lines to the WebSocket manager
  - Persists a state snapshot after completion
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from backend.websocket.manager import ws_manager
from backend.services.state_service import save_snapshot, PHASE2_DIR, PHASE1_DIR

logger = logging.getLogger(__name__)

# ── in-memory run status registry ────────────────────────────────────────────
# Shared mutable dict; for a production system use Redis or a DB.
_status: dict[str, dict[str, Any]] = {}


def get_status(run_id: str) -> dict[str, Any] | None:
    return _status.get(run_id)


def _set_status(run_id: str, **kwargs: Any) -> None:
    if run_id not in _status:
        _status[run_id] = {"run_id": run_id, "phase": "phase2", "pct": 0, "status": "starting", "errors": []}
    _status[run_id].update(kwargs)


# ── main entry point ──────────────────────────────────────────────────────────

async def run_phase2(
    run_id: str,
    phase1_dir: str | None = None,
    phase2_output_dir: str | None = None,
    custom_voices: dict[str, str] | None = None,
    freesound_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Run Phase 2 (EnhancedAudioAgent) and return its result dict.
    Broadcasts log lines to WebSocket subscribers for run_id.
    """
    _set_status(run_id, status="running", pct=0)

    p1_dir = phase1_dir or str(PHASE1_DIR)
    p2_dir = phase2_output_dir or str(PHASE2_DIR)
    api_key = freesound_api_key or os.getenv("FREESOUND_API_KEY")

    await ws_manager.info(run_id, "Phase 2 starting — loading Phase 1 data...")
    _set_status(run_id, pct=5)

    try:
        # Import here so startup is fast even if deps are missing
        from agents.audio_agent.enhanced_agent import EnhancedAudioAgent  # type: ignore

        agent = EnhancedAudioAgent(
            phase1_data_dir=p1_dir,
            phase2_output_dir=p2_dir,
            custom_voice_mappings=custom_voices,
            freesound_api_key=api_key,
            run_id=run_id,
        )

        await ws_manager.info(run_id, f"Phase 2 agent initialised (run_id={agent.run_manager.current_run_id})")
        _set_status(run_id, pct=10)

        # Run the (potentially long) async process
        result: dict[str, Any] = await agent.process()

    except ImportError as exc:
        msg = f"Phase 2 import error — {exc}"
        await ws_manager.error(run_id, msg)
        _set_status(run_id, status="error", errors=[msg])
        return {"status": "failure", "error": msg}
    except Exception as exc:
        msg = f"Phase 2 error — {exc}"
        await ws_manager.error(run_id, msg)
        _set_status(run_id, status="error", errors=[msg])
        return {"status": "failure", "error": msg}

    if result.get("status") == "success":
        _set_status(run_id, pct=100, status="complete")
        await ws_manager.success(run_id, f"✓ Phase 2 complete — {result.get('audio_files_generated', 0)} audio files, {result.get('scenes_with_bgm', 0)} scenes with BGM")

        # Save state snapshot
        save_snapshot(
            run_id=run_id,
            phase="phase2",
            summary_path=result.get("summary"),
            asset_paths=[result.get("master_audio_track", ""), result.get("timing_manifest_path", "")],
            description=f"Phase 2 complete — {result.get('audio_files_generated', 0)} audio files",
        )
    else:
        err = result.get("error", "Unknown Phase 2 error")
        _set_status(run_id, status="error", errors=[err])
        await ws_manager.error(run_id, f"✗ Phase 2 failed — {err}")

    return result


# ── selective re-run ──────────────────────────────────────────────────────────

async def rerun_phase2_steps(
    run_id: str,
    steps: list[str],
    custom_voices: dict[str, str] | None = None,
    freesound_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Re-run a subset of Phase 2 steps.
    Accepted step values: "tts", "bgm", "compose", "full"
    """
    await ws_manager.info(run_id, f"Phase 2 partial re-run — steps: {steps}")

    if "full" in steps or set(steps) >= {"tts", "bgm", "compose"}:
        return await run_phase2(
            run_id,
            custom_voices=custom_voices,
            freesound_api_key=freesound_api_key,
        )

    # For now individual sub-steps also trigger the full agent;
    # a future optimisation can skip steps inside EnhancedAudioAgent.
    await ws_manager.warn(run_id, "Selective sub-step re-run not yet granular — running full Phase 2")
    return await run_phase2(
        run_id,
        custom_voices=custom_voices,
        freesound_api_key=freesound_api_key,
    )