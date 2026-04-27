# 🎬 AI-Animated-Video-Generation System

> From a single prompt to a complete short film — fully agentic, end-to-end, autonomous production.

![Status](https://img.shields.io/badge/Status-Phase%202%20Complete-brightgreen?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![Edge-TTS](https://img.shields.io/badge/Edge--TTS-Neural%20Voices-green?style=flat-square)
![Freesound](https://img.shields.io/badge/Freesound-BGM%20Integration-red?style=flat-square)

---

## 📖 Quick Navigation

- [🌟 Project Overview](#-project-overview)
- [📋 Phase Status](#-phase-status)  
- [🎤 Phase 2: Audio Generation](#-phase-2-audio-generation--integration) ← **COMPLETE**
- [🛠 Setup & Installation](#-setup--installation)
- [🚀 Running the Pipeline](#-running-the-pipeline)
- [📁 Project Structure](#-project-structure)

---

## 🌟 Project Overview

**AI-Animated-Video-Generation** is a multi-phase, LangGraph-based agentic system that orchestrates end-to-end video creation from a single natural-language prompt:

```
User Prompt
    ↓
[Phase 1] Story & Script Generation (LLM)
    ↓
[Phase 2] Audio Generation & BGM Integration ✅
    ↓
[Phase 3] Video Composition (Future)
    ↓
[Phase 4] Web Interface & Orchestration (Future)
    ↓
[Phase 5] Edit Agent & Undo System (Future)
    ↓
Final MP4 Output
```

Each phase is an independent agentic module that:
- Reads structured JSON input from previous phase
- Processes through orchestrated agents
- Outputs validated JSON for downstream phases
- Supports re-running in isolation

---

## 📋 Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ⏳ Pending | LLM-based story & script generation |
| **Phase 2** | ✅ **COMPLETE** | Audio synthesis with BGM layering |
| **Phase 3** | ⏳ Pending | Image generation & video composition |
| **Phase 4** | ⏳ Pending | Web dashboard & orchestration |
| **Phase 5** | ⏳ Pending | Edit agent & versioned undo system |

---

## 🎤 Phase 2: Audio Generation & Integration

**Status**: ✅ **FULLY IMPLEMENTED & TESTED**

Phase 2 transforms Phase 1 narrative outputs into high-quality synchronized audio with atmospheric background music. Each scene receives:

1. **Character Voiceovers** - TTS with unique neural voices per character
2. **Background Music** - Scene-mood-based ambient audio via Freesound API
3. **Audio Composition** - Voice + BGM mixing with ducking and smooth transitions
4. **Timing Manifest** - Millisecond-accurate A/V sync data for Phase 3

### Key Capabilities

#### 🎭 Character Voice Mapping
- **15+ Unique Voices** - Microsoft Edge-TTS neural voices
- **Per-Character Consistency** - Same character always uses same voice
- **Automatic Gender Detection** - Unknown characters assigned appropriate voice
- **Custom Mappings** - Override defaults with custom assignments

**Example Voice Assignments**:
```
JACK      → en-US-GuyNeural (American male)
RACHEL    → en-US-AriaNeural (American female)
VLADIMIR  → en-GB-OliverNeural (British male - authority for Russian character)
ALEXANDRA → en-GB-SoniaNeural (British female)
```

#### 🎵 Background Music Integration
- **Freesound API Search** - Queries for mood-based ambient audio
- **LLM Mood Analysis** - Groq generates 3-word search queries from scene descriptions
  - Example: "dark synth ambient" for tense scenes
- **Fallback Support** - Uses default neutral BGM if search fails
- **Smart Looping** - Automatically loops short BGM clips to match dialogue duration

#### 🔊 Per-Scene Audio Composition
- **Volume Ducking** - BGM reduced to -20dB during dialogue
- **Fade Transitions** - 500ms fade-in/fade-out for smooth scene changes
- **FFmpeg Integration** - Professional-grade audio mixing
- **Graceful Degradation** - Works with or without BGM/FFmpeg

#### 📁 Organized Output Structure
```
data/outputs/Phase2/
├── run_01/                    ← Sequential numbering
│   ├── audio/
│   │   ├── scene01/           ← Per-scene directories
│   │   │   ├── JACK_line001.mp3
│   │   │   ├── RACHEL_line002.mp3
│   │   │   └── bgm.mp3
│   │   ├── scene02/
│   │   └── ...
│   ├── timing_manifest.json   ← A/V sync metadata
│   ├── bgm_metadata.json      ← Freesound details per scene
│   ├── master_audio_track.mp3 ← Concatenated final audio
│   ├── phase2_summary.json
│   └── phase2_config.json
├── run_02/
└── ...
```

#### ⏱ Timing Manifest Format
```json
[
  {
    "scene_id": 1,
    "speaker": "JACK",
    "audio_file": "data/outputs/Phase2/run_01/audio/scene01/JACK_line001.mp3",
    "duration_ms": 2250,
    "line_index": 1,
    "text": "We can't keep her here for much longer, Rachel. The KGB will find her.",
    "voice": "en-US-GuyNeural",
    "bgm_used": true,
    "bgm_info": {
      "query": "dark synth ambient",
      "source": "freesound",
      "name": "Dark Ambient Synth Loop",
      "freesound_id": 123456
    }
  }
]
```

### Module Architecture

```
mcp/tools/audio_tools/
├── voice_mapper.py        → Character-to-voice assignment
├── tts_tool.py           → Edge-TTS synthesis engine
├── bgm_tool.py           → Freesound API integration
├── scene_mood_analyzer.py → LLM-based mood analysis
└── audio_composer.py     → FFmpeg mixing & ducking

agents/audio_agent/
├── agent.py              → Basic audio-only agent
├── enhanced_agent.py     → Full BGM-integrated agent ✨
├── run_manager.py        → Run directory management
├── planner.py           → Workflow orchestration
└── PHASE2_IMPLEMENTATION.md → Detailed technical docs
```

### Usage Examples

#### Basic Usage
```python
import asyncio
from agents.audio_agent.enhanced_agent import run_enhanced_audio_agent

# Run with all features
results = asyncio.run(run_enhanced_audio_agent(
    phase1_dir="data/outputs/Phase1",
    phase2_dir="data/outputs/Phase2",
    freesound_api_key="your_api_key_here"  # Optional
))

print(f"Generated {results['audio_files_generated']} audio files")
print(f"Scenes with BGM: {results['scenes_with_bgm']}")
print(f"Master track: {results['master_audio_track']}")
```

#### Test with Dummy Data
```bash
python scripts/test_phase2.py
```

### Configuration

#### Environment Variables
```bash
FREESOUND_API_KEY=your_api_key_here     # Optional for Freesound search
GROQ_API_KEY=your_groq_key              # Optional for mood analysis
```

#### Custom Voice Mappings
```python
custom_voices = {
    "VILLAIN": "en-GB-RyanNeural",
    "HERO": "en-US-GuyNeural",
    "NARRATOR": "en-US-ArthurNeural"
}

agent = EnhancedAudioAgent(
    custom_voice_mappings=custom_voices
)
```

### Performance

**Benchmark (4 scenes, 17 dialogues)**:
- TTS Synthesis: ~5 minutes
- BGM Search & Download: ~30 seconds per scene
- Audio Composition: ~2 minutes
- Master Concatenation: ~10 seconds
- **Total**: ~8 minutes (with BGM) / ~3 minutes (voice-only)

---

## 🛠 Setup & Installation

### Prerequisites
- Python 3.10+
- Virtual environment (recommended)
- FFmpeg (optional, for audio composition)
- Freesound API key (optional, for BGM)

### Installation Steps

```bash
# 1. Clone repository
git clone <repo_url>
cd AI-Animated-Video-Gen

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (optional)
cp .env.example .env
# Edit .env with your API keys

# 5. Install FFmpeg (optional)
# Ubuntu/Debian:
sudo apt-get install ffmpeg

# macOS:
brew install ffmpeg

# Windows: Download from https://ffmpeg.org/download.html
```

---

## 🚀 Running the Pipeline

### Test Phase 2
```bash
python scripts/test_phase2.py
```

### Run Phase 2 Programmatically
```python
import asyncio
from agents.audio_agent.enhanced_agent import run_enhanced_audio_agent

async def main():
    results = await run_enhanced_audio_agent()
    print(results)

asyncio.run(main())
```

---

## 📁 Project Structure

```
AI-Animated-Video-Gen/
├── README.md                          ← You are here
├── requirements.txt
├── .env                              # API keys (not committed)
│
├── agents/
│   └── audio_agent/                  # Phase 2 ✅
│       ├── __init__.py
│       ├── agent.py                  # Basic agent
│       ├── enhanced_agent.py         # BGM-integrated agent ✨
│       ├── run_manager.py            # Run management
│       ├── planner.py               # Workflow planning
│       ├── PHASE2_IMPLEMENTATION.md  # Full technical docs
│       └── tests/
│
├── mcp/tools/audio_tools/
│   ├── __init__.py
│   ├── voice_mapper.py               # Voice mapping
│   ├── tts_tool.py                  # TTS engine
│   ├── bgm_tool.py                  # Freesound integration
│   ├── scene_mood_analyzer.py       # Mood analysis
│   └── audio_composer.py            # Audio mixing
│
├── data/
│   ├── outputs/
│   │   ├── Phase1/                   # Phase 1 outputs (when ready)
│   │   │   ├── scene_manifest_auto.json
│   │   │   └── character_db_auto.json
│   │   │
│   │   └── Phase2/                   # Phase 2 outputs ✅
│   │       ├── run_01/
│   │       ├── run_02/
│   │       └── ...
│   │
│   ├── bgm_library/                  # Local BGM fallback
│   │   └── neutral_ambient.mp3
│   │
│   └── cache/
│       └── scene_mood_cache.json     # Mood analysis cache
│
├── scripts/
│   └── test_phase2.py               # Phase 2 test script
│
├── shared/
│   ├── schemas/
│   ├── utils/
│   └── constants/
│
└── docs/
    └── requirements/                # Project requirements
```

---

## 🔄 Data Flow

```
Phase 1 JSON Outputs
├── scene_manifest.json
│   └── scenes[] {scene_id, location, dialogue[]{speaker, line}}
└── character_db.json
    └── characters[] {name, role, personality}
         ↓
Phase 2 Processing
├─→ Voice Mapper: character → unique voice
├─→ TTS: dialogue → MP3 files (scene01/, scene02/, ...)
├─→ Mood Analyzer: scene → "3-word bgm query"
├─→ Freesound: query → ambient audio download
├─→ Composer: voice + BGM → per-scene composition
└─→ Concatenator: scenes → master_audio_track.mp3
         ↓
Phase 2 JSON Outputs
├── timing_manifest.json (millisecond A/V sync)
├── bgm_metadata.json (Freesound details per scene)
├── phase2_summary.json (execution report)
├── audio/scene01/*.mp3 (individual dialogue files)
└── master_audio_track.mp3 (final concatenated audio)
         ↓
Phase 3 (Video Composition) - Future
└─→ Uses timing_manifest.json for image-audio alignment
```

---

## 🔗 Detailed Documentation

- [Phase 2 Full Technical Implementation](agents/audio_agent/PHASE2_IMPLEMENTATION.md)
- [Project Requirements](docs/Requirements/)

---

## 📝 Phase 1: Story & Script (Future)

Placeholder for Phase 1 implementation details.