"""Phase 3 mock-mode smoke test script."""

import json
import sys
from datetime import datetime
from pathlib import Path


script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from agents.video_agent.agent import VideoAgent


def _print_assert(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label}")
    return condition


def _write_test_inputs(phase1_dir: Path, phase2_run_dir: Path) -> None:
    phase1_dir.mkdir(parents=True, exist_ok=True)
    phase2_run_dir.mkdir(parents=True, exist_ok=True)

    scenes = [
        {
            "scene_id": "s1",
            "setting": "A dark Martian cave with glowing blue water",
            "tone": "mysterious",
            "visual_description": "Astronaut Maya stands at cave entrance",
            "characters": ["Maya"],
            "duration_ms": 2000,
        },
        {
            "scene_id": "s2",
            "setting": "A calm ridge under a sunrise sky",
            "tone": "calm",
            "visual_description": "Maya looks at the horizon",
            "characters": ["Maya"],
            "duration_ms": 2000,
        },
    ]

    with open(phase1_dir / "scene_manifest_auto.json", "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, indent=2)

    with open(phase1_dir / "character_db_auto.json", "w", encoding="utf-8") as f:
        json.dump({"characters": [{"name": "Maya"}]}, f, indent=2)

    manifest = [
        {
            "scene_id": "s1",
            "audio_file": "",
            "start_ms": 0,
            "end_ms": 2000,
        },
        {
            "scene_id": "s2",
            "audio_file": "",
            "start_ms": 2000,
            "end_ms": 4000,
        },
    ]
    with open(phase2_run_dir / "timing_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def main() -> None:
    test_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    phase1_test_dir = project_root / "data" / "outputs" / "Phase1" / f"phase3_test_{test_tag}"
    phase2_test_run = project_root / "data" / "outputs" / "Phase2" / f"phase3_test_{test_tag}"
    run_id = f"phase3_test_{test_tag}"

    _write_test_inputs(phase1_test_dir, phase2_test_run)

    try:
        agent = VideoAgent(run_id=run_id)
        result = agent.run(
            phase1_dir=str(phase1_test_dir),
            phase2_run_dir=str(phase2_test_run),
            mock=True,
        )
    except Exception as exc:
        print(f"FAIL: Agent execution failed: {exc}")
        sys.exit(1)

    output_json = project_root / "data" / "outputs" / "Phase3" / run_id / "phase3_output.json"
    final_video = Path(result.get("final_video", ""))

    ok1 = _print_assert("phase3_output.json exists", output_json.exists())
    ok2 = _print_assert("final_output.mp4 exists", final_video.exists())

    if ok1 and ok2:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
