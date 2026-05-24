import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from .storage import get_connection

class Snapshot(BaseModel):
    version: int
    run_id: str
    timestamp: str
    edit_command: Optional[str]
    state_json: Dict[str, Any]
    asset_paths: List[str]

def create_snapshot(run_id: str, edit_command: str, state_json: Dict[str, Any], asset_paths: List[str]) -> Snapshot:
    conn = get_connection()
    cursor = conn.cursor()
    
    state_str = json.dumps(state_json)
    assets_str = json.dumps(asset_paths)
    
    cursor.execute('''
        INSERT INTO snapshots (run_id, edit_command, state_json, asset_paths)
        VALUES (?, ?, ?, ?)
    ''', (run_id, edit_command, state_str, assets_str))
    
    version = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT timestamp FROM snapshots WHERE version = ?", (version,))
    row = cursor.fetchone()
    timestamp = row["timestamp"]
    
    conn.close()
    
    return Snapshot(
        version=version,
        run_id=run_id,
        timestamp=timestamp,
        edit_command=edit_command,
        state_json=state_json,
        asset_paths=asset_paths
    )
