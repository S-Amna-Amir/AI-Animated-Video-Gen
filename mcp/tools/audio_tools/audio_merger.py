"""
mcp/tools/audio_tools/audio_merger.py
----------------------------------------
FFmpeg-based audio utilities: merge WAV files, compose voice + BGM.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def get_audio_duration_seconds(path: str) -> Optional[float]:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return float(r.stdout.strip())
    except Exception:
        pass
    return None


def concatenate_audio_files(audio_files: List[str], output_file: str) -> bool:
    """Concatenate MP3/WAV files using ffmpeg concat demuxer."""
    if not audio_files or not _has_ffmpeg():
        return False
    concat_list = Path(output_file).parent / "_concat_list.txt"
    try:
        with open(concat_list, "w") as f:
            for p in audio_files:
                f.write(f"file '{Path(p).resolve()}'\n")
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_list), "-c", "copy", output_file],
            capture_output=True, text=True, timeout=120,
        )
        return r.returncode == 0
    except Exception as e:
        logger.error(f"[AudioMerger] Concatenation failed: {e}")
        return False
    finally:
        concat_list.unlink(missing_ok=True)


def compose_voice_with_bgm(
    voice_file: str,
    bgm_file: str,
    output_file: str,
    bgm_volume_db: float = -20.0,
    fade_sec: float = 0.5,
) -> bool:
    """Mix voice + BGM (ducked) using ffmpeg filter_complex."""
    if not _has_ffmpeg():
        shutil.copy(voice_file, output_file)
        return True
    try:
        voice_dur = get_audio_duration_seconds(voice_file)
        bgm_dur = get_audio_duration_seconds(bgm_file)
        if not voice_dur:
            return False

        if bgm_dur and bgm_dur < voice_dur:
            loops = int(voice_dur / bgm_dur) + 2
            bgm_part = f"[0:a]aloop=loop={loops}[bl];"
            bgm_input = "[bl]"
        else:
            bgm_part = ""
            bgm_input = "[0:a]"

        fade_out_st = max(0, voice_dur - fade_sec)
        filt = (
            f"{bgm_part}"
            f"{bgm_input}afade=t=in:st=0:d={fade_sec}[bi];"
            f"[bi]afade=t=out:st={fade_out_st}:d={fade_sec}[bf];"
            f"[bf]volume={bgm_volume_db}dB[bd];"
            f"[1:a][bd]amix=inputs=2:duration=first[aout]"
        )
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", bgm_file, "-i", voice_file,
             "-filter_complex", filt, "-map", "[aout]", "-q:a", "0", output_file],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            logger.error(f"[AudioMerger] ffmpeg error: {r.stderr[-300:]}")
            shutil.copy(voice_file, output_file)
        return True
    except Exception as e:
        logger.error(f"[AudioMerger] compose failed: {e}")
        shutil.copy(voice_file, output_file)
        return False
