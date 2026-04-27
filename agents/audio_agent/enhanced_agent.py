"""
Enhanced Phase 2 Audio Agent with Background Music Integration.
Orchestrates per-scene audio composition (voice + BGM) and master track creation.
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from mcp.tools.audio_tools.voice_mapper import VoiceMapper
from mcp.tools.audio_tools.tts_tool import TTSTool
from mcp.tools.audio_tools.bgm_tool import search_and_download_bgm, BGMLocator
from mcp.tools.audio_tools.scene_mood_analyzer import SceneMoodAnalyzer, SceneAnalysisCache
from mcp.tools.audio_tools.audio_composer import AudioComposer, compose_voice_with_fallback_bgm
from agents.audio_agent.run_manager import AudioRunManager
from agents.audio_agent.planner import AudioPhasePlanner, DialogueExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedAudioAgent:
    """
    Phase 2 Audio Agent with Background Music Integration.
    
    Features:
    - Per-scene TTS synthesis with character-specific voices
    - LLM-based scene mood analysis for BGM search queries
    - Freesound API integration for ambient background music
    - Per-scene voice+BGM composition with ducking and fading
    - Master audio track concatenation
    - Comprehensive metadata tracking
    """
    
    def __init__(
        self,
        phase1_data_dir: str = "data/outputs/Phase1",
        phase2_output_dir: str = "data/outputs/Phase2",
        custom_voice_mappings: Optional[Dict[str, str]] = None,
        groq_client=None,
        freesound_api_key: Optional[str] = None,
        run_id: Optional[str] = None
    ):
        """
        Initialize Enhanced Audio Agent.
        
        Args:
            phase1_data_dir: Directory containing Phase 1 outputs
            phase2_output_dir: Directory for Phase 2 outputs
            custom_voice_mappings: Optional custom character-to-voice mappings
            groq_client: Optional Groq client for mood analysis
            freesound_api_key: Optional Freesound API key
            run_id: Optional custom run ID
        """
        self.phase1_data_dir = Path(phase1_data_dir)
        
        self.voice_mapper = VoiceMapper(custom_voice_mappings)
        self.run_manager = AudioRunManager(phase2_output_dir)
        self.planner = AudioPhasePlanner()
        self.mood_analyzer = SceneMoodAnalyzer(groq_client)
        self.mood_cache = SceneAnalysisCache()
        self.freesound_api_key = freesound_api_key
        
        # Create run directory
        self.run_manager.create_run_directory(run_id)
        self.tts_tool = TTSTool(str(self.run_manager.get_audio_output_dir()))
        
        # Data containers
        self.scene_manifest: Dict = {}
        self.character_db: Dict = {}
        self.audio_metadata: List[Dict] = []
        self.bgm_metadata: Dict[int, Dict] = {}  # scene_id -> BGM info
        self.scene_compositions: Dict[int, Path] = {}  # scene_id -> composed audio path
        
        # Ensure FFmpeg available for composition
        if not AudioComposer.has_ffmpeg():
            logger.warning("FFmpeg not available - audio composition will be limited")
    
    def load_phase1_data(self) -> bool:
        """Load Phase 1 outputs."""
        try:
            scene_files = [
                self.phase1_data_dir / "scene_manifest_auto.json",
                self.phase1_data_dir / "scene_manifest_manual.json",
                self.phase1_data_dir / "scene_manifest.json"
            ]
            
            scene_file = next((f for f in scene_files if f.exists()), None)
            if not scene_file:
                logger.error(f"No scene manifest found in {self.phase1_data_dir}")
                self.planner.mark_step_failed(
                    self.planner.STEP_LOAD_DATA,
                    "No scene manifest found"
                )
                return False
            
            with open(scene_file) as f:
                self.scene_manifest = json.load(f)
            
            logger.info(f"Loaded scene manifest from {scene_file}")
            self.planner.mark_step_complete(
                self.planner.STEP_LOAD_DATA,
                {"scene_manifest": str(scene_file)}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading Phase 1 data: {str(e)}")
            self.planner.mark_step_failed(self.planner.STEP_LOAD_DATA, str(e))
            return False
    
    def _extract_dialogues(self) -> List[Dict]:
        """Extract dialogues with voice mappings."""
        dialogues = DialogueExtractor.extract_from_manifest(self.scene_manifest)
        
        for dialogue in dialogues:
            speaker = dialogue["speaker"]
            dialogue["voice"] = self.voice_mapper.get_voice_for_character(speaker)
        
        validation = DialogueExtractor.validate_dialogues(dialogues)
        logger.info(f"Dialogue validation: {validation['valid']} valid")
        
        self.planner.mark_step_complete(
            self.planner.STEP_EXTRACT_DIALOGUES,
            {"total_dialogues": len(dialogues)}
        )
        
        return dialogues
    
    async def _synthesize_scene_voiceovers(
        self,
        scene_dialogues: List[Dict],
        scene_id: int
    ) -> List[Dict]:
        """Synthesize all dialogue for a single scene."""
        scene_audio_dir = self.run_manager.get_audio_scene_dir(scene_id)
        results = await self.tts_tool.synthesize_batch(scene_dialogues, scene_audio_dir)
        return results
    
    async def _obtain_scene_bgm(self, scene_id: int) -> Optional[Path]:
        """
        Obtain background music for a scene.
        Uses mood-based Freesound search with fallback.
        """
        try:
            scene = next((s for s in self.scene_manifest.get("scenes", []) 
                         if s.get("scene_id") == scene_id), None)
            
            if not scene:
                return None
            
            # Generate mood query using cache
            scene_desc = f"{scene.get('location', '')} {scene.get('dialogue', [{}])[0].get('visual_cue', '')}"
            mood_query = self.mood_cache.get_or_generate(
                scene_id,
                scene_desc,
                self.mood_analyzer
            )
            
            logger.info(f"Scene {scene_id} BGM query: {mood_query}")
            
            # Search and download BGM
            bgm_path, bgm_info = search_and_download_bgm(
                mood_query=mood_query,
                output_path=self.run_manager.get_audio_scene_dir(scene_id) / "bgm.mp3",
                api_key=self.freesound_api_key,
                use_fallback=True
            )
            
            if bgm_info:
                self.bgm_metadata[scene_id] = {
                    "query": mood_query,
                    "source": bgm_info.get("source", "freesound"),
                    "name": bgm_info.get("name", "unknown"),
                    "freesound_id": bgm_info.get("id"),
                    "url": bgm_info.get("url")
                }
            
            return bgm_path
            
        except Exception as e:
            logger.error(f"Error obtaining BGM for scene {scene_id}: {str(e)}")
            return None
    
    async def _compose_scene_audio(
        self,
        scene_id: int,
        scene_audio_files: List[Dict],
        bgm_path: Optional[Path]
    ) -> Optional[Path]:
        """
        Compose voice + BGM for a single scene.
        Merges all dialogue lines with background music.
        """
        try:
            scene_dir = self.run_manager.get_audio_scene_dir(scene_id)
            
            # For now, use first dialogue as scene audio
            # In production, this would concatenate multiple lines
            if not scene_audio_files:
                return None
            
            voice_file = scene_audio_files[0]["audio_file"]
            composed_file = scene_dir / f"scene{scene_id:02d}_composed.mp3"
            
            # Compose voice with BGM
            if bgm_path and Path(bgm_path).exists():
                success = AudioComposer.compose_voice_with_bgm(
                    voice_file=str(voice_file),
                    bgm_file=str(bgm_path),
                    output_file=str(composed_file),
                    bgm_volume_db=-20.0,
                    fade_duration_ms=500
                )
            else:
                # No BGM, use voice only
                import shutil
                shutil.copy(voice_file, composed_file)
                success = True
            
            if success:
                logger.info(f"Scene {scene_id} composition: {composed_file.name}")
                self.scene_compositions[scene_id] = composed_file
                return composed_file
            
            return None
            
        except Exception as e:
            logger.error(f"Error composing scene {scene_id}: {str(e)}")
            return None
    
    async def _create_master_audio_track(self) -> Optional[Path]:
        """
        Concatenate all scene compositions into master audio track.
        """
        if not self.scene_compositions:
            logger.warning("No scene compositions available for master track")
            return None
        
        try:
            # Sort by scene ID
            scene_files = [
                self.scene_compositions[sid]
                for sid in sorted(self.scene_compositions.keys())
                if self.scene_compositions[sid].exists()
            ]
            
            if not scene_files:
                return None
            
            master_path = self.run_manager.get_master_audio_path()
            
            success = AudioComposer.concatenate_audio_files(
                audio_files=[str(f) for f in scene_files],
                output_file=str(master_path)
            )
            
            if success:
                logger.info(f"Master audio track created: {master_path}")
                return master_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating master audio track: {str(e)}")
            return None
    
    async def process(self) -> Dict[str, Any]:
        """
        Process Phase 2: Generate audio with BGM and create compositions.
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
                return {
                    "status": "failure",
                    "error": "No dialogues found",
                    "workflow_progress": self.planner.get_progress()
                }
            
            # Step 4: Synthesize audio per scene and compose with BGM
            logger.info("Starting per-scene audio synthesis and composition...")
            
            scenes = self.scene_manifest.get("scenes", [])
            total_synthesized = 0
            
            for scene in scenes:
                scene_id = scene.get("scene_id")
                
                # Get dialogues for this scene
                scene_dialogues = [d for d in dialogues if d["scene_id"] == scene_id]
                
                if not scene_dialogues:
                    continue
                
                # Synthesize voiceovers
                scene_audio = await self._synthesize_scene_voiceovers(
                    scene_dialogues,
                    scene_id
                )
                
                total_synthesized += len(scene_audio)
                self.audio_metadata.extend(scene_audio)
                
                # Obtain BGM
                bgm_path = await self._obtain_scene_bgm(scene_id)
                
                # Compose scene (voice + BGM)
                await self._compose_scene_audio(scene_id, scene_audio, bgm_path)
            
            if not self.audio_metadata:
                return {
                    "status": "failure",
                    "error": "No audio files were generated",
                    "workflow_progress": self.planner.get_progress()
                }
            
            self.planner.mark_step_complete(
                self.planner.STEP_SYNTHESIZE_AUDIO,
                {"audio_files_generated": total_synthesized}
            )
            
            # Step 5: Create master audio track
            logger.info("Creating master audio track...")
            master_path = await self._create_master_audio_track()
            
            self.planner.mark_step_complete(
                self.planner.STEP_BUILD_MANIFEST,
                {"scene_compositions": len(self.scene_compositions)}
            )
            
            # Step 6: Save outputs
            timing_manifest = self._build_timing_manifest()
            manifest_path = self.run_manager.save_timing_manifest(timing_manifest)
            
            # Save BGM metadata
            bgm_summary = self.run_manager.save_bgm_metadata({
                "scenes": self.bgm_metadata,
                "total_scenes_with_bgm": len(self.bgm_metadata)
            })
            
            # Create comprehensive summary
            summary = {
                "workflow_id": f"phase2_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(scenes),
                "total_dialogues": len(self.audio_metadata),
                "total_scenes_with_bgm": len(self.bgm_metadata),
                "audio_output_dir": str(self.run_manager.get_audio_output_dir()),
                "master_audio_track": str(master_path) if master_path else None,
                "timing_manifest": str(manifest_path),
                "bgm_metadata": str(bgm_summary),
                "character_voices": self.voice_mapper.get_all_character_voices()
            }
            
            summary_path = self.run_manager.save_phase2_summary(summary)
            
            # Save config
            config = {
                "phase1_data_dir": str(self.phase1_data_dir),
                "freesound_api_available": bool(self.freesound_api_key),
                "ffmpeg_available": AudioComposer.has_ffmpeg(),
                "voice_mapper_config": {
                    "mappings": self.voice_mapper.get_all_character_voices()
                }
            }
            self.run_manager.save_phase2_config(config)
            
            self.planner.mark_step_complete(
                self.planner.STEP_SAVE_OUTPUTS,
                {
                    "summary": str(summary_path),
                    "manifest": str(manifest_path),
                    "bgm_metadata": str(bgm_summary)
                }
            )
            
            return {
                "status": "success",
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(scenes),
                "total_dialogues": len(self.audio_metadata),
                "audio_files_generated": len(self.audio_metadata),
                "scenes_with_bgm": len(self.bgm_metadata),
                "master_audio_track": str(master_path) if master_path else None,
                "output_directory": str(self.run_manager.current_run_dir),
                "character_voices_used": self.voice_mapper.get_all_character_voices(),
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
    
    def _build_timing_manifest(self) -> List[Dict]:
        """Build timing manifest with scene and BGM information."""
        timing_entries = []
        
        for audio in sorted(self.audio_metadata, key=lambda x: (x["scene_id"], x["line_index"])):
            scene_id = audio["scene_id"]
            
            entry = {
                "scene_id": scene_id,
                "speaker": audio["speaker"],
                "audio_file": audio["audio_file"],
                "duration_ms": audio["duration_ms"],
                "line_index": audio["line_index"],
                "text": audio["text"],
                "voice": audio["voice"],
                "bgm_used": scene_id in self.bgm_metadata,
                "bgm_info": self.bgm_metadata.get(scene_id)
            }
            
            timing_entries.append(entry)
        
        return timing_entries


async def run_enhanced_audio_agent(
    phase1_dir: str = "data/outputs/Phase1",
    phase2_dir: str = "data/outputs/Phase2",
    custom_voices: Optional[Dict[str, str]] = None,
    groq_client=None,
    freesound_api_key: Optional[str] = None,
    run_id: Optional[str] = None
) -> Dict:
    """
    Run the Enhanced Audio Agent for Phase 2.
    """
    agent = EnhancedAudioAgent(
        phase1_dir,
        phase2_dir,
        custom_voices,
        groq_client,
        freesound_api_key,
        run_id
    )
    return await agent.process()


if __name__ == "__main__":
    results = asyncio.run(run_enhanced_audio_agent())
    print(json.dumps(results, indent=2))
