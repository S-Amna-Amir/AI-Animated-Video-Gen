# Project Montage — AI-Powered Animated Video Generation

> From a single natural-language prompt to a polished short animated video — end-to-end with LLM agents.

**Course:** Agentic AI 2026 | **NUCES Islamabad**

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/AgenticAI_Project_<GroupName>.git
cd AgenticAI_Project_<GroupName>

# 2. Create a virtual environment (Python 3.11 or 3.12 recommended)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and fill in at minimum: GROQ_API_KEY
```

---

## Environment Variables

| Variable | Required | Used In | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ | Phase 1, 2 | LLM script generation + mood analysis |
| `HF_API_TOKEN` | Phase 3 only | Phase 3 | Hugging Face image generation |
| `FREESOUND_API_KEY` | Optional | Phase 2 | BGM search — falls back to `data/bgm_library/neutral_ambient.mp3` |
| `OPENAI_API_KEY` | Optional | Phase 1 | DALL-E character images — falls back to placeholder PNG |
| `MEMORY_BACKEND` | Optional | All | `chromadb` (default) or `mock` (no install needed) |
| `WAV2LIP_CHECKPOINT` | Optional | Phase 3 | Path to `wav2lip_gan.pth` for real lip sync |
| `WAV2LIP_REPO_PATH` | Optional | Phase 3 | Path to cloned Wav2Lip repo |

---

## Running Each Phase

### Phase 1 — Story, Script & Character Design

Generates a screenplay from a prompt (or validates an uploaded one), builds character profiles, and generates reference images.

```bash
# Auto mode: LLM generates script from your prompt
python main.py --phase 1 --mode auto --prompt "A spy thriller set in 1960s Berlin"

# Manual mode: validate and parse your own screenplay
python main.py --phase 1 --mode manual --file my_screenplay.txt

# Interactive mode (prompts you to choose)
python main.py
```

**Outputs** written to `data/outputs/`:

```
data/outputs/
├── scene_manifest.json   ← structured screenplay (consumed by Phase 2 & 3)
├── character_db.json     ← character profiles
├── memory_log.json       ← audit trail
└── images/               ← character reference PNGs
```

---

### Phase 2 — Audio Generation

Synthesises dialogue with Edge-TTS (free, no key needed), layers background music via Freesound, and produces a master audio track + timing manifest.

```bash
# Standard run (reads from data/outputs/)
python scripts/test_phase2.py --phase1-dir data/outputs

# Custom output directory
python scripts/test_phase2.py --phase1-dir data/outputs --phase2-dir data/outputs/Phase2

# Optional: place a fallback BGM file for offline use
mkdir -p data/bgm_library
cp your_ambient_track.mp3 data/bgm_library/neutral_ambient.mp3
```

**Outputs** written to `data/outputs/Phase2/run_XX/`:

```
data/outputs/Phase2/run_01/
├── timing_manifest.json  ← A/V sync map (consumed by Phase 3)
├── master_audio_track.mp3
├── phase2_summary.json
├── bgm_metadata.json
└── audio/
    └── scene01/          ← per-line MP3 files
```

---

### Phase 3 — Video Generation & Composition

Generates one image per dialogue line (via Hugging Face), animates each with Ken Burns effects, and composes the final MP4.

```bash
# ── Recommended for testing (no HF token used) ────────────────────────────
# Short mode: 1 scene, 3 lines, mock (black placeholder) images
python scripts/run_phase3_short.py --mock --phase1-dir data/outputs

# Short mode with real HF images (uses token, ~3 images)
python scripts/run_phase3_short.py --phase1-dir data/outputs

# ── Full pipeline ─────────────────────────────────────────────────────────
# All scenes, mock images
python scripts/run_phase3.py --mock --phase1-dir data/outputs

# All scenes, real HF images
python scripts/run_phase3.py --phase1-dir data/outputs

# With subtitle burn-in
python scripts/run_phase3.py --phase1-dir data/outputs --use-subtitles

# Specify a Phase 2 run manually (otherwise auto-detects latest)
python scripts/run_phase3.py --phase1-dir data/outputs --phase2-run data/outputs/Phase2/run_01
```

**Outputs** written to `data/outputs/Phase3/run_XX/`:

```
data/outputs/Phase3/run_01/
├── final_output.mp4          ← the finished video
├── phase3_output.json
├── phase3_video_handoff.json ← consumed by Phase 4 web interface
├── images/                   ← scene_N_line_M.png files
└── clips/                    ← per-dialogue animated MP4 clips
```

---

### Phase 4 — Web Interface

Full-stack FastAPI + React web application. Runs all phases from the browser with live log streaming over WebSocket.

```bash
# Install Phase 4 dependencies (if not already done)
pip install fastapi uvicorn[standard] websockets python-multipart aiofiles

