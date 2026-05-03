"""CLI entry point for a short Phase 3 video generation (Testing only)."""

import argparse
import sys
from pathlib import Path

script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from agents.video_agent.agent import VideoAgent

class ShortVideoAgent(VideoAgent):
    def load_phase1_output(self, phase1_dir: str):
        data = super().load_phase1_output(phase1_dir)
        # Filter scenes to only keep the first one
        if data.get("scenes"):
            first_scene = data["scenes"][0]
            print(f"Limiting to scene: {first_scene.get('scene_id')}")
            data["scenes"] = [first_scene]
        return data

    def load_phase2_manifest(self, phase2_run_dir: str):
        manifest = super().load_phase2_manifest(phase2_run_dir)
        # Filter manifest to only include entries for the first scene, max 3 items
        if manifest:
            first_scene_id = manifest[0].get("scene_id")
            scene_entries = [m for m in manifest if m.get("scene_id") == first_scene_id]
            
            # Limit to 3 items
            limited_manifest = scene_entries[:3]
            print(f"Limiting manifest to {len(limited_manifest)} items for scene {first_scene_id}")
            
            # Fetch actual duration for each individual dialogue line audio
            try:
                from mcp.tools.audio_tools.tts_tool import TTSTool
                import os
                
                audio_dir = Path(phase2_run_dir) / "audio" / f"scene{int(first_scene_id):02d}" / f"scene{int(first_scene_id):02d}"
                if audio_dir.exists():
                    for entry in limited_manifest:
                        speaker = entry.get("speaker", "").replace(" ", "_").upper()
                        original_idx = scene_entries.index(entry)
                        matched_file = str(audio_dir / f"{speaker}_line{original_idx+1:03d}.mp3")
                        if os.path.exists(matched_file):
                            duration_ms = TTSTool._get_audio_duration_ms(matched_file)
                            entry["duration_ms"] = duration_ms
                            print(f"Found exact duration for {speaker} line {original_idx+1}: {duration_ms}ms")
                        else:
                            print(f"File not found for exact duration mapping: {matched_file}")
            except Exception as e:
                print(f"Could not load exact durations: {e}")
                
            return limited_manifest
        return manifest

def detect_latest_phase2_run(base_dir: str = "data/outputs/Phase2") -> str:
    """Auto-detect latest Phase 2 run directory."""
    phase2_root = Path(base_dir)
    if not phase2_root.exists():
        raise FileNotFoundError(f"Phase 2 output directory not found: {phase2_root}")

    run_dirs = [p for p in phase2_root.iterdir() if p.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"No Phase 2 run directories found in: {phase2_root}")

    latest = max(run_dirs, key=lambda p: p.stat().st_mtime)
    return str(latest)

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3 video generation pipeline (SHORT VERSION).")
    parser.add_argument(
        "--phase1-dir",
        default="data/outputs/Phase1/",
        help="Directory containing Phase 1 outputs.",
    )
    parser.add_argument(
        "--phase2-run",
        default=None,
        help="Phase 2 run directory containing timing_manifest.json. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock mode (placeholder images, skip ComfyUI generation).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional custom Phase 3 run ID.",
    )
    parser.add_argument(
        "--use-subtitles",
        action="store_true",
        help="Enable subtitle rendering during video composition.",
    )
    args = parser.parse_args()

    try:
        phase2_run_dir = args.phase2_run or detect_latest_phase2_run()
        print(f"Using Phase 2 run directory: {phase2_run_dir}")
        agent = ShortVideoAgent(run_id=args.run_id)
        result = agent.run(
            phase1_dir=args.phase1_dir,
            phase2_run_dir=phase2_run_dir,
            mock=args.mock,
            use_subtitles=args.use_subtitles
        )

        scene_images = result.get("scene_images", {})
        scene_clips = result.get("scene_clips", {})
        total_scenes = max(len(scene_images), len(scene_clips))
        images_generated = sum(1 for p in scene_images.values() if p)
        clips_generated = sum(1 for p in scene_clips.values() if p)

        print("\n--- Phase 3 SHORT Complete ---")
        print(f"Run ID     : {result.get('run_id', '')}")
        print(f"Images     : {images_generated}/{total_scenes} generated")
        print(f"Clips      : {clips_generated}/{total_scenes} animated")
        print(f"Final Video: {result.get('final_video', '')}")

    except Exception as exc:
        print(f"Phase 3 failed: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
