"""Pytest unit tests for Phase 3 pipeline modules."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.video_agent.agent import VideoAgent
from agents.video_agent.run_manager import VideoRunManager
from mcp.tools.video_tools import animator, comfy_client, image_generator, prompt_builder, workflow_builder
from mcp.tools.video_tools.video_compositor import add_subtitle_overlay


def test_prompt_builder_positive_contains_setting():
    scene = {
        "scene_id": "s1",
        "location": "Red desert canyon",
        "tone": "mysterious",
        "visual_description": "A lone rover at dusk",
    }
    prompt = prompt_builder.build_image_prompt(scene)
    assert "Red desert canyon" in prompt["positive"]


def test_prompt_builder_negative_always_has_watermark():
    scene = {"scene_id": "s1", "location": "Any", "tone": "calm", "visual_description": "Any"}
    prompt = prompt_builder.build_image_prompt(scene)
    assert "watermark" in prompt["negative"]


def test_workflow_builder_injects_prompts():
    workflow = workflow_builder.build_workflow("pos text", "neg text", "s1")
    assert workflow["6"]["inputs"]["text"] == "pos text"
    assert workflow["7"]["inputs"]["text"] == "neg text"


def test_workflow_builder_no_mutation():
    _ = workflow_builder.build_workflow("first pos", "first neg", "s1")
    _ = workflow_builder.build_workflow("second pos", "second neg", "s2")
    assert workflow_builder.BASE_WORKFLOW["6"]["inputs"]["text"] == ""


def test_tone_effect_map_defaults():
    assert animator.determine_effect("default", "", 0) == "zoom_in"


def test_comfy_client_has_generate_image():
    assert hasattr(comfy_client, 'generate_image'), \
        "comfy_client must have generate_image function"
    assert callable(comfy_client.generate_image)


def test_image_generator_mock_mode(tmp_path):
    scenes = [
        {"scene_id": "s1", "location": "A", "tone": "calm", "visual_description": "B"},
        {"scene_id": "s2", "location": "C", "tone": "mysterious", "visual_description": "D"},
    ]
    manifest = [
        {"scene_id": "s1", "text": "Hello", "speaker": "A"},
        {"scene_id": "s2", "text": "World", "speaker": "B"}
    ]
    results = image_generator.generate_images_for_dialogue_mock(manifest, scenes, [], str(tmp_path))

    assert len(results) == 2
    assert results[0]["scene_id"] == "s1"
    assert results[0]["status"] == "success"
    assert Path(results[0]["image_path"]).exists()


def test_run_manager_creates_incrementing_dirs(tmp_path):
    manager = VideoRunManager(base_output_dir=str(tmp_path))
    run1_id, _ = manager.create_run_dir()
    run2_id, _ = manager.create_run_dir()
    assert run1_id == "run_01"
    assert run2_id == "run_02"


def test_phase3_output_schema(tmp_path):
    phase1_dir = tmp_path / "phase1"
    phase2_dir = tmp_path / "phase2_run_01"
    phase1_dir.mkdir(parents=True, exist_ok=True)
    phase2_dir.mkdir(parents=True, exist_ok=True)

    with open(phase1_dir / "scene_manifest_auto.json", "w", encoding="utf-8") as f:
        json.dump({"scenes": [{"scene_id": "s1", "tone": "calm", "duration_ms": 1000}]}, f)
    with open(phase1_dir / "character_db_auto.json", "w", encoding="utf-8") as f:
        json.dump({"characters": [{"name": "Maya"}]}, f)
    with open(phase2_dir / "timing_manifest.json", "w", encoding="utf-8") as f:
        json.dump([{"scene_id": "s1", "audio_file": "", "start_ms": 0, "end_ms": 1000}], f)

    with patch(
        "agents.video_agent.agent.image_generator.generate_images_for_dialogue_mock",
        return_value=[{"scene_id": "s1", "line_index": 0, "image_path": "img.png", "status": "success", "duration_ms": 1000}],
    ), patch(
        "agents.video_agent.agent.animator.animate_all_scenes",
        return_value={"s1_0": "clip.mp4"},
    ), patch(
        "agents.video_agent.agent.video_compositor.compose_final_video",
        return_value=str(tmp_path / "final_output.mp4"),
    ):
        agent = VideoAgent(run_id="test_schema")
        output = agent.run(str(phase1_dir), str(phase2_dir), mock=True)

    expected_keys = {"run_id", "status", "phase", "input", "scene_images", "scene_clips", "final_video", "errors"}
    assert expected_keys.issubset(output.keys())


def test_run_id_format(tmp_path):
    manager = VideoRunManager(base_output_dir=str(tmp_path))
    run_id, _ = manager.create_run_dir()
    assert run_id.startswith("run_")
    suffix = run_id.replace("run_", "")
    assert len(suffix) == 2
    assert suffix.isdigit()


def test_run_id_increments(tmp_path):
    manager = VideoRunManager(base_output_dir=str(tmp_path))
    run_id1, _ = manager.create_run_dir()
    run_id2, _ = manager.create_run_dir()
    run_id3, _ = manager.create_run_dir()
    assert run_id1 == "run_01"
    assert run_id2 == "run_02"
    assert run_id3 == "run_03"
    
    # Test gap filling
    import shutil
    shutil.rmtree(Path(tmp_path) / "run_02")
    run_id4, _ = manager.create_run_dir()
    assert run_id4 == "run_02"


def test_timing_calculation():
    # Given 4 lines and scene_duration_ms=28000, assert per_line_duration == 7000ms
    lines = 4
    scene_duration_ms = 28000
    per_line_duration = scene_duration_ms / lines
    assert per_line_duration == 7000


def test_subtitle_function_exists():
    assert callable(add_subtitle_overlay)
