"""Scene image generation orchestration for Phase 3."""

import logging
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from . import comfy_client, prompt_builder

logger = logging.getLogger(__name__)



def generate_images_for_dialogue(
    manifest_entries: list[dict[str, Any]], 
    scenes: list[dict[str, Any]], 
    characters: list[dict[str, Any]], 
    run_dir: str
) -> list[dict[str, Any]]:
    """
    Generate one image per dialogue line using Hugging Face API.
    """
    results: list[dict[str, Any]] = []
    
    # Calculate line counts per scene for duration splitting
    scene_line_counts = Counter(str(entry.get("scene_id", "")) for entry in manifest_entries)
    
    # Create maps for easy lookup
    scenes_map = {str(scene.get("scene_id", "")): scene for scene in scenes}
    chars_map = {str(char.get("name", "")).upper(): char for char in characters}

    total = len(manifest_entries)
    
    for index, entry in enumerate(manifest_entries):
        scene_id = str(entry.get("scene_id", ""))
        speaker = str(entry.get("speaker", "")).upper()
        dialogue_text = str(entry.get("text", ""))
        
        logger.info("Generating dialogue image %d of %d: scene_id=%s, speaker=%s...", index + 1, total, scene_id, speaker)
        
        scene_data = scenes_map.get(scene_id, {})
        char_data = chars_map.get(speaker, {})
        
        prompt_used = prompt_builder.build_dialogue_image_prompt(
            scene=scene_data, 
            character=char_data, 
            dialogue_text=dialogue_text, 
            line_index=index
        )
        
        line_count = scene_line_counts.get(scene_id, 1)
        scene_duration_ms = entry.get("scene_duration_ms", 5000 * line_count)
        duration_ms = scene_duration_ms / max(1, line_count)
        
        try:
            image_bytes = comfy_client.generate_image(
                positive_prompt=prompt_used["positive"],
                negative_prompt=prompt_used["negative"],
                scene_id=scene_id,
            )

            output_path = Path(run_dir) / "images" / f"scene_{scene_id}_line_{index}.png"
            saved_path = comfy_client.save_image(image_bytes, str(output_path))
            
            status = "success"
            error_msg = ""
            logger.info("✓ Scene %s line %d done — saved to %s", scene_id, index, saved_path)
        except Exception as exc:
            logger.exception("Dialogue image generation failed for scene_id=%s line=%d", scene_id, index)
            saved_path = ""
            status = "failed"
            error_msg = str(exc)
            logger.error("✗ Scene %s line %d failed — %s", scene_id, index, error_msg)

        results.append({
            "scene_id": scene_id,
            "line_index": index,
            "speaker": speaker,
            "text": dialogue_text,
            "image_path": saved_path,
            "audio_file": str(entry.get("audio_file", "")),
            "start_ms": int(entry.get("cumulative_start_ms", 0)),
            "duration_ms": duration_ms,
            "status": status,
            "error": error_msg
        })

    return results


def generate_placeholder_image(scene_id: str, line_index: int, run_dir: str) -> str:
    """
    Create a simple black 512x512 placeholder PNG for mock mode.
    """
    output_path = Path(run_dir) / "images" / f"scene_{scene_id}_line_{line_index}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (512, 512), color="black")
    image.save(output_path, format="PNG")

    return str(output_path)


def generate_images_for_dialogue_mock(
    manifest_entries: list[dict[str, Any]], 
    scenes: list[dict[str, Any]], 
    characters: list[dict[str, Any]], 
    run_dir: str
) -> list[dict[str, Any]]:
    """
    Generate placeholder images per dialogue line for mock/test flows.
    """
    results: list[dict[str, Any]] = []
    scene_line_counts = Counter(str(entry.get("scene_id", "")) for entry in manifest_entries)
    
    for index, entry in enumerate(manifest_entries):
        scene_id = str(entry.get("scene_id", ""))
        speaker = str(entry.get("speaker", "")).upper()
        dialogue_text = str(entry.get("text", ""))
        
        line_count = scene_line_counts.get(scene_id, 1)
        scene_duration_ms = entry.get("scene_duration_ms", 5000 * line_count)
        duration_ms = scene_duration_ms / max(1, line_count)
        
        image_path = generate_placeholder_image(scene_id, index, run_dir)
        
        results.append({
            "scene_id": scene_id,
            "line_index": index,
            "speaker": speaker,
            "text": dialogue_text,
            "image_path": image_path,
            "audio_file": str(entry.get("audio_file", "")),
            "start_ms": int(entry.get("cumulative_start_ms", 0)),
            "duration_ms": duration_ms,
            "status": "success",
            "error": ""
        })

    return results

def generate_all_scenes_mock(scenes: list, run_dir: str) -> dict:
    """Mock mode: generates placeholder black images without calling HF API."""
    import os
    from PIL import Image
    results = {}
    os.makedirs(os.path.join(run_dir, "images"), exist_ok=True)
    for scene in scenes:
        scene_id = str(scene.get("scene_id", scene.get("id", "unknown")))
        image_path = os.path.join(run_dir, "images", f"scene_{scene_id}.png")
        img = Image.new("RGB", (512, 512), color=(0, 0, 0))
        img.save(image_path)
        results[scene_id] = {
            "scene_id": scene_id,
            "image_path": image_path,
            "status": "success",
            "prompt_used": {"positive": "mock", "negative": "mock"}
        }
    return results

def generate_scene_image(scene: dict[str, Any], run_dir: str) -> dict[str, Any]:
    """
    Generate one scene image using Hugging Face API.
    """
    scene_id = str(scene.get("scene_id", "")).strip()
    if not scene_id:
        logger.error("Scene generation failed: scene is missing required field: scene_id")
        return {
            "scene_id": "",
            "image_path": "",
            "status": "failed",
            "error": "scene is missing required field: scene_id"
        }

    prompt_used = prompt_builder.build_image_prompt(scene)
    
    try:
        image_bytes = comfy_client.generate_image(
            positive_prompt=prompt_used["positive"],
            negative_prompt=prompt_used["negative"],
            scene_id=scene_id,
        )

        output_path = Path(run_dir) / "images" / f"scene_{scene_id}.png"
        saved_path = comfy_client.save_image(image_bytes, str(output_path))

        return {
            "scene_id": scene_id,
            "image_path": saved_path,
            "status": "success",
            "prompt_used": prompt_used,
        }
    except Exception as exc:
        logger.exception("Scene generation failed for %s", scene_id)
        return {
            "scene_id": scene_id,
            "image_path": "",
            "status": "failed",
            "error": str(exc),
            "prompt_used": prompt_used,
        }

def generate_all_scenes(scenes: list[dict[str, Any]], run_dir: str) -> dict[str, dict[str, Any]]:
    """
    Generate images for all scenes sequentially via Hugging Face API.
    """
    results: dict[str, dict[str, Any]] = {}
    total = len(scenes)

    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id", "")).strip() or f"scene_{index}"
        logger.info("Generating scene %d of %d: scene_id=%s...", index, total, scene_id)

        result_dict = generate_scene_image(scene, run_dir)
        results[scene_id] = result_dict

        if result_dict.get("status") == "success":
            logger.info("✓ Scene %s done — saved to %s", scene_id, result_dict.get("image_path"))
        else:
            logger.error("✗ Scene %s failed — %s", scene_id, result_dict.get("error", "Unknown error"))

    return results
