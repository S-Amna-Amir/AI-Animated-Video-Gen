"""
agents/edit_agent/intent_classifier.py
----------------------------------------
LLM-powered intent classifier for free-text edit commands.

Maps user queries like "make the scene darker" to structured intent objects:
{
    "intent":          "apply_brightness_adjustment",
    "target":          "video_effect",
    "scope":           "all_scenes" | "scene:N",
    "operation_type":  "apply_effect",
    "parameters":      {"brightness": -0.3}
}

Targets:
    audio             — re-run TTS / BGM for affected scenes
    video_effect      — apply color grading / filters WITHOUT regenerating images (fast)
    video_frame       — re-generate images for affected scenes (slow, uses HF Inference API)
    video_composition — re-compose final MP4 with FFmpeg only, no image regeneration
    script            — re-run Phase 1 and cascade all downstream phases
    system            — undo / redo / version management

Key principle: visual adjustments (brightness, contrast, tint, vignette) are
ALWAYS video_effect — never video_frame. Only use video_frame when the actual
image content (character, setting, expression) must change.

Test coverage: 10 query types as required by project spec.
"""
import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Keyword rules ─────────────────────────────────────────────────────────────
# (pattern, target, intent, operation_type, default_params)
# Order matters: more-specific rules first.
_KEYWORD_RULES = [
    # ── system ────────────────────────────────────────────────────────────────
    (r"\bundo\b",                              "system",            "undo",                         "system_action", {}),
    (r"\bredo\b",                              "system",            "redo",                         "system_action", {}),

    # ── audio ─────────────────────────────────────────────────────────────────
    (r"voice|tone|speak|tts|narrat",           "audio",             "change_voice_tone",             "regenerate",    {"tone": "neutral"}),
    (r"background.?music|bgm|music|ambient",   "audio",             "add_background_music",          "regenerate",    {"mood": "ambient"}),

    # ── video_effect: color grading / visual filters (NO image regeneration) ──
    (r"dark(?:er)?|dim(?:mer)?|low.?key",      "video_effect",      "apply_brightness_adjustment",   "apply_effect",  {"brightness": -0.3}),
    (r"bright(?:er)?|light(?:er)?|high.?key",  "video_effect",      "apply_brightness_adjustment",   "apply_effect",  {"brightness": 0.3}),
    (r"contrast",                              "video_effect",      "apply_contrast_adjustment",     "apply_effect",  {"contrast": 1.4}),
    (r"saturat|vivid|colour.?pop",             "video_effect",      "apply_saturation_adjustment",   "apply_effect",  {"saturation": 1.4}),
    (r"tint|hue",                              "video_effect",      "apply_tint",                    "apply_effect",  {"tint": "blue", "intensity": 0.5}),
    (r"vignette",                              "video_effect",      "apply_vignette",                "apply_effect",  {"vignette": 0.4}),
    (r"cinematic|film.?look|noir",             "video_effect",      "apply_cinematic_look",          "apply_effect",  {"vignette": 0.3, "contrast": 1.2, "saturation": 1.1}),
    (r"warm(?:er)?|warm.?tone",               "video_effect",      "apply_color_temperature",       "apply_effect",  {"temperature": "warm"}),
    (r"cool(?:er)?|cool.?tone",               "video_effect",      "apply_color_temperature",       "apply_effect",  {"temperature": "cool"}),

    # ── video_frame: content changes that require image regeneration ───────────
    (r"character.?design|redesign|appear",     "video_frame",       "change_character_design",       "regenerate",    {"scope": "all"}),
    (r"angr(?:y|ier)|expression|emotion",      "video_frame",       "adjust_character_expression",   "regenerate",    {}),
    (r"background|setting|scene.?look",        "video_frame",       "change_scene_setting",          "regenerate",    {}),
    (r"scene.?image|regenerate.?image",        "video_frame",       "regenerate_scene_image",        "regenerate",    {}),
    (r"dull|boring|lifeless",                  "video_frame",       "improve_scene_aesthetic",       "regenerate",    {"aesthetic": "vibrant"}),

    # ── video_composition: FFmpeg-only recompose ──────────────────────────────
    (r"subtitle|caption|text.?overlay",        "video_composition", "toggle_subtitles",              "recompose",     {"subtitles_enabled": False}),
    (r"transition|fade|dissolve|crossfade",    "video_composition", "change_transition",             "recompose",     {"transition_type": "crossfade", "duration_ms": 500}),
    (r"speed.?up|faster",                      "video_composition", "adjust_speed",                  "recompose",     {"speed_factor": 1.5}),
    (r"slow.?down|slower",                     "video_composition", "adjust_speed",                  "recompose",     {"speed_factor": 0.75}),

    # ── script: full pipeline restart ─────────────────────────────────────────
    (r"script|story|regenerate|rewrite|plot",  "script",            "regenerate_script",             "regenerate",    {}),
]

