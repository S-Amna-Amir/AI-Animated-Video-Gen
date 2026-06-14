"""
mcp/tools/llm_tools/text_generator.py
--------------------------------------
MCP tool: generate_script_segment

Generates a structured multi-scene screenplay from a natural-language prompt.
Delegates to the Groq LLM (or a mock fallback when no API key is available).
"""
import json
import logging
import os
from typing import Any, Dict

from mcp.base_tool import BaseTool
from mcp.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class GenerateScriptSegmentTool(BaseTool):
    name = "generate_script_segment"
    description = (
        "Generates a structured screenplay JSON from a natural language prompt. "
        "Returns a SceneManifest object."
    )
    owner_agent = "story_agent"
    input_schema = {
        "prompt":     {"type": "string",  "required": True},
        "num_scenes": {"type": "integer", "required": False, "default": 5},
        "genre":      {"type": "string",  "required": False, "default": "drama"},
        "style":      {"type": "string",  "required": False, "default": "cinematic"},
    }

    # ── System prompt ──────────────────────────────────────────────────────
    _SYSTEM_PROMPT = """You are a professional Hollywood screenwriter.
Your task is to generate a structured screenplay in strict JSON format.
Output ONLY valid JSON. No markdown fences, no explanation, no preamble.

Output schema:
{
  "title": "string",
  "genre": "string",
  "total_scenes": integer,
  "scenes": [
    {
      "scene_id": integer,
      "location": "INT./EXT. PLACE - DAY/NIGHT",
      "characters": ["string"],
      "action_description": "string",
      "dialogue": [
        {
          "speaker": "string",
          "line": "string",
          "visual_cue": "Close-up / Wide shot / Medium shot + lighting description"
        }
      ]
    }
  ]
}

Rules:
- Every scene MUST have at least one dialogue entry.
- visual_cue must describe camera angle and lighting.
- Location format: INT./EXT. PLACE - DAY/NIGHT
- Output ONLY the JSON object."""

    def execute(
        self,
        prompt: str,
        num_scenes: int = 5,
        genre: str = "drama",
        style: str = "cinematic",
        **_,
    ) -> Dict[str, Any]:
        client = self._get_client()
        if client:
            try:
                user_msg = (
                    f"Write a {genre} screenplay in a {style} style.\n"
                    f"Story idea: {prompt}\n"
                    f"Generate exactly {num_scenes} scenes."
                )
                resp = client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=[
                        {"role": "system", "content": self._SYSTEM_PROMPT},
                        {"role": "user",   "content": user_msg},
                    ],
                    temperature=0.85,
                )
                raw = resp.choices[0].message.content.strip()
                script = json.loads(raw)
                logger.info(
                    f"[GenerateScript] LLM generated {len(script.get('scenes', []))} scenes."
                )
                return script
            except Exception as e:
                logger.error(f"[GenerateScript] LLM call failed: {e} — using mock.")

        logger.warning("[GenerateScript] No LLM client — using mock script.")
        return self._mock_script(prompt, num_scenes, genre)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _get_client():
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                return None
            return Groq(api_key=api_key)
        except ImportError:
            return None

    @staticmethod
    def _mock_script(prompt: str, num_scenes: int, genre: str) -> Dict[str, Any]:
        locations = [
            "INT. ABANDONED WAREHOUSE - NIGHT",
            "EXT. CITY ROOFTOP - DUSK",
            "INT. POLICE PRECINCT - DAY",
            "EXT. RAIN-SOAKED ALLEY - NIGHT",
            "INT. SAFE HOUSE - DAY",
        ]
        scenes = []
        for i in range(1, num_scenes + 1):
            scenes.append({
                "scene_id": i,
                "location": locations[(i - 1) % len(locations)],
                "characters": ["ALEX", "MORGAN"],
                "action_description": f"Scene {i} unfolds from: {prompt[:60]}...",
                "dialogue": [
                    {
                        "speaker": "ALEX",
                        "line": f"We can't keep running. Scene {i} changes everything.",
                        "visual_cue": "Close-up, tense lighting, shallow depth of field.",
                    },
                    {
                        "speaker": "MORGAN",
                        "line": "Then we stop running. We fight back.",
                        "visual_cue": "Wide shot, both silhouetted against city lights.",
                    },
                ],
            })
        return {
            "title": f"Mock Script: {prompt[:40]}",
            "genre": genre,
            "total_scenes": num_scenes,
            "scenes": scenes,
        }


# Self-register at import time
ToolRegistry.register(GenerateScriptSegmentTool())
