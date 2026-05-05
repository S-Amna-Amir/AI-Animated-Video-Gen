"""
Story Agent Prompts
System and user prompt templates for every LangGraph node in Phase 1.
"""

# ── Node 1: Story Arc Generator ───────────────────────────────────────────────

STORY_SYSTEM = """You are an expert story architect for animated short films.
Your job is to take a raw user idea and craft a rich, coherent story structure.
You always output ONLY valid JSON — no markdown fences, no explanatory text."""

STORY_USER_TEMPLATE = """Create a complete story structure for this animated short film idea:

"{user_prompt}"

Requirements:
- Title must be evocative and memorable
- Logline: one sentence that captures the entire arc
- Genre and tone must feel authentic
- Include exactly 3 or 4 acts (intro → conflict → climax → resolution)
- Themes: 2–4 thematic keywords
- Protagonist and optional antagonist named
- "world" field: 1–2 sentences describing the story world

Output a JSON object matching this exact structure:
{{
  "title": "...",
  "logline": "...",
  "genre": "...",
  "tone": "...",
  "setting": "...",
  "time_period": "...",
  "themes": ["...", "..."],
  "acts": [
    {{"act": 1, "label": "Introduction", "description": "..."}},
    {{"act": 2, "label": "Conflict", "description": "..."}},
    {{"act": 3, "label": "Climax", "description": "..."}},
    {{"act": 4, "label": "Resolution", "description": "..."}}
  ],
  "protagonist": "...",
  "antagonist": "...",
  "world": "..."
}}"""


# ── Node 2: Character Designer ────────────────────────────────────────────────

CHARACTER_SYSTEM = """You are a character designer for animated short films.
Given a story structure, you create a vivid, consistent character roster.
Output ONLY valid JSON — no markdown, no extra text."""

CHARACTER_USER_TEMPLATE = """Design the full character roster for this story:

STORY TITLE: {title}
LOGLINE: {logline}
GENRE: {genre}
TONE: {tone}
ACTS SUMMARY:
{acts_summary}

Requirements:
- 2–5 characters total
- Each character needs: name, role (protagonist/antagonist/supporting/narrator),
  personality (2–3 sentences), appearance (detailed visual description for image generation),
  style_reference (artistic style cue), voice_config, first_appearance (scene number 1–{num_scenes}),
  and 1–2 dialogue_samples (leave empty list [] if no dialogue yet)
- voice_config must include: tone, speed (0.5–2.0), pitch (low/medium/high), emotion

Output a JSON array of character objects:
[
  {{
    "name": "CHARACTER_NAME",
    "role": "protagonist",
    "personality": "...",
    "appearance": "...",
    "style_reference": "...",
    "voice_config": {{
      "tone": "warm",
      "speed": 1.0,
      "pitch": "medium",
      "emotion": "curious"
    }},
    "first_appearance": 1,
    "dialogue_samples": []
  }}
]"""


# ── Node 3: Script Writer ─────────────────────────────────────────────────────

SCRIPT_SYSTEM = """You are a screenplay writer for animated short films.
You write vivid, dialogue-driven scenes that translate perfectly to visual storytelling.
Output ONLY valid JSON — no markdown, no preamble."""

SCRIPT_USER_TEMPLATE = """Write the full scene-by-scene script for this animated short film.

STORY:
Title: {title}
Genre: {genre}
Tone: {tone}
Setting: {setting}
World: {world}

ACTS:
{acts_summary}

CHARACTERS:
{character_summary}

Requirements:
- Write exactly {num_scenes} scenes
- Each scene: location, setting_description, mood (for BGM), tone,
  dialogue lines with speaker/line/visual_cue/emotion,
  characters list (names only), duration_seconds (10–60),
  and a visual block with image_prompt/camera_angle/lighting/color_palette/transition_in/transition_out
- Dialogue: 2–6 lines per scene; make it snappy and visual
- image_prompt must be a full Stable Diffusion / DALL-E style prompt
- mood must be one of: tense, joyful, melancholic, mysterious, action, peaceful, dramatic

Output a JSON array of scene objects:
[
  {{
    "scene_id": 1,
    "location": "...",
    "setting_description": "...",
    "mood": "tense",
    "tone": "...",
    "dialogue": [
      {{
        "speaker": "CHARACTER_NAME",
        "line": "Dialogue text here.",
        "visual_cue": "Camera angle and expression description.",
        "emotion": "determined"
      }}
    ],
    "characters": ["CHARACTER_NAME"],
    "duration_seconds": 30,
    "visual": {{
      "image_prompt": "Full detailed image generation prompt...",
      "camera_angle": "medium shot",
      "lighting": "warm golden hour",
      "color_palette": "warm amber tones",
      "transition_in": "fade",
      "transition_out": "cut"
    }}
  }}
]"""


# ── Node 4: Validator / Consistency Checker ───────────────────────────────────

VALIDATOR_SYSTEM = """You are a script continuity editor.
Review a story, character roster, and scene list for consistency issues.
Output ONLY valid JSON."""

VALIDATOR_USER_TEMPLATE = """Review this script for consistency issues:

STORY: {story_json}
CHARACTERS: {characters_json}
SCENES (first 2 for brevity): {scenes_sample_json}

Check for:
1. Characters referenced in scenes but not defined
2. Scene moods inconsistent with genre/tone
3. Visual prompts missing key scene elements

Output JSON:
{{
  "is_valid": true/false,
  "issues": ["list of any problems found, or empty list"],
  "fixes_applied": ["list of auto-corrections made, or empty list"]
}}"""