# ── Improved LLM system prompt ────────────────────────────────────────────────
_LLM_SYSTEM = """You are an intent classifier for an AI video editing system.
Analyze the user's edit request and classify it. Your response MUST be valid JSON.

{
  "intent":         string,   // short snake_case label
  "target":         string,   // one of: audio | video_effect | video_frame | video_composition | script | system
  "scope":          string,   // "all_scenes", "scene:N", "character:NAME", "full"
  "operation_type": string,   // one of: apply_effect | regenerate | recompose | system_action
  "parameters":     object    // action-specific key/value pairs
}

TARGET REFERENCE — pick the MINIMUM necessary target:

  audio            Re-synthesize voice/BGM. Examples:
                   "Make the narrator sound more dramatic"
                   → target: "audio", operation_type: "regenerate"

  video_effect     Apply color grading / visual filters WITHOUT regenerating images (fast).
                   ALWAYS use this for brightness, contrast, saturation, tint, vignette, and
                   any adjective that only changes the look of existing frames.
                   Examples:
                   "Make the scene darker"
                   → intent: "apply_brightness_adjustment", target: "video_effect",
                     operation_type: "apply_effect", parameters: {"brightness": -0.3}
                   "Add more contrast"
                   → intent: "apply_contrast_adjustment", target: "video_effect",
                     operation_type: "apply_effect", parameters: {"contrast": 1.5}
                   "Tint everything blue"
                   → intent: "apply_tint", target: "video_effect",
                     operation_type: "apply_effect", parameters: {"tint": "blue", "intensity": 0.6}
                   "Make it look more cinematic"
                   → intent: "apply_cinematic_look", target: "video_effect",
                     operation_type: "apply_effect",
                     parameters: {"vignette": 0.3, "contrast": 1.2, "saturation": 1.1}

  video_frame      Regenerate individual scene images (triggers HF Inference API — slow).
                   Use ONLY when image CONTENT must change (character, expression, setting).
                   Examples:
                   "Make Jack look angrier in scene 3"
                   → intent: "adjust_character_expression", target: "video_frame",
                     operation_type: "regenerate", parameters: {"character": "Jack", "scene": "3"}
                   "Change the background to a forest"
                   → intent: "change_scene_setting", target: "video_frame",
                     operation_type: "regenerate", parameters: {"setting": "forest"}

  video_composition  Re-compose final video with FFmpeg only (no image regeneration).
                   Examples:
                   "Remove subtitles"
                   → intent: "toggle_subtitles", target: "video_composition",
                     operation_type: "recompose", parameters: {"subtitles_enabled": false}
                   "Speed up the video by 1.5x"
                   → intent: "adjust_speed", target: "video_composition",
                     operation_type: "recompose", parameters: {"speed_factor": 1.5}
                   "Add fade transitions"
                   → intent: "change_transition", target: "video_composition",
                     operation_type: "recompose",
                     parameters: {"transition_type": "fade", "duration_ms": 500}

  script           Full pipeline restart with a new story.
                   "Rewrite the story with a happier ending"
                   → intent: "regenerate_script", target: "script",
                     operation_type: "regenerate"

  system           Undo / redo / version management.
                   "Undo the last change"
                   → intent: "undo", target: "system", operation_type: "system_action"

For audio: include volume_factor (e.g. 1.5 to increase, 0.5 to decrease) or
mood_query (e.g. "jazz music") when relevant.

Return ONLY the JSON. No markdown, no explanation."""


_VALID_TARGETS = frozenset(
    ("audio", "video_effect", "video_frame", "video_composition", "script", "system")
)
_VALID_OPS = frozenset(("apply_effect", "regenerate", "recompose", "system_action"))


