"""
scripts/run_server.py
----------------------
Start the Phase 4 FastAPI + WebSocket server.

Usage:
    python scripts/run_server.py              # default: port 8000
    python scripts/run_server.py --port 8080
    python scripts/run_server.py --reload     # dev hot-reload
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project Montage API server")
    parser.add_argument("--host",   default="0.0.0.0")
    parser.add_argument("--port",   type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Hot-reload (dev only)")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print("  PROJECT MONTAGE — API SERVER")
    print(f"{'='*55}")
    print(f"  URL  : http://localhost:{args.port}")
    print(f"  Docs : http://localhost:{args.port}/docs")
    print(f"  Reload: {args.reload}")
    print(f"{'='*55}\n")

    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
