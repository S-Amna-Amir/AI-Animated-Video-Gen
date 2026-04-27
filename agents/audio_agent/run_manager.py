"""
Audio Output Directory Manager for Phase 2.
Manages run-based directory structure for audio outputs and timing manifests.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AudioRunManager:
    """
    Manages Phase 2 run-based output directory structure.
    Creates and maintains directories for audio files and manifests.
    """
    
    def __init__(self, base_output_dir: str = "data/outputs/Phase2"):
        """
        Initialize the run manager.
        
        Args:
            base_output_dir: Base directory for all Phase 2 outputs
        """
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_run_dir: Optional[Path] = None
        self.current_run_id: Optional[str] = None
    
    def create_run_directory(self, run_id: Optional[str] = None) -> Path:
        """
        Create a new run directory with unique ID.
        
        Args:
            run_id: Optional custom run ID. If not provided, auto-generates sequential one.
            
        Returns:
            Path to the created run directory
        """
        if not run_id:
            # Auto-generate sequential run ID (01, 02, 03, etc.)
            existing_runs = self.list_all_runs()
            run_number = len(existing_runs) + 1
            run_id = f"run_{run_number:02d}"
        
        self.current_run_id = run_id
        self.current_run_dir = self.base_output_dir / run_id
        self.current_run_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created run directory: {self.current_run_dir}")
        
        return self.current_run_dir
    
    def get_audio_scene_dir(self, scene_id: int, create: bool = True) -> Path:
        """
        Get or create audio directory for a specific scene.
        
        Args:
            scene_id: Scene identifier
            create: Whether to create the directory if it doesn't exist
            
        Returns:
            Path to scene audio directory
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        scene_audio_dir = self.current_run_dir / "audio" / f"scene{scene_id:02d}"
        
        if create:
            scene_audio_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Scene audio directory: {scene_audio_dir}")
        
        return scene_audio_dir
    
    def get_audio_output_dir(self, create: bool = True) -> Path:
        """
        Get the main audio output directory for current run.
        
        Args:
            create: Whether to create the directory if it doesn't exist
            
        Returns:
            Path to audio output directory
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        audio_dir = self.current_run_dir / "audio"
        
        if create:
            audio_dir.mkdir(parents=True, exist_ok=True)
        
        return audio_dir
    
    def get_manifest_path(self) -> Path:
        """
        Get path for timing manifest in current run.
        
        Returns:
            Path to timing_manifest.json
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        return self.current_run_dir / "timing_manifest.json"
    
    def save_timing_manifest(self, manifest_data: list) -> Path:
        """
        Save timing manifest to current run directory.
        
        Args:
            manifest_data: List of timing manifest entries
            
        Returns:
            Path to saved manifest file
        """
        manifest_path = self.get_manifest_path()
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest_data, f, indent=2)
        
        logger.info(f"Saved timing manifest to {manifest_path}")
        
        return manifest_path
    
    def save_phase2_config(self, config_data: Dict) -> Path:
        """
        Save Phase 2 configuration and metadata to run directory.
        
        Args:
            config_data: Configuration dictionary
            
        Returns:
            Path to saved config file
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        config_path = self.current_run_dir / "phase2_config.json"
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        logger.info(f"Saved Phase 2 config to {config_path}")
        
        return config_path
    
    def save_phase2_summary(self, summary_data: Dict) -> Path:
        """
        Save Phase 2 processing summary to run directory.
        
        Args:
            summary_data: Summary dictionary with processing results
            
        Returns:
            Path to saved summary file
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        summary_path = self.current_run_dir / "phase2_summary.json"
        
        with open(summary_path, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        logger.info(f"Saved Phase 2 summary to {summary_path}")
        
        return summary_path
    
    def get_run_info(self) -> Dict:
        """
        Get information about current run.
        
        Returns:
            Dict with run information
        """
        if not self.current_run_dir:
            return {"status": "no_active_run"}
        
        return {
            "run_id": self.current_run_id,
            "run_directory": str(self.current_run_dir),
            "audio_directory": str(self.get_audio_output_dir(create=False)),
            "timing_manifest": str(self.get_manifest_path()),
            "exists": self.current_run_dir.exists()
        }
    
    def list_all_runs(self) -> list:
        """
        List all Phase 2 runs in base directory.
        
        Returns:
            List of run IDs (directory names)
        """
        runs = [d.name for d in self.base_output_dir.iterdir() if d.is_dir()]
        return sorted(runs)
    
    def get_latest_run_dir(self) -> Optional[Path]:
        """
        Get the latest run directory by modification time.
        
        Returns:
            Path to latest run directory or None if no runs exist
        """
        runs = list(self.base_output_dir.iterdir())
        if not runs:
            return None
        
        latest = max(runs, key=lambda p: p.stat().st_mtime)
        return latest if latest.is_dir() else None
    
    def load_timing_manifest(self, run_id: Optional[str] = None) -> Optional[list]:
        """
        Load timing manifest from a specific run or current run.
        
        Args:
            run_id: Optional run ID to load from. Uses current run if not provided.
            
        Returns:
            List of timing manifest entries or None if not found
        """
        if run_id:
            manifest_path = self.base_output_dir / run_id / "timing_manifest.json"
        else:
            manifest_path = self.get_manifest_path()
        
        if not manifest_path.exists():
            logger.warning(f"Timing manifest not found at {manifest_path}")
            return None
        
        with open(manifest_path) as f:
            return json.load(f)
    
    def get_master_audio_path(self) -> Path:
        """
        Get path for master audio track in current run.
        
        Returns:
            Path to master_audio_track.mp3
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        return self.current_run_dir / "master_audio_track.mp3"
    
    def save_bgm_metadata(self, bgm_data: Dict) -> Path:
        """
        Save background music metadata to current run directory.
        
        Args:
            bgm_data: BGM metadata dict with scene info and Freesound details
            
        Returns:
            Path to saved BGM metadata file
        """
        if not self.current_run_dir:
            raise ValueError("No active run directory. Call create_run_directory() first.")
        
        bgm_path = self.current_run_dir / "bgm_metadata.json"
        
        with open(bgm_path, 'w') as f:
            json.dump(bgm_data, f, indent=2)
        
        logger.info(f"Saved BGM metadata to {bgm_path}")
        
        return bgm_path
    
    def cleanup_run(self, run_id: str, confirm: bool = True) -> bool:
        """
        Delete a specific run directory and all its contents.
        
        Args:
            run_id: Run ID to delete
            confirm: Whether to require confirmation (not implemented, always deletes)
            
        Returns:
            True if successful, False otherwise
        """
        run_dir = self.base_output_dir / run_id
        
        if not run_dir.exists():
            logger.warning(f"Run directory not found: {run_dir}")
            return False
        
        try:
            shutil.rmtree(run_dir)
            logger.info(f"Deleted run directory: {run_dir}")
            return True
        except Exception as e:
            logger.error(f"Error deleting run directory: {str(e)}")
            return False
