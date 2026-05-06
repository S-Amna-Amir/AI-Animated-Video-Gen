"""Compose final Phase 3 video from scene clips and timing manifest."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips, vfx
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

logger = logging.getLogger(__name__)


def load_timing_manifest(manifest_path: str) -> list[dict[str, Any]]:
    """
    Load raw timing manifest JSON without deduplication.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Timing manifest not found: {manifest_path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in timing manifest: {manifest_path}") from exc

    if not isinstance(data, list):
        raise ValueError("Timing manifest must be a JSON list")

    return data


def add_subtitle_overlay(clip: VideoFileClip, text: str, duration: float) -> CompositeVideoClip:
    """
    Add a subtitle overlay using MoviePy TextClip.
    """
    if not text:
        return clip

    try:
        txt_clip = TextClip(
            font="Arial", 
            text=text, 
            font_size=28, 
            color="white", 
            stroke_color="black", 
            stroke_width=2,
            method="caption",
            size=(clip.w - 40, None)
        )
        txt_clip = txt_clip.with_position(("center", clip.h - 60)).with_duration(duration)
        return CompositeVideoClip([clip, txt_clip])
    except Exception as exc:
        logger.warning("Failed to add subtitle overlay: %s", exc)
        return clip


def build_scene_clip(scene_id: str, clip_path: str, manifest_entry: dict[str, Any]) -> VideoFileClip:
    """
    Load a clip and apply duration and subtitle overlay if needed.
    """
    if not clip_path or not Path(clip_path).exists():
        raise FileNotFoundError(f"Clip not found: {clip_path}")
        
    duration_ms = float(manifest_entry.get("duration_ms", 5000))
    duration_seconds = duration_ms / 1000.0
    
    clip = VideoFileClip(clip_path).with_duration(duration_seconds)
    return clip
def compose_final_video(
    scene_clips_map: dict[str, str],
    dialogue_results: list[dict[str, Any]],
    output_path: str,
    use_transitions: bool = True,
    use_subtitles: bool = True,
) -> str:
    """
    Compose final video from per-dialogue clips.
    """
    # Group results by scene
    scene_groups = defaultdict(list)
    for result in dialogue_results:
        scene_groups[str(result["scene_id"])].append(result)

    sorted_scene_ids = sorted(scene_groups.keys(), key=lambda k: int(k))
    final_clips: list[VideoFileClip] = []
    
    try:
        for scene_id in sorted_scene_ids:
            scene_lines = sorted(scene_groups[scene_id], key=lambda x: int(x["line_index"]))
            scene_video_clips = []
            
            # Use the audio length to calculate perfect per_line_duration
            audio_file = scene_lines[0].get("audio_file", "")
            audio_clip = None
            scene_duration_ms = float(scene_lines[0].get("duration_ms", 5000)) * len(scene_lines)
            
            if audio_file and Path(audio_file).exists():
                audio_clip = AudioFileClip(audio_file).with_duration(scene_duration_ms / 1000.0)
                scene_duration_ms = audio_clip.duration * 1000.0
                
            per_line_duration_seconds = (scene_duration_ms / len(scene_lines)) / 1000.0
            
            for result in scene_lines:
                line_index = result["line_index"]
                clip_key = f"{scene_id}_{line_index}"
                clip_path = scene_clips_map.get(clip_key, "")

                if not clip_path:
                    logger.warning("Skipping clip %s because path is missing", clip_key)
                    continue

                line_duration_ms = result.get("duration_ms")
                if line_duration_ms:
                    line_duration_seconds = float(line_duration_ms) / 1000.0
                else:
                    line_duration_seconds = per_line_duration_seconds

                clip = VideoFileClip(clip_path).with_duration(line_duration_seconds)
                
                # Removed old MoviePy subtitle overlay
                    
                scene_video_clips.append(clip)
            
            if not scene_video_clips:
                continue
                
            # Concatenate all lines for this scene into one scene clip
            scene_clip = concatenate_videoclips(scene_video_clips, method="compose")
            
            if audio_clip:
                scene_clip = scene_clip.with_audio(audio_clip)
                # Ensure the scene clip duration exactly matches the audio duration
                scene_clip = scene_clip.with_duration(audio_clip.duration)
                logger.info("Scene %s: %d images x %.2fs = %.2fs audio", scene_id, len(scene_lines), per_line_duration_seconds, audio_clip.duration)
            else:
                logger.warning("Audio missing for scene_id=%s, exporting scene as silent", scene_id)
                logger.info("Scene %s: %d images x %.2fs = %.2fs", scene_id, len(scene_lines), per_line_duration_seconds, scene_clip.duration)
                
            if use_transitions and final_clips:
                scene_clip = scene_clip.with_effects([vfx.CrossFadeIn(0.4)])
                
            final_clips.append(scene_clip)

        if not final_clips:
            raise RuntimeError("No scene clips available to compose final video")

        # Validate timing
        total_video_duration = sum(c.duration for c in final_clips)
        logger.info("Total composed video duration approx %.2fs", total_video_duration)

        final_video = concatenate_videoclips(final_clips, method="compose")
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Writing final video to %s", output_file)
        final_video.write_videofile(
            str(output_file), 
            fps=24, 
            codec="libx264",
            audio_codec="aac",
            bitrate="4000k",
            audio_bitrate="192k",
            temp_audiofile="temp_audio.m4a",
            remove_temp=True,
            logger=None,
            threads=2
        )
        final_video.close()
        
        # Apply strict subtitles using ffmpeg if requested
        if use_subtitles:
            try:
                from .subtitle_generator import burn_captions
                # Write dialogue_results to a temp manifest
                temp_manifest_path = output_file.parent / "temp_subtitle_manifest.json"
                # Dialogue results have start_ms and duration_ms
                manifest_data = []
                for res in dialogue_results:
                    start = int(res.get("start_ms", 0))
                    duration = float(res.get("duration_ms", 0))
                    manifest_data.append({
                        "speaker": res.get("speaker", ""),
                        "text": res.get("text", ""),
                        "start_ms": start,
                        "end_ms": int(start + duration),
                        "scene_id": res.get("scene_id", "")
                    })
                    
                with open(temp_manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest_data, f)
                    
                captioned_output = burn_captions(str(temp_manifest_path), str(output_file))
                
                # We return the captioned output
                # Clean up temp manifest
                temp_manifest_path.unlink(missing_ok=True)
                return captioned_output
            except Exception as e:
                logger.error(f"Subtitle burning failed: {e}")
                # Fallback to uncaptioned video
                return str(output_file)

        return str(output_file)
    finally:
        for clip in final_clips:
            try:
                clip.close()
            except Exception:
                pass
