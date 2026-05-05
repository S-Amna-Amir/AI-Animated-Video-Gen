# AgenticAI — Phase 1: Story, Script & Character Design

## Overview

Phase 1 is the **creative foundation** of the AI-Powered Animated Video Generation System. It accepts a single free-form natural language prompt and autonomously produces a fully validated JSON pipeline state containing:

- **Story structure** — title, logline, genre, tone, 3–4 acts, protagonist/antagonist
- **Character roster** — names, roles, visual descriptions, voice configs (consumed by Phase 2)
- **Scene-by-scene script** — dialogue, visual cues, camera angles, image generation prompts (consumed by Phase 3)
- **Downstream handoff files** — `phase2_audio_handoff.json` and `phase3_video_handoff.json`

All output is validated against a shared Pydantic schema that acts as the inter-phase contract.

---

## Architecture

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│          LangGraph Pipeline (Phase 1)        │
│                                             │
│  story_node ──► character_node ──►          │
│  script_node ──► validate_node              │
│                                             │
│  Each node: TextGeneratorTool / JsonStructurer │
│  Error handler: auto-retry (max 2)          │
└─────────────────────────────────────────────┘
    │
    ▼
Phase1Output (Pydantic validated)
    │
    ├── story.json
    ├── characters.json
    ├── script.json
    ├── phase2_audio_handoff.json  ──► Phase 2
    ├── phase3_video_handoff.json  ──► Phase 3
    ├── summary.json               ──► Phase 4 dashboard
    └── phase1_output.json         (full consolidated state)
```

### LangGraph Nodes

| Node | Responsibility | Tools Used |
|------|---------------|-----------|
| `story_node` | Expand prompt into full narrative arc | `JsonStructurerTool` |
| `character_node` | Design character roster with voice configs | `TextGeneratorTool` |
| `script_node` | Write scene-by-scene script with visual prompts | `TextGeneratorTool` |
| `validate_node` | Consistency check (local + LLM-powered) | `TextGeneratorTool` |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API key

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run Phase 1

```bash
# With a prompt argument
python run_phase1.py "A brave knight must retrieve a stolen dragon egg"

# With scene count
python run_phase1.py "Space explorers find an ancient alien city" --scenes 5

# Interactive mode
python run_phase1.py --interactive
```

---

## Output Files

All artefacts are saved to `data/outputs/`:

| File | Description | Consumed By |
|------|-------------|------------|
| `story.json` | Narrative structure | All phases |
| `characters.json` | Character roster | All phases |
| `script.json` | Scene-by-scene script | Phase 3 |
| `phase2_audio_handoff.json` | Voice config map | Phase 2 |
| `phase3_video_handoff.json` | Visual prompts + camera | Phase 3 |
| `summary.json` | Run status, errors, tool log | Phase 4 |
| `phase1_output.json` | Full consolidated state | All phases |

---

## JSON Schema

### `Phase1Output` (root)

```json
{
  "workflow_id": "workflow_20260501_120000",
  "timestamp": "2026-05-01T12:00:00",
  "user_prompt": "...",
  "story": { ... },
  "characters": [ ... ],
  "scenes": [ ... ],
  "phase2_audio_handoff": { ... },
  "phase3_video_handoff": { ... },
  "summary": { ... }
}
```

### `Character`

```json
{
  "name": "ARIA",
  "role": "protagonist",
  "personality": "...",
  "appearance": "...",
  "style_reference": "Anime cinematic, vibrant colors",
  "voice_config": {
    "tone": "warm",
    "speed": 1.0,
    "pitch": "medium",
    "emotion": "curious"
  },
  "first_appearance": 1,
  "dialogue_samples": []
}
```

### `Scene`

```json
{
  "scene_id": 1,
  "location": "MARS SURFACE",
  "setting_description": "...",
  "mood": "mysterious",
  "tone": "...",
  "dialogue": [
    {
      "speaker": "ARIA",
      "line": "There's water. There's actually water.",
      "visual_cue": "Close-up of ARIA, eyes wide with wonder.",
      "emotion": "amazed"
    }
  ],
  "characters": ["ARIA"],
  "duration_seconds": 25,
  "visual": {
    "image_prompt": "Astronaut on Mars surface, glowing ocean below...",
    "camera_angle": "wide shot",
    "lighting": "dramatic blue glow",
    "color_palette": "red and blue contrast",
    "transition_in": "fade",
    "transition_out": "cut"
  }
}
```

---

## Running Tests

```bash
pytest agents/story_agent/tests/test_story_agent.py -v
```

16 tests covering:
- Pydantic schema validation (field bounds, required fields)
- `JsonStructurerTool` fence-stripping and parse logic
- `FileTool` read/write operations
- Full `StoryAgent.run()` with mocked LLM calls
- Edge cases: empty prompt, invalid `num_scenes`

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Agent Framework | LangGraph `StateGraph` with `MemorySaver` checkpointer |
| Schema Validation | Pydantic v2 |
| MCP Tools | `TextGeneratorTool`, `JsonStructurerTool`, `FileTool`, `LoggerTool` |
| Testing | pytest + pytest-mock |

---

## File Structure

```
phase1/
├── run_phase1.py                    # CLI entry point
├── requirements.txt
├── README.md
├── shared/
│   └── schemas/
│       └── phase1_schema.py         # Shared Pydantic contract
├── mcp/
│   ├── base_tool.py
│   └── tools/
│       ├── llm_tools/
│       │   ├── text_generator.py    # Claude API wrapper
│       │   └── json_structurer.py   # Schema-enforced JSON generator
│       └── system_tools/
│           ├── file_tool.py
│           └── logger_tool.py
├── agents/
│   └── story_agent/
│       ├── agent.py                 # Main StoryAgent class
│       ├── planner.py               # LangGraph nodes + graph builder
│       ├── prompts.py               # All system + user prompt templates
│       └── tests/
│           └── test_story_agent.py  # 16 unit tests
└── data/
    └── outputs/                     # Generated artefacts
```
