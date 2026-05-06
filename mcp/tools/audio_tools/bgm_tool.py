"""
Freesound API Integration Tool for Background Music.
Downloads and manages ambient/loop audio clips for scene backgrounds.
"""

import os
import json
import requests
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class FreesoundAPI:
    """
    Interfaces with Freesound.com API to search and download background music.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Freesound API client.
        
        Args:
            api_key: Freesound API key. If not provided, tries to load from environment.
        """
        self.api_key = api_key or os.getenv("FREESOUND_API_KEY")
        self.base_url = "https://freesound.org/apiv2"
        self.session = requests.Session()

        if self.api_key:
            logger.info("Freesound API initialized with API key")
        else:
            logger.warning("Freesound API key not provided - will use fallback audio")
    
    def search_ambient_audio(
        self,
        query: str,
        duration_min: int = 10,
        duration_max: int = 120,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Search Freesound for ambient/loop background audio.
        
        Args:
            query: Search query (e.g., "dark ambient synth")
            duration_min: Minimum audio duration in seconds
            duration_max: Maximum audio duration in seconds
            tags: Optional list of required tags (e.g., ["loop", "ambient"])
            
        Returns:
            Dict with audio metadata or None if search fails
        """
        if not self.api_key:
            logger.warning(f"Freesound API key not available, skipping search for: {query}")
            return None
        
        try:
            # Keep search broad to avoid empty result sets.
            effective_query = (query or "").strip() or "cinematic ambient music"
            params = {
                "query": effective_query,
                "sort": "rating_desc",
                "page_size": 5,
                "token": self.api_key,
                "fields": "id,name,url,duration,tags,rating,previews",
            }

            logger.info(f"Searching Freesound for: {effective_query}")
            
            response = self.session.get(
                f"{self.base_url}/search/text/",
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Freesound search failed: {response.status_code}")
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning(f"No results found for query: {effective_query}")
                return None
            
            # Get first result with best rating
            best_result = results[0]
            previews = best_result.get("previews", {})
            preview_url = previews.get("preview-hq-mp3")

            if not preview_url:
                logger.warning("Top Freesound result has no preview-hq-mp3 URL")
                return None
            
            return {
                "id": best_result.get("id"),
                "name": best_result.get("name"),
                "duration": best_result.get("duration"),
                "url": best_result.get("url"),
                "preview_url": preview_url,
                "download_url": f"{self.base_url}/sounds/{best_result.get('id')}/download/",
                "tags": best_result.get("tags", []),
                "rating": best_result.get("rating")
            }
            
        except Exception as e:
            logger.error(f"Freesound API error: {str(e)}")
            return None
    
    def download_audio(
        self,
        preview_url: str,
        output_path: Path
    ) -> bool:
        """
        Download audio preview from Freesound.
        
        Args:
            preview_url: URL to the audio preview
            output_path: Path to save the downloaded audio
            
        Returns:
            True if successful, False otherwise
        """
        try:
            params = {"token": self.api_key} if self.api_key else None
            response = self.session.get(preview_url, timeout=30, stream=True, params=params)
            
            if response.status_code != 200:
                logger.error(f"Download failed: {response.status_code}")
                return False
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Downloaded audio to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return False


class BGMLocator:
    """
    Manages fallback default background music.
    """
    
    DEFAULT_BGM_DIR = Path("data/bgm_library")
    DEFAULT_AMBIENT = "neutral_ambient.mp3"
    
    @staticmethod
    def ensure_fallback_bgm() -> Path:
        """
        Ensure a default neutral ambient background music file exists.
        Creates a silent fallback if needed.
        
        Returns:
            Path to fallback BGM file
        """
        bgm_dir = BGMLocator.DEFAULT_BGM_DIR
        bgm_dir.mkdir(parents=True, exist_ok=True)
        
        fallback_path = bgm_dir / BGMLocator.DEFAULT_AMBIENT
        
        if not fallback_path.exists():
            logger.warning(f"Default BGM not found at {fallback_path}")
            logger.info("Use: cp <your_ambient.mp3> data/bgm_library/neutral_ambient.mp3")
        
        return fallback_path
    
    @staticmethod
    def get_fallback_bgm() -> Optional[Path]:
        """
        Get the fallback BGM path if it exists.
        
        Returns:
            Path to fallback BGM or None if not found
        """
        fallback = BGMLocator.DEFAULT_BGM_DIR / BGMLocator.DEFAULT_AMBIENT
        
        if fallback.exists():
            logger.info(f"Using fallback BGM: {fallback}")
            return fallback
        
        return None


def search_and_download_bgm(
    mood_query: str,
    output_path: Path,
    api_key: Optional[str] = None,
    use_fallback: bool = True
) -> Tuple[Optional[Path], Optional[Dict]]:
    """
    Search Freesound for ambient audio and download it.
    Falls back to default ambient if API search fails.
    
    Args:
        mood_query: 3-word mood-based search query (e.g., "dark synth ambient")
        output_path: Where to save the downloaded audio
        api_key: Optional Freesound API key
        use_fallback: Whether to use fallback BGM if search fails
        
    Returns:
        Tuple of (audio_path, metadata_dict) or (fallback_path, None) or (None, None)
    """
    # Try Freesound API
    if api_key or os.getenv("FREESOUND_API_KEY"):
        fs_api = FreesoundAPI(api_key)
        result = fs_api.search_ambient_audio(
            query=mood_query,
            tags=["loop", "ambient"]
        )
        
        if result and result.get("preview_url"):
            print(f"Selected BGM: {result.get('name')}")
            print(f"Preview URL: {result.get('preview_url')}")
            if fs_api.download_audio(result["preview_url"], output_path):
                return output_path, result
    
    # Fallback to default ambient
    if use_fallback:
        fallback = BGMLocator.get_fallback_bgm()
        if fallback and fallback.exists():
            return fallback, {
                "source": "fallback",
                "name": "neutral_ambient",
                "query": mood_query
            }
    
    logger.warning(f"Could not obtain BGM for query: {mood_query}")
    return None, None
