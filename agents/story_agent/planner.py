"""
agents/story_agent/planner.py
------------------------------
Helper functions for the Story Agent:
  - parse_raw_script_to_manifest(): converts uploaded screenplay text → SceneManifest
  - extract_unique_characters(): pulls all character names from scenes
  - infer_personality(): derives traits from dialogue patterns
  - generate_appearance(): builds visual description from personality
"""
import logging
import os
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ── Script Parsing ─────────────────────────────────────────────────────────────

def parse_raw_script_to_manifest(script_text: str) -> Dict[str, Any]:
    """
    Convert validated raw screenplay text into a SceneManifest dict.
    Splits on INT./EXT. headings, then parses speaker labels and dialogue.
    """
    scenes = []
    scene_id = 0

    heading_re = re.compile(r"((?:INT\.|EXT\.)\s+.+)", re.IGNORECASE)
    parts = heading_re.split(script_text.strip())

    i = 0
    while i < len(parts):
        chunk = parts[i].strip()
        if re.match(r"^(INT\.|EXT\.)\s+", chunk, re.IGNORECASE):
            scene_id += 1
            body = parts[i + 1].strip() if (i + 1) < len(parts) else ""
            i += 2
            dialogue, characters, action_lines = _parse_scene_body(body)
            scenes.append({
                "scene_id":          scene_id,
                "location":          chunk,
                "characters":        characters,
                "action_description": " ".join(action_lines) or "(No action description)",
                "dialogue":          dialogue,
            })
        else:
            i += 1

    return {
        "title":        "Uploaded Script",
        "genre":        "drama",
        "total_scenes": scene_id,
        "scenes":       scenes,
    }


def _parse_scene_body(body: str) -> Tuple[List, List, List]:
    """Returns (dialogue_entries, characters, action_lines) for a scene body."""
    lines           = body.splitlines()
    dialogue        = []
    characters      = []
    action_lines    = []
    speaker_re      = re.compile(r"^[A-Z][A-Z\s]{1,30}$")
    current_speaker = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if speaker_re.match(stripped):
            current_speaker = stripped
            if current_speaker not in characters:
                characters.append(current_speaker)
        elif current_speaker:
            dialogue.append({
                "speaker":    current_speaker,
                "line":       stripped,
                "visual_cue": "Medium shot, neutral lighting.",
            })
            current_speaker = None
        else:
            action_lines.append(stripped)

    return dialogue, characters, action_lines


# ── Character Helpers ──────────────────────────────────────────────────────────

def extract_unique_characters(scenes: List[Dict]) -> List[str]:
    """Collect all unique character names across scenes (preserves order)."""
    seen, ordered = set(), []
    for scene in scenes:
        for name in scene.get("characters", []):
            key = name.strip().upper()
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
        for line in scene.get("dialogue", []):
            key = line.get("speaker", "").strip().upper()
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def infer_personality(char_name: str, scenes: List[Dict]) -> str:
    """Derive personality traits from a character's dialogue lines."""
    lines = [
        dl["line"]
        for scene in scenes
        for dl in scene.get("dialogue", [])
        if dl.get("speaker", "").upper() == char_name.upper()
    ]
    if not lines:
        return "mysterious, reserved, enigmatic"

    total_words = sum(len(l.split()) for l in lines)
    avg_words   = total_words / len(lines)
    all_text    = " ".join(lines).lower()
    traits      = []

    if avg_words > 15:
        traits.append("articulate")
    elif avg_words < 6:
        traits.append("terse")
    else:
        traits.append("measured")

    if sum(l.count("?") for l in lines) > 1:
        traits.append("inquisitive")

    if any(w in all_text for w in ["now", "must", "immediately", "quick", "hurry", "stop", "run"]):
        traits.append("urgent")

    if any(w in all_text for w in ["feel", "love", "hate", "afraid", "hope", "believe", "trust"]):
        traits.append("emotionally driven")

    return ", ".join(traits) if traits else "composed, determined"


def generate_appearance(char_name: str, personality: str) -> str:
    """Generate a visual appearance description. Attempts LLM, falls back to template."""
    client = _get_llm_client()
    if client:
        try:
            prompt = (
                f"Write a concise visual appearance description (2-3 sentences) "
                f"for a film character named '{char_name}' with these traits: {personality}. "
                f"Focus on: age range, clothing style, hair, distinguishing features. "
                f"Write in the style of a film production brief."
            )
            resp = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[Planner] LLM appearance generation failed: {e}")

    # Template fallback
    trait      = personality.split(",")[0].strip()
    appearance_map = {
        "articulate":       "Mid-30s, sharp-eyed professional. Neat dark clothing, clean-cut hair.",
        "terse":            "Late-40s, weathered face. Worn jacket, close-cropped grey hair.",
        "measured":         "Early-30s, composed bearing. Well-fitted neutral clothing.",
        "inquisitive":      "Mid-20s, bright alert eyes. Casual layered clothing, thin-framed glasses.",
        "urgent":           "Late-20s, kinetic energy. Athletic build, practical dark clothing.",
        "emotionally driven": "Early-30s, expressive face. Soft textures, warm colours.",
    }
    return appearance_map.get(
        trait,
        f"A compelling individual whose {trait} nature is evident in their bearing.",
    )


def _get_llm_client():
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY", "")
        return Groq(api_key=key) if key else None
    except ImportError:
        return None
