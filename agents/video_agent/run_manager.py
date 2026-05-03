"""Video Output Directory Manager for Phase 3."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VideoRunManager:
    """
    Manages Phase 3 run-based output directory structure.
    """

    def __init__(self, base_output_dir: str = "data/outputs/Phase3/"):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def create_run_dir(self) -> tuple[str, str]:
        """
        Create next sequential run directory (run_XX) with images and clips subdirs.
        """
        used_nums = set()
        for path in self.base_output_dir.iterdir():
            if not path.is_dir():
                continue
            name = path.name
            if not name.startswith("run_"):
                continue
            suffix = name.replace("run_", "", 1)
            if suffix.isdigit():
                used_nums.add(int(suffix))

        next_num = 1
        while next_num in used_nums:
            next_num += 1

        run_id = f"run_{next_num:02d}"
        run_dir = self.base_output_dir / run_id
        (run_dir / "images").mkdir(parents=True, exist_ok=True)
        (run_dir / "clips").mkdir(parents=True, exist_ok=True)

        logger.info("Created Phase 3 run directory: %s", run_dir)
        return run_id, str(run_dir)

    def save_run_summary(self, run_dir: str, summary: dict[str, Any]) -> None:
        """
        Save Phase 3 run summary to phase3_output.json.
        """
        output_path = Path(run_dir) / "phase3_output.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        logger.info("Saved Phase 3 summary to %s", output_path)

    def load_run_summary(self, run_dir: str) -> dict[str, Any]:
        """
        Load and return phase3_output.json from run directory.
        """
        summary_path = Path(run_dir) / "phase3_output.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"Run summary not found: {summary_path}")
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_all_runs(self) -> list[dict[str, Any]]:
        """
        Return summaries for all runs with at least run_id and status.
        """
        runs: list[dict[str, Any]] = []
        run_dirs = sorted([p for p in self.base_output_dir.iterdir() if p.is_dir()])

        for run_dir in run_dirs:
            summary_path = run_dir / "phase3_output.json"
            if summary_path.exists():
                try:
                    summary = self.load_run_summary(str(run_dir))
                except Exception as exc:
                    logger.warning("Could not load summary for %s: %s", run_dir, exc)
                    summary = {}
            else:
                summary = {}

            runs.append(
                {
                    "run_id": summary.get("run_id", run_dir.name),
                    "status": summary.get("status", "unknown"),
                    "run_dir": str(run_dir),
                    "summary": summary,
                }
            )

        return runs

    def get_latest_run(self) -> dict[str, Any]:
        """
        Return summary of the most recent run directory.
        """
        run_dirs = [p for p in self.base_output_dir.iterdir() if p.is_dir()]
        if not run_dirs:
            return {}

        latest_run_dir = max(run_dirs, key=lambda p: p.stat().st_mtime)
        summary_path = latest_run_dir / "phase3_output.json"

        if summary_path.exists():
            try:
                summary = self.load_run_summary(str(latest_run_dir))
            except Exception as exc:
                logger.warning("Failed to load latest run summary: %s", exc)
                summary = {}
        else:
            summary = {}

        return {
            "run_id": summary.get("run_id", latest_run_dir.name),
            "status": summary.get("status", "unknown"),
            "run_dir": str(latest_run_dir),
            "summary": summary,
        }