class IntentClassifier:
    """
    Classifies a free-text edit query into a structured intent object.
    Uses Groq LLM when available; falls back to keyword matching.
    """

    def __init__(self, groq_client=None):
        self._client = groq_client or self._make_client()

    @staticmethod
    def _make_client():
        try:
            from groq import Groq
            key = os.getenv("GROQ_API_KEY", "")
            return Groq(api_key=key) if key else None
        except ImportError:
            return None

    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classify an edit query. Returns a structured intent dict.
        Always returns a valid dict even if classification fails.
        """
        if self._client:
            result = self._classify_llm(query)
            if result:
                return result

        return self._classify_keywords(query)

    def _classify_llm(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM},
                    {"role": "user",   "content": query},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
            # Validate required keys
            for k in ("intent", "target", "scope", "parameters"):
                if k not in result:
                    raise ValueError(f"Missing key: {k}")
            if result["target"] not in _VALID_TARGETS:
                raise ValueError(f"Invalid target: {result['target']}")
            # Ensure operation_type is present (backfill from target if missing)
            if "operation_type" not in result:
                result["operation_type"] = _default_op(result["target"])
            logger.info("[IntentClassifier] LLM: %s → %s / %s", query[:50], result["intent"], result["target"])
            return result
        except Exception as e:
            logger.warning("[IntentClassifier] LLM failed (%s), falling back to keywords", e)
            return None

    def _classify_keywords(self, query: str) -> Dict[str, Any]:
        text = query.lower()

        # 1. Parse scope
        scope = "all_scenes"
        scene_match = re.search(r"scene\s*[:#]?\s*(\d+)", text)
        if scene_match:
            scope = f"scene:{scene_match.group(1)}"
        char_match = re.search(r"character\s+([a-z]+)", text)
        if char_match:
            scope = f"character:{char_match.group(1).upper()}"

        # 2. Volume increases (audio — before generic BGM rule)
        is_increase = ("increase" in text or "louder" in text or "higher" in text) and \
                      ("volume" in text or "bgm" in text or "music" in text)
        if is_increase:
            return {
                "intent":         "increase_bgm_volume",
                "target":         "audio",
                "scope":          scope,
                "operation_type": "regenerate",
                "parameters":     {"volume_factor": 1.5},
            }

        # 3. Volume decreases
        is_decrease = ("decrease" in text or "quieter" in text or "softer" in text or "lower" in text) and \
                      ("volume" in text or "bgm" in text or "music" in text)
        if is_decrease:
            return {
                "intent":         "decrease_bgm_volume",
                "target":         "audio",
                "scope":          scope,
                "operation_type": "regenerate",
                "parameters":     {"volume_factor": 0.5},
            }

        # 4. Change BGM to a specific style
        bgm_change_match = re.search(
            r"(?:change|swap|set|replace)\s+(?:the\s+)?(?:background\s+)?(?:bgm|music|ambient)\s+(?:to\s+)?([a-z0-9\s_\-]+)",
            text,
        )
        if bgm_change_match:
            return {
                "intent":         "change_bgm",
                "target":         "audio",
                "scope":          scope,
                "operation_type": "regenerate",
                "parameters":     {"mood_query": bgm_change_match.group(1).strip()},
            }

        # 5. Tint with explicit colour name  e.g. "tint it red" / "add a blue tint"
        tint_match = re.search(r"tint.{0,10}?(red|green|blue|orange|purple|yellow|pink|cyan)", text) or \
                     re.search(r"(red|green|blue|orange|purple|yellow|pink|cyan).{0,10}?tint", text)
        if tint_match:
            colour = tint_match.group(1)
            return {
                "intent":         "apply_tint",
                "target":         "video_effect",
                "scope":          scope,
                "operation_type": "apply_effect",
                "parameters":     {"tint": colour, "intensity": 0.5},
            }

        # 6. General keyword rules
        for pattern, target, intent, op_type, params in _KEYWORD_RULES:
            if re.search(pattern, text):
                result = {
                    "intent":         intent,
                    "target":         target,
                    "scope":          scope,
                    "operation_type": op_type,
                    "parameters":     dict(params),
                }
                logger.info("[IntentClassifier] Keyword: %s → %s / %s", query[:50], intent, target)
                return result

        # Unknown — safe fallback
        logger.warning("[IntentClassifier] No match for: %s — defaulting to script", query)
        return {
            "intent":         "unknown",
            "target":         "script",
            "scope":          "all_scenes",
            "operation_type": "regenerate",
            "parameters":     {"original_query": query},
        }


def _default_op(target: str) -> str:
    """Return a sensible default operation_type for a given target."""
    return {
        "audio":             "regenerate",
        "video_effect":      "apply_effect",
        "video_frame":       "regenerate",
        "video_composition": "recompose",
        "script":            "regenerate",
        "system":            "system_action",
    }.get(target, "regenerate")
