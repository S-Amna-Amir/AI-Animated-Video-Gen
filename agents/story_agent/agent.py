"""
agents/story_agent/agent.py
----------------------------
Phase 1 LangGraph nodes:

  scriptwriter_node   — auto mode: generates script from prompt via LLM
  validator_node      — manual mode: validates + parses uploaded screenplay
  hitl_node           — human checkpoint: approve / reject / edit
  character_node      — extracts characters and builds profiles
  image_node          — generates character reference images
  memory_commit_node  — final commit of all outputs to persistent memory

All tool calls go through mcp.invoke_tool() — no direct API calls.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from shared.schemas.state import ProjectState, CharacterProfile
from shared.constants import OUTPUTS_DIR, STATUS_PROCESSING, STATUS_COMPLETE, STATUS_FAILED

logger = logging.getLogger(__name__)


# ── Scriptwriter Node (auto mode) ──────────────────────────────────────────────

def scriptwriter_node(state: ProjectState) -> ProjectState:
    """Generates a screenplay from the user's prompt using the LLM."""
    import mcp
    from mcp import invoke_tool

    logger.info("[Scriptwriter] Generating screenplay from prompt...")

    script = invoke_tool("generate_script_segment", {
        "prompt":     state["raw_input"],
        "num_scenes": 5,
        "genre":      "drama",
        "style":      "cinematic",
    })

    invoke_tool("commit_memory", {
        "collection": "scripts",
        "data":       script,
        "doc_id":     f"script_{_now()}",
    })

    return {
        **state,
        "script": script,
        "status": STATUS_PROCESSING,
        "memory_log": state.get("memory_log", []) + [{
            "timestamp":  _ts(),
            "collection": "scripts",
            "doc_id":     "script_latest",
            "summary":    f"Generated {len(script.get('scenes', []))} scenes from prompt.",
        }],
    }


# ── Validator Node (manual mode) ───────────────────────────────────────────────

def validator_node(state: ProjectState) -> ProjectState:
    """Validates and parses an uploaded screenplay."""
    import mcp
    from mcp import invoke_tool
    from agents.story_agent.planner import parse_raw_script_to_manifest

    logger.info("[Validator] Validating uploaded screenplay...")

    errors = invoke_tool("validate_script_structure", {
        "script_text": state["raw_input"],
        "strict_mode": False,
    })

    if errors:
        logger.warning(f"[Validator] FAILED — {len(errors)} error(s).")
        return {
            **state,
            "validation_errors": errors,
            "status":            STATUS_FAILED,
            "error_message": (
                "Script validation failed. Please fix:\n"
                + "\n".join(f"  • {e}" for e in errors)
            ),
        }

    logger.info("[Validator] PASSED — converting to SceneManifest.")
    script = parse_raw_script_to_manifest(state["raw_input"])

    invoke_tool("commit_memory", {
        "collection": "scripts",
        "data":       script,
        "doc_id":     f"script_manual_{_now()}",
    })

    return {
        **state,
        "script":            script,
        "validation_errors": [],
        "status":            STATUS_PROCESSING,
        "memory_log": state.get("memory_log", []) + [{
            "timestamp":  _ts(),
            "collection": "scripts",
            "doc_id":     "script_manual_latest",
            "summary":    f"Validated manual script: {len(script.get('scenes', []))} scenes.",
        }],
    }


# ── HITL Node ─────────────────────────────────────────────────────────────────

