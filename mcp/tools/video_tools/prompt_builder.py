"""Build Stable Diffusion prompts from Phase 1 scene data."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STYLE = "cinematic, highly detailed"
QUALITY_BOOSTERS = "sharp focus, high detail, 8k"
DEFAULT_NEGATIVE = (
    "different art style, inconsistent character, face deformity, "
    "multiple faces, text, watermark, blurry, low quality, cartoon, anime, illustration"
)

GLOBAL_STYLE_SUFFIX = "cinematic photography, 1960s cold war aesthetic, film noir lighting, 35mm film grain, consistent art direction throughout"
STYLE_LOCK = "cinematic film photography, consistent character design, same art style throughout, 35mm film, unified color palette, professional cinematography"

TONE_STYLE_MAP: dict[str, str] = {
    "mysterious": "dramatic lighting, deep shadows, cinematic atmosphere",
    "action": "dynamic composition, motion blur, high energy",
    "calm": "soft lighting, peaceful, serene",
    "sad": "muted colors, overcast, melancholic",
    "happy": "bright colors, warm lighting, vibrant",
}

def build_character_anchor(character: dict[str, Any]) -> str:
    """
    Build a consistent character description string from Phase 1 character data.
    """
    if not character:
        return ""
    name = str(character.get("name", "")).strip()
    appearance = str(character.get("appearance", "")).strip()
    style = str(character.get("style_reference", "")).strip()
    
    parts = []
    if name:
        parts.append(name.upper() + ":")
    if appearance:
        parts.append(appearance)
    if style:
        parts.append(style)
        
    return " ".join(parts).strip()



def build_image_prompt(scene: dict[str, Any]) -> dict[str, str]:
    """
    Build positive/negative prompts for one scene.
    """
    scene_id = str(scene.get("scene_id", ""))
    location = str(scene.get("location", scene.get("setting", ""))).strip()
    tone = str(scene.get("tone", "")).strip().lower()
    visual_description = str(scene.get("visual_description", "")).strip()

    tone_style = TONE_STYLE_MAP.get(tone, DEFAULT_STYLE)

    positive_parts = [
        visual_description,
        location,
        tone_style,
        QUALITY_BOOSTERS,
        GLOBAL_STYLE_SUFFIX
    ]
    positive = ", ".join([p for p in positive_parts if p])

    logger.debug("Built prompt for scene_id=%s", scene_id)
    return {"positive": positive, "negative": DEFAULT_NEGATIVE}

def build_dialogue_image_prompt(
    scene: dict[str, Any], character: dict[str, Any], dialogue_text: str, line_index: int
) -> dict[str, str]:
    """
    Build prompts per dialogue line based on scene setting, character style, and emotion.
    """
    scene_id = str(scene.get("scene_id", ""))
    location = str(scene.get("location", "")).strip()
    tone = str(scene.get("tone", "")).strip().lower()
    
    char_anchor = build_character_anchor(character)
    
    tone_style = TONE_STYLE_MAP.get(tone, DEFAULT_STYLE)
    
    # Emotional cue from text
    if "!" in dialogue_text:
        emotion = "tense, dramatic, excited"
    elif "?" in dialogue_text:
        emotion = "uncertain, questioning, suspenseful"
    else:
        emotion = "calm, focused"
        
    positive_parts = [
        char_anchor,
        location,
        emotion,
        STYLE_LOCK,
        QUALITY_BOOSTERS
    ]
    positive = ", ".join([part for part in positive_parts if part])

    logger.debug(
        "Built dialogue prompt for scene_id=%s, line_index=%d", scene_id or "unknown", line_index
    )
    return {"positive": positive, "negative": DEFAULT_NEGATIVE}

def build_prompts_for_all_scenes(scenes: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """
    Build prompts for all scenes in a manifest.
    """
    prompts: dict[str, dict[str, str]] = {}

    for index, scene in enumerate(scenes):
        scene_id = str(scene.get("scene_id", "")).strip() or f"scene_{index + 1}"
        prompts[scene_id] = build_image_prompt(scene)

    logger.info("Built prompts for %d scene(s)", len(prompts))
    return prompts
