"""
agents/edit_agent/intent_classifier.py
----------------------------------------
LLM-powered intent classifier for free-text edit commands.

Maps user queries like "make the scene darker" to structured intent objects:
{
    "intent":     "make_scene_darker",
    "target":     "video_frame",
    "scope":      "all_scenes" | "scene:N",
    "parameters": {"aesthetic": "dark", ...}
}

Targets:
    audio       — re-run TTS / BGM for affected scenes
    video_frame — re-generate images for affected scenes
    video       — recompose final MP4 with new parameters
    script      — re-run Phase 1 and cascade all downstream phases

Test coverage: 10 query types as required by project spec.
"""
import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Intent definitions ────────────────────────────────────────────────────────
# Maps (keyword_pattern, target, default_intent, default_params)
_KEYWORD_RULES = [
    # audio intents
    (r"voice|tone|speak|tts|narrat",         "audio",       "change_voice_tone",       {"tone": "neutral"}),
    (r"background.?music|bgm|music|ambient",  "audio",       "add_background_music",    {"mood": "ambient"}),
    (r"speed.?up|faster|slow.?down|slower",   "video",       "speed_up_scene",          {"speed_factor": 1.5}),
    # video_frame intents
    (r"dark|darker|brightness|dim|shadow",    "video_frame", "make_scene_darker",       {"aesthetic": "dark"}),
    (r"bright|lighter|vivid|saturat",         "video_frame", "make_scene_brighter",     {"aesthetic": "bright"}),
    (r"character.?design|redesign|appear",    "video_frame", "change_character_design",  {"scope": "all"}),
    (r"scene.?image|regenerate.?image",       "video_frame","regenerate_scene_image",   {}),
    # video intents
    (r"subtitle|caption|text.?overlay",       "video",       "remove_subtitle",         {"action": "remove"}),
    (r"transition|fade|dissolve",             "video",       "change_transition",       {"type": "crossfade"}),
    # script intents — must come before generic re.?gen to avoid false match
    (r"script|story|regenerate|rewrite|plot", "script",      "regenerate_script",       {}),
]

_LLM_SYSTEM = """You are an intent classifier for a video editing pipeline.
Given a user edit command, return ONLY a JSON object with these exact keys:
{
  "intent":     string,   // snake_case action name
  "target":     string,   // one of: audio | video_frame | video | script
  "scope":      string,   // "all_scenes", "scene:1", "character:NAME", etc.
  "parameters": object    // action-specific key/value pairs
}

Valid targets and example intents:
  audio:       change_voice_tone, add_background_music, change_voice_speed
  video_frame: make_scene_darker, make_scene_brighter, change_character_design, regenerate_scene_image
  video:       remove_subtitle, add_subtitle, speed_up_scene, change_transition
  script:      regenerate_script, change_genre, change_tone

Return ONLY the JSON. No explanation. No markdown fences."""


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
                max_tokens=200,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
            # Validate required keys
            for k in ("intent", "target", "scope", "parameters"):
                if k not in result:
                    raise ValueError(f"Missing key: {k}")
            if result["target"] not in ("audio", "video_frame", "video", "script"):
                raise ValueError(f"Invalid target: {result['target']}")
            logger.info("[IntentClassifier] LLM: %s → %s", query[:50], result["intent"])
            return result
        except Exception as e:
            logger.warning("[IntentClassifier] LLM failed (%s), falling back to keywords", e)
            return None

    def _classify_keywords(self, query: str) -> Dict[str, Any]:
        text = query.lower()
        for pattern, target, intent, params in _KEYWORD_RULES:
            if re.search(pattern, text):
                # Try to extract scene number from query e.g. "scene 2" or "scene:3"
                scope = "all_scenes"
                scene_match = re.search(r"scene\s*[:#]?\s*(\d+)", text)
                if scene_match:
                    scope = f"scene:{scene_match.group(1)}"
                char_match = re.search(r"character\s+([a-z]+)", text)
                if char_match:
                    scope = f"character:{char_match.group(1).upper()}"

                result = {
                    "intent":     intent,
                    "target":     target,
                    "scope":      scope,
                    "parameters": dict(params),
                }
                logger.info("[IntentClassifier] Keyword: %s → %s", query[:50], intent)
                return result

        # Unknown — default to regenerate_script as safe fallback
        logger.warning("[IntentClassifier] No match for: %s — defaulting to script", query)
        return {
            "intent":     "unknown",
            "target":     "script",
            "scope":      "all_scenes",
            "parameters": {"original_query": query},
        }
