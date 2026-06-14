"""
scripts/test_phase2.py
-----------------------
Phase 2 test script. Reads Phase 1 outputs and runs audio generation.

Usage:
    python scripts/test_phase2.py
    python scripts/test_phase2.py --phase1-dir data/outputs/Phase1
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Project root on path ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from agents.audio_agent.enhanced_agent import EnhancedAudioAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


async def main(phase1_dir: str, phase2_dir: str) -> None:
    print("\n" + "=" * 70)
    print("PHASE 2 — AUDIO GENERATION")
    print("=" * 70 + "\n")

    p1 = Path(phase1_dir)
    if not p1.exists():
        print(f"❌  Phase 1 directory not found: {p1}")
        print("    Run Phase 1 first:  python main.py --phase 1 --mode auto --prompt '...'")
        sys.exit(1)

    # Check at least one manifest exists
    candidates = [
        p1 / "scene_manifest_auto.json",
        p1 / "scene_manifest_manual.json",
        p1 / "scene_manifest.json",
    ]
    found = next((f for f in candidates if f.exists()), None)
    if not found:
        print(f"❌  No scene_manifest*.json found in {p1}")
        print("    Tip: if Phase 1 wrote to data/outputs/, pass --phase1-dir data/outputs")
        sys.exit(1)

    print(f"📁  Phase 1 dir : {p1}")
    print(f"📁  Phase 2 dir : {phase2_dir}")
    print(f"✅  Manifest    : {found.name}")
    print(f"🔑  Freesound   : {'set' if os.getenv('FREESOUND_API_KEY') else 'not set (fallback BGM)'}")
    print(f"🔑  Groq        : {'set' if os.getenv('GROQ_API_KEY') else 'not set (keyword mood)'}\n")

    agent = EnhancedAudioAgent(
        phase1_data_dir=phase1_dir,
        phase2_output_dir=phase2_dir,
        freesound_api_key=os.getenv("FREESOUND_API_KEY"),
    )
    results = await agent.process()

    print("\n" + "=" * 70)
    if results.get("status") == "success":
        print("✅  PHASE 2 SUCCESS\n")
        print(f"  Run ID          : {results['run_id']}")
        print(f"  Scenes processed: {results['scenes_processed']} / {results['total_scenes']}")
        print(f"  Scenes with BGM : {results['scenes_with_bgm']}")
        print(f"  Total duration  : {results['total_duration_ms'] / 1000:.1f}s")
        print(f"  Master track    : {results.get('master_audio_track', 'N/A')}")
        print(f"  Timing manifest : {results['timing_manifest_path']}")
        print(f"\n  Voices used:")
        for char, voice in sorted(results.get("character_voices_used", {}).items()):
            print(f"    {char:20} -> {voice}")
    else:
        print(f"❌  PHASE 2 FAILED: {results.get('error')}")
        sys.exit(1)

    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 2 audio generation")
    parser.add_argument(
        "--phase1-dir", default="data/outputs",
        help="Directory containing Phase 1 outputs (default: data/outputs)"
    )
    parser.add_argument(
        "--phase2-dir", default="data/outputs/Phase2",
        help="Output directory for Phase 2 (default: data/outputs/Phase2)"
    )
    args = parser.parse_args()
    asyncio.run(main(args.phase1_dir, args.phase2_dir))
