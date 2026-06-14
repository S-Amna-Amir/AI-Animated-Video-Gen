"""
agents/video_agent/agent.py
-----------------------------
Phase 3 Video Agent.
Orchestrates: image generation → Ken Burns animation → video composition.

Integration notes vs Phase 1/2:
  - Phase 1 writes:  data/outputs/scene_manifest.json + character_db.json
  - Phase 2 writes:  data/outputs/Phase2/run_XX/timing_manifest.json
  - load_phase1_output() tries all known filename variants automatically.
  - Pass --phase1-dir data/outputs (not data/outputs/Phase1/) unless you
    copied the files over.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.tools.video_tools import animator, image_generator, video_compositor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# All filename variants Phase 1 may produce
_SCENE_MANIFEST_NAMES = [
    "scene_manifest.json",
    "scene_manifest_auto.json",
    "scene_manifest_manual.json",
]
_CHAR_DB_NAMES = [
    "character_db.json",
    "character_db_auto.json",
    "character_db_manual.json",
]


class VideoAgent:
    def __init__(self, run_id: Optional[str] = None):
        from agents.video_agent.run_manager import VideoRunManager
        manager = VideoRunManager()
        if run_id:
            self.run_id  = run_id
            self.run_dir = manager.base_output_dir / run_id
            (self.run_dir / "images").mkdir(parents=True, exist_ok=True)
            (self.run_dir / "clips").mkdir(parents=True, exist_ok=True)
        else:
            self.run_id, run_dir_str = manager.create_run_dir()
            self.run_dir = Path(run_dir_str)
        self.logger = logging.getLogger(f"{__name__}.VideoAgent")

    # ── Phase 1 loader ────────────────────────────────────────────────────────

    def load_phase1_output(self, phase1_dir: str = "data/outputs") -> Dict[str, List[Any]]:
        """
        Load Phase 1 scene manifest + character DB.
        Tries all known filename variants so it works whether Phase 1 wrote
        scene_manifest.json, scene_manifest_auto.json, etc.
        """
        base = Path(phase1_dir)
        if not base.exists():
            raise FileNotFoundError(f"Phase 1 directory not found: {base}")

        scene_file = next((base / n for n in _SCENE_MANIFEST_NAMES if (base / n).exists()), None)
        char_file  = next((base / n for n in _CHAR_DB_NAMES  if (base / n).exists()), None)

        if not scene_file:
            tried = [str(base / n) for n in _SCENE_MANIFEST_NAMES]
            raise FileNotFoundError(
                f"No scene manifest found in {base}. Tried: {tried}\n"
                f"Hint: run with --phase1-dir data/outputs (not data/outputs/Phase1)"
            )
        if not char_file:
            tried = [str(base / n) for n in _CHAR_DB_NAMES]
            raise FileNotFoundError(f"No character DB found in {base}. Tried: {tried}")

        self.logger.info("Loading scene manifest: %s", scene_file)
        with open(scene_file, encoding="utf-8") as f:
            scene_payload = json.load(f)

        self.logger.info("Loading character DB: %s", char_file)
        with open(char_file, encoding="utf-8") as f:
            char_payload = json.load(f)

        scenes = scene_payload.get("scenes", []) if isinstance(scene_payload, dict) else scene_payload
        # character_db.json can be a list directly or {"characters": [...]}
        if isinstance(char_payload, list):
            characters = char_payload
        else:
            characters = char_payload.get("characters", char_payload) if isinstance(char_payload, dict) else []

        if not isinstance(scenes, list):
            raise ValueError("Scene manifest must contain a scenes list")
        if not isinstance(characters, list):
            raise ValueError("Character DB must be a list or contain a characters list")

        self.logger.info("Loaded %d scenes, %d characters", len(scenes), len(characters))
        return {"scenes": scenes, "characters": characters}

    # ── Phase 2 manifest loader ───────────────────────────────────────────────

    def load_phase2_manifest(self, phase2_run_dir: str) -> List[Dict[str, Any]]:
        manifest_path = Path(phase2_run_dir) / "timing_manifest.json"
        if not manifest_path.exists():
            self.logger.warning("Phase 2 manifest not found: %s", manifest_path)
            return []
        try:
            return video_compositor.load_timing_manifest(str(manifest_path))
        except Exception as e:
            self.logger.warning("Failed loading Phase 2 manifest: %s", e)
            return []

    def _fallback_manifest(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Silent fallback — one entry per scene with 5s duration."""
        manifest, cursor = [], 0
        for scene in scenes:
            sid = str(scene.get("scene_id", "")).strip()
            if not sid:
                continue
            dur = int(scene.get("duration_ms", 5000) or 5000)
            # One entry per dialogue line if available, else one per scene
            dialogues = scene.get("dialogue", [])
            if dialogues:
                line_dur = dur // max(1, len(dialogues))
                for idx, dl in enumerate(dialogues):
                    manifest.append({
                        "scene_id":  sid,
                        "speaker":   dl.get("speaker", ""),
                        "text":      dl.get("line", ""),
                        "audio_file": "",
                        "start_ms":  cursor,
                        "end_ms":    cursor + line_dur,
                        "duration_ms": line_dur,
                        "cumulative_start_ms": cursor,
                    })
                    cursor += line_dur
            else:
                manifest.append({
                    "scene_id": sid, "audio_file": "",
                    "start_ms": cursor, "end_ms": cursor + dur, "duration_ms": dur,
                    "cumulative_start_ms": cursor,
                })
                cursor += dur
        return manifest

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def run(
        self,
        phase1_dir: str = "data/outputs",
        phase2_run_dir: str = "",
        mock: bool = False,
        use_subtitles: bool = False,
    ) -> Dict[str, Any]:
        errors: List[str] = []

        # 1. Load inputs
        phase1_data = self.load_phase1_output(phase1_dir=phase1_dir)
        scenes:     List[Dict[str, Any]] = phase1_data["scenes"]
        characters: List[Dict[str, Any]] = phase1_data["characters"]

        timing_manifest = self.load_phase2_manifest(phase2_run_dir) if phase2_run_dir else []
        if not timing_manifest:
            self.logger.warning("Using fallback silent timing manifest")
            timing_manifest = self._fallback_manifest(scenes)

        # 2. Image generation
        try:
            gen_fn = image_generator.generate_images_for_dialogue_mock if mock \
                     else image_generator.generate_images_for_dialogue
            dialogue_results = gen_fn(
                manifest_entries=timing_manifest,
                scenes=scenes,
                characters=characters,
                run_dir=str(self.run_dir),
            )
        except Exception as e:
            dialogue_results = []
            errors.append(f"Image generation failed: {e}")
            self.logger.error("Image generation failed: %s", e, exc_info=True)

        # 3. Animation
        try:
            scene_clips = animator.animate_all_scenes(
                dialogue_results=dialogue_results,
                scenes=scenes,
                run_dir=str(self.run_dir),
            )
        except Exception as e:
            scene_clips = {}
            errors.append(f"Animation failed: {e}")
            self.logger.error("Animation failed: %s", e, exc_info=True)

        # 4. Video composition
        final_video_path    = str(self.run_dir / "final_output.mp4")
        subtitled_video_path = str(self.run_dir / "final_output_captioned.mp4")
        output_path = subtitled_video_path if use_subtitles else final_video_path

        try:
            final_video = video_compositor.compose_final_video(
                scene_clips_map=scene_clips,
                dialogue_results=dialogue_results,
                output_path=output_path,
                use_transitions=True,
                use_subtitles=use_subtitles,
            )
        except Exception as e:
            final_video = ""
            errors.append(f"Video composition failed: {e}")
            self.logger.error("Video composition failed: %s", e, exc_info=True)

        # 5. Build output
        scene_images_map = {
            f"{r['scene_id']}_{r['line_index']}": str(r.get("image_path", ""))
            for r in dialogue_results
        }
        total_dur_ms = sum(float(r.get("duration_ms", 0)) for r in dialogue_results)
        unique_sids  = {str(r["scene_id"]) for r in dialogue_results}

        if final_video and not errors:
            status = "success"
        elif final_video or scene_images_map or scene_clips:
            status = "partial"
        else:
            status = "failed"

        # Replace the output dict construction:
        output = {
            "run_id": self.run_id,
            "status": status,
            "phase":  3,
            "input":  {"phase1_dir": phase1_dir, "phase2_run_dir": phase2_run_dir},
            "scene_images":           scene_images_map,
            "scene_clips":            scene_clips,
            "final_video":            final_video or final_video_path,
            "final_video_captioned":  (final_video or subtitled_video_path) if use_subtitles else None,
            "use_subtitles":          use_subtitles,
            "total_duration_seconds": total_dur_ms / 1000.0,
            "scene_count":            len(unique_sids),
            "images_generated":       len(scene_images_map),
            "errors":                 errors,
            "timestamp":              datetime.now().isoformat(),
        }

        with open(self.run_dir / "phase3_output.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        # Phase 4 handoff JSON
        groups: Dict[str, List] = defaultdict(list)
        for r in dialogue_results:
            groups[str(r["scene_id"])].append(r)

        handoff_scenes = []
        for sid in sorted(groups.keys(), key=lambda k: int(k) if k.isdigit() else k):
            lines    = sorted(groups[sid], key=lambda x: int(x["line_index"]))
            tone     = next((str(s.get("tone","default")).lower() for s in scenes
                             if str(s.get("scene_id","")) == sid), "default")
            handoff_scenes.append({
                "scene_id":        sid,
                "image_paths":     [l.get("image_path","") for l in lines],
                "clip_paths":      [scene_clips.get(f"{sid}_{l['line_index']}","") for l in lines],
                "audio_file":      lines[0].get("audio_file","") if lines else "",
                "duration_seconds": sum(float(l.get("duration_ms",0)) for l in lines) / 1000.0,
                "tone":            tone,
            })

        handoff = {
            "final_video_path":       final_video or final_video_path,
            "run_id":                 self.run_id,
            "scene_count":            len(unique_sids),
            "total_duration_seconds": total_dur_ms / 1000.0,
            "scenes":                 handoff_scenes,
        }
        with open(self.run_dir / "phase3_video_handoff.json", "w", encoding="utf-8") as f:
            json.dump(handoff, f, indent=2)

        return output

    def get_latest_run_dir(self) -> str:
        base = Path("data/outputs/Phase3")
        if not base.exists():
            return ""
        dirs = [p for p in base.iterdir() if p.is_dir()]
        return str(max(dirs, key=lambda p: p.stat().st_mtime)) if dirs else ""
