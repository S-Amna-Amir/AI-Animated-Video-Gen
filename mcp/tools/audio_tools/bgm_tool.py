"""
mcp/tools/audio_tools/bgm_tool.py
------------------------------------
Freesound API search + download for background music.
Falls back to data/bgm_library/neutral_ambient.mp3 when unavailable.
"""
import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


_GENERIC_BGM_QUERIES = [
    "ambient background music",
    "instrumental loop",
    "ambient instrumental",
    "soft cinematic ambient",
]

_QUERY_STOPWORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "with", "without", "over", "under", "very",
    "scene", "scenes", "music", "track", "background", "soundtrack", "audio",
}


class FreesoundAPI:
    BASE = "https://freesound.org/apiv2"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FREESOUND_API_KEY")

    def search(self, query: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            q = query.strip() or "ambient background music"
            resp = requests.get(
                f"{self.BASE}/search/text/",
                params={
                    "query": q,
                    "sort": "rating_desc",
                    "page_size": 10,
                    "token": self.api_key,
                    "fields": "id,name,url,duration,tags,rating,previews",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning(f"[BGM] Freesound search returned {resp.status_code} for '{q}'")
                return None
            results = resp.json().get("results", [])
            if not results:
                return None
            best = results[0]
            previews = best.get("previews", {})
            preview = previews.get("preview-lq-mp3") or previews.get("preview-hq-mp3")
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
                preview_url,
                timeout=30,
                stream=True,
                params={"token": self.api_key} if self.api_key else None,
            )
            if resp.status_code != 200:
                return False
            output_path.parent.mkdir(parents=True, exist_ok=True)
            MAX_BYTES = 3 * 1024 * 1024
            written = 0
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        if written >= MAX_BYTES:
                            logger.warning(
                                f"[BGM] Download capped at {MAX_BYTES // 1024}KB for {preview_url}"
                            )
                            break
            return output_path.exists() and output_path.stat().st_size > 0
        except requests.Timeout:
            logger.warning(f"[BGM] Download timed out: {preview_url}")
            return False
        except Exception as e:
            logger.warning(f"[BGM] Download error: {e}")
            return False


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def _broaden_query(query: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _QUERY_STOPWORDS]
    if not words:
        return query.strip()
    return " ".join(words[:4])


def _build_query_candidates(mood_query: str, fallback_queries: Optional[Iterable[str]] = None) -> List[str]:
    candidates: List[str] = []
    for candidate in [_broaden_query(_normalize_query(mood_query)), _normalize_query(mood_query)]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for candidate in fallback_queries or _GENERIC_BGM_QUERIES:
        normalized = _normalize_query(candidate)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


class BGMLocator:
    DEFAULT_BGM_DIR = Path("data/bgm_library")
    DEFAULT_AMBIENT = "neutral_ambient.mp3"

    @staticmethod
    def get_fallback_bgm() -> Optional[Path]:
        preferred = BGMLocator.DEFAULT_BGM_DIR / BGMLocator.DEFAULT_AMBIENT
        if preferred.exists():
            logger.info(f"[BGM] Using fallback: {preferred}")
            return preferred

        if BGMLocator.DEFAULT_BGM_DIR.exists():
            for candidate in sorted(BGMLocator.DEFAULT_BGM_DIR.iterdir()):
                if candidate.is_file() and candidate.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}:
                    logger.info(f"[BGM] Using fallback: {candidate}")
                    return candidate

        logger.warning(
            f"[BGM] No fallback found at {preferred}. "
            "Place an ambient MP3 at data/bgm_library/neutral_ambient.mp3"
        )
        return None


def search_and_download_bgm(
    mood_query: str,
    output_path: Path,
    api_key: Optional[str] = None,
    use_fallback: bool = True,
    fallback_queries: Optional[Iterable[str]] = None,
) -> Tuple[Optional[Path], Optional[Dict]]:
    """Search Freesound and download. Returns (path, metadata) or (fallback, None)."""
    fs = FreesoundAPI(api_key)
    for query in _build_query_candidates(mood_query, fallback_queries):
        result = fs.search(query)
        if result and result.get("preview_url"):
            if fs.download(result["preview_url"], output_path):
                logger.info(f"[BGM] Downloaded '{result.get('name')}' for query '{query}'")
                result["query"] = mood_query
                result["query_used"] = query
                return output_path, result
            logger.warning(f"[BGM] Failed to download result for query '{query}'")
        else:
            logger.warning(f"[BGM] No Freesound results for query '{query}'")

    if use_fallback:
        fallback = BGMLocator.get_fallback_bgm()
        if fallback:
            return fallback, {
                "source": "fallback",
                "name": fallback.name,
                "query": mood_query,
                "query_used": "local_fallback",
            }

    logger.warning(f"[BGM] No BGM obtained after Freesound + fallback attempts for: {mood_query}")
    return None, None
