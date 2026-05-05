"""
Unit Tests — Phase 1 Story Agent
Tests schema validation, tool utilities, and agent logic with mocked LLM calls.
Run: pytest agents/story_agent/tests/test_story_agent.py -v
"""

import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# ── Resolve project root ──────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.schemas.phase1_schema import (
    Phase1Output, Story, Character, Scene,
    VoiceConfig, DialogueLine, SceneVisual, Act,
)
from mcp.tools.llm_tools.json_structurer import JsonStructurerTool
from mcp.tools.system_tools.file_tool import FileTool


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — Minimal valid payloads
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_voice_config():
    return VoiceConfig(tone="warm", speed=1.0, pitch="medium", emotion="curious")


@pytest.fixture
def valid_character(valid_voice_config):
    return Character(
        name="ARIA",
        role="protagonist",
        personality="Courageous and empathetic.",
        appearance="A young woman with silver hair and bright eyes.",
        style_reference="Anime cinematic, vibrant colors.",
        voice_config=valid_voice_config,
        first_appearance=1,
        dialogue_samples=[],
    )


@pytest.fixture
def valid_scene():
    return Scene(
        scene_id=1,
        location="MARS SURFACE",
        setting_description="A barren red landscape under twin moons.",
        mood="mysterious",
        tone="awe-inspiring",
        dialogue=[
            DialogueLine(
                speaker="ARIA",
                line="There's water. There's actually water.",
                visual_cue="Close-up of ARIA, eyes wide with wonder.",
                emotion="amazed",
            )
        ],
        characters=["ARIA"],
        duration_seconds=25,
        visual=SceneVisual(
            image_prompt="Astronaut standing on Mars surface, looking at glowing ocean below cliff, dramatic lighting, 4K cinematic",
            camera_angle="wide shot",
            lighting="dramatic blue glow",
            color_palette="red and blue contrast",
            transition_in="fade",
            transition_out="cut",
        ),
    )


