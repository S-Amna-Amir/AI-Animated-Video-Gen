import json
from typing import List, Dict, Any
from pathlib import Path

# Need to adjust python path for __main__ execution to resolve relative imports
if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager.snapshot import create_snapshot, Snapshot
from state_manager.history import get_history, diff_summary
from state_manager.storage import get_connection
import state_manager.storage as storage

class StateManager:
    def __init__(self):
        storage.init_db()

    def snapshot(self, run_id: str, edit_command: str, state_json: Dict[str, Any], asset_paths: List[str]) -> Snapshot:
        return create_snapshot(run_id, edit_command, state_json, asset_paths)

    def revert(self, run_id: str, version: int) -> Snapshot:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM snapshots WHERE run_id = ? AND version = ?", (run_id, version))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(f"Snapshot with version {version} not found for run_id {run_id}")
            
        snap = Snapshot(
            version=row["version"],
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            edit_command=row["edit_command"],
            state_json=json.loads(row["state_json"]),
            asset_paths=json.loads(row["asset_paths"])
        )
        
        # Normally here we would perform physical file copies to restore asset_paths.
        # Then we create a new snapshot reflecting this restored state.
        return self.snapshot(run_id, f"Revert to version {version}", snap.state_json, snap.asset_paths)

    def history(self, run_id: str) -> List[Snapshot]:
        return get_history(run_id)

if __name__ == '__main__':
    import state_manager.storage as storage
    from pathlib import Path
    
    # Use temporary database for testing
    test_db = Path("test_state.db")
    if test_db.exists():
        test_db.unlink()
    storage.db_path = str(test_db)
    storage.init_db()

    sm = StateManager()
    run_id = "run_12345"

    print("--- Creating 3 fake snapshots ---")
    sm.snapshot(run_id, "Initial generation", {"narrator": "normal", "scene": "bright"}, ["/assets/1.png"])
    sm.snapshot(run_id, "Voice tone changed for Narrator", {"narrator": "dramatic", "scene": "bright"}, ["/assets/1.png", "/assets/audio_dramatic.mp3"])
    sm.snapshot(run_id, "Make scene darker", {"narrator": "dramatic", "scene": "dark"}, ["/assets/1_dark.png", "/assets/audio_dramatic.mp3"])

    print("\n--- Listing History ---")
    hist = sm.history(run_id)
    for h in hist:
        print(f"v{h.version} | {h.timestamp} | {h.edit_command} | state: {h.state_json}")

    print("\n--- Testing Diff Summary ---")
    print(f"Diff v1 -> v2: {diff_summary(hist[0], hist[1])}")
    print(f"Diff v2 -> v3: {diff_summary(hist[1], hist[2])}")

    print("\n--- Reverting to version 1 ---")
    restored = sm.revert(run_id, 1)
    
    print("\n--- History after revert ---")
    hist_after = sm.history(run_id)
    for h in hist_after:
        print(f"v{h.version} | {h.timestamp} | {h.edit_command} | state: {h.state_json}")
    
    print(f"\nCurrently active state: {restored.state_json}")
    
    # Confirm the state was restored correctly
    original_v1 = hist[0]
    if restored.state_json == original_v1.state_json:
        print("✓ State restored correctly to version 1")
    else:
        print("✗ State restoration failed")
