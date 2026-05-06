import json
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT time format (HH:MM:SS,mmm)."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def get_video_duration_ms(video_path: str) -> int:
    """Get video duration in milliseconds using MoviePy."""
    try:
        from moviepy import VideoFileClip
        with VideoFileClip(video_path) as clip:
            duration_seconds = clip.duration
        return int(duration_seconds * 1000)
    except Exception as e:
        logger.error(f"Failed to get video duration: {e}")
        # Default to a very large number if we can't determine it
        return 999999999

def generate_srt(manifest_path: str, video_duration_ms: int, output_srt_path: str) -> str:
    """Generate an SRT file based on the timing manifest."""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
        
    srt_lines = []
    subtitle_index = 1
    
    # We must ensure one caption on screen at a time, never overlap
    # We will sort by start_ms just in case
    
    valid_entries = []
    for entry in manifest:
        text = entry.get("text", "").strip()
        if not text:
            continue
            
        start_ms = int(entry.get("start_ms", 0))
        # Support duration_ms or end_ms
        if "end_ms" in entry:
            end_ms = int(entry["end_ms"])
        elif "duration_ms" in entry:
            end_ms = start_ms + int(entry["duration_ms"])
        else:
            continue
            
        if start_ms >= video_duration_ms:
            continue
            
        if end_ms > video_duration_ms:
            end_ms = video_duration_ms - 50
            
        if end_ms <= start_ms:
            continue
            
        valid_entries.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "speaker": entry.get("speaker", "")
        })
        
    # Sort entries by start_ms
    valid_entries.sort(key=lambda x: x["start_ms"])
    
    # Fix overlaps
    for i in range(len(valid_entries) - 1):
        if valid_entries[i]["end_ms"] > valid_entries[i+1]["start_ms"]:
            valid_entries[i]["end_ms"] = valid_entries[i+1]["start_ms"] - 1
            
    for entry in valid_entries:
        start_time_str = ms_to_srt_time(entry["start_ms"])
        end_time_str = ms_to_srt_time(entry["end_ms"])
        
        srt_lines.append(str(subtitle_index))
        srt_lines.append(f"{start_time_str} --> {end_time_str}")
        srt_lines.append(entry["text"])
        srt_lines.append("")
        
        subtitle_index += 1
        
    with open(output_srt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(srt_lines))
        
    return output_srt_path

def escape_path_for_ffmpeg(path: str) -> str:
    """Escape path specifically for the FFmpeg subtitles filter."""
    # FFmpeg's subtitles filter requires escaping colons and backslashes
    path = path.replace('\\', '/')
    path = path.replace(':', '\\:')
    # Single quotes need to be escaped in some shells but since we pass as list it's usually fine
    return path

def burn_captions(manifest_path: str, video_path: str) -> str:
    """
    Burn subtitles into the video using FFmpeg.
    Output is saved to same directory as video_path with _captioned suffix.
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
        
    video_path_obj = Path(video_path)
    output_path = video_path_obj.parent / f"{video_path_obj.stem}_captioned{video_path_obj.suffix}"
    
    # Get video duration
    video_duration_ms = get_video_duration_ms(video_path)
    
    # Generate SRT
    srt_path = video_path_obj.parent / "temp_captions.srt"
    generate_srt(manifest_path, video_duration_ms, str(srt_path))
    
    logger.info(f"Generated SRT at {srt_path}")
    
    # Burn subtitles using FFmpeg
    # subtitles filter syntax: subtitles='filename.srt'
    # we need to ensure the path is correctly formatted for ffmpeg
    escaped_srt_path = escape_path_for_ffmpeg(str(srt_path))
    # Apply better styling: FontSize=20, Alignment=2 (Bottom Center), MarginV=30 (higher from bottom)
    style = "FontSize=20,Alignment=2,MarginV=30,Outline=2,Shadow=1,FontName=Arial"
    filter_arg = f"subtitles='{escaped_srt_path}':force_style='{style}'"
    
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    command = [
        ffmpeg_exe,
        "-y",
        "-i", video_path,
        "-vf", filter_arg,
        "-c:a", "copy",          # Do not re-encode audio
        "-c:v", "libx264",       # Encode video to burn subtitles
        "-preset", "slow",
        "-crf", "18",
        str(output_path)
    ]
    
    logger.info(f"Running FFmpeg to burn captions...")
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg failed:\n{result.stderr}")
        raise RuntimeError(f"FFmpeg captioning failed: {result.stderr}")
        
    logger.info(f"Captioned video saved to {output_path}")
    
    # Cleanup
    if srt_path.exists():
        srt_path.unlink()
        
    return str(output_path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Burn subtitles into video.")
    parser.add_argument("--manifest", required=True, help="Path to timing_manifest.json")
    parser.add_argument("--video", required=True, help="Path to final_output.mp4")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    burn_captions(args.manifest, args.video)