# Start the server
python scripts/run_server.py

# Dev mode with hot-reload
python scripts/run_server.py --reload

# Custom port
python scripts/run_server.py --port 8080
```

Open **http://localhost:8000** in your browser.

| URL | Purpose |
|-----|---------|
| `http://localhost:8000` | Web UI |
| `http://localhost:8000/docs` | Auto-generated API docs (Swagger) |

**API endpoints:**

```
POST /api/pipeline/phase1         start Phase 1 job
POST /api/pipeline/phase2         start Phase 2 job
POST /api/pipeline/phase3         start Phase 3 job (full)
POST /api/pipeline/phase3/short   start Phase 3 job (1 scene)
GET  /api/pipeline/status/{id}    poll job status
WS   /api/pipeline/ws/{id}        stream live logs

GET  /api/runs/phase2             list Phase 2 runs
GET  /api/runs/phase2/latest      latest Phase 2 run
GET  /api/runs/phase3             list Phase 3 runs
GET  /api/runs/phase3/latest      latest Phase 3 run

GET  /api/files/video/{run_id}    stream final MP4
GET  /api/files/audio/{run_id}    stream master audio
GET  /api/files/scene-manifest    Phase 1 scene manifest JSON
GET  /api/files/character-db      Phase 1 character DB JSON

POST /api/edit/apply              apply free-text edit
POST /api/edit/undo/{version}     revert to snapshot
GET  /api/edit/history            list all versions
GET  /api/edit/history/{version}  version detail
GET  /api/edit/diff/{v1}/{v2}     diff two versions
WS   /api/edit/ws/{job_id}        stream edit job logs
```

---

### Phase 5 — Intelligent Edit & Undo

Apply natural language edits to any pipeline output. The agent classifies intent, re-runs only the affected phase, and saves a version snapshot before and after every edit.

```bash
# The edit agent runs through the web interface (Phase 4 server must be running)
python scripts/run_server.py
# Then open http://localhost:8000 → "Phase 5 — Edit" in the sidebar

# Or run edits directly from the command line
python scripts/run_edit.py "Make the scene darker"
python scripts/run_edit.py "Change voice tone"
python scripts/run_edit.py "Regenerate the script"

# Revert to a specific version
python scripts/run_edit.py --undo 3

# List version history
python scripts/run_edit.py --history
```

**Supported edit intents (10 required by spec):**

| Example Query | Detected Target | Action |
|---------------|----------------|--------|
| "Change voice tone" | audio | Re-run TTS for all scenes |
| "Make the scene darker" | video_frame | Re-generate images with dark aesthetic |
| "Add background music" | audio | Re-fetch BGM + recompose |
| "Remove the subtitle" | video | Recompose without subtitle burn |
| "Change character design" | video_frame | Re-generate all character images |
| "Speed up this scene" | video | Recompose with speed factor |
| "Regenerate the script" | script | Re-run Phase 1 + full cascade |
| "Make scene 2 brighter" | video_frame | Re-gen images for scene 2 only |
| "Add subtitle overlay" | video | Recompose with subtitle burn |
| "Change transition style" | video | Recompose with different transitions |

**Version snapshots** are stored in `data/state_versions/`:

```
data/state_versions/
├── index.json            ← version index (never deleted)
├── v001_20260101_120000.json
├── v002_20260101_120500.json
└── ...
```

---

## Running Tests

```bash
# Phase 1 tests
MEMORY_BACKEND=mock pytest agents/story_agent/test/ -v

# Phase 5 tests (intent classification + state manager)
MEMORY_BACKEND=mock pytest agents/edit_agent/test/ -v

# All tests
MEMORY_BACKEND=mock pytest -v
```

---

## Project Structure

