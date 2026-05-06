"""
Audio Agent - Orchestrates Phase 2 Audio Generation & Integration.
Processes Phase 1 output (scenes & characters) to generate audio with timing manifest.
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from mcp.tools.audio_tools.voice_mapper import VoiceMapper
from mcp.tools.audio_tools.tts_tool import TTSTool
from agents.audio_agent.run_manager import AudioRunManager
from agents.audio_agent.planner import AudioPhasePlanner, DialogueExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TimingManifestBuilder:
    """
    Builds the timing manifest from generated audio files.
    Maps scene IDs to millisecond-accurate timestamps for A/V sync.
    """
    
    @staticmethod
    def build_manifest(audio_metadata_list: List[Dict]) -> List[Dict]:
        """
        Build timing manifest from audio metadata.
        
        Args:
            audio_metadata_list: List of audio metadata dicts
            
        Returns:
            List of timing entries sorted by scene and cumulative time
        """
        timing_entries = []
        scene_timings: Dict[int, int] = {}  # scene_id -> cumulative time (ms)
        
        # Sort by scene_id and line_index
        sorted_audios = sorted(
            audio_metadata_list,
            key=lambda x: (x["scene_id"], x["line_index"])
        )
        
        for audio in sorted_audios:
            scene_id = audio["scene_id"]
            
            # Initialize scene timing if not exists
            if scene_id not in scene_timings:
                scene_timings[scene_id] = 0
            
            start_ms = scene_timings[scene_id]
            end_ms = start_ms + audio["duration_ms"]
            
            timing_entry = {
                "scene_id": scene_id,
                "speaker": audio["speaker"],
                "audio_file": audio["audio_file"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": audio["duration_ms"],
                "line_index": audio["line_index"],
                "text": audio["text"]
            }
            
            timing_entries.append(timing_entry)
            scene_timings[scene_id] = end_ms
        
        return timing_entries
    
    @staticmethod
    def save_manifest(
        timing_entries: List[Dict],
        output_path: Path
    ) -> str:
        """
        Save timing manifest to JSON file.
        
        Args:
            timing_entries: List of timing entries
            output_path: Path to save the manifest
            
        Returns:
            Path to the saved manifest file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(timing_entries, f, indent=2)
        
        logger.info(f"Timing manifest saved to {output_path}")
        return str(output_path)


