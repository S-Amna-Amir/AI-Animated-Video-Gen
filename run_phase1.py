#!/usr/bin/env python3
"""
Phase 1 CLI Runner
Runs the full Story Agent pipeline from the command line.

Usage:
    python run_phase1.py "A brave knight must retrieve a stolen dragon egg"
    python run_phase1.py "Space explorers find an ancient alien city" --scenes 5
    python run_phase1.py --interactive
"""

import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# Resolve project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.story_agent.agent import StoryAgent


def print_banner():
    print("\n" + "=" * 60)
    print("  AgenticAI — Phase 1: Story, Script & Character Design")
    print("=" * 60 + "\n")


def print_summary(result):
    print("\n" + "─" * 60)
    print(f"  ✅ Pipeline Complete!")
    print("─" * 60)
    print(f"  📖 Title:       {result.story.title}")
    print(f"  🎬 Genre:       {result.story.genre}")
    print(f"  🎭 Tone:        {result.story.tone}")
    print(f"  👥 Characters:  {', '.join(c.name for c in result.characters)}")
    print(f"  🎞  Scenes:      {len(result.scenes)}")
    print(f"  ⏱  Est. Length: {result.summary['estimated_total_seconds']}s")
    print(f"  📁 Outputs:     data/outputs/Phase1/")
    print("─" * 60 + "\n")
    print("  Artefacts saved:")
    artefacts = [
        "character_db.json", "character_db_auto.json", "character_db_manual.json",
        "scene_manifest_auto.json", "scene_manifest_manual.json",
        "story_manifest_auto.json", "timing_manifest.json",
        "last_script.txt", "last_script_auto.txt", "last_script_manual.txt",
        "sample_script.txt", "mcp_registry.json", "run_counter.json",
    ]
    for name in artefacts:
        print(f"    • data/outputs/Phase1/{name}")
    print()


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="Phase 1: Story Agent")
    parser.add_argument("prompt", nargs="?", help="Story idea prompt")
    parser.add_argument("--scenes", type=int, default=4,
                        help="Number of scenes to generate (2–8, default: 4)")
    parser.add_argument("--interactive", action="store_true",
                        help="Enter prompt interactively")
    args = parser.parse_args()

    # ── Get prompt ────────────────────────────────────────────────────────────
    if args.interactive or not args.prompt:
        print("  Enter your story idea (press Enter twice when done):")
        lines = []
        while True:
            line = input("  > ")
            if not line and lines:
                break
            if line:
                lines.append(line)
        prompt = " ".join(lines)
    else:
        prompt = args.prompt

    if not prompt.strip():
        print("  ❌ Error: prompt is empty.")
        sys.exit(1)

    print(f"\n  Prompt: \"{prompt}\"")
    print(f"  Scenes: {args.scenes}")
    print("\n  Running Phase 1 pipeline...\n")

    # ── Run agent ─────────────────────────────────────────────────────────────
    try:
        agent = StoryAgent()
        result = agent.run(prompt, num_scenes=args.scenes)
        print_summary(result)
        return result
    except RuntimeError as e:
        print(f"\n  ❌ Pipeline failed: {e}")
        sys.exit(1)
    except EnvironmentError as e:
        print(f"\n  ❌ Configuration error: {e}")
        print("  Make sure ANTHROPIC_API_KEY is set in your .env file.")
        sys.exit(1)


if __name__ == "__main__":
    main()
