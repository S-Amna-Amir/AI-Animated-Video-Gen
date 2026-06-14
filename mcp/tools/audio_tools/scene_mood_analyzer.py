"""
mcp/tools/audio_tools/scene_mood_analyzer.py
----------------------------------------------
Generates 3-word BGM search queries from scene text using Groq LLM,
with a keyword-based fallback.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MOOD_MAP = {
    "dark": "dark ominous tense",
    "danger": "tense cinematic pulse",
    "kgb": "dark cold spy",
    "safehouse": "ambient interior calm",
    "extract": "urgent cinematic action",
    "spy": "dark suspenseful ambient",
    "berlin": "urban tense cinematic",
    "soviet": "cold industrial ambient",
    "happy": "cheerful uplifting bright",
    "fight": "intense action percussion",
    "rain": "melancholic ambient rain",
    "night": "dark atmospheric cinematic",
    "chase": "urgent action pulse",
    "love": "warm emotional gentle",
    "mystery": "mysterious ambient suspense",
}


class SceneMoodAnalyzer:
    PROMPT = (
        "Analyze this scene and return ONLY a 3-word search query for background music.\n"
        "Scene: {scene}\nLocation: {location}\n"
        "Return exactly 3 words like: dark synth ambient"
    )

    def __init__(self, groq_client=None):
        self.groq_client = groq_client

    def generate_bgm_query(
        self,
        scene_description: str,
        location: str = "Unknown",
        duration: int = 30,
    ) -> str:
        if self.groq_client:
            try:
                resp = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{
                        "role": "user",
                        "content": self.PROMPT.format(
                            scene=scene_description[:400], location=location
                        ),
                    }],
                    temperature=0.3,
                    max_tokens=20,
                )
                query = resp.choices[0].message.content.strip().lower()
                words = query.split()
                if len(words) >= 3:
                    return " ".join(words[:3])
            except Exception as e:
                logger.warning(f"[MoodAnalyzer] LLM failed: {e}")

        return self._keyword_fallback(scene_description, location)

    @staticmethod
    def _keyword_fallback(scene_description: str, location: str) -> str:
        text = (scene_description + " " + location).lower()
        for keyword, mood in MOOD_MAP.items():
            if keyword in text:
                return mood
        return "ambient interior calm"
