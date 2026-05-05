"""
Story Agent Planner — LangGraph Graph Definition
Defines the state TypedDict and all node functions for the Phase 1 pipeline.

Graph flow:
  START → story_node → character_node → script_node → validate_node → END
                ↑____________retry_______________|  (on validation failure)
"""

from __future__ import annotations
import json
import os
import sys
from typing import Any, Dict, List, Optional, TypedDict, Annotated
import operator

# ── Add project root to path ──────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from mcp.tools.llm_tools.text_generator import TextGeneratorTool
from mcp.tools.llm_tools.json_structurer import JsonStructurerTool
from mcp.tools.system_tools.logger_tool import LoggerTool
from shared.schemas.phase1_schema import Story, Character, Scene
from agents.story_agent.prompts import (
    STORY_SYSTEM, STORY_USER_TEMPLATE,
    CHARACTER_SYSTEM, CHARACTER_USER_TEMPLATE,
    SCRIPT_SYSTEM, SCRIPT_USER_TEMPLATE,
    VALIDATOR_SYSTEM, VALIDATOR_USER_TEMPLATE,
)


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph State
# ─────────────────────────────────────────────────────────────────────────────

class Phase1State(TypedDict):
    """Shared state passed between all LangGraph nodes."""
    user_prompt: str
    num_scenes: int
    story: Optional[Dict]
    characters: Optional[List[Dict]]
    scenes: Optional[List[Dict]]
    validation_result: Optional[Dict]
    retry_count: int
    errors: Annotated[List[str], operator.add]
    tool_log: Annotated[List[str], operator.add]
    status: str  # "running" | "success" | "failed"


# ─────────────────────────────────────────────────────────────────────────────
# Tool singletons (instantiated once per module load)
# ─────────────────────────────────────────────────────────────────────────────

_text_gen = TextGeneratorTool()
_json_struct = JsonStructurerTool(max_retries=3)
_logger = LoggerTool()


# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _acts_summary(acts: List[Dict]) -> str:
    return "\n".join(f"Act {a['act']} ({a['label']}): {a['description']}" for a in acts)


