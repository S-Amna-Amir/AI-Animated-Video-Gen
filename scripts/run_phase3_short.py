"""
scripts/run_phase3_short.py
-----------------------------
Phase 3 short test — first scene only, max 3 dialogue lines.
Saves HF API tokens. Use --mock for zero API calls.

Usage:
    python scripts/run_phase3_short.py --mock
    python scripts/run_phase3_short.py --phase1-dir data/outputs
"""
import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.video_agent.agent import VideoAgent


class ShortVideoAgent(VideoAgent):
    """Limits to first scene, max 3 manifest entries."""

    MAX_LINES = 3

    def load_phase1_output(self, phase1_dir: str = "data/outputs"):
        data = super().load_phase1_output(phase1_dir)
        if data.get("scenes"):
            first = data["scenes"][0]
            print(f"[Short] Using scene: {first.get('scene_id')}")
            data["scenes"] = [first]
        return data

    def load_phase2_manifest(self, phase2_run_dir: str):
        manifest = super().load_phase2_manifest(phase2_run_dir)
        if not manifest:
            return manifest
        first_sid = manifest[0].get("scene_id")
        limited   = [m for m in manifest if m.get("scene_id") == first_sid][:self.MAX_LINES]
        print(f"[Short] Manifest limited to {len(limited)} entries (scene {first_sid})")
        return limited


def _latest_phase2_run(base: str = "data/outputs/Phase2") -> str:
    root = Path(base)
    if not root.exists():
        raise FileNotFoundError(f"Phase 2 output dir not found: {root}")
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"No Phase 2 run dirs in: {root}")
    return str(max(dirs, key=lambda p: p.stat().st_mtime))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 SHORT test (1 scene, 3 lines)")
    parser.add_argument("--phase1-dir",    default="data/outputs")
    parser.add_argument("--phase2-run",    default=None)
    parser.add_argument("--mock",          action="store_true",
                        help="Black placeholder images — no HF API call")
    parser.add_argument("--run-id",        default=None)
    parser.add_argument("--use-subtitles", action="store_true")
    args = parser.parse_args()

    phase2_run = args.phase2_run or _latest_phase2_run()
    print(f"Phase 1 dir : {args.phase1_dir}")
    print(f"Phase 2 run : {phase2_run}")
    print(f"Mock mode   : {args.mock}\n")

    agent  = ShortVideoAgent(run_id=args.run_id)
    result = agent.run(
        phase1_dir=args.phase1_dir,
        phase2_run_dir=phase2_run,
        mock=args.mock,
        use_subtitles=args.use_subtitles,
    )

    imgs  = result.get("scene_images", {})
    clips = result.get("scene_clips", {})
    total = max(len(imgs), len(clips))
    print(f"\n--- Phase 3 SHORT Complete ---")
    print(f"Status      : {result['status']}")
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
