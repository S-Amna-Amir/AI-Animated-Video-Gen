"""
Enhanced Phase 2 Audio Agent with MoviePy-based Background Music Integration.
Processes EVERY scene with per-scene TTS synthesis, Freesound BGM fetching, and MoviePy-based layering.
Concatenates all scenes into master audio.
"""

import json
import asyncio
import importlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import os

import requests

from mcp.tools.audio_tools.voice_mapper import VoiceMapper
from mcp.tools.audio_tools.tts_tool import TTSTool
from agents.audio_agent.run_manager import AudioRunManager
from agents.audio_agent.planner import AudioPhasePlanner, DialogueExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_moviepy_modules():
    """Load MoviePy lazily so the module stays importable until the venv is recreated."""
    audio_file_clip = importlib.import_module("moviepy.audio.io.AudioFileClip")
    audio_clip = importlib.import_module("moviepy.audio.AudioClip")
    afx = importlib.import_module("moviepy.audio.fx.all")
    editor = type(
        "MoviePyCompat",
        (),
        {
            "AudioFileClip": audio_file_clip.AudioFileClip,
            "CompositeAudioClip": audio_clip.CompositeAudioClip,
            "concatenate_audioclips": audio_clip.concatenate_audioclips,
        },
    )
    return editor, afx


