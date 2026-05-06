"""Audio Tools - MCP Layer for Audio Operations."""

from mcp.tools.audio_tools.voice_mapper import VoiceMapper, EdgeTTSVoice
from mcp.tools.audio_tools.tts_tool import TTSTool, run_tts_synthesis
from mcp.tools.audio_tools.bgm_tool import FreesoundAPI, BGMLocator, search_and_download_bgm
from mcp.tools.audio_tools.scene_mood_analyzer import SceneMoodAnalyzer, SceneAnalysisCache
from mcp.tools.audio_tools.audio_composer import AudioComposer, compose_voice_with_fallback_bgm

__all__ = [
    "VoiceMapper",
    "EdgeTTSVoice",
    "TTSTool",
    "run_tts_synthesis",
    "FreesoundAPI",
    "BGMLocator",
    "search_and_download_bgm",
    "SceneMoodAnalyzer",
    "SceneAnalysisCache",
    "AudioComposer",
    "compose_voice_with_fallback_bgm"
]
