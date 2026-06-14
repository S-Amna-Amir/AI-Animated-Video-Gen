"""
scripts/run_edit.py
--------------------
Phase 5 edit agent — CLI interface.

Usage:
    python scripts/run_edit.py "Make the scene darker"
    python scripts/run_edit.py "Regenerate the script"
    python scripts/run_edit.py --undo 3
    python scripts/run_edit.py --history
    python scripts/run_edit.py --diff 2 4
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()


async def run_edit(query: str) -> None:
    from agents.edit_agent.agent import EditAgent

    def log(msg):
        print(f"  {msg}")

    agent  = EditAgent(log_callback=log)
    print(f"\n{'='*60}")
    print(f"  EDIT: {query}")
    print(f"{'='*60}\n")

    result = await agent.edit(query)

    print(f"\n{'='*60}")
    if result["success"]:
        print(f"  SUCCESS: Edit complete")
        intent = result["intent"]
        print(f"  Intent   : {intent['intent']} -> {intent['target']} (scope: {intent['scope']})")
        print(f"  Snapshot : v{result['snapshot_before']:03d} -> v{result['snapshot_after']:03d}")
        
        # Find final video output path if any
        final_video_path = None
        for step in result["execution"].get("steps", []):
            step_res = step.get("result")
            if isinstance(step_res, dict) and "final_video" in step_res:
                final_video_path = step_res["final_video"]
        if final_video_path:
            print(f"  New Output Video: {final_video_path}")
    else:
        print(f"  FAILED: Edit failed: {result.get('error')}")
    print(f"{'='*60}\n")


def run_undo(version: int) -> None:
    from agents.edit_agent.agent import EditAgent
    agent  = EditAgent()
    result = agent.undo(version)
    if result["success"]:
        print(f"SUCCESS: Reverted to v{version:03d} -> new version v{result['new_version']:03d}")
        print(f"   Assets restored: {result['restored_assets']}")
    else:
        print(f"FAILED: Revert failed: {result.get('error')}")


def show_history() -> None:
    from agents.edit_agent.agent import EditAgent
    history = EditAgent().history()
    if not history:
        print("No snapshots yet.")
        return
    print(f"\n{'Version':<10} {'Timestamp':<25} {'Description'}")
    print("-" * 70)
    for v in history:
        ts   = v["timestamp"][:19].replace("T", " ")
        desc = v.get("description") or "(no description)"
        q    = v.get("edit_query", "")
        line = f"v{v['version']:03d}      {ts}  {desc}"
        if q and q != desc:
            line += f'  "{q}"'
        print(line)
    print()


def show_diff(v1: int, v2: int) -> None:
    from state_manager.state_manager import StateManager
    diff = StateManager().diff(v1, v2)
    print(json.dumps(diff, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 — Edit Agent CLI")
    parser.add_argument("query",        nargs="?", help="Free-text edit command")
    parser.add_argument("--undo",       type=int, metavar="VERSION", help="Revert to version N")
    parser.add_argument("--history",    action="store_true", help="Show version history")
    parser.add_argument("--diff",       nargs=2, type=int, metavar=("V1","V2"), help="Diff two versions")
    args = parser.parse_args()

    if args.undo:
        run_undo(args.undo)
    elif args.history:
        show_history()
    elif args.diff:
        show_diff(*args.diff)
    elif args.query:
        asyncio.run(run_edit(args.query))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
