"""Apply Ken Burns style animation to generated scene images."""

import logging
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg

logger = logging.getLogger(__name__)

FPS = 24

TONE_EFFECT_MAP = {
    "mysterious": "zoom_in",
    "tense": "dramatic_push",
    "action": "dramatic_push",
    "calm": "pan_right_zoom",
    "peaceful": "pan_right_zoom",
    "sad": "zoom_out",
    "melancholic": "zoom_out",
    "happy": "pan_up",
    "default": "zoom_in"
}
def get_ffmpeg_zoompan_filter(effect: str, duration_seconds: float) -> str:
    """
    Build FFmpeg zoompan filter string for a tone effect.
    """
    frames = max(1, int(round(duration_seconds * FPS)))
    
    if effect == "zoom_in":
        # smooth slow zoom from 1.0x to 1.3x over full duration
        return f"zoompan=z='min(zoom+0.0015,1.3)':d={frames}:s=512x512"
    if effect == "zoom_out":
        # starts at 1.3x zoom, slowly pulls back to 1.0x
        return f"zoompan=z='if(eq(on,1),1.3,zoom-0.0015)':d={frames}:s=512x512"
    if effect == "pan_left_zoom":
        # zoom 1.2x + pan from right to left
        return f"zoompan=z=1.2:x='(iw-iw/zoom)*(1-on/{frames})':d={frames}:s=512x512"
    if effect == "pan_right_zoom":
        # zoom 1.2x + pan from left to right
        return f"zoompan=z=1.2:x='(iw-iw/zoom)*(on/{frames})':d={frames}:s=512x512"
    if effect == "pan_up":
        # zoom 1.2x + slow upward pan
        return f"zoompan=z=1.2:y='(ih-ih/zoom)*(1-on/{frames})':d={frames}:s=512x512"
    if effect == "pan_down":
        # zoom 1.2x + slow downward pan
        return f"zoompan=z=1.2:y='(ih-ih/zoom)*(on/{frames})':d={frames}:s=512x512"
    if effect == "dramatic_push":
        # fast zoom from 1.0x to 1.5x (for tense moments)
        return f"zoompan=z='min(zoom+0.01,1.5)':d={frames}:s=512x512"
        
    return f"zoompan=z='zoom+0.0015':d={frames}:s=512x512"


def get_color_grade_filter(tone: str) -> str:
    if tone == "mysterious":
        return "eq=brightness=-0.05:saturation=0.8:contrast=1.1"
    if tone == "tense":
        return "eq=brightness=-0.03:saturation=1.2:contrast=1.2"
    if tone == "calm":
        return "eq=brightness=0.02:saturation=0.9:contrast=0.95"
    if tone == "sad":
        return "eq=brightness=-0.08:saturation=0.6:contrast=1.0"
    return ""


def determine_effect(tone: str, text: str, line_index: int) -> str:
    tone = tone.lower().strip()
    if tone == "mysterious":
        return "zoom_in" if line_index % 2 == 0 else "pan_left_zoom"
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
        
    choices = ["zoom_in", "pan_left_zoom", "pan_right_zoom"]
    return choices[line_index % 3]


def animate_scene(
    image_path: str,
    output_path: str,
    duration_ms: float,
    tone: str = "default",
    text: str = "",
    line_index: int = 0
) -> str:
    """
    Animate a static image into a short clip via FFmpeg.
    """
    duration_seconds = max(0.001, float(duration_ms) / 1000.0)
    
    effect = determine_effect(tone, text, line_index)
    zoompan_filter = get_ffmpeg_zoompan_filter(effect, duration_seconds)
    color_filter = get_color_grade_filter(tone)
    
    # Combine filters: zoompan, color (if any), vignette, fade-in
    filter_chain = [zoompan_filter]
    if color_filter:
        filter_chain.append(color_filter)
    filter_chain.append("vignette=PI/4")
    filter_chain.append("fade=t=in:st=0:d=0.3")
    
    vf_string = ",".join(filter_chain)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_exe,
        "-loop", "1",
        "-i", image_path,
        "-vf", vf_string,
        "-c:v", "libx264",
        "-t", str(duration_seconds),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-y",
        str(out_path),
    ]

    logger.info("Animating scene image with effect=%s -> %s", effect, out_path)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"FFmpeg animation failed for '{image_path}': {error_text}")

    return str(out_path)


def animate_all_scenes(
    dialogue_results: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    run_dir: str,
) -> dict[str, str]:
    """
    Animate all successful dialogue images and return clip paths.
    """
    tone_by_scene_id = {
        str(scene.get("scene_id", "")).strip(): str(scene.get("tone", "default")).strip()
        for scene in scenes
    }

    clips_dir = Path(run_dir) / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    clip_results: dict[str, str] = {}
    for result in dialogue_results:
        scene_id = str(result.get("scene_id", ""))
        line_index = result.get("line_index", 0)
        
        if result.get("status") != "success":
            logger.warning("Skipping animation for failed scene_id=%s line=%d", scene_id, line_index)
            continue

        image_path = result.get("image_path", "")
        if not image_path:
            logger.warning("Skipping animation for scene_id=%s line=%d due to missing image_path", scene_id, line_index)
            continue

        tone = tone_by_scene_id.get(scene_id, "default")
        text = result.get("text", "")
        duration_ms = float(result.get("duration_ms", 5000))
        output_path = clips_dir / f"scene_{scene_id}_line_{line_index}.mp4"

        clip_path = animate_scene(
            image_path=str(image_path),
            output_path=str(output_path),
            duration_ms=duration_ms,
            tone=tone,
            text=text,
            line_index=line_index
        )
        clip_results[f"{scene_id}_{line_index}"] = clip_path

    return clip_results
