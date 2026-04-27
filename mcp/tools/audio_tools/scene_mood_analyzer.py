"""
Scene Mood Analyzer - Uses LLM to generate BGM search queries from scene descriptions.
"""

import json
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class SceneMoodAnalyzer:
    """
    Analyzes scene descriptions and generates 3-word mood-based search queries
    for background music using Groq LLM.
    """
    
    MOOD_PROMPT_TEMPLATE = """
Analyze the following scene description and generate a concise 3-word search query for background music.
The query should capture the mood, setting, and atmosphere of the scene.

Scene Description: {scene_description}
Scene Location: {location}
Scene Duration: {duration} seconds

Return ONLY a 3-word search query like: "dark synth ambient" or "cheerful park birds" or "tense cinematic pulse"
Do not include quotes, do not explain, just the 3 words separated by spaces.
"""
    
    def __init__(self, groq_client=None):
        """
        Initialize the scene mood analyzer.
        
        Args:
            groq_client: Groq client instance (from groq package)
        """
        self.groq_client = groq_client
    
    def generate_bgm_query(
        self,
        scene_description: str,
        location: str = "Unknown",
        duration: int = 30
    ) -> str:
        """
        Generate a 3-word BGM search query from scene description.
        
        Args:
            scene_description: Description of the scene (dialogue/narrative)
            location: Scene location (from Phase 1)
            duration: Scene duration in seconds
            
        Returns:
            3-word search query for BGM (e.g., "dark synth ambient")
        """
        if not self.groq_client:
            # Fallback: simple mood detection from keywords
            return self._simple_mood_detection(scene_description, location)
        
        try:
            prompt = self.MOOD_PROMPT_TEMPLATE.format(
                scene_description=scene_description[:500],  # Limit length
                location=location,
                duration=duration
            )
            
            logger.info(f"Generating BGM query for scene at {location}")
            
            response = self.groq_client.chat.completions.create(
                model="mixtral-8x7b-32768",  # or appropriate Groq model
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=20
            )
            
            query = response.choices[0].message.content.strip().lower()
            
            # Ensure it's exactly 3 words
            words = query.split()
            if len(words) > 3:
                query = " ".join(words[:3])
            elif len(words) < 3:
                query = self._simple_mood_detection(scene_description, location)
            
            logger.info(f"Generated BGM query: {query}")
            return query
            
        except Exception as e:
            logger.error(f"Error generating BGM query: {str(e)}")
            return self._simple_mood_detection(scene_description, location)
    
    @staticmethod
    def _simple_mood_detection(scene_description: str, location: str) -> str:
        """
        Simple fallback mood detection based on keywords.
        
        Args:
            scene_description: Scene description text
            location: Scene location
            
        Returns:
            3-word BGM query
        """
        text = (scene_description + " " + location).lower()
        
        # Mood detection keywords
        mood_map = {
            "dark": ("dark", "ominous", "tense"),
            "danger": ("tense", "cinematic", "pulse"),
            "kgb": ("dark", "cold", "spy"),
            "safehouse": ("ambient", "interior", "calm"),
            "extract": ("urgent", "cinematic", "action"),
            "problem": ("tense", "dramatic", "moment"),
            "trust": ("dramatic", "emotional", "tense"),
            "defect": ("serious", "cinematic", "dramatic"),
            "happy": ("cheerful", "uplifting", "bright"),
            "spy": ("dark", "suspenseful", "ambient"),
            "berlin": ("urban", "tense", "cinematic"),
            "soviet": ("cold", "industrial", "ambient"),
        }
        
        for keyword, mood_set in mood_map.items():
            if keyword in text:
                return " ".join(mood_set)
        
        # Default fallback
        return "ambient interior calm"


class SceneAnalysisCache:
    """
    Caches scene mood analysis to avoid redundant LLM calls.
    """
    
    def __init__(self, cache_file: str = "data/cache/scene_mood_cache.json"):
        """
        Initialize analysis cache.
        
        Args:
            cache_file: Path to cache JSON file
        """
        self.cache_file = cache_file
        self.cache: Dict[str, str] = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from file if it exists."""
        try:
            import os
            if os.path.exists(self.cache_file):
                with open(self.cache_file) as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded mood cache with {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Could not load cache: {str(e)}")
            self.cache = {}
    
    def _save_cache(self):
        """Save cache to file."""
        try:
            import os
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache: {str(e)}")
    
    def get_or_generate(
        self,
        scene_id: int,
        scene_description: str,
        analyzer: SceneMoodAnalyzer
    ) -> str:
        """
        Get cached mood query or generate and cache new one.
        
        Args:
            scene_id: Scene identifier
            scene_description: Scene description for generation
            analyzer: SceneMoodAnalyzer instance
            
        Returns:
            BGM mood query (3 words)
        """
        cache_key = f"scene_{scene_id}"
        
        if cache_key in self.cache:
            logger.info(f"Using cached mood for {cache_key}")
            return self.cache[cache_key]
        
        query = analyzer.generate_bgm_query(scene_description)
        self.cache[cache_key] = query
        self._save_cache()
        
        return query
