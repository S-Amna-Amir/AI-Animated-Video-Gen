"""
TTS Tool - Edge-TTS integration for high-quality audio synthesis.
Generates individual dialogue audio files with character-specific voices.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import edge_tts
import logging

logger = logging.getLogger(__name__)


class TTSTool:
    """
    Handles text-to-speech synthesis using Microsoft Edge-TTS.
    Generates individual audio files for each dialogue line.
    """
    
    def __init__(self, output_base_path: str = "data/outputs/Phase2"):
        """
        Initialize the TTS tool.
        
        Args:
            output_base_path: Base directory for audio output
        """
        self.output_base_path = Path(output_base_path)
        self.output_base_path.mkdir(parents=True, exist_ok=True)
    
    async def synthesize_dialogue(
        self,
        text: str,
        character_name: str,
        voice: str,
        scene_id: int,
        line_index: int,
        output_dir: Path
    ) -> Dict:
        """
        Synthesize a single dialogue line to audio file.
        Saves to scene subdirectory structure.
        
        Args:
            text: The dialogue text to synthesize
            character_name: Name of the speaking character
            voice: Edge-TTS voice (e.g., "en-US-GuyNeural")
            scene_id: Scene identifier
            line_index: Index of this line within the scene
            output_dir: Base directory for audio output (will create scene subdirs)
            
        Returns:
            Dict with audio metadata:
            {
                "speaker": character_name,
                "scene_id": scene_id,
                "line_index": line_index,
                "audio_file": path_to_file,
                "duration_ms": duration_in_milliseconds,
                "text": dialogue_text
            }
        """
        try:
            # Create scene-specific output directory
            scene_dir = output_dir / f"scene{scene_id:02d}"
            scene_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            safe_char_name = character_name.replace(" ", "_").upper()
            filename = f"{safe_char_name}_line{line_index:03d}.mp3"
            filepath = scene_dir / filename
            
            # Clean text - remove excess quotes and newlines
            clean_text = text.strip().strip('"').strip("'")
            
            logger.info(f"Synthesizing: {character_name} (Scene {scene_id}, Line {line_index})")
            logger.info(f"Voice: {voice} | Text: {clean_text[:60]}...")
            
            # Use Edge-TTS to synthesize
            communicate = edge_tts.Communicate(clean_text, voice)
            await communicate.save(str(filepath))
            
            # Get audio duration in milliseconds
            duration_ms = self._get_audio_duration_ms(str(filepath))
            
            logger.info(f"Generated: {filename} (Duration: {duration_ms}ms)")
            
            return {
                "speaker": character_name,
                "scene_id": scene_id,
                "line_index": line_index,
                "audio_file": str(filepath),
                "duration_ms": duration_ms,
                "text": clean_text,
                "voice": voice,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error synthesizing dialogue for {character_name}: {str(e)}")
            raise
    
    @staticmethod
    def _get_audio_duration_ms(filepath: str) -> int:
        """
        Get the duration of an audio file in milliseconds.
        Uses ffprobe if available, otherwise estimates based on text length.
        
        Args:
            filepath: Path to the audio file
            
        Returns:
            Duration in milliseconds (int)
        """
        try:
            # Try using ffprobe (from FFmpeg)
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                    filepath
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                try:
                    duration_seconds = float(result.stdout.strip())
                    return int(duration_seconds * 1000)
                except (ValueError, AttributeError):
                    pass
        
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Fallback: try using mediainfo if available
        try:
            result = subprocess.run(
                ["mediainfo", "--Inform=General;%Duration%", filepath],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                try:
                    duration_ms = int(result.stdout.strip())
                    return duration_ms
                except (ValueError, AttributeError):
                    pass
        
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Final fallback: estimate duration from file size
        # MP3 typically encodes at about 128 kbps, estimate 16 kbps per second
        try:
            file_size_bytes = os.path.getsize(filepath)
            # Rough estimate: 128 kbps = 16 KB/s, so size_in_kb / 16 = seconds
            estimated_seconds = (file_size_bytes / 1024) / 16
            return max(1000, int(estimated_seconds * 1000))  # At least 1 second
        except Exception as e:
            logger.warning(f"Could not estimate duration: {str(e)}")
            return 1000  # Default to 1 second if all else fails
    
    async def synthesize_batch(
        self,
        dialogues: List[Dict],
        output_dir: Path
    ) -> List[Dict]:
        """
        Synthesize multiple dialogue lines in batch.
        
        Args:
            dialogues: List of dialogue dicts with keys:
                      {speaker, text, voice, scene_id, line_index}
            output_dir: Directory to save audio files
            
        Returns:
            List of audio metadata dicts
        """
        results = []
        for dialogue in dialogues:
            try:
                result = await self.synthesize_dialogue(
                    text=dialogue["text"],
                    character_name=dialogue["speaker"],
                    voice=dialogue["voice"],
                    scene_id=dialogue["scene_id"],
                    line_index=dialogue["line_index"],
                    output_dir=output_dir
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to synthesize dialogue: {str(e)}")
                continue
        
        return results


def run_tts_synthesis(
    dialogues: List[Dict],
    output_dir: str = "data/outputs/Phase2/audio"
) -> List[Dict]:
    """
    Synchronous wrapper to run TTS synthesis using asyncio.
    
    Args:
        dialogues: List of dialogue dicts to synthesize
        output_dir: Directory to save audio files
        
    Returns:
        List of audio metadata dicts
    """
    tool = TTSTool()
    output_path = Path(output_dir)
    
    # Run async synthesis
    results = asyncio.run(tool.synthesize_batch(dialogues, output_path))
    
    return results
