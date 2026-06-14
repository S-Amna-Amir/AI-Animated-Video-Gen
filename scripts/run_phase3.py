"""
scripts/run_phase3.py
----------------------
CLI entry point for Phase 3 video generation (full pipeline).

Usage:
    python scripts/run_phase3.py --mock                          # placeholder images
    python scripts/run_phase3.py --phase1-dir data/outputs       # real HF images
    python scripts/run_phase3.py --phase1-dir data/outputs --use-subtitles
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.video_agent.agent import VideoAgent


def _latest_phase2_run(base: str = "data/outputs/Phase2") -> str:
    root = Path(base)
    if not root.exists():
        raise FileNotFoundError(f"Phase 2 output dir not found: {root}")
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"No Phase 2 run dirs in: {root}")
    return str(max(dirs, key=lambda p: p.stat().st_mtime))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 — Video Generation")
    parser.add_argument("--phase1-dir",  default="data/outputs",
                        help="Phase 1 output directory (default: data/outputs)")
    parser.add_argument("--phase2-run",  default=None,
                        help="Phase 2 run dir with timing_manifest.json (auto-detected if omitted)")
    parser.add_argument("--mock",        action="store_true",
                        help="Mock mode — black placeholder images, no HF API call")
    parser.add_argument("--run-id",      default=None)
    parser.add_argument("--use-subtitles", action="store_true")
    args = parser.parse_args()

    phase2_run = args.phase2_run or _latest_phase2_run()
    print(f"Phase 1 dir : {args.phase1_dir}")
    print(f"Phase 2 run : {phase2_run}")
    print(f"Mock mode   : {args.mock}\n")

    agent  = VideoAgent(run_id=args.run_id)
    result = agent.run(
        phase1_dir=args.phase1_dir,
        phase2_run_dir=phase2_run,
        mock=args.mock,
        use_subtitles=args.use_subtitles,
    )

    imgs   = result.get("scene_images", {})
    clips  = result.get("scene_clips", {})
    total  = max(len(imgs), len(clips))
    print(f"\nStatus      : {result['status']}")
    print(f"Run ID      : {result['run_id']}")
    print(f"Images      : {sum(1 for p in imgs.values() if p)}/{total}")
    print(f"Clips       : {sum(1 for p in clips.values() if p)}/{total}")
    print(f"Final video : {result.get('final_video','')}")
    if result.get("errors"):
        print("\nErrors:")
        for e in result["errors"]:
            print(f"  • {e}")
    sys.exit(0 if result["status"] in ("success", "partial") else 1)


if __name__ == "__main__":
    main()