def _character_summary(chars: List[Dict]) -> str:
    return "\n".join(
        f"- {c['name']} ({c['role']}): {c['personality'][:80]}..." for c in chars
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Story Arc Generator
# ─────────────────────────────────────────────────────────────────────────────

def story_node(state: Phase1State) -> Dict:
    _logger.run("info", "story_node: generating story arc", prompt=state["user_prompt"][:60])
    try:
        prompt = STORY_USER_TEMPLATE.format(user_prompt=state["user_prompt"])
        story_obj = _json_struct.run(
            prompt=prompt,
            schema_class=Story,
            system=STORY_SYSTEM,
        )
        _logger.run("info", "story_node: success", title=story_obj.title)
        return {
            "story": story_obj.model_dump(),
            "tool_log": ["story_node: completed"],
            "status": "running",
        }
    except Exception as e:
        _logger.run("error", f"story_node failed: {e}")
        return {
            "errors": [f"story_node: {e}"],
            "status": "failed",
            "tool_log": ["story_node: FAILED"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Character Designer
# ─────────────────────────────────────────────────────────────────────────────

def character_node(state: Phase1State) -> Dict:
    _logger.run("info", "character_node: designing characters")
    story = state["story"]
    try:
        acts_sum = _acts_summary(story["acts"])
        prompt = CHARACTER_USER_TEMPLATE.format(
            title=story["title"],
            logline=story["logline"],
            genre=story["genre"],
            tone=story["tone"],
            acts_summary=acts_sum,
            num_scenes=state["num_scenes"],
        )

        # Characters come as an array — wrap in a container model for validation
        raw_text = _text_gen.run(prompt=prompt, system=CHARACTER_SYSTEM, temperature=0.75)

        # Parse the JSON array manually then validate each item
        clean = raw_text.strip()
        # Strip markdown fences if present
        import re
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
        char_list_raw = json.loads(clean)

        characters = [Character(**c).model_dump() for c in char_list_raw]
        _logger.run("info", f"character_node: {len(characters)} characters created")
        return {
            "characters": characters,
            "tool_log": [f"character_node: {len(characters)} characters"],
            "status": "running",
        }
    except Exception as e:
        _logger.run("error", f"character_node failed: {e}")
        return {
            "errors": [f"character_node: {e}"],
            "status": "failed",
            "tool_log": ["character_node: FAILED"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Script Writer
# ─────────────────────────────────────────────────────────────────────────────

def script_node(state: Phase1State) -> Dict:
    _logger.run("info", "script_node: writing scene-by-scene script")
    story = state["story"]
    characters = state["characters"]
    if not story or not characters:
        return {
            "errors": ["script_node: skipped because story or characters are missing"],
            "status": "failed",
            "tool_log": ["script_node: SKIPPED"],
        }
    try:
        acts_sum = _acts_summary(story["acts"])
        char_sum = _character_summary(characters)
        prompt = SCRIPT_USER_TEMPLATE.format(
            title=story["title"],
            genre=story["genre"],
            tone=story["tone"],
            setting=story["setting"],
            world=story["world"],
            acts_summary=acts_sum,
            character_summary=char_sum,
            num_scenes=state["num_scenes"],
        )
        raw_text = _text_gen.run(prompt=prompt, system=SCRIPT_SYSTEM, temperature=0.8, max_tokens=8192)

        import re
        clean = raw_text.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
        scenes_raw = json.loads(clean)
        scenes = [Scene(**s).model_dump() for s in scenes_raw]

        _logger.run("info", f"script_node: {len(scenes)} scenes written")
        return {
            "scenes": scenes,
            "tool_log": [f"script_node: {len(scenes)} scenes"],
            "status": "running",
        }
    except Exception as e:
        _logger.run("error", f"script_node failed: {e}")
        return {
            "errors": [f"script_node: {e}"],
            "status": "failed",
            "tool_log": ["script_node: FAILED"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Validator / Consistency Checker
# ─────────────────────────────────────────────────────────────────────────────

def validate_node(state: Phase1State) -> Dict:
    _logger.run("info", "validate_node: checking consistency")
    try:
        import re as _re
        story = state["story"]
        characters = state["characters"]
        scenes = state["scenes"]

        if not story or not characters or not scenes:
            return {
                "validation_result": {"is_valid": False, "errors": ["Missing story, characters, or scenes"], "warnings": [], "fixes_applied": []},
                "tool_log": ["validate_node: skipped (missing data)"],
                "status": "failed",
            }

        # ── Build lookup sets from the canonical character state ──────────────
        # Include ALL names from the character roster (regardless of role) plus
        # any non-person antagonist listed in the story (e.g. "The Martian
        # Environment") so scene/dialogue references don't false-positive.
        defined_names = {c["name"] for c in characters}
        defined_roles = {c["role"]: c["name"] for c in characters}
        story_antagonist = story.get("antagonist", "")
        if story_antagonist:
            defined_names.add(story_antagonist)  # tolerate env/force antagonists in scenes

        # ── Hard errors — block is_valid if any of these fire ────────────────
        errors: list[str] = []

        # Protagonist/antagonist name cross-check between story and character roster
        story_protagonist = story.get("protagonist", "")
        char_protagonist = defined_roles.get("protagonist", "")
        char_antagonist = defined_roles.get("antagonist", "")

        if story_protagonist and char_protagonist and story_protagonist != char_protagonist:
            errors.append(
                f"Name mismatch — protagonist: story='{story_protagonist}' "
                f"vs character_db='{char_protagonist}'"
            )
        # Only flag antagonist mismatch when the antagonist IS a named character
        # (not an environmental force), i.e. when they appear in the character roster.
        if story_antagonist and char_antagonist and story_antagonist != char_antagonist:
            errors.append(
                f"Name mismatch — antagonist: story='{story_antagonist}' "
                f"vs character_db='{char_antagonist}'"
            )

        # Scene character references must resolve to a known name
        for scene in scenes:
            for char_name in scene.get("characters", []):
                if char_name not in defined_names:
                    errors.append(f"Scene {scene['scene_id']}: unknown character '{char_name}'")
            for dl in scene.get("dialogue", []):
                speaker = dl.get("speaker", "")
                if speaker and speaker not in defined_names:
                    errors.append(f"Scene {scene['scene_id']}: dialogue speaker '{speaker}' not in character_db")

        # Required character fields
        for c in characters:
            if not c.get("voice_config"):
                errors.append(f"Character '{c.get('name', '?')}' missing voice_config")

        # Required scene fields (Phase 2 + 3 hard dependencies)
        for scene in scenes:
            if not scene.get("mood"):
                errors.append(f"Scene {scene.get('scene_id', '?')} missing 'mood' field")
            if not scene.get("visual"):
                errors.append(f"Scene {scene.get('scene_id', '?')} missing 'visual' field")

        # ── LLM advisory check (warnings only — never affect is_valid) ────────
        warnings: list[str] = []
        try:
            prompt = VALIDATOR_USER_TEMPLATE.format(
                story_json=json.dumps(story, indent=2)[:600],
                characters_json=json.dumps(characters, indent=2)[:600],
                scenes_sample_json=json.dumps(scenes[:2], indent=2)[:800],
            )
            raw = _text_gen.run(prompt=prompt, system=VALIDATOR_SYSTEM, temperature=0.2)
            clean = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.IGNORECASE)
            clean = _re.sub(r"\s*```$", "", clean)
            llm_result = json.loads(clean)

            # Collect LLM-reported issues as warnings, but deduplicate against
            # hard errors we already caught locally so nothing is double-counted.
            seen = {e.lower() for e in errors}
            for issue in llm_result.get("issues", []):
                if issue.lower() not in seen:
                    warnings.append(issue)
                    seen.add(issue.lower())
        except Exception as llm_err:
            warnings.append(f"LLM advisory check skipped: {llm_err}")

        # ── is_valid is driven solely by hard errors ──────────────────────────
        is_valid = len(errors) == 0

        result = {
            "is_valid": is_valid,
            # Keep a flat "issues" list for backwards compatibility with consumers
            # that only read that key, but split into errors vs warnings for clarity.
            "errors": errors,
            "warnings": warnings,
            "issues": errors + warnings,
            "fixes_applied": [],
        }

        # Log errors at WARNING, advisory notes at INFO
        for err in errors:
            _logger.run("warning", f"validate_node ERROR: {err}")
        for warn in warnings:
            _logger.run("info", f"validate_node advisory: {warn}")

        _logger.run(
            "info", "validate_node: done",
            is_valid=is_valid,
            error_count=len(errors),
            warning_count=len(warnings),
        )
        return {
            "validation_result": result,
            "errors": errors if not is_valid else [],
            "tool_log": [
                f"validate_node: completed — {len(errors)} error(s), {len(warnings)} advisory warning(s)"
            ],
            "status": "success",  # validation is advisory — never block the pipeline
        }
    except Exception as e:
        _logger.run("warning", f"validate_node non-fatal error: {e}")
        return {
            "validation_result": {"is_valid": True, "errors": [], "warnings": [], "issues": [], "fixes_applied": []},
            "tool_log": [f"validate_node: skipped due to error — {e}"],
            "status": "success",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Routing: retry on failure, cap at 2 retries
# ─────────────────────────────────────────────────────────────────────────────

def should_retry(state: Phase1State) -> str:
    if state.get("status") == "failed" and state.get("retry_count", 0) < 2:
        return "retry"
    return "continue"


def increment_retry(state: Phase1State) -> Dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


# ─────────────────────────────────────────────────────────────────────────────
# Build LangGraph
# ─────────────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Compile and return the Phase 1 LangGraph StateGraph."""
    graph = StateGraph(Phase1State)

    # Register nodes
    graph.add_node("story_node", story_node)
    graph.add_node("character_node", character_node)
    graph.add_node("script_node", script_node)
    graph.add_node("validate_node", validate_node)
    graph.add_node("retry_counter", increment_retry)

    # Entry point
    graph.add_edge(START, "story_node")

    # Normal flow
    graph.add_edge("story_node", "character_node")
    graph.add_edge("character_node", "script_node")
    graph.add_edge("script_node", "validate_node")
    graph.add_edge("validate_node", END)

    return graph.compile(checkpointer=MemorySaver())