def hitl_node(state: ProjectState) -> ProjectState:
    logger.info("[HITL] Awaiting human review...")

    script = state.get("script", {})
    if not script:
        return {
            **state,
            "hitl_approved": False,
            "status":        STATUS_FAILED,
            "error_message": "HITL reached but no script was in state.",
        }

    _print_script_summary(script)

    choice    = state.get("hitl_decision")
    hitl_edit = state.get("hitl_edit")

    if choice:
        normalized = str(choice).strip().lower()
        logger.info(f"[HITL] Pre-supplied decision: {normalized}")

        if normalized in ("yes", "approve", "approved"):
            logger.info("[HITL] Approved.")
            return {
                **state,
                "hitl_approved": True,
                "status":        STATUS_PROCESSING,
                "memory_log": state.get("memory_log", []) + [{
                    "timestamp":  _ts(),
                    "collection": "hitl",
                    "doc_id":     "hitl_approval",
                    "summary":    "Script approved by human operator.",
                }],
            }

        if normalized in ("no", "reject", "rejected"):
            logger.info("[HITL] Rejected.")
            return {
                **state,
                "hitl_approved": False,
                "status":        STATUS_FAILED,
                "error_message": "Script rejected by human operator at HITL.",
            }

        if normalized in ("edit", "correct", "edited", "correction"):
            if isinstance(hitl_edit, dict):
                logger.info("[HITL] Script corrected by pre-supplied JSON.")
                return {
                    **state,
                    "script":        hitl_edit,
                    "hitl_approved": True,
                    "status":        STATUS_PROCESSING,
                    "memory_log": state.get("memory_log", []) + [{
                        "timestamp":  _ts(),
                        "collection": "hitl",
                        "doc_id":     "hitl_correction",
                        "summary":    "Script corrected and approved.",
                    }],
                }
            return {
                **state,
                "hitl_approved": False,
                "status":        STATUS_FAILED,
                "error_message": "HITL edit decision provided without a valid script JSON payload.",
            }

        # Unknown pre-supplied decision — fail fast instead of blocking on stdin
        logger.error(f"[HITL] Unrecognised pre-supplied decision '{normalized}' — failing.")
        return {
            **state,
            "hitl_approved": False,
            "status":        STATUS_FAILED,
            "error_message": f"Unrecognised HITL decision: '{normalized}'",
        }

    # No pre-supplied decision — interactive CLI path (main.py only)
    # In a web server context this branch should never be reached.
    while True:
        print("\n  Options: [yes] approve  |  [no] reject  |  [edit] paste JSON  |  [view] raw JSON\n")
        try:
            choice = input("  Your choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError):
            logger.warning("[HITL] Non-interactive environment — auto-approving.")
            choice = "yes"
        

        if choice == "yes":
            logger.info("[HITL] Approved.")
            return {
                **state,
                "hitl_approved": True,
                "status":        STATUS_PROCESSING,
                "memory_log": state.get("memory_log", []) + [{
                    "timestamp":  _ts(),
                    "collection": "hitl",
                    "doc_id":     "hitl_approval",
                    "summary":    "Script approved by human operator.",
                }],
            }

        elif choice == "no":
            logger.info("[HITL] Rejected.")
            return {
                **state,
                "hitl_approved": False,
                "status":        STATUS_FAILED,
                "error_message": "Script rejected by human operator at HITL.",
            }

        elif choice == "edit":
            corrected = _collect_json_edit()
            if corrected:
                return {
                    **state,
                    "script":        corrected,
                    "hitl_approved": True,
                    "status":        STATUS_PROCESSING,
                    "memory_log": state.get("memory_log", []) + [{
                        "timestamp":  _ts(),
                        "collection": "hitl",
                        "doc_id":     "hitl_correction",
                        "summary":    "Script corrected and approved.",
                    }],
                }
            print("  [!] Invalid JSON — try again.")

        elif choice == "view":
            print("\n" + json.dumps(script, indent=2))

        else:
            print(f"  [!] Unknown option '{choice}'.")


# ── Character Node ─────────────────────────────────────────────────────────────

def character_node(state: ProjectState) -> ProjectState:
    """Extracts characters from the approved script and builds profiles."""
    import mcp
    from mcp import invoke_tool
    from agents.story_agent.planner import (
        extract_unique_characters,
        infer_personality,
        generate_appearance,
    )

    logger.info("[CharacterDesigner] Building character profiles...")

    scenes    = state.get("script", {}).get("scenes", [])
    char_names = extract_unique_characters(scenes)
    logger.info(f"[CharacterDesigner] Found {len(char_names)} character(s): {char_names}")

    profiles: List[CharacterProfile] = []
    memory_log = list(state.get("memory_log", []))

    for name in char_names:
        personality  = infer_personality(name, scenes)
        appearance   = generate_appearance(name, personality)
        style_ref    = invoke_tool("query_stock_footage", {
            "character_name": name,
            "style":  "cinematic",
            "traits": personality.split(", "),
        })
        profile: CharacterProfile = {
            "name":            name,
            "personality":     personality,
            "appearance":      appearance,
            "style_reference": style_ref,
            "image_path":      None,
        }
        doc_id = f"character_{name.lower().replace(' ', '_')}"
        invoke_tool("commit_memory", {
            "collection": "characters",
            "data":       profile,
            "doc_id":     doc_id,
        })
        memory_log.append({
            "timestamp":  _ts(),
            "collection": "characters",
            "doc_id":     doc_id,
            "summary":    f"Profile committed for '{name}'.",
        })
        profiles.append(profile)
        logger.info(f"[CharacterDesigner] Profile built for '{name}'.")

    return {
        **state,
        "characters": profiles,
        "memory_log": memory_log,
        "status":     STATUS_PROCESSING,
    }


# ── Image Node ────────────────────────────────────────────────────────────────

def image_node(state: ProjectState) -> ProjectState:
    """Deprecated: Phase 1 image generation removed. Images now generated in Phase 3."""
    logger.info("[ImageNode] Skipped — character images generated in Phase 3 instead.")
    return state


# ── Memory Commit Node ─────────────────────────────────────────────────────────

def memory_commit_node(state: ProjectState) -> ProjectState:
    """Final node: commits all outputs to memory and saves JSON files."""
    from mcp import invoke_tool

    logger.info("[MemoryCommit] Committing final state to memory...")

    invoke_tool("commit_memory", {"collection": "scripts",    "data": state.get("script", {}),    "doc_id": "scene_manifest_final"})
    invoke_tool("commit_memory", {"collection": "characters", "data": state.get("characters", []), "doc_id": "character_db_final"})

    # ── Write to data/outputs/ as shared "current-run pointer" ───────────────
    # Phase 2 + 3 agents read scene_manifest.json from here by default.
    invoke_tool("save_json_file", {"data": state.get("script",     {}),  "filepath": str(OUTPUTS_DIR / "scene_manifest.json")})
    invoke_tool("save_json_file", {"data": state.get("characters", []),  "filepath": str(OUTPUTS_DIR / "character_db.json")})
    invoke_tool("save_json_file", {"data": state.get("memory_log", []),  "filepath": str(OUTPUTS_DIR / "memory_log.json")})

    # ── Create named project folder: data/runs/<timestamp>_<slug>/ ───────────
    title = state.get("script", {}).get("title", "untitled")
    project_run_id = ""
    try:
        import json as _json
        from agents.pipeline_run_manager import PipelineRunManager
        pm = PipelineRunManager.create(title)

        # Write Phase 1 outputs into phase1/ — ONLY location, no duplication
        (pm.phase1_dir / "scene_manifest.json").write_text(
            _json.dumps(state.get("script", {}), indent=2), encoding="utf-8"
        )
        (pm.phase1_dir / "character_db.json").write_text(
            _json.dumps(state.get("characters", []), indent=2), encoding="utf-8"
        )
        (pm.phase1_dir / "memory_log.json").write_text(
            _json.dumps(state.get("memory_log", []), indent=2), encoding="utf-8"
        )
        pm.mark_phase_complete(1)
        project_run_id = pm.run_id
        logger.info("[MemoryCommit] Project folder: %s", pm.run_dir)
    except Exception as e:
        logger.warning("[MemoryCommit] Could not create project folder: %s", e)

    memory_log = list(state.get("memory_log", [])) + [{
        "timestamp":  _ts(),
        "collection": "all",
        "doc_id":     "workflow_complete",
        "summary":    f"Phase 1 complete. Project run_id={project_run_id}",
    }]

    # Stash run_id on script so pipeline.py can report it to the frontend
    updated_script = {**state.get("script", {}), "_project_run_id": project_run_id}

    logger.info("[MemoryCommit] All outputs committed. Phase 1 COMPLETE.")
    return {**state, "script": updated_script, "status": STATUS_COMPLETE, "memory_log": memory_log}


# ── Private helpers ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _print_script_summary(script: dict) -> None:
    sep = "═" * 60
    print(f"\n{sep}")
    print("  HUMAN-IN-THE-LOOP REVIEW CHECKPOINT")
    print(sep)
    print(f"  Title  : {script.get('title', 'Untitled')}")
    print(f"  Genre  : {script.get('genre', 'Unknown')}")
    print(f"  Scenes : {script.get('total_scenes', 0)}")
    print(sep)
    for scene in script.get("scenes", []):
        print(f"\n  SCENE {scene['scene_id']} — {scene['location']}")
        print(f"  Characters : {', '.join(scene.get('characters', []))}")
        action = scene.get("action_description", "")[:120]
        print(f"  Action     : {action}...")
        for dl in scene.get("dialogue", []):
            print(f"    {dl['speaker']}: \"{dl['line']}\"")
            print(f"    [Visual: {dl['visual_cue']}]")
    print(sep)


def _collect_json_edit() -> dict | None:
    print("\n  Paste corrected JSON (blank line to finish):\n")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line == "":
            break
        lines.append(line)
    try:
        return json.loads("\n".join(lines).strip())
    except json.JSONDecodeError:
        return None