```
project/
├── agents/
│   ├── orchestrator/           Phase 1 LangGraph workflow
│   │   ├── graph.py            StateGraph definition
│   │   ├── state.py            State re-exports
│   │   └── workflow.py         run_phase1() entry point
│   ├── story_agent/            Phase 1 LangGraph nodes
│   │   ├── agent.py            scriptwriter, validator, hitl, character, image, memory_commit nodes
│   │   ├── planner.py          script parsing + character helpers
│   │   └── test/               Phase 1 unit tests
│   ├── audio_agent/            Phase 2
│   │   ├── agent.py            EnhancedAudioAgent (TTS + BGM + MoviePy)
│   │   ├── enhanced_agent.py   re-export shim
│   │   ├── planner.py          AudioPhasePlanner + DialogueExtractor
│   │   └── run_manager.py      sequential run_XX directories
│   ├── video_agent/            Phase 3
│   │   ├── agent.py            VideoAgent (images → animation → composition)
│   │   └── run_manager.py      VideoRunManager
│   └── edit_agent/             Phase 5
│       ├── agent.py            EditAgent orchestrator
│       ├── intent_classifier.py LLM + keyword intent classification
│       ├── planner.py          EditPlanner (intent → re-run plan)
│       ├── executor.py         EditExecutor (runs each step)
│       └── test/               Phase 5 unit tests (25 tests)
├── backend/                    Phase 4 FastAPI server
│   ├── app.py                  Application factory
│   ├── routes/
│   │   ├── pipeline.py         Phase 1-3 job endpoints + WebSocket
│   │   ├── edit.py             Phase 5 edit + undo endpoints
│   │   ├── runs.py             Run history endpoints
│   │   └── files.py            File serving (video, audio, images)
│   └── services/
│       └── job_store.py        In-process job registry
├── frontend/
│   └── dist/
│       └── index.html          Single-file React UI (no build step)
├── mcp/                        MCP tool layer
│   ├── base_tool.py            BaseTool abstract class
│   ├── tool_registry.py        Runtime tool discovery
│   ├── tool_executor.py        invoke_tool() dispatch
│   └── tools/
│       ├── llm_tools/          generate_script_segment, validate_script_structure
│       ├── system_tools/       commit_memory, query_memory, save_json_file
│       ├── audio_tools/        TTSTool, VoiceMapper, BGMTool, SceneMoodAnalyzer
│       └── video_tools/        image_generator, animator, video_compositor, lip_sync
├── shared/
│   ├── schemas/state.py        ProjectState TypedDict (single source of truth)
│   ├── constants/              Directory paths, status codes, LLM defaults
│   └── utils/                  JSON helpers, logging
├── state_manager/              Phase 5 state versioning
│   ├── state_manager.py        StateManager facade (snapshot/revert/history)
│   ├── snapshot.py             Asset collection + snapshot creation
│   ├── history.py              Version queries + diffs
│   └── storage.py              Append-only file store
├── scripts/
│   ├── test_phase2.py          Phase 2 CLI runner
│   ├── run_phase3.py           Phase 3 full CLI
│   ├── run_phase3_short.py     Phase 3 short test CLI
│   ├── run_edit.py             Phase 5 edit CLI
│   └── run_server.py           Phase 4 server entry point
├── data/
│   ├── outputs/                All phase outputs
│   ├── state_versions/         Version snapshots (Phase 5)
│   ├── bgm_library/            Fallback BGM files
│   └── temp/
├── main.py                     Phase 1 CLI entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## Technology Stack

| Layer | Primary | Budget / Local Alternative |
|-------|---------|---------------------------|
| LLM / Agents | Groq + LLaMA 3.3 70B, LangGraph | Ollama + LLaMA 3 |
| Image Gen | Hugging Face FLUX.1-schnell | Stable Diffusion (local) / Pillow placeholder |
| TTS | Microsoft Edge-TTS (free) | pyttsx3, gTTS |
| BGM | Freesound API | Local `neutral_ambient.mp3` |
| Video | FFmpeg + MoviePy | FFmpeg only |
| Memory | ChromaDB | In-process mock store |
| Backend | FastAPI + Uvicorn | Django |
| Frontend | React (CDN, no build) | — |
| State Store | File-based JSON snapshots | SQLite (LangGraph SqliteSaver) |

---

## Evaluation Criteria

| Criterion | Weight |
|-----------|--------|
| Phase 1 — Story & Script | 15% |
| Phase 2 — Audio Generation | 15% |
| Phase 3 — Video Composition | 20% |
| Phase 4 — Web Interface | 10% |
| Integration & Pipeline | 10% |
| Report & Presentation | 10% |
| Phase 5 — Edit Agent & Undo | 20% |

---

## Shared JSON Schema

All phases communicate via `ProjectState` (`shared/schemas/state.py`):

```
SceneManifest  { title, genre, total_scenes, scenes[] }
Scene          { scene_id, location, characters[], dialogue[], action_description }
DialogueLine   { speaker, line, visual_cue }
CharacterProfile { name, personality, appearance, style_reference, image_path }
```

Phase 2 adds: `timing_manifest.json` `{ scene_id, speaker, text, audio_file, start_ms, end_ms, duration_ms }`

Phase 3 adds: `phase3_video_handoff.json` `{ final_video_path, scenes[], run_id }`

Phase 5 adds: `data/state_versions/index.json` `{ version, timestamp, description, edit_query, asset_count }`