class AudioAgent:
    """
    Phase 2 Audio Agent.
    Generates audio from Phase 1 script using Edge-TTS with character-specific voices.
    Produces audio files and timing manifest for Phase 3.
    """
    
    def __init__(
        self,
        phase1_data_dir: str = "data/outputs/Phase1",
        phase2_output_dir: str = "data/outputs/Phase2",
        custom_voice_mappings: Optional[Dict[str, str]] = None,
        run_id: Optional[str] = None
    ):
        """
        Initialize the Audio Agent.
        
        Args:
            phase1_data_dir: Directory containing Phase 1 outputs
            phase2_output_dir: Directory for Phase 2 outputs
            custom_voice_mappings: Optional custom character-to-voice mappings
            run_id: Optional run ID for organizing outputs
        """
        self.phase1_data_dir = Path(phase1_data_dir)
        
        self.voice_mapper = VoiceMapper(custom_voice_mappings)
        self.run_manager = AudioRunManager(phase2_output_dir)
        self.planner = AudioPhasePlanner()
        
        # Create run directory
        self.run_manager.create_run_directory(run_id)
        self.tts_tool = TTSTool(str(self.run_manager.get_audio_output_dir()))
        
        # Data containers
        self.scene_manifest: Dict = {}
        self.character_db: Dict = {}
        self.audio_metadata: List[Dict] = []
    
    def load_phase1_data(self) -> bool:
        """
        Load Phase 1 outputs (scene manifest and character database).
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try different filename variations
            scene_files = [
                self.phase1_data_dir / "scene_manifest_auto.json",
                self.phase1_data_dir / "scene_manifest_manual.json",
                self.phase1_data_dir / "scene_manifest.json"
            ]
            
            char_files = [
                self.phase1_data_dir / "character_db_auto.json",
                self.phase1_data_dir / "character_db_manual.json",
                self.phase1_data_dir / "character_db.json"
            ]
            
            # Load scene manifest
            scene_file = None
            for f in scene_files:
                if f.exists():
                    scene_file = f
                    break
            
            if not scene_file:
                logger.error(f"No scene manifest found in {self.phase1_data_dir}")
                self.planner.mark_step_failed(
                    self.planner.STEP_LOAD_DATA,
                    f"No scene manifest found in {self.phase1_data_dir}"
                )
                return False
            
            with open(scene_file) as f:
                self.scene_manifest = json.load(f)
            
            logger.info(f"Loaded scene manifest from {scene_file}")
            
            # Load character database
            char_file = None
            for f in char_files:
                if f.exists():
                    char_file = f
                    break
            
            if not char_file:
                logger.error(f"No character database found in {self.phase1_data_dir}")
                self.planner.mark_step_failed(
                    self.planner.STEP_LOAD_DATA,
                    f"No character database found in {self.phase1_data_dir}"
                )
                return False
            
            with open(char_file) as f:
                self.character_db = json.load(f)
            
            logger.info(f"Loaded character database from {char_file}")
            
            self.planner.mark_step_complete(
                self.planner.STEP_LOAD_DATA,
                {
                    "scene_manifest": str(scene_file),
                    "character_db": str(char_file)
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading Phase 1 data: {str(e)}")
            self.planner.mark_step_failed(self.planner.STEP_LOAD_DATA, str(e))
            return False
    
    def _extract_dialogues(self) -> List[Dict]:
        """
        Extract all dialogues from scene manifest with character voice mappings.
        
        Returns:
            List of dialogue dicts ready for TTS synthesis
        """
        dialogues = DialogueExtractor.extract_from_manifest(self.scene_manifest)
        
        # Add voice mappings to each dialogue
        for dialogue in dialogues:
            speaker = dialogue["speaker"]
            dialogue["voice"] = self.voice_mapper.get_voice_for_character(speaker)
        
        # Validate dialogues
        validation = DialogueExtractor.validate_dialogues(dialogues)
        logger.info(f"Dialogue validation: {validation['valid']} valid, "
                   f"{validation['missing_speaker']} missing speaker, "
                   f"{validation['missing_text']} missing text")
        
        self.planner.mark_step_complete(
            self.planner.STEP_EXTRACT_DIALOGUES,
            {
                "total_dialogues": len(dialogues),
                "validation": validation
            }
        )
        
        return dialogues
    
    async def process(self) -> Dict[str, Any]:
        """
        Process Phase 2: Generate audio for all dialogues and create timing manifest.
        
        Returns:
            Dict with processing results:
            {
                "status": "success" | "failure",
                "total_scenes": int,
                "total_dialogues": int,
                "audio_files_generated": int,
                "timing_manifest_path": str,
                "character_voices_used": dict,
                "output_directory": str,
                "total_duration_ms": int,
                "run_id": str,
                "workflow_progress": dict
            }
        """
        try:
            # Step 1: Load Phase 1 data
            if not self.load_phase1_data():
                return {
                    "status": "failure",
                    "error": "Failed to load Phase 1 data",
                    "workflow_progress": self.planner.get_progress()
                }
            
            # Step 2: Map character voices
            self.planner.mark_step_complete(
                self.planner.STEP_MAP_VOICES,
                self.voice_mapper.get_all_character_voices()
            )
            
            # Step 3: Extract dialogues
            dialogues = self._extract_dialogues()
            
            if not dialogues:
                logger.warning("No dialogues found in scene manifest")
                self.planner.mark_step_failed(
                    self.planner.STEP_SYNTHESIZE_AUDIO,
                    "No dialogues found"
                )
                return {
                    "status": "failure",
                    "error": "No dialogues found",
                    "workflow_progress": self.planner.get_progress()
                }
            
            logger.info(f"Starting TTS synthesis for {len(dialogues)} dialogue lines...")
            
            # Step 4: Synthesize audio
            self.audio_metadata = await self.tts_tool.synthesize_batch(
                dialogues,
                self.run_manager.get_audio_output_dir()
            )
            
            if not self.audio_metadata:
                self.planner.mark_step_failed(
                    self.planner.STEP_SYNTHESIZE_AUDIO,
                    "No audio files were generated"
                )
                return {
                    "status": "failure",
                    "error": "No audio files were generated",
                    "workflow_progress": self.planner.get_progress()
                }
            
            logger.info(f"Generated {len(self.audio_metadata)} audio files")
            self.planner.mark_step_complete(
                self.planner.STEP_SYNTHESIZE_AUDIO,
                {"audio_files_generated": len(self.audio_metadata)}
            )
            
            # Step 5: Build timing manifest
            timing_manifest = TimingManifestBuilder.build_manifest(self.audio_metadata)
            self.planner.mark_step_complete(
                self.planner.STEP_BUILD_MANIFEST,
                {"timing_entries": len(timing_manifest)}
            )
            
            # Step 6: Save outputs
            # Save timing manifest
            manifest_path = self.run_manager.save_timing_manifest(timing_manifest)
            
            # Calculate total duration
            total_duration_ms = sum(item["duration_ms"] for item in self.audio_metadata)
            
            # Save summary
            summary = {
                "workflow_id": f"phase2_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(self.scene_manifest.get("scenes", [])),
                "total_dialogues": len(self.audio_metadata),
                "total_duration_ms": total_duration_ms,
                "audio_output_dir": str(self.run_manager.get_audio_output_dir()),
                "timing_manifest": str(manifest_path),
                "character_voices": self.voice_mapper.get_all_character_voices()
            }
            
            summary_path = self.run_manager.save_phase2_summary(summary)
            
            # Save phase 2 config
            config = {
                "phase1_data_dir": str(self.phase1_data_dir),
                "phase2_output_dir": str(self.run_manager.base_output_dir),
                "voice_mapper_config": {
                    "mappings": self.voice_mapper.get_all_character_voices()
                }
            }
            self.run_manager.save_phase2_config(config)
            
            self.planner.mark_step_complete(
                self.planner.STEP_SAVE_OUTPUTS,
                {
                    "summary": str(summary_path),
                    "manifest": str(manifest_path)
                }
            )
            
            return {
                "status": "success",
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(self.scene_manifest.get("scenes", [])),
                "total_dialogues": len(self.audio_metadata),
                "audio_files_generated": len(self.audio_metadata),
                "timing_manifest_path": str(manifest_path),
                "character_voices_used": self.voice_mapper.get_all_character_voices(),
                "output_directory": str(self.run_manager.current_run_dir),
                "total_duration_ms": total_duration_ms,
                "summary": str(summary_path),
                "workflow_progress": self.planner.get_progress()
            }
            
        except Exception as e:
            logger.error(f"Error during Phase 2 processing: {str(e)}")
            self.planner.mark_step_failed(self.planner.STEP_SAVE_OUTPUTS, str(e))
            return {
                "status": "failure",
                "error": str(e),
                "workflow_progress": self.planner.get_progress()
            }


async def run_audio_agent(
    phase1_dir: str = "data/outputs/Phase1",
    phase2_dir: str = "data/outputs/Phase2",
    custom_voices: Optional[Dict[str, str]] = None,
    run_id: Optional[str] = None
) -> Dict:
    """
    Run the Audio Agent for Phase 2.
    
    Args:
        phase1_dir: Directory containing Phase 1 outputs
        phase2_dir: Directory for Phase 2 outputs
        custom_voices: Optional custom character-to-voice mappings
        run_id: Optional run ID for organizing outputs
        
    Returns:
        Processing results dictionary
    """
    agent = AudioAgent(phase1_dir, phase2_dir, custom_voices, run_id)
    return await agent.process()


# Entry point for direct execution
if __name__ == "__main__":
    results = asyncio.run(run_audio_agent())
    print(json.dumps(results, indent=2))
