"""
shared/constants/__init__.py
-----------------------------
Project-wide constants shared across all phases.
"""
from pathlib import Path

# ── Directory layout ───────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).resolve().parents[2]
DATA_DIR       = PROJECT_ROOT / "data"
OUTPUTS_DIR    = DATA_DIR / "outputs"
RUNS_DIR       = DATA_DIR / "runs"       # unified per-story project folders
TEMP_DIR       = DATA_DIR / "temp"
STATE_VERSIONS = DATA_DIR / "state_versions"

# Ensure directories exist at import time
for _d in (OUTPUTS_DIR, RUNS_DIR, TEMP_DIR, STATE_VERSIONS, OUTPUTS_DIR / "images"):
    _d.mkdir(parents=True, exist_ok=True)

# ── MCP / memory collections ───────────────────────────────────────────────────
COLLECTION_SCRIPTS    = "scripts"
COLLECTION_CHARACTERS = "characters"
COLLECTION_IMAGES     = "images"

# ── Workflow statuses ──────────────────────────────────────────────────────────
STATUS_PROCESSING = "processing"
STATUS_COMPLETE   = "complete"
STATUS_FAILED     = "failed"

# ── LLM defaults ──────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "llama-3.3-70b-versatile"
DEFAULT_NUM_SCENES = 5
DEFAULT_GENRE      = "drama"
DEFAULT_STYLE      = "cinematic"
