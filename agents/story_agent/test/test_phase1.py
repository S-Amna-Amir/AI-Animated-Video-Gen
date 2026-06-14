"""
agents/story_agent/test/test_phase1.py
---------------------------------------
Unit tests for Phase 1 — Story, Script & Character Design.

Run with:
    pytest agents/story_agent/test/ -v
"""
import json
import os
import sys
from pathlib import Path

# Ensure project root is on the path when running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest


# ── Tool tests ─────────────────────────────────────────────────────────────────

class TestValidateScriptStructure:
    def setup_method(self):
        import mcp  # registers all tools
        from mcp.tool_executor import invoke_tool
        self.invoke = invoke_tool

    def test_valid_script_passes(self):
        script = (
            "INT. OFFICE - DAY\n"
            "A tense room. Papers everywhere.\n"
            "JOHN\n"
            "We need to act now.\n"
            "EXT. STREET - NIGHT\n"
            "Rain falls heavily.\n"
            "SARAH\n"
            "There's no time left.\n"
        )
        errors = self.invoke("validate_script_structure", {"script_text": script})
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_empty_script_fails(self):
        errors = self.invoke("validate_script_structure", {"script_text": ""})
        assert len(errors) > 0

    def test_missing_headings_fails(self):
        errors = self.invoke("validate_script_structure", {
            "script_text": "JOHN\nHello world.\n"
        })
        assert any("heading" in e.lower() for e in errors)

    def test_missing_dialogue_labels_fails(self):
        errors = self.invoke("validate_script_structure", {
            "script_text": "INT. ROOM - DAY\nSome action happens here.\n"
        })
        assert any("speaker" in e.lower() or "label" in e.lower() for e in errors)

    def test_strict_mode_requires_two_scenes(self):
        script = (
            "INT. ROOM - DAY\n"
            "Action.\n"
            "ALEX\n"
            "One scene only.\n"
        )
        errors = self.invoke("validate_script_structure", {
            "script_text": script,
            "strict_mode": True,
        })
        assert any("strict" in e.lower() or "minimum" in e.lower() for e in errors)


class TestGenerateScriptSegment:
    def setup_method(self):
        import mcp
        from mcp.tool_executor import invoke_tool
        self.invoke = invoke_tool

    def test_mock_script_structure(self):
        """Test that mock script (no API key) returns valid structure."""
        # Force mock by temporarily unsetting GROQ_API_KEY
        orig = os.environ.pop("GROQ_API_KEY", None)
        try:
            result = self.invoke("generate_script_segment", {
                "prompt": "A detective in rainy London",
                "num_scenes": 3,
            })
            assert "title" in result
            assert "scenes" in result
            assert isinstance(result["scenes"], list)
            assert len(result["scenes"]) == 3
            for scene in result["scenes"]:
                assert "scene_id" in scene
                assert "dialogue" in scene
                assert len(scene["dialogue"]) > 0
        finally:
            if orig is not None:
                os.environ["GROQ_API_KEY"] = orig

    def test_default_num_scenes(self):
        orig = os.environ.pop("GROQ_API_KEY", None)
        try:
            result = self.invoke("generate_script_segment", {"prompt": "Test"})
            assert len(result["scenes"]) == 5
        finally:
            if orig is not None:
                os.environ["GROQ_API_KEY"] = orig


# ── Planner helper tests ───────────────────────────────────────────────────────

class TestPlanner:
    def test_extract_unique_characters(self):
        from agents.story_agent.planner import extract_unique_characters
        scenes = [
            {"characters": ["ALEX", "MORGAN"], "dialogue": [
                {"speaker": "ALEX", "line": "Hi", "visual_cue": ""}
            ]},
            {"characters": ["MORGAN"], "dialogue": [
                {"speaker": "MORGAN", "line": "Bye", "visual_cue": ""},
                {"speaker": "ALEX",   "line": "Wait", "visual_cue": ""},
            ]},
        ]
        chars = extract_unique_characters(scenes)
        assert chars == ["ALEX", "MORGAN"]  # order preserved, no duplicates

    def test_infer_personality_no_lines(self):
        from agents.story_agent.planner import infer_personality
        result = infer_personality("GHOST", [])
        assert "mysterious" in result

    def test_infer_personality_urgent(self):
        from agents.story_agent.planner import infer_personality
        scenes = [{"dialogue": [
            {"speaker": "HERO", "line": "Run now! We must hurry!", "visual_cue": ""}
        ]}]
        result = infer_personality("HERO", scenes)
        assert "urgent" in result

    def test_parse_raw_script(self):
        from agents.story_agent.planner import parse_raw_script_to_manifest
        raw = (
            "INT. LAB - DAY\n"
            "Scientists work furiously.\n"
            "DR CHEN\n"
            "The experiment is ready.\n"
            "EXT. PARK - NIGHT\n"
            "Stars fill the sky.\n"
            "MAYA\n"
            "We did it.\n"
        )
        manifest = parse_raw_script_to_manifest(raw)
        assert manifest["total_scenes"] == 2
        assert len(manifest["scenes"]) == 2
        assert manifest["scenes"][0]["location"].startswith("INT.")
        assert len(manifest["scenes"][0]["dialogue"]) == 1


# ── Memory tool tests ──────────────────────────────────────────────────────────

class TestMemoryTools:
    def setup_method(self):
        os.environ["MEMORY_BACKEND"] = "mock"
        import mcp
        from mcp.tool_executor import invoke_tool
        self.invoke = invoke_tool

    def test_commit_and_query(self):
        self.invoke("commit_memory", {
            "collection": "test_scripts",
            "data":       {"title": "Test", "scenes": []},
            "doc_id":     "test_001",
        })
        results = self.invoke("query_memory", {
            "collection": "test_scripts",
            "query":      "test",
            "n_results":  5,
        })
        assert any(r["id"] == "test_001" for r in results)

    def test_commit_returns_confirmation(self):
        result = self.invoke("commit_memory", {
            "collection": "test",
            "data":       {"x": 1},
            "doc_id":     "test_confirm",
        })
        assert result["status"] == "committed"
        assert result["doc_id"] == "test_confirm"


# ── Workflow integration smoke test ───────────────────────────────────────────

class TestPhase1WorkflowSmoke:
    def test_auto_mode_completes(self):
        """End-to-end smoke: auto mode with mock LLM + memory + placeholder images."""
        os.environ["MEMORY_BACKEND"] = "mock"
        # Ensure no real API keys interfere
        orig_groq = os.environ.pop("GROQ_API_KEY", None)
        orig_oai  = os.environ.pop("OPENAI_API_KEY", None)

        try:
            from agents.orchestrator.workflow import run_phase1
            state = run_phase1(
                mode="auto",
                raw_input="A time traveller stranded in ancient Rome",
            )
            # HITL auto-approves in non-interactive mode (EOFError → yes)
            # The graph will have run through: scriptwriter → hitl → character → image → commit
            assert state["status"] in ("complete", "processing")
            assert "script" in state
            assert isinstance(state["script"], dict)
            assert "scenes" in state["script"]
        finally:
            if orig_groq: os.environ["GROQ_API_KEY"] = orig_groq
            if orig_oai:  os.environ["OPENAI_API_KEY"] = orig_oai
