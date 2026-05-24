import json
from typing import List
from .storage import get_connection
from .snapshot import Snapshot

def get_history(run_id: str) -> List[Snapshot]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM snapshots WHERE run_id = ? ORDER BY version ASC", (run_id,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append(Snapshot(
            version=row["version"],
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            edit_command=row["edit_command"],
            state_json=json.loads(row["state_json"]),
            asset_paths=json.loads(row["asset_paths"])
        ))
    return history

def diff_summary(v1: Snapshot, v2: Snapshot) -> str:
    """Compare two snapshots and return a human-readable diff string."""
    if v2.edit_command and v2.edit_command != v1.edit_command:
        return f"Command applied: '{v2.edit_command}'"
    
    # Check for basic dictionary differences in state_json
    diffs = []
    for key, val in v2.state_json.items():
        if key not in v1.state_json or v1.state_json[key] != val:
            diffs.append(f"{key} updated")
            
    if diffs:
        return ", ".join(diffs)
        
    return "State modified"
