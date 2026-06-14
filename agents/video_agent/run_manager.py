"""
agents/video_agent/run_manager.py
------------------------------------
Manages Phase 3 sequential run directories.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VideoRunManager:
    def __init__(self, base_output_dir: str = "data/outputs/Phase3"):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def create_run_dir(self) -> tuple[str, str]:
        """Create next sequential run_XX directory."""
        used = {
            int(p.name.replace("run_", ""))
            for p in self.base_output_dir.iterdir()
            if p.is_dir() and p.name.startswith("run_") and p.name[4:].isdigit()
        }
        n = 1
        while n in used:
            n += 1
        run_id  = f"run_{n:02d}"
        run_dir = self.base_output_dir / run_id
        (run_dir / "images").mkdir(parents=True, exist_ok=True)
        (run_dir / "clips").mkdir(parents=True, exist_ok=True)
        logger.info("Created Phase 3 run directory: %s", run_dir)
        return run_id, str(run_dir)

    def save_run_summary(self, run_dir: str, summary: Dict[str, Any]) -> None:
        out = Path(run_dir) / "phase3_output.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def load_run_summary(self, run_dir: str) -> Dict[str, Any]:
        p = Path(run_dir) / "phase3_output.json"
        if not p.exists():
            raise FileNotFoundError(f"Run summary not found: {p}")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def list_all_runs(self) -> List[Dict[str, Any]]:
        runs = []
        for d in sorted(p for p in self.base_output_dir.iterdir() if p.is_dir()):
            try:
                summary = self.load_run_summary(str(d))
            except Exception:
                summary = {}
            runs.append({
                "run_id":  summary.get("run_id", d.name),
                "status":  summary.get("status", "unknown"),
                "run_dir": str(d),
                "summary": summary,
            })
        return runs

    def get_latest_run(self) -> Dict[str, Any]:
        dirs = [p for p in self.base_output_dir.iterdir() if p.is_dir()]
        if not dirs:
            return {}
        latest = max(dirs, key=lambda p: p.stat().st_mtime)
        try:
            summary = self.load_run_summary(str(latest))
        except Exception:
            summary = {}
        return {
            "run_id":  summary.get("run_id", latest.name),
            "status":  summary.get("status", "unknown"),
            "run_dir": str(latest),
            "summary": summary,
        }
