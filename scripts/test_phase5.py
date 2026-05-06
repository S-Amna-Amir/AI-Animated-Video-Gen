"""Phase 5 Edit Agent test script."""

import asyncio
import json
import sys
from pathlib import Path

script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from agents.edit_agent.intent_classifier import IntentClassifier
from state_manager.state_manager import StateManager
from agents.edit_agent.agent import EditAgent


def _print_assert(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label}")
    return condition


def test_intent_classifier():
    """Test 10 different edit queries through intent classifier."""
    print("\n=== Testing Intent Classifier ===")
    
    classifier = IntentClassifier()
    
    test_cases = [
        ("Make the narrator sound more dramatic", "audio"),
        ("The scene looks too bright", "video_frame"),
        ("Add subtitles to the video", "video"),
        ("Change the story ending", "script"),
        ("Undo the last change", "system"),
        ("Make the character speak faster", "audio"),
        ("Darken the background", "video_frame"),
        ("Remove the music", "audio"),
        ("Regenerate the entire script", "script"),
        ("Revert to version 2", "system"),
    ]
    
    all_passed = True
    for query, expected_target in test_cases:
        intent_data = classifier.classify(query)
        actual_target = intent_data["target"]
        passed = _print_assert(
            f"'{query}' -> target: {actual_target} (expected: {expected_target})",
            actual_target == expected_target
        )
        all_passed = all_passed and passed
    
    return all_passed


def test_snapshot_revert():
    """Test snapshot→modify→revert round trip."""
    print("\n=== Testing Snapshot Revert Round Trip ===")
    
    # Use temp db for testing
    import tempfile
    import state_manager.storage as storage
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    storage.db_path = temp_db.name
    storage.init_db()
    
    sm = StateManager()
    run_id = "test_revert_run"
    
    # Initial state
    initial_state = {"narrator": "normal", "scene": "bright"}
    
    # Snapshot initial
    snap1 = sm.snapshot(run_id, "Initial state", initial_state, ["asset1.png"])
    print(f"Created snapshot v{snap1.version}")
    
    # Modify state
    modified_state = {"narrator": "dramatic", "scene": "dark"}
    
    # Snapshot modified
    snap2 = sm.snapshot(run_id, "Modified state", modified_state, ["asset1.png", "audio_dramatic.mp3"])
    print(f"Created snapshot v{snap2.version}")
    
    # Revert to v1
    reverted = sm.revert(run_id, 1)
    print(f"Reverted to v{reverted.version}")
    
    # Check restored state matches initial
    restored_state = reverted.state_json
    passed = _print_assert(
        f"Restored state {restored_state} matches initial {initial_state}",
        restored_state == initial_state
    )
    
    # Cleanup
    import os
    os.unlink(temp_db.name)
    
    return passed


async def test_end_to_end_agent():
    """Test end-to-end agent run with 3 chained commands."""
    print("\n=== Testing End-to-End Agent Run ===")
    
    # Use temp db
    import tempfile
    import state_manager.storage as storage
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    storage.db_path = temp_db.name
    storage.init_db()
    
    agent = EditAgent()
    run_id = "test_e2e_run"
    
    # Initial state
    current_state = {"narrator": "normal", "scene": "bright"}
    
    # Command 1
    result1 = await agent.process_edit(run_id, "Make the narrator sound more dramatic", current_state)
    current_state = result1["result"]["updated_state"]
    print(f"Command 1: new_version={result1['new_version']}")
    
    # Command 2
    result2 = await agent.process_edit(run_id, "The scene looks too bright", current_state)
    current_state = result2["result"]["updated_state"]
    print(f"Command 2: new_version={result2['new_version']}")
    
    # Command 3
    result3 = await agent.process_edit(run_id, "Undo that", current_state)
    print(f"Command 3: new_version={result3['new_version']}")
    
    # Check history has 3 snapshots (plus revert creates extra)
    history = agent.state_manager.history(run_id)
    print(f"Total snapshots: {len(history)}")
    
    # Should have at least 3 snapshots from the commands
    passed = _print_assert(
        f"History has at least 3 snapshots (actual: {len(history)})",
        len(history) >= 3
    )
    
    # Cleanup
    import os
    os.unlink(temp_db.name)
    
    return passed


async def main():
    """Run all tests."""
    print("Phase 5 Edit Agent Tests")
    print("=" * 50)
    
    test1_passed = test_intent_classifier()
    test2_passed = test_snapshot_revert()
    test3_passed = await test_end_to_end_agent()
    
    print("\n" + "=" * 50)
    all_passed = test1_passed and test2_passed and test3_passed
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)