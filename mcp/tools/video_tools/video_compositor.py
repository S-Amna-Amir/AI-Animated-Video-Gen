"""
mcp/tools/video_tools/video_compositor.py
-------------------------------------------
Composes final video from per-dialogue clips + audio via MoviePy.
Optional: burns subtitles via FFmpeg after composition.
"""
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips, vfx

logger = logging.getLogger(__name__)


def load_timing_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Timing manifest not found: {manifest_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Timing manifest must be a JSON list")
    return data


def compose_final_video(
    scene_clips_map: Dict[str, str],
    dialogue_results: List[Dict[str, Any]],
    output_path: str,
    use_transitions: bool = True,
    use_subtitles: bool = False,
) -> str:
    scene_groups: Dict[str, List] = defaultdict(list)
    for r in dialogue_results:
        scene_groups[str(r["scene_id"])].append(r)

    sorted_ids  = sorted(scene_groups.keys(), key=lambda k: int(k) if k.isdigit() else k)
    final_clips: List[VideoFileClip] = []

    try:
        for scene_id in sorted_ids:
            lines = sorted(scene_groups[scene_id], key=lambda x: int(x["line_index"]))
            scene_video_clips: List[VideoFileClip] = []

            audio_file     = lines[0].get("audio_file", "")
            audio_clip     = None
            scene_dur_ms   = sum(float(l.get("duration_ms", 5000)) for l in lines)

            if audio_file and Path(audio_file).exists():
                audio_clip   = AudioFileClip(audio_file)
                scene_dur_ms = audio_clip.duration * 1000.0

            per_line_sec = (scene_dur_ms / len(lines)) / 1000.0

            for r in lines:
                key       = f"{scene_id}_{r['line_index']}"
                clip_path = scene_clips_map.get(key, "")
                if not clip_path or not Path(clip_path).exists():
                    logger.warning("Missing clip %s, skipping", key)
                    continue
                line_sec = float(r.get("duration_ms", per_line_sec * 1000)) / 1000.0
                try:
                    clip = VideoFileClip(clip_path).with_duration(line_sec)
                    scene_video_clips.append(clip)
                except Exception as e:
                    logger.warning("Cannot load clip %s: %s", clip_path, e)

            if not scene_video_clips:
                continue

            scene_clip = concatenate_videoclips(scene_video_clips, method="compose")
            if audio_clip:
                scene_clip = scene_clip.with_audio(audio_clip).with_duration(audio_clip.duration)
            if use_transitions and final_clips:
                scene_clip = scene_clip.with_effects([vfx.CrossFadeIn(0.4)])
            final_clips.append(scene_clip)

        if not final_clips:
            raise RuntimeError("No clips available for composition")

        final_video = concatenate_videoclips(final_clips, method="compose")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Writing final video → %s (%.1fs)", out, final_video.duration)
        final_video.write_videofile(
            str(out), fps=24, codec="libx264", audio_codec="aac",
            bitrate="4000k", audio_bitrate="192k",
            temp_audiofile="temp_audio.m4a", remove_temp=True,
            logger=None, threads=2,
        )
        final_video.close()

        if use_subtitles:
            try:
                from .subtitle_generator import burn_captions
                temp_manifest = out.parent / "temp_subtitle_manifest.json"
                manifest_data = [
                    {
                        "speaker": r.get("speaker", ""), "text": r.get("text", ""),
                        "start_ms": int(r.get("start_ms", 0)),
                        "end_ms":   int(r.get("start_ms", 0) + r.get("duration_ms", 0)),
                        "scene_id": r.get("scene_id", ""),
                    }
                    for r in dialogue_results
                ]
                with open(temp_manifest, "w") as f:
                    json.dump(manifest_data, f)
                captioned = burn_captions(str(temp_manifest), str(out))
                temp_manifest.unlink(missing_ok=True)
                return captioned
            except Exception as e:
                logger.error("Subtitle burn failed: %s", e)

        return str(out)

    finally:
        for c in final_clips:
            try: c.close()
            except Exception: pass
