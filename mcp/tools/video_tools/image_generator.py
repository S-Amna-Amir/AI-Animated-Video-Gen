"""
mcp/tools/video_tools/image_generator.py
------------------------------------------
Phase 3 image generation: one image per dialogue line via HF API.
Mock mode generates black placeholder PNGs (no API call).
"""
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from . import comfy_client, prompt_builder

logger = logging.getLogger(__name__)


def generate_images_for_dialogue(
    manifest_entries: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    characters: List[Dict[str, Any]],
    run_dir: str,
) -> List[Dict[str, Any]]:
    """Generate one image per dialogue line using HF API."""
    results: List[Dict[str, Any]] = []
    scene_line_counts = Counter(str(e.get("scene_id", "")) for e in manifest_entries)
    scenes_map = {str(s.get("scene_id", "")): s for s in scenes}
    chars_map  = {str(c.get("name", "")).upper(): c for c in characters}
    total = len(manifest_entries)

    for idx, entry in enumerate(manifest_entries):
        scene_id     = str(entry.get("scene_id", ""))
        speaker      = str(entry.get("speaker", "")).upper()
        dialogue_text = str(entry.get("text", ""))
        logger.info("Image %d/%d: scene=%s speaker=%s", idx + 1, total, scene_id, speaker)

        scene_data  = scenes_map.get(scene_id, {})
        char_data   = chars_map.get(speaker, {})
        prompt_used = prompt_builder.build_dialogue_image_prompt(
            scene=scene_data, character=char_data,
            dialogue_text=dialogue_text, line_index=idx,
        )

        line_count      = scene_line_counts.get(scene_id, 1)
        scene_dur_ms    = entry.get("scene_duration_ms", 5000 * line_count)
        duration_ms     = entry.get("duration_ms") or (scene_dur_ms / max(1, line_count))
        output_path     = Path(run_dir) / "images" / f"scene_{scene_id}_line_{idx}.png"

        if output_path.exists():
            results.append({
                "scene_id": scene_id, "line_index": idx,
                "speaker": speaker, "text": dialogue_text,
                "image_path": str(output_path),
                "audio_file": str(entry.get("audio_file", "")),
                "start_ms": int(entry.get("start_ms", entry.get("cumulative_start_ms", 0))),
                "duration_ms": duration_ms, "status": "success", "error": "",
            })
            continue

        try:
            image_bytes = comfy_client.generate_image(
                positive_prompt=prompt_used["positive"],
                negative_prompt=prompt_used["negative"],
                scene_id=scene_id, character_name=speaker,
            )
            saved = comfy_client.save_image(image_bytes, str(output_path))
            status, error = "success", ""
            logger.info("✓ scene %s line %d → %s", scene_id, idx, saved)
        except Exception as e:
            logger.exception("✗ scene %s line %d: %s", scene_id, idx, e)
            saved, status, error = "", "failed", str(e)

        results.append({
            "scene_id": scene_id, "line_index": idx,
            "speaker": speaker, "text": dialogue_text,
            "image_path": saved,
            "audio_file": str(entry.get("audio_file", "")),
            "start_ms": int(entry.get("start_ms", entry.get("cumulative_start_ms", 0))),
            "duration_ms": duration_ms, "status": status, "error": error,
        })
    return results


def _placeholder_image(scene_id: str, line_index: int, run_dir: str) -> str:
    out = Path(run_dir) / "images" / f"scene_{scene_id}_line_{line_index}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 512), color="black").save(out, format="PNG")
    return str(out)


def generate_images_for_dialogue_mock(
    manifest_entries: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    characters: List[Dict[str, Any]],
    run_dir: str,
) -> List[Dict[str, Any]]:
    """Mock mode: black placeholder PNGs, no API call."""
    results = []
    scene_line_counts = Counter(str(e.get("scene_id", "")) for e in manifest_entries)
    for idx, entry in enumerate(manifest_entries):
        scene_id      = str(entry.get("scene_id", ""))
        speaker       = str(entry.get("speaker", "")).upper()
        dialogue_text = str(entry.get("text", ""))
        line_count    = scene_line_counts.get(scene_id, 1)
        scene_dur_ms  = entry.get("scene_duration_ms", 5000 * line_count)
        duration_ms   = scene_dur_ms / max(1, line_count)
        image_path    = _placeholder_image(scene_id, idx, run_dir)
        results.append({
            "scene_id": scene_id, "line_index": idx,
            "speaker": speaker, "text": dialogue_text,
            "image_path": image_path,
            "audio_file": str(entry.get("audio_file", "")),
            "start_ms": int(entry.get("cumulative_start_ms", 0)),
            "duration_ms": duration_ms, "status": "success", "error": "",
        })
    return results