@pytest.fixture
def valid_story():
    return Story(
        title="The Hidden Ocean",
        logline="A young astronaut discovers life beneath the Martian surface.",
        genre="Sci-Fi Adventure",
        tone="wonder and tension",
        setting="Mars, near-future",
        time_period="2147",
        themes=["Discovery", "Survival"],
        acts=[
            Act(act=1, label="Introduction", description="Aria lands on Mars."),
            Act(act=2, label="Conflict", description="Signal detected underground."),
            Act(act=3, label="Climax", description="Aria dives into the ocean."),
            Act(act=4, label="Resolution", description="Contact with Earth confirmed."),
        ],
        protagonist="ARIA",
        antagonist=None,
        world="A colonised Mars where resources are running low.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_voice_config_speed_bounds(self):
        with pytest.raises(Exception):
            VoiceConfig(tone="calm", speed=3.0, pitch="high", emotion="happy")

    def test_scene_duration_minimum(self):
        with pytest.raises(Exception):
            Scene(
                scene_id=1, location="X", setting_description="Y", mood="tense",
                tone="dark", dialogue=[], characters=[], duration_seconds=2,
                visual=SceneVisual(image_prompt="x", camera_angle="shot", lighting="a",
                                   color_palette="b", transition_in="cut", transition_out="cut"),
            )

    def test_phase1_output_requires_scenes(self, valid_story, valid_character):
        with pytest.raises(Exception):
            Phase1Output(
                workflow_id="test", timestamp="2026-01-01", user_prompt="test",
                story=valid_story, characters=[valid_character], scenes=[],
            )

    def test_phase1_output_requires_characters(self, valid_story, valid_scene):
        with pytest.raises(Exception):
            Phase1Output(
                workflow_id="test", timestamp="2026-01-01", user_prompt="test",
                story=valid_story, characters=[], scenes=[valid_scene],
            )

    def test_valid_phase1_output(self, valid_story, valid_character, valid_scene):
        out = Phase1Output(
            workflow_id="wf_001",
            timestamp="2026-01-01T00:00:00",
            user_prompt="A young astronaut discovers a hidden ocean on Mars",
            story=valid_story,
            characters=[valid_character],
            scenes=[valid_scene],
        )
        assert out.story.title == "The Hidden Ocean"
        assert len(out.characters) == 1
        assert len(out.scenes) == 1

    def test_phase2_handoff_structure(self, valid_story, valid_character, valid_scene):
        out = Phase1Output(
            workflow_id="wf_002",
            timestamp="2026-01-01T00:00:00",
            user_prompt="test",
            story=valid_story,
            characters=[valid_character],
            scenes=[valid_scene],
        )
        handoff = out.to_phase2_handoff()
        assert "ARIA" in handoff
        assert "voice_config" in handoff["ARIA"]

    def test_phase3_handoff_structure(self, valid_story, valid_character, valid_scene):
        out = Phase1Output(
            workflow_id="wf_003",
            timestamp="2026-01-01T00:00:00",
            user_prompt="test",
            story=valid_story,
            characters=[valid_character],
            scenes=[valid_scene],
        )
        handoff = out.to_phase3_handoff()
        assert "scenes" in handoff
        assert handoff["scenes"][0]["scene_id"] == 1
        assert "visual" in handoff["scenes"][0]


# ─────────────────────────────────────────────────────────────────────────────
# JSON Structurer Tool Tests (no live API)
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonStructurerTool:
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_strip_fences(self, mock_anthropic):
        tool = JsonStructurerTool()
        raw = '```json\n{"title": "Test"}\n```'
        result = tool._strip_fences(raw)
        assert result == '{"title": "Test"}'

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_parse_only_valid(self, mock_anthropic):
        from pydantic import BaseModel
        class Simple(BaseModel):
            title: str

        tool = JsonStructurerTool()
        obj = tool.parse_only('{"title": "Hello"}', Simple)
        assert obj.title == "Hello"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_parse_only_invalid_raises(self, mock_anthropic):
        from pydantic import BaseModel
        class Simple(BaseModel):
            title: str

        tool = JsonStructurerTool()
        with pytest.raises(Exception):
            tool.parse_only('{"wrong_field": "Hello"}', Simple)


# ─────────────────────────────────────────────────────────────────────────────
# File Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFileTool:
    def test_write_and_read_json(self, tmp_path):
        tool = FileTool()
        path = str(tmp_path / "test.json")
        data = {"key": "value", "number": 42}
        tool.run("write_json", path, data)
        result = tool.run("read_json", path)
        assert result["key"] == "value"
        assert result["number"] == 42

    def test_write_and_read_text(self, tmp_path):
        tool = FileTool()
        path = str(tmp_path / "test.txt")
        tool.run("write_text", path, "Hello Phase 1")
        result = tool.run("read_text", path)
        assert result == "Hello Phase 1"

    def test_unknown_action_raises(self):
        tool = FileTool()
        with pytest.raises(ValueError, match="Unknown FileTool action"):
            tool.run("delete", "/tmp/x.json")


# ─────────────────────────────────────────────────────────────────────────────
# Story Agent Integration Test (fully mocked)
# ─────────────────────────────────────────────────────────────────────────────

MOCK_STORY = {
    "title": "The Hidden Ocean",
    "logline": "An astronaut finds water on Mars.",
    "genre": "Sci-Fi",
    "tone": "wonder",
    "setting": "Mars",
    "time_period": "2147",
    "themes": ["Discovery"],
    "acts": [
        {"act": 1, "label": "Intro", "description": "Start."},
        {"act": 2, "label": "Conflict", "description": "Middle."},
        {"act": 3, "label": "Climax", "description": "Peak."},
        {"act": 4, "label": "Resolution", "description": "End."},
    ],
    "protagonist": "ARIA",
    "antagonist": None,
    "world": "A colonised Mars.",
}

MOCK_CHARACTERS = [
    {
        "name": "ARIA",
        "role": "protagonist",
        "personality": "Brave and curious.",
        "appearance": "Young woman, silver hair.",
        "style_reference": "Anime cinematic.",
        "voice_config": {"tone": "warm", "speed": 1.0, "pitch": "medium", "emotion": "curious"},
        "first_appearance": 1,
        "dialogue_samples": [],
    }
]

MOCK_SCENES = [
    {
        "scene_id": 1,
        "location": "MARS SURFACE",
        "setting_description": "Red landscape.",
        "mood": "mysterious",
        "tone": "wonder",
        "dialogue": [
            {"speaker": "ARIA", "line": "Water!", "visual_cue": "Close-up.", "emotion": "amazed"}
        ],
        "characters": ["ARIA"],
        "duration_seconds": 20,
        "visual": {
            "image_prompt": "Mars surface, astronaut, glowing ocean below.",
            "camera_angle": "wide shot",
            "lighting": "blue glow",
            "color_palette": "red and blue",
            "transition_in": "fade",
            "transition_out": "cut",
        },
    }
]

MOCK_VALIDATION = {"is_valid": True, "issues": [], "fixes_applied": []}


class TestStoryAgentMocked:
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("agents.story_agent.planner._json_struct")
    @patch("agents.story_agent.planner._text_gen")
    def test_full_run_mocked(self, mock_text_gen, mock_json_struct, tmp_path):
        import json

        mock_json_struct.run.return_value = Story(**MOCK_STORY)
        mock_text_gen.run.side_effect = [
            json.dumps(MOCK_CHARACTERS),  # character_node
            json.dumps(MOCK_SCENES),       # script_node
            json.dumps(MOCK_VALIDATION),   # validate_node
        ]

        from agents.story_agent.agent import StoryAgent
        agent = StoryAgent(output_dir=str(tmp_path))
        result = agent.run("A young astronaut discovers a hidden ocean on Mars", num_scenes=2)

        assert result.story.title == "The Hidden Ocean"
        assert len(result.characters) == 1
        assert result.characters[0].name == "ARIA"
        assert len(result.scenes) == 1
        assert result.scenes[0].location == "MARS SURFACE"
        assert result.phase2_audio_handoff is not None
        assert result.phase3_video_handoff is not None
        # Check artefacts were saved
        assert (tmp_path / "story.json").exists()
        assert (tmp_path / "characters.json").exists()
        assert (tmp_path / "script.json").exists()
        assert (tmp_path / "phase2_audio_handoff.json").exists()
        assert (tmp_path / "phase3_video_handoff.json").exists()
        assert (tmp_path / "summary.json").exists()
        assert (tmp_path / "phase1_output.json").exists()

    def test_empty_prompt_raises(self, tmp_path):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                from agents.story_agent.agent import StoryAgent
                agent = StoryAgent(output_dir=str(tmp_path))
                with pytest.raises(ValueError, match="user_prompt"):
                    agent.run("")

    def test_invalid_num_scenes_raises(self, tmp_path):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                from agents.story_agent.agent import StoryAgent
                agent = StoryAgent(output_dir=str(tmp_path))
                with pytest.raises(ValueError, match="num_scenes"):
                    agent.run("test", num_scenes=10)
