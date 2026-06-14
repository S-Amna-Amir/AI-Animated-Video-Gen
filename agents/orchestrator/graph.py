"""
agents/orchestrator/graph.py
-----------------------------
LangGraph StateGraph for Phase 1 — Story, Script & Character Design.

Graph topology:
  mode_selector
    ├── (manual) → validator → [fail: END] → hitl
    └── (auto)   → scriptwriter             → hitl
                                              ├── (rejected) → END
                                              └── (approved) → character → image → memory_commit → END
"""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from shared.schemas.state import ProjectState
from agents.story_agent.agent import (
    scriptwriter_node,
    validator_node,
    hitl_node,
    character_node,
    memory_commit_node,
)

logger = logging.getLogger(__name__)


# ── Mode Selector ──────────────────────────────────────────────────────────────

def mode_selector_node(state: ProjectState) -> ProjectState:
    """Entry node: normalises input_mode, no other processing."""
    mode = state.get("input_mode", "auto").strip().lower()
    if mode not in ("manual", "auto"):
        logger.warning(f"[ModeSelector] Unknown mode '{mode}' — defaulting to 'auto'.")
        mode = "auto"
    logger.info(f"[ModeSelector] Mode: {mode.upper()}")
    return {**state, "input_mode": mode, "status": "processing"}


# ── Routing functions ──────────────────────────────────────────────────────────

def _route_mode(state: ProjectState) -> Literal["manual", "auto"]:
    return state.get("input_mode", "auto")


def _route_validation(state: ProjectState) -> Literal["pass", "fail"]:
    return "fail" if state.get("validation_errors") else "pass"


def _route_hitl(state: ProjectState) -> Literal["approved", "rejected"]:
    return "approved" if state.get("hitl_approved", False) else "rejected"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_phase1_graph() -> StateGraph:
    """Compile and return the Phase 1 LangGraph application."""
    g = StateGraph(ProjectState)

    # Register nodes
    g.add_node("mode_selector",  mode_selector_node)
    g.add_node("validator",      validator_node)
    g.add_node("scriptwriter",   scriptwriter_node)
    g.add_node("hitl",           hitl_node)
    g.add_node("character",      character_node)
    g.add_node("memory_commit",  memory_commit_node)

    # Entry point
    g.set_entry_point("mode_selector")

    # Mode routing
    g.add_conditional_edges(
        "mode_selector",
        _route_mode,
        {"manual": "validator", "auto": "scriptwriter"},
    )

    # Validation routing
    g.add_conditional_edges(
        "validator",
        _route_validation,
        {"pass": "hitl", "fail": END},
    )

    # Scriptwriter always goes to HITL
    g.add_edge("scriptwriter", "hitl")

    # HITL routing
    g.add_conditional_edges(
        "hitl",
        _route_hitl,
        {"approved": "character", "rejected": END},
    )

    # Linear downstream pipeline
    g.add_edge("character",    "memory_commit")
    g.add_edge("memory_commit", END)

    return g.compile()

def build_phase1_generate_graph() -> StateGraph:
    """Stops after script generation (before HITL)."""
    g = StateGraph(ProjectState)
    g.add_node("mode_selector", mode_selector_node)
    g.add_node("validator",     validator_node)
    g.add_node("scriptwriter",  scriptwriter_node)

    g.set_entry_point("mode_selector")
    g.add_conditional_edges(
        "mode_selector", _route_mode,
        {"manual": "validator", "auto": "scriptwriter"},
    )
    g.add_conditional_edges(
        "validator", _route_validation,
        {"pass": END, "fail": END},   # both exit; caller checks status
    )
    g.add_edge("scriptwriter", END)
    return g.compile()


def build_phase1_resume_graph(skip_hitl: bool = False) -> StateGraph:
    g = StateGraph(ProjectState)

    if skip_hitl:
        g.add_node("hitl_gate",     _hitl_gate_node)
        g.add_node("character",     character_node)
        g.add_node("memory_commit", memory_commit_node)

        g.set_entry_point("hitl_gate")
        g.add_conditional_edges(
            "hitl_gate", _route_hitl,
            {"approved": "character", "rejected": END},
        )
    else:
        g.add_node("hitl",          hitl_node)
        g.add_node("character",     character_node)
        g.add_node("memory_commit", memory_commit_node)

        g.set_entry_point("hitl")
        g.add_conditional_edges(
            "hitl", _route_hitl,
            {"approved": "character", "rejected": END},
        )

    g.add_edge("character",     "memory_commit")
    g.add_edge("memory_commit", END)
    return g.compile()


def _hitl_gate_node(state: ProjectState) -> ProjectState:
    """
    Lightweight gate node — no I/O, no prompts.
    Just logs the pre-baked decision and passes state through unchanged.
    The routing function _route_hitl reads hitl_approved and branches.
    """
    approved = state.get("hitl_approved", False)
    logger.info(f"[HITLGate] Decision already applied — hitl_approved={approved}")
    return state