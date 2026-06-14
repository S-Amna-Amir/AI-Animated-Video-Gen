"""
mcp/tools/video_tools/animator.py
------------------------------------
Ken Burns style animation of still images via FFmpeg zoompan filter.
"""
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import imageio_ffmpeg

logger = logging.getLogger(__name__)
FPS = 24

TONE_EFFECT_MAP = {
    "mysterious": "zoom_in", "tense": "dramatic_push", "action": "dramatic_push",
    "calm": "pan_right_zoom", "peaceful": "pan_right_zoom",
    "sad": "zoom_out", "melancholic": "zoom_out",
    "happy": "pan_up", "default": "zoom_in",
}


def _zoompan_filter(effect: str, duration_seconds: float) -> str:
    frames = max(1, int(round(duration_seconds * FPS)))
    safe   = frames + 24
    res    = "512x512"
    if effect == "zoom_in":
        return f"zoompan=z='min(zoom+0.0015,1.3)':d={safe}:s={res}:fps={FPS}"
    if effect == "zoom_out":
        return f"zoompan=z='if(eq(on,1),1.3,zoom-0.0015)':d={safe}:s={res}:fps={FPS}"
    if effect == "pan_right_zoom":
        return f"zoompan=z=1.2:x='(iw-iw/zoom)*(on/{frames})':d={safe}:s={res}:fps={FPS}"
    if effect == "pan_left_zoom":
        return f"zoompan=z=1.2:x='(iw-iw/zoom)*(1-on/{frames})':d={safe}:s={res}:fps={FPS}"
    if effect == "pan_up":
        return f"zoompan=z=1.2:y='(ih-ih/zoom)*(1-on/{frames})':d={safe}:s={res}:fps={FPS}"
    if effect == "dramatic_push":
        return f"zoompan=z='min(zoom+0.01,1.5)':d={safe}:s={res}:fps={FPS}"
    return f"zoompan=z='zoom+0.0015':d={safe}:s={res}:fps={FPS}"


def _color_grade(tone: str) -> str:
    grades = {
        "mysterious": "eq=brightness=-0.05:saturation=0.8:contrast=1.1",
        "tense":      "eq=brightness=-0.03:saturation=1.2:contrast=1.2",
        "calm":       "eq=brightness=0.02:saturation=0.9:contrast=0.95",
        "sad":        "eq=brightness=-0.08:saturation=0.6:contrast=1.0",
    }
    return grades.get(tone, "")


def _pick_effect(tone: str, text: str, line_index: int) -> str:
    tone = tone.lower().strip()
    if tone in ("tense", "action") or "!" in text:
        return "dramatic_push"
    if tone in ("calm", "peaceful"):
        return "pan_right_zoom"
    if tone == "sad":
        return "zoom_out"
    if tone == "happy":
        return "pan_up"
    if "?" in text:
        return "pan_down"
    return ["zoom_in", "pan_left_zoom", "pan_right_zoom"][line_index % 3]


def animate_scene(
    image_path: str,
    output_path: str,
    duration_ms: float,
    tone: str = "default",
    text: str = "",
    line_index: int = 0,
) -> str:
    dur = max(0.001, float(duration_ms) / 1000.0)
    effect   = _pick_effect(tone, text, line_index)
    zp       = _zoompan_filter(effect, dur)
    grade    = _color_grade(tone)
    vf       = ",".join(f for f in [zp, grade] if f)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg   = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg, "-loop", "1", "-r", str(FPS), "-i", image_path,
        "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-t", str(dur), "-pix_fmt", "yuv420p", "-r", str(FPS), "-y", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg animation failed for '{image_path}': {result.stderr[-300:]}")
    return str(out_path)


def animate_all_scenes(
    dialogue_results: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    run_dir: str,
) -> Dict[str, str]:
    tone_map = {
        str(s.get("scene_id", "")).strip(): str(s.get("tone", "default")).strip()
        for s in scenes
    }
    clips_dir = Path(run_dir) / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_results: Dict[str, str] = {}

    for r in dialogue_results:
        if r.get("status") != "success":
            continue
        scene_id   = str(r.get("scene_id", ""))
        line_index = r.get("line_index", 0)
        image_path = r.get("image_path", "")
        if not image_path:
            continue
        tone       = tone_map.get(scene_id, "default")
        out_path   = clips_dir / f"scene_{scene_id}_line_{line_index}.mp4"
        try:
            clip = animate_scene(
                image_path=image_path,
                output_path=str(out_path),
                duration_ms=float(r.get("duration_ms", 5000)),
                tone=tone, text=r.get("text", ""), line_index=line_index,
            )
            clip_results[f"{scene_id}_{line_index}"] = clip
        except Exception as e:
            logger.error("Animation failed scene %s line %d: %s", scene_id, line_index, e)
    return clip_results
