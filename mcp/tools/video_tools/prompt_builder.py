"""
mcp/tools/video_tools/prompt_builder.py
-----------------------------------------
Stable Diffusion / FLUX prompt builder from Phase 1 scene + character data.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

DEFAULT_NEGATIVE = (
    "different art style, inconsistent character, face deformity, "
    "multiple faces, text, watermark, blurry, low quality, cartoon, anime, illustration"
)
QUALITY_BOOSTERS = "sharp focus, high detail, 8k"
GLOBAL_STYLE = "cinematic photography, 1960s cold war aesthetic, film noir lighting, 35mm film grain"
STYLE_LOCK   = "cinematic film photography, consistent character design, 35mm film, unified color palette"

TONE_STYLE: Dict[str, str] = {
    "mysterious": "dramatic lighting, deep shadows, cinematic atmosphere",
    "action":     "dynamic composition, motion blur, high energy",
    "calm":       "soft lighting, peaceful, serene",
    "sad":        "muted colors, overcast, melancholic",
    "happy":      "bright colors, warm lighting, vibrant",
    "tense":      "high contrast, dramatic shadows, tension",
}


def build_character_anchor(character: Dict[str, Any]) -> str:
    parts = []
    name       = str(character.get("name", "")).strip()
    appearance = str(character.get("appearance", "")).strip()
    style      = str(character.get("style_reference", "")).strip()
    if name:       parts.append(name.upper() + ":")
    if appearance: parts.append(appearance)
    if style:      parts.append(style)
    return " ".join(parts).strip()


def build_image_prompt(scene: Dict[str, Any]) -> Dict[str, str]:
    location    = str(scene.get("location", scene.get("setting", ""))).strip()
    tone        = str(scene.get("tone", "")).strip().lower()
    visual_desc = str(scene.get("visual_description", "")).strip()
    tone_style  = TONE_STYLE.get(tone, "cinematic, highly detailed")
    positive = ", ".join(p for p in [visual_desc, location, tone_style, QUALITY_BOOSTERS, GLOBAL_STYLE] if p)
    return {"positive": positive, "negative": DEFAULT_NEGATIVE}


def build_dialogue_image_prompt(
    scene: Dict[str, Any],
    character: Dict[str, Any],
    dialogue_text: str,
    line_index: int,
) -> Dict[str, str]:
    location   = str(scene.get("location", "")).strip()
    tone       = str(scene.get("tone", "")).strip().lower()
    char_anchor = build_character_anchor(character)
    tone_style  = TONE_STYLE.get(tone, "cinematic, highly detailed")

    if "!" in dialogue_text:
        emotion = "tense, dramatic, excited"
    elif "?" in dialogue_text:
        emotion = "uncertain, questioning, suspenseful"
    else:
        emotion = "calm, focused"

    positive = ", ".join(p for p in [char_anchor, location, emotion, STYLE_LOCK, QUALITY_BOOSTERS] if p)
    return {"positive": positive, "negative": DEFAULT_NEGATIVE}


def build_prompts_for_all_scenes(scenes: list) -> Dict[str, Dict[str, str]]:
    return {
        str(s.get("scene_id", i + 1)): build_image_prompt(s)
        for i, s in enumerate(scenes)
    }
