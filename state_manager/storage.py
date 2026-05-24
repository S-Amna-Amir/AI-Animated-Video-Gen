import sqlite3
import json
from pathlib import Path

DB_PATH = Path("data/state/state.db")
db_path = str(DB_PATH)

def get_connection(db_path_override=None):
    path = db_path_override if db_path_override else db_path
    if path == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path_override=None):
    conn = get_connection(db_path_override)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            version INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            edit_command TEXT,
            state_json TEXT,
            asset_paths TEXT
        )
    ''')
    conn.commit()
    conn.close()
