"""Video Agent - Orchestrates Phase 3 image-to-video pipeline."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict

from mcp.tools.video_tools import animator, image_generator, video_compositor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VideoAgent:
    """
    Phase 3 Video Agent.
    Orchestrates image generation, animation, and final video composition.
    """

    def __init__(self, run_id: Optional[str] = None):
        from .run_manager import VideoRunManager
        manager = VideoRunManager()
        if run_id:
            self.run_id = run_id
            self.run_dir = manager.base_output_dir / run_id
            (self.run_dir / "images").mkdir(parents=True, exist_ok=True)
            (self.run_dir / "clips").mkdir(parents=True, exist_ok=True)
        else:
            self.run_id, run_dir_str = manager.create_run_dir()
            self.run_dir = Path(run_dir_str)
        self.logger = logging.getLogger(f"{__name__}.VideoAgent")

    def load_phase1_output(self, phase1_dir: str = "data/outputs/Phase1/") -> dict[str, list[Any]]:
        """
        Load Phase 1 scene and character outputs.
        """
        phase1_path = Path(phase1_dir)
        scene_file = phase1_path / "scene_manifest_auto.json"
        char_file = phase1_path / "character_db_auto.json"

        if not scene_file.exists():
            raise FileNotFoundError(f"Missing Phase 1 scene manifest: {scene_file}")
        if not char_file.exists():
            raise FileNotFoundError(f"Missing Phase 1 character DB: {char_file}")

        with open(scene_file, "r", encoding="utf-8") as f:
            scene_payload = json.load(f)
        with open(char_file, "r", encoding="utf-8") as f:
            char_payload = json.load(f)

        scenes = scene_payload.get("scenes", []) if isinstance(scene_payload, dict) else scene_payload
        characters = (
            char_payload.get("characters", []) if isinstance(char_payload, dict) else char_payload
        )

        if not isinstance(scenes, list):
            raise ValueError("Phase 1 scene manifest must contain a scenes list")
        if not isinstance(characters, list):
            raise ValueError("Phase 1 character DB must contain a characters list")

        return {"scenes": scenes, "characters": characters}

    def load_phase2_manifest(self, phase2_run_dir: str) -> list[dict[str, Any]]:
        """
        Load Phase 2 timing manifest from a run directory.
        Returns empty list if unavailable.
        """
        manifest_path = Path(phase2_run_dir) / "timing_manifest.json"
        if not manifest_path.exists():
            self.logger.warning("Phase 2 timing manifest not found at %s", manifest_path)
            return []

        try:
            return video_compositor.load_timing_manifest(str(manifest_path))
        except Exception as exc:
            self.logger.warning("Failed loading timing manifest (%s): %s", manifest_path, exc)
            return []

    def _build_fallback_manifest(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Build a silent fallback timing manifest when Phase 2 output is unavailable.
        """
        manifest: list[dict[str, Any]] = []
        current_start_ms = 0
        for scene in scenes:
            scene_id = str(scene.get("scene_id", "")).strip()
            if not scene_id:
                continue
            duration_ms = int(scene.get("duration_ms", 5000) or 5000)
            entry = {
                "scene_id": scene_id,
                "audio_file": "",
                "start_ms": current_start_ms,
                "end_ms": current_start_ms + duration_ms,
            }
            manifest.append(entry)
            current_start_ms += duration_ms
        return manifest

    def run(self, phase1_dir: str, phase2_run_dir: str, mock: bool = False, use_subtitles: bool = False) -> dict[str, Any]:
        """
        Run full Phase 3 pipeline and save phase3_output.json.
        """
        errors: list[str] = []

        phase1_data = self.load_phase1_output(phase1_dir=phase1_dir)
        scenes: list[dict[str, Any]] = phase1_data["scenes"]
        characters: list[dict[str, Any]] = phase1_data["characters"]
        
        timing_manifest = self.load_phase2_manifest(phase2_run_dir=phase2_run_dir)
        if not timing_manifest:
            self.logger.warning("Using fallback silent timing manifest from scene durations")
            timing_manifest = self._build_fallback_manifest(scenes)

        try:
            if mock:
                dialogue_results = image_generator.generate_images_for_dialogue_mock(
                    manifest_entries=timing_manifest,
                    scenes=scenes,
                    characters=characters,
                    run_dir=str(self.run_dir),
                )
            else:
                dialogue_results = image_generator.generate_images_for_dialogue(
                    manifest_entries=timing_manifest,
                    scenes=scenes,
                    characters=characters,
                    run_dir=str(self.run_dir),
                )
        except Exception as exc:
            dialogue_results = []
            errors.append(f"Image generation failed: {exc}")
            self.logger.error("Image generation step failed: %s", exc, exc_info=True)

        try:
            scene_clips = animator.animate_all_scenes(
                dialogue_results=dialogue_results,
                scenes=scenes,
                run_dir=str(self.run_dir),
            )
        except Exception as exc:
            scene_clips = {}
            errors.append(f"Animation failed: {exc}")
            self.logger.error("Animation step failed: %s", exc, exc_info=True)

        final_video_path = str(self.run_dir / "final_output.mp4")
        try:
            final_video = video_compositor.compose_final_video(
                scene_clips_map=scene_clips,
                dialogue_results=dialogue_results,
                output_path=final_video_path,
                use_transitions=True,
                use_subtitles=use_subtitles,
            )
        except Exception as exc:
            final_video = ""
            errors.append(f"Video composition failed: {exc}")
            self.logger.error("Video composition step failed: %s", exc, exc_info=True)

        scene_images_map = {
            f"{result['scene_id']}_{result['line_index']}": str(result.get("image_path", ""))
            for result in dialogue_results
        }
        
        total_duration_ms = sum(float(r.get("duration_ms", 0)) for r in dialogue_results)
        total_duration_seconds = total_duration_ms / 1000.0

        if final_video and not errors:
            status = "success"
        elif final_video or scene_images_map or scene_clips:
            status = "partial"
        else:
            status = "failed"
            
        unique_scene_ids = {str(r["scene_id"]) for r in dialogue_results}

        output = {
            "run_id": self.run_id,
            "status": status,
            "phase": 3,
            "input": {
                "phase1_dir": str(phase1_dir),
                "phase2_run_dir": str(phase2_run_dir)
            },
            "scene_images": scene_images_map,
            "scene_clips": scene_clips,
            "final_video": final_video or final_video_path,
            "total_duration_seconds": total_duration_seconds,
            "scene_count": len(unique_scene_ids),
            "images_generated": len(scene_images_map),
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }

        output_path = self.run_dir / "phase3_output.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
            
        # Create Phase 4 handoff JSON
        scene_groups = defaultdict(list)
        for r in dialogue_results:
            scene_groups[str(r["scene_id"])].append(r)
            
        handoff_scenes = []
        for scene_id in sorted(scene_groups.keys(), key=lambda k: int(k) if str(k).isdigit() else k):
            lines = sorted(scene_groups[scene_id], key=lambda x: int(x["line_index"]))
            audio_file = lines[0].get("audio_file", "")
            scene_duration = sum(float(l.get("duration_ms", 0)) for l in lines) / 1000.0
            
            # Find tone from original Phase 1 scene
            tone = "default"
            for s in scenes:
                if str(s.get("scene_id", "")) == scene_id:
                    tone = str(s.get("tone", "default")).lower()
                    break
                    
            handoff_scenes.append({
                "scene_id": scene_id,
                "image_paths": [l.get("image_path", "") for l in lines],
                "clip_paths": [scene_clips.get(f"{scene_id}_{l['line_index']}", "") for l in lines],
                "audio_file": audio_file,
                "duration_seconds": scene_duration,
                "tone": tone
            })
            
        handoff = {
            "final_video_path": final_video or final_video_path,
            "run_id": self.run_id,
            "scene_count": len(unique_scene_ids),
            "total_duration_seconds": total_duration_seconds,
            "scenes": handoff_scenes
        }
        
        handoff_path = self.run_dir / "phase3_video_handoff.json"
        with open(handoff_path, "w", encoding="utf-8") as f:
            json.dump(handoff, f, indent=2)

        return output

    def get_latest_run_dir(self) -> str:
        """
        Return most recently modified Phase 3 run directory.
        """
        base_dir = Path("data/outputs/Phase3")
        if not base_dir.exists():
            return ""

        run_dirs = [path for path in base_dir.iterdir() if path.is_dir()]
        if not run_dirs:
            return ""

        latest = max(run_dirs, key=lambda path: path.stat().st_mtime)
        return str(latest)
