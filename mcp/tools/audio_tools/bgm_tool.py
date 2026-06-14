"""
mcp/tools/audio_tools/bgm_tool.py
------------------------------------
Freesound API search + download for background music.
Falls back to data/bgm_library/neutral_ambient.mp3 when unavailable.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class FreesoundAPI:
    BASE = "https://freesound.org/apiv2"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FREESOUND_API_KEY")

    def search(self, query: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            q = query.strip() or "cinematic ambient music"
            resp = requests.get(
                f"{self.BASE}/search/text/",
                params={
                    "query": q, "sort": "rating_desc", "page_size": 5,
                    "token": self.api_key,
                    "fields": "id,name,url,duration,tags,rating,previews",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            results = resp.json().get("results", [])
            if not results:
                return None
            best = results[0]
            preview = best.get("previews", {}).get("preview-hq-mp3")
            if not preview:
                return None
            return {
                "id": best.get("id"),
                "name": best.get("name"),
                "preview_url": preview,
                "source": "freesound",
            }
        except Exception as e:
            logger.warning(f"[BGM] Freesound search error: {e}")
            return None

    def download(self, preview_url: str, output_path: Path) -> bool:
        try:
            resp = requests.get(
                preview_url, timeout=30, stream=True,
                params={"token": self.api_key} if self.api_key else None,
            )
            if resp.status_code != 200:
                return False
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.warning(f"[BGM] Download error: {e}")
            return False


class BGMLocator:
    DEFAULT_BGM_DIR = Path("data/bgm_library")
    DEFAULT_AMBIENT = "neutral_ambient.mp3"

    @staticmethod
    def get_fallback_bgm() -> Optional[Path]:
        p = BGMLocator.DEFAULT_BGM_DIR / BGMLocator.DEFAULT_AMBIENT
        if p.exists():
            logger.info(f"[BGM] Using fallback: {p}")
            return p
        logger.warning(
            f"[BGM] No fallback found at {p}. "
            "Place an ambient MP3 at data/bgm_library/neutral_ambient.mp3"
        )
        return None


def search_and_download_bgm(
    mood_query: str,
    output_path: Path,
    api_key: Optional[str] = None,
    use_fallback: bool = True,
) -> Tuple[Optional[Path], Optional[Dict]]:
    """Search Freesound and download. Returns (path, metadata) or (fallback, None)."""
    fs = FreesoundAPI(api_key)
    result = fs.search(mood_query)
    if result and result.get("preview_url"):
        if fs.download(result["preview_url"], output_path):
            logger.info(f"[BGM] Downloaded '{result.get('name')}' for query '{mood_query}'")
            return output_path, result

    if use_fallback:
        fallback = BGMLocator.get_fallback_bgm()
        if fallback:
            return fallback, {"source": "fallback", "name": "neutral_ambient", "query": mood_query}

    logger.warning(f"[BGM] No BGM obtained for: {mood_query}")
    return None, None
