"""
agents/orchestrator/workflow.py
--------------------------------
High-level workflow runner for Phase 1.

Provides run_phase1() — the single function called by main.py.
Handles state initialisation, graph execution, and result surfacing.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from shared.schemas.state import ProjectState
from shared.constants import STATUS_COMPLETE, STATUS_FAILED, OUTPUTS_DIR
from agents.orchestrator.graph import build_phase1_generate_graph, build_phase1_graph, build_phase1_resume_graph

logger = logging.getLogger(__name__)


def run_phase1_generate(mode: str, raw_input: str) -> ProjectState:
    """Run from mode_selector through scriptwriter/validator, stop before HITL."""
    if not raw_input.strip():
        raise ValueError("No input provided.")

    initial_state: ProjectState = {
        "input_mode":        mode,
        "raw_input":         raw_input,
        "script":            {},
        "characters":        [],
        "images":            [],
        "validation_errors": [],
        "hitl_approved":     False,
        "hitl_decision":     None,
        "hitl_edit":         None,
        "status":            "processing",
        "error_message":     None,
        "memory_log":        [],
    }

    app = build_phase1_generate_graph()   # graph that ends at HITL
    return app.invoke(initial_state)


def run_phase1_resume(parked_state: ProjectState, hitl_decision: str, hitl_edit: dict | None) -> ProjectState:
    decision = hitl_decision.strip().lower()

    if decision in ("yes", "approve"):
        state = {**parked_state, "hitl_approved": True,  "hitl_decision": decision, "hitl_edit": None}
        app = build_phase1_resume_graph(skip_hitl=True)   # ← skip the HITL node entirely

    elif decision in ("no", "reject"):
        state = {**parked_state, "hitl_approved": False, "hitl_decision": decision, "hitl_edit": None}
        app = build_phase1_resume_graph(skip_hitl=True)   # ← same, gate will route to END

    elif decision == "edit":
        # Edit still needs hitl_node to swap the script dict
        state = {**parked_state, "hitl_approved": False, "hitl_decision": decision, "hitl_edit": hitl_edit}
        app = build_phase1_resume_graph(skip_hitl=False)

    else:
        logger.error(f"[Workflow] Unrecognised HITL decision '{decision}'")
        return {
            **parked_state,
            "status":        STATUS_FAILED,
            "error_message": f"Unrecognised HITL decision: '{decision}'",
        }

    return app.invoke(state)


def print_summary(state: ProjectState) -> None:
    """Print a human-readable Phase 1 run summary."""
    sep = "═" * 60
    print(f"\n{sep}")
    print("  PROJECT MONTAGE — PHASE 1 COMPLETE")
    print(sep)
    print(f"  Status  : {state.get('status', 'unknown').upper()}")
    print(f"  Mode    : {state.get('input_mode', '?').upper()}")
    script = state.get("script", {})
    print(f"  Title   : {script.get('title', 'N/A')}")
    print(f"  Scenes  : {script.get('total_scenes', 0)}")
    print(f"  Chars   : {len(state.get('characters', []))}")
    print(f"  Images  : {len(state.get('images', []))}")
    if state.get("error_message"):
        print(f"\n  ERROR   : {state['error_message']}")
    print(f"\n  Outputs → {OUTPUTS_DIR.resolve()}/")
    print(f"    ├── scene_manifest.json")
    print(f"    ├── character_db.json")
    print(f"    ├── memory_log.json")
    print(f"    └── images/")
    for img in state.get("images", []):
        print(f"         └── {Path(img).name}")
    print(sep + "\n")
