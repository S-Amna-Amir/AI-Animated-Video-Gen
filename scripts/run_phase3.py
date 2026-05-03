"""CLI entry point for Phase 3 video generation."""

import argparse
import sys
from pathlib import Path


script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from agents.video_agent.agent import VideoAgent


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
    parser = argparse.ArgumentParser(description="Run Phase 3 video generation pipeline.")
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
    args = parser.parse_args()

    try:
        phase2_run_dir = args.phase2_run or detect_latest_phase2_run()
        agent = VideoAgent(run_id=args.run_id)
        result = agent.run(
            phase1_dir=args.phase1_dir,
            phase2_run_dir=phase2_run_dir,
            mock=args.mock,
        )

        scene_images = result.get("scene_images", {})
        scene_clips = result.get("scene_clips", {})
        total_scenes = max(len(scene_images), len(scene_clips))
        images_generated = sum(1 for p in scene_images.values() if p)
        clips_generated = sum(1 for p in scene_clips.values() if p)

        print("Phase 3 Complete")
        print(f"Run ID     : {result.get('run_id', '')}")
        print(f"Images     : {images_generated}/{total_scenes} generated")
        print(f"Clips      : {clips_generated}/{total_scenes} animated")
        print(f"Final Video: {result.get('final_video', '')}")

    except Exception as exc:
        print(f"Phase 3 failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