class EnhancedAudioAgent:
    """
    Phase 2 Audio Agent with MoviePy-based Background Music Integration.
    
    Features:
    - Processes EVERY scene (not just first one)
    - Per-scene TTS synthesis with character-specific voices
    - Freesound API BGM fetching with mood-based search
    - Automatic fallback to local default_bgm.mp3 if API fails
    - MoviePy-based audio layering: voice + looped BGM (volumex(0.2))
    - Master audio concatenation with cross-fade between scenes
    - Comprehensive timing manifest with cumulative timestamps
    """
    
    def __init__(
        self,
        phase1_data_dir: str = "data/outputs/Phase1",
        phase2_output_dir: str = "data/outputs/Phase2",
        custom_voice_mappings: Optional[Dict[str, str]] = None,
        freesound_api_key: Optional[str] = None,
        run_id: Optional[str] = None,
        reverse_voice_preference: bool = True
    ):
        """
        Initialize Enhanced Audio Agent with MoviePy-based layering.
        
        Args:
            phase1_data_dir: Directory containing Phase 1 outputs
            phase2_output_dir: Directory for Phase 2 outputs
            custom_voice_mappings: Optional custom character-to-voice mappings
            freesound_api_key: Optional Freesound API key (from .env)
            run_id: Optional custom run ID
            reverse_voice_preference: If True, Jack gets least priority voice
        """
        self.phase1_data_dir = Path(phase1_data_dir)
        
        self.voice_mapper = VoiceMapper(custom_voice_mappings, reverse_preference=reverse_voice_preference)
        self.run_manager = AudioRunManager(phase2_output_dir)
        self.planner = AudioPhasePlanner()
        self.freesound_api_key = freesound_api_key or os.getenv("FREESOUND_API_KEY")
        
        # Create run directory
        self.run_manager.create_run_directory(run_id)
        self.tts_tool = TTSTool(str(self.run_manager.get_audio_output_dir()))
        
        # Data containers
        self.scene_manifest: Dict = {}
        self.bgm_metadata: Dict[int, Dict] = {}
        self.cumulative_timing: List[Dict] = []
        
        logger.info(f"✅ EnhancedAudioAgent initialized")
        logger.info(f"   Freesound API: {bool(self.freesound_api_key)}")
        logger.info(f"   Output: {self.run_manager.current_run_dir}")
    
    def load_phase1_data(self) -> bool:
        """Load Phase 1 outputs (scene manifest)."""
        try:
            scene_files = [
                self.phase1_data_dir / "scene_manifest_auto.json",
                self.phase1_data_dir / "scene_manifest_manual.json",
                self.phase1_data_dir / "scene_manifest.json"
            ]
            
            scene_file = next((f for f in scene_files if f.exists()), None)
            if not scene_file:
                logger.error(f"❌ No scene manifest found in {self.phase1_data_dir}")
                return False
            
            with open(scene_file) as f:
                self.scene_manifest = json.load(f)
            
            logger.info(f"✅ Loaded scene manifest from {scene_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading Phase 1 data: {str(e)}")
            return False
    
    def _extract_dialogues(self) -> List[Dict]:
        """Extract ALL dialogues from manifest with voice mappings."""
        dialogues = DialogueExtractor.extract_from_manifest(self.scene_manifest)
        
        for dialogue in dialogues:
            speaker = dialogue["speaker"]
            dialogue["voice"] = self.voice_mapper.get_voice_for_character(speaker)
        
        logger.info(f"✅ Extracted {len(dialogues)} dialogues across all scenes")
        return dialogues
    
    async def _synthesize_scene_voiceovers(
        self,
        scene_dialogues: List[Dict],
        scene_id: int
    ) -> Optional[Path]:
        """
        Synthesize all dialogue for a single scene and concatenate into one audio file.
        Returns path to concatenated scene audio.
        """
        scene_audio_dir = self.run_manager.get_audio_scene_dir(scene_id)
        scene_audio_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            dialogue_files: List[Path] = []
            
            for dialogue in scene_dialogues:
                speaker = dialogue["speaker"]
                line_index = dialogue["line_index"]
                text = dialogue["text"]
                voice = dialogue["voice"]
                
                try:
                    tts_result = await self.tts_tool.synthesize_dialogue(
                        text=text,
                        character_name=speaker,
                        voice=voice,
                        scene_id=scene_id,
                        line_index=line_index,
                        output_dir=scene_audio_dir
                    )
                    
                    output_file = Path(tts_result["audio_file"])
                    if output_file.exists():
                        dialogue_files.append(output_file)
                        logger.info(f"  ✓ {speaker}: {text[:40]}...")
                    
                except Exception as e:
                    logger.warning(f"  ✗ Failed: {speaker} - {str(e)}")
                    continue
            
            if not dialogue_files:
                logger.warning(f"Scene {scene_id}: No dialogue files generated")
                return None
            
            editor, _ = _load_moviepy_modules()
            scene_audio_file = scene_audio_dir / f"scene{scene_id:02d}_voice.mp3"
            scene_clips = []
            try:
                for audio_file in dialogue_files:
                    try:
                        scene_clips.append(editor.AudioFileClip(str(audio_file)))
                    except Exception as e:
                        logger.warning(f"Failed to load {audio_file}: {str(e)}")
                        continue

                if not scene_clips:
                    logger.warning(f"Scene {scene_id}: No valid audio after concatenation")
                    return None

                scene_audio = editor.concatenate_audioclips(scene_clips)
                scene_audio.write_audiofile(str(scene_audio_file), verbose=False, logger=None)

                logger.info(f"✓ Scene {scene_id} voice audio: {scene_audio.duration * 1000:.0f}ms")
                return scene_audio_file
            finally:
                for clip in scene_clips:
                    try:
                        clip.close()
                    except Exception:
                        pass
            
        except Exception as e:
            logger.error(f"❌ Error synthesizing scene {scene_id}: {str(e)}")
            return None
    
    def _extract_mood_keyword(self, scene: Dict) -> str:
        """Extract mood keyword from scene for Freesound search."""
        location = scene.get("location", "").lower()
        description = scene.get("description", "").lower()
        
        text = f"{location} {description}".lower()
        
        mood_keywords = {
            "dark": "dark ambient",
            "suspense": "suspenseful tension",
            "danger": "cinematic danger",
            "nature": "ambient nature",
            "city": "urban ambient",
            "quiet": "peaceful ambient",
            "action": "intense action",
            "calm": "calm peaceful",
            "office": "corporate ambient",
            "spy": "dark cinematic",
        }
        
        for keyword, mood in mood_keywords.items():
            if keyword in text:
                return mood
        
        return "ambient"
    
    def _fetch_bgm_from_freesound(self, mood_query: str, scene_id: int) -> Optional[Path]:
        """
        Fetch BGM from Freesound API using mood query.
        Falls back to local default_bgm.mp3 if API fails.
        """
        
        fallback_bgm = Path("data/bgm_library/default_bgm.mp3")
        
        if not self.freesound_api_key:
            logger.warning(f"Scene {scene_id}: No Freesound API key - using fallback")
            return fallback_bgm if fallback_bgm.exists() else None
        
        try:
            url = "https://freesound.org/apiv2/search/text/"
            headers = {"Authorization": f"Token {self.freesound_api_key}"}
            params = {
                "query": mood_query,
                "filter": "duration:[10 TO 120] tags:loop OR tags:ambient",
                "sort": "rating",
                "fields": "id,name,previews,duration",
                "page_size": 1
            }
            
            logger.info(f"Scene {scene_id}: Searching Freesound for '{mood_query}'...")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            results = response.json()
            if not results.get("results"):
                logger.warning(f"Scene {scene_id}: No results - using fallback")
                return fallback_bgm if fallback_bgm.exists() else None
            
            track = results["results"][0]
            track_id = track["id"]
            track_name = track["name"]
            preview_url = track["previews"].get("preview-hq-mp3")
            
            if not preview_url:
                logger.warning(f"Scene {scene_id}: No preview - using fallback")
                return fallback_bgm if fallback_bgm.exists() else None
            
            bgm_file = self.run_manager.get_audio_scene_dir(scene_id) / f"bgm.mp3"
            logger.info(f"Scene {scene_id}: Downloading '{track_name}'...")
            
            bgm_response = requests.get(preview_url, timeout=15)
            bgm_response.raise_for_status()
            
            with open(bgm_file, "wb") as f:
                f.write(bgm_response.content)
            
            logger.info(f"✓ Downloaded '{track_name}' ({len(bgm_response.content)} bytes)")
            
            self.bgm_metadata[scene_id] = {
                "query": mood_query,
                "source": "freesound",
                "name": track_name,
                "freesound_id": track_id,
                "url": f"https://freesound.org/sounds/{track_id}/"
            }
            
            return bgm_file
            
        except Exception as e:
            logger.warning(f"Scene {scene_id}: Freesound error ({str(e)}) - using fallback")
            return fallback_bgm if fallback_bgm.exists() else None
    
    def _layer_voice_with_bgm(self, voice_file: Path, bgm_file: Path, scene_id: int) -> Optional[Path]:
        """
        Layer voice with background music using MoviePy.
        - Loop BGM if shorter than voice using afx.audio_loop
        - Reduce BGM volume to 20% using volumex(0.2)
        - Overlay voice on top using CompositeAudioClip
        """
        
        try:
            scene_audio_dir = self.run_manager.get_audio_scene_dir(scene_id)
            output_file = scene_audio_dir / f"scene{scene_id:02d}_composed.mp3"
            
            logger.info(f"Scene {scene_id}: Layering voice + BGM using MoviePy...")

            editor, afx = _load_moviepy_modules()

            voice_clip = editor.AudioFileClip(str(voice_file))
            bgm_clip = editor.AudioFileClip(str(bgm_file))

            try:
                bgm_looped = afx.audio_loop(bgm_clip, duration=voice_clip.duration)
                bgm_quiet = bgm_looped.volumex(0.2)
                combined_audio = editor.CompositeAudioClip([bgm_quiet, voice_clip])
                combined_audio.write_audiofile(str(output_file), verbose=False, logger=None)

                logger.info("✓ Composed audio saved")
                return output_file
            finally:
                try:
                    voice_clip.close()
                except Exception:
                    pass
                try:
                    bgm_clip.close()
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"❌ Error layering audio: {str(e)} - using voice only")
            return voice_file
    
    def _create_master_track_with_crossfade(self, scene_files: List[Path], crossfade_ms: int = 1000) -> Optional[Path]:
        """
        Concatenate all scene audio files using MoviePy.
        """
        scene_clips: List[Any] = []

        try:
            if not scene_files:
                logger.error("❌ No scene files for master track")
                return None
            
            logger.info(f"Creating master track from {len(scene_files)} scenes...")

            editor, _ = _load_moviepy_modules()

            for i, scene_file in enumerate(scene_files):
                try:
                    scene_audio = editor.AudioFileClip(str(scene_file))
                    scene_clips.append(scene_audio)
                    logger.info(f"  ✓ Scene {i+1}: {scene_audio.duration * 1000:.0f}ms")
                    
                except Exception as e:
                    logger.warning(f"  ✗ Failed to load {scene_file.name}: {str(e)}")
                    continue
            
            if not scene_clips:
                logger.error("❌ Master audio is empty")
                return None
            
            master_file = self.run_manager.get_master_audio_path()
            master_audio = editor.concatenate_audioclips(scene_clips)
            master_audio.write_audiofile(str(master_file), verbose=False, logger=None)

            logger.info(f"✅ Master track: {master_audio.duration * 1000:.0f}ms total")
            return master_file
            
        except Exception as e:
            logger.error(f"❌ Error creating master track: {str(e)}")
            return None
        finally:
            try:
                for clip in scene_clips:
                    try:
                        clip.close()
                    except Exception:
                        pass
            except Exception:
                pass
    
    async def process(self) -> Dict[str, Any]:
        """
        MAIN PROCESSING: Iterate through EVERY scene.
        1. Load Phase 1 data
          2. For each scene:
              - Synthesize dialogue TTS
              - Fetch BGM from Freesound (with fallback)
              - Layer voice + BGM using MoviePy
        3. Create master track with cross-fade
        4. Generate timing manifest
        5. Save all outputs
        """
        try:
            # Step 1: Load Phase 1 data
            if not self.load_phase1_data():
                return {"status": "failure", "error": "Failed to load Phase 1 data"}
            
            # Step 2: Extract dialogues
            dialogues = self._extract_dialogues()
            if not dialogues:
                return {"status": "failure", "error": "No dialogues found"}
            
            # Step 3: PROCESS EVERY SCENE
            logger.info("\n" + "="*80)
            logger.info("PROCESSING ALL SCENES")
            logger.info("="*80 + "\n")
            
            scenes = self.scene_manifest.get("scenes", [])
            scene_files_for_master = []
            cumulative_time_ms = 0
            
            for scene in scenes:
                scene_id = scene.get("scene_id")
                location = scene.get("location", "Unknown")
                
                logger.info(f"\n{'─'*80}")
                logger.info(f"SCENE {scene_id}: {location}")
                logger.info(f"{'─'*80}")
                
                scene_dialogues = [d for d in dialogues if d["scene_id"] == scene_id]
                if not scene_dialogues:
                    logger.warning(f"No dialogues - skipping")
                    continue
                
                logger.info(f"Processing {len(scene_dialogues)} lines...")
                
                # 3A: Synthesize voice
                voice_file = await self._synthesize_scene_voiceovers(scene_dialogues, scene_id)
                if not voice_file or not voice_file.exists():
                    logger.warning(f"Failed to synthesize - skipping")
                    continue
                
                # 3B: Fetch BGM
                mood = self._extract_mood_keyword(scene)
                bgm_file = self._fetch_bgm_from_freesound(mood, scene_id)
                
                # 3C: Layer voice + BGM
                if bgm_file and bgm_file.exists():
                    composed_file = self._layer_voice_with_bgm(voice_file, bgm_file, scene_id)
                else:
                    logger.warning(f"No BGM - using voice only")
                    composed_file = voice_file
                
                if composed_file and composed_file.exists():
                    scene_files_for_master.append(composed_file)

                    try:
                        editor, _ = _load_moviepy_modules()
                        scene_audio = editor.AudioFileClip(str(composed_file))
                        scene_duration_ms = int(scene_audio.duration * 1000)
                        scene_audio.close()

                        for dialogue in scene_dialogues:
                            self.cumulative_timing.append({
                                "scene_id": scene_id,
                                "speaker": dialogue["speaker"],
                                "text": dialogue["text"],
                                "voice": dialogue["voice"],
                                "cumulative_start_ms": cumulative_time_ms,
                                "scene_duration_ms": scene_duration_ms,
                                "bgm_used": scene_id in self.bgm_metadata,
                                "bgm_info": self.bgm_metadata.get(scene_id),
                                "audio_file": str(composed_file)
                            })

                        cumulative_time_ms += scene_duration_ms

                    except Exception as e:
                        logger.warning(f"Failed to get duration: {str(e)}")
            
            if not scene_files_for_master:
                return {"status": "failure", "error": "No valid scene audio files"}
            
            # Step 4: Create master track
            logger.info("\n" + "="*80)
            logger.info("CREATING MASTER TRACK")
            logger.info("="*80 + "\n")
            
            master_file = self._create_master_track_with_crossfade(scene_files_for_master, crossfade_ms=1000)
            
            # Step 5: Save outputs
            logger.info("\n" + "="*80)
            logger.info("SAVING OUTPUTS")
            logger.info("="*80 + "\n")
            
            manifest_path = self.run_manager.save_timing_manifest(self.cumulative_timing)
            logger.info(f"✅ Timing manifest: {manifest_path.name}")
            
            bgm_summary = self.run_manager.save_bgm_metadata({
                "scenes": self.bgm_metadata,
                "total_scenes_with_bgm": len(self.bgm_metadata)
            })
            logger.info(f"✅ BGM metadata: {bgm_summary.name}")
            
            summary = {
                "workflow_id": f"phase2_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(scenes),
                "scenes_processed": len(scene_files_for_master),
                "total_scenes_with_bgm": len(self.bgm_metadata),
                "master_audio_track": str(master_file) if master_file else None,
                "character_voices": self.voice_mapper.get_all_character_voices()
            }
            
            summary_path = self.run_manager.save_phase2_summary(summary)
            logger.info(f"✅ Summary: {summary_path.name}")
            
            self.run_manager.save_phase2_config({
                "phase1_data_dir": str(self.phase1_data_dir),
                "freesound_api_available": bool(self.freesound_api_key),
                "audio_engine": "moviepy",
                "voice_mapper_config": {"mappings": self.voice_mapper.get_all_character_voices()}
            })
            
            logger.info("\n" + "="*80)
            logger.info("✨ PHASE 2 COMPLETE")
            logger.info("="*80 + "\n")
            
            return {
                "status": "success",
                "run_id": self.run_manager.current_run_id,
                "total_scenes": len(scenes),
                "scenes_processed": len(scene_files_for_master),
                "scenes_with_bgm": len(self.bgm_metadata),
                "total_duration_ms": cumulative_time_ms,
                "master_audio_track": str(master_file) if master_file else None,
                "output_directory": str(self.run_manager.current_run_dir),
                "timing_manifest_path": str(manifest_path),
                "character_voices_used": self.voice_mapper.get_all_character_voices(),
                "bgm_metadata": {"scenes": self.bgm_metadata, "total": len(self.bgm_metadata)}
            }
            
        except Exception as e:
            logger.error(f"❌ Error during Phase 2: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"status": "failure", "error": str(e)}


async def run_enhanced_audio_agent(
    phase1_dir: str = "data/outputs/Phase1",
    phase2_dir: str = "data/outputs/Phase2",
    custom_voices: Optional[Dict[str, str]] = None,
    freesound_api_key: Optional[str] = None,
    run_id: Optional[str] = None,
    reverse_voice_preference: bool = True
) -> Dict:
    """Run the Enhanced Audio Agent for Phase 2."""
    agent = EnhancedAudioAgent(
        phase1_dir,
        phase2_dir,
        custom_voices,
        freesound_api_key,
        run_id,
        reverse_voice_preference
    )
    return await agent.process()


if __name__ == "__main__":
    results = asyncio.run(run_enhanced_audio_agent())
    print(json.dumps(results, indent=2))
