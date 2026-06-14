"""
agents/audio_agent/run_manager.py
------------------------------------
Manages Phase 2 sequential run directories.
"""
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AudioRunManager:
    def __init__(self, base_output_dir: str = "data/outputs/Phase2"):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        self.current_run_dir: Optional[Path] = None
        self.current_run_id: Optional[str] = None

    def create_run_directory(self, run_id: Optional[str] = None) -> Path:
        if not run_id:
            existing = [d.name for d in self.base_output_dir.iterdir() if d.is_dir()]
            run_id = f"run_{len(existing) + 1:02d}"
        self.current_run_id = run_id
        self.current_run_dir = self.base_output_dir / run_id
        self.current_run_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[RunManager] Created: {self.current_run_dir}")
        return self.current_run_dir

    def _require_run(self):
        if not self.current_run_dir:
            raise ValueError("No active run. Call create_run_directory() first.")

    def get_audio_output_dir(self, create: bool = True) -> Path:
        self._require_run()
        d = self.current_run_dir / "audio"
        if create:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def get_audio_scene_dir(self, scene_id: int, create: bool = True) -> Path:
        self._require_run()
        d = self.current_run_dir / "audio" / f"scene{scene_id:02d}"
        if create:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def get_manifest_path(self) -> Path:
        self._require_run()
        return self.current_run_dir / "timing_manifest.json"

    def get_master_audio_path(self) -> Path:
        self._require_run()
        return self.current_run_dir / "master_audio_track.mp3"

    def save_timing_manifest(self, data: list) -> Path:
        path = self.get_manifest_path()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"[RunManager] Timing manifest → {path}")
        return path

    def save_phase2_summary(self, data: Dict) -> Path:
        self._require_run()
        path = self.current_run_dir / "phase2_summary.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def save_phase2_config(self, data: Dict) -> Path:
        self._require_run()
        path = self.current_run_dir / "phase2_config.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def save_bgm_metadata(self, data: Dict) -> Path:
        self._require_run()
        path = self.current_run_dir / "bgm_metadata.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def list_all_runs(self) -> List[str]:
        return sorted(d.name for d in self.base_output_dir.iterdir() if d.is_dir())

    def load_timing_manifest(self, run_id: Optional[str] = None) -> Optional[list]:
        path = (
            self.base_output_dir / run_id / "timing_manifest.json"
            if run_id
            else self.get_manifest_path()
        )
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
