"""
Audio Composition Tool - Mixes voice and background music with ducking.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AudioComposer:
    """
    Composes voice and background music using FFmpeg.
    Applies ducking, fading, and mixing.
    """
    
    @staticmethod
    def has_ffmpeg() -> bool:
        """
        Check if FFmpeg is available on the system.
        
        Returns:
            True if FFmpeg is available
        """
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def get_audio_duration(audio_path: str) -> Optional[float]:
        """
        Get duration of an audio file in seconds using FFprobe.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Duration in seconds or None if retrieval fails
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"FFprobe error: {str(e)}")
        
        return None
    
    @staticmethod
    def compose_voice_with_bgm(
        voice_file: str,
        bgm_file: str,
        output_file: str,
        bgm_volume_db: float = -20.0,
        fade_duration_ms: int = 500
    ) -> bool:
        """
        Mix voice audio with background music.
        Applies volume ducking to BGM (-20dB) and fade-in/fade-out.
        
        Args:
            voice_file: Path to voice audio
            bgm_file: Path to background music audio
            output_file: Path for output mixed audio
            bgm_volume_db: BGM volume reduction in dB (negative value)
            fade_duration_ms: Fade-in/fade-out duration in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        if not AudioComposer.has_ffmpeg():
            logger.error("FFmpeg not available for audio composition")
            return False
        
        try:
            # Get voice duration
            voice_duration = AudioComposer.get_audio_duration(voice_file)
            if voice_duration is None:
                logger.error(f"Could not get duration of {voice_file}")
                return False
            
            # Get BGM duration
            bgm_duration = AudioComposer.get_audio_duration(bgm_file)
            if bgm_duration is None:
                logger.warning(f"Could not get BGM duration, will loop as needed")
                bgm_duration = voice_duration
            
            # Convert fade duration to seconds
            fade_sec = fade_duration_ms / 1000.0
            
            # Build FFmpeg filter complex
            # 1. Loop BGM if it's shorter than voice
            # 2. Apply fade-in to BGM
            # 3. Apply fade-out to BGM
            # 4. Apply volume ducking to BGM
            # 5. Mix voice and BGM
            
            if bgm_duration < voice_duration:
                # Need to loop BGM
                loop_count = int(voice_duration / bgm_duration) + 2
                bgm_filter = (
                    f"[bgm_in]aloop=loop={loop_count}[bgm_looped];"
                    f"[bgm_looped]afade=t=in:st=0:d={fade_sec}[bgm_fade_in];"
                    f"[bgm_fade_in]afade=t=out:st={voice_duration - fade_sec}:d={fade_sec}[bgm_faded];"
                    f"[bgm_faded]volume={bgm_volume_db}dB[bgm_ducked]"
                )
            else:
                # BGM is long enough
                bgm_filter = (
                    f"[bgm_in]afade=t=in:st=0:d={fade_sec}[bgm_fade_in];"
                    f"[bgm_fade_in]afade=t=out:st={voice_duration - fade_sec}:d={fade_sec}[bgm_faded];"
                    f"[bgm_faded]volume={bgm_volume_db}dB[bgm_ducked]"
                )
            
            filter_complex = (
                f"[0:a]{bgm_filter};"
                f"[1:a][bgm_ducked]amix=inputs=2:duration=first[aout]"
            )
            
            command = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-i", bgm_file,  # Input 0: BGM
                "-i", voice_file,  # Input 1: Voice
                "-filter_complex", filter_complex,
                "-map", "[aout]",
                "-q:a", "0",  # High quality
                output_file
            ]
            
            logger.info(f"Composing audio: {Path(output_file).name}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
            
            logger.info(f"Audio composition successful: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error composing audio: {str(e)}")
            return False
    
    @staticmethod
    def concatenate_audio_files(
        audio_files: list,
        output_file: str,
        format: str = "mp3"
    ) -> bool:
        """
        Concatenate multiple audio files into one.
        
        Args:
            audio_files: List of audio file paths in order
            output_file: Path for concatenated output
            format: Audio format (mp3, wav, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if not AudioComposer.has_ffmpeg():
            logger.error("FFmpeg not available for concatenation")
            return False
        
        if not audio_files:
            logger.error("No audio files provided for concatenation")
            return False
        
        try:
            # Create concat demuxer file
            concat_file = Path(output_file).parent / "concat_list.txt"
            
            with open(concat_file, 'w') as f:
                for audio_file in audio_files:
                    # Escape special characters in file path
                    safe_path = str(Path(audio_file).resolve())
                    f.write(f"file '{safe_path}'\n")
            
            command = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                output_file
            ]
            
            logger.info(f"Concatenating {len(audio_files)} audio files...")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            # Clean up concat file
            try:
                concat_file.unlink()
            except:
                pass
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return False
            
            logger.info(f"Concatenation successful: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error concatenating audio: {str(e)}")
            return False


def compose_voice_with_fallback_bgm(
    voice_file: str,
    bgm_file: Optional[str],
    output_file: str
) -> bool:
    """
    Compose voice with BGM, or just copy voice if BGM unavailable.
    
    Args:
        voice_file: Path to voice audio
        bgm_file: Path to BGM or None
        output_file: Path for output
        
    Returns:
        True if successful, False otherwise
    """
    if not bgm_file or not Path(bgm_file).exists():
        # Just copy voice as output
        logger.warning(f"BGM unavailable, using voice only: {output_file}")
        try:
            import shutil
            shutil.copy(voice_file, output_file)
            return True
        except Exception as e:
            logger.error(f"Error copying voice: {str(e)}")
            return False
    
    # Compose voice with BGM
    return AudioComposer.compose_voice_with_bgm(
        voice_file,
        bgm_file,
        output_file
    )
