AgenticAI_Project_<GroupName>/
│
├── README.md
├── requirements.txt
├── .env
├── .gitignore
│
├── docs/
├── data/
│   ├── outputs/
│   ├── temp/
│   └── state_versions/
│
├── shared/
│   ├── schemas/
│   ├── utils/
│   └── constants/
│
├── mcp/                              # 🧩 MCP Layer (Tool Abstraction)
│   ├── base_tool.py                  # Base Tool Interface
│   ├── tool_registry.py              # Register & discover tools
│   ├── tool_executor.py              # Executes tools dynamically
│   │
│   ├── tools/                        # 🔧 Actual Tools
│   │   ├── llm_tools/
│   │   │   ├── text_generator.py
│   │   │   └── json_structurer.py
│   │   │
│   │   ├── audio_tools/
│   │   │   ├── tts_tool.py
│   │   │   ├── bgm_tool.py
│   │   │   └── audio_merger.py
│   │   │
│   │   ├── vision_tools/
│   │   │   ├── image_gen_tool.py
│   │   │   ├── image_edit_tool.py
│   │   │   └── style_transfer.py
│   │   │
│   │   ├── video_tools/
│   │   │   ├── ffmpeg_tool.py
│   │   │   ├── compositor_tool.py
│   │   │   └── subtitle_tool.py
│   │   │
│   │   └── system_tools/
│   │       ├── file_tool.py
│   │       ├── state_tool.py
│   │       └── logger_tool.py
│
├── agents/                           # 🤖 Agents use MCP tools
│   ├── orchestrator/
│   │   ├── graph.py
│   │   ├── workflow.py
│   │   └── state.py
│   │
│   ├── story_agent/                  # Phase 1
│   │   ├── agent.py                  # Uses LLM tools
│   │   ├── planner.py
│   │   └── tests/
│   │
│   ├── audio_agent/                  # Phase 2
│   │   ├── agent.py                  # Uses TTS + BGM tools
│   │   └── tests/
│   │
│   ├── video_agent/                  # Phase 3
│   │   ├── agent.py                  # Uses vision + video tools
│   │   └── tests/
│   │
│   └── edit_agent/                   # Phase 5 ⭐
│       ├── agent.py
│       ├── intent_classifier.py
│       ├── planner.py
│       ├── executor.py               # Calls MCP tools
│       └── tests/
│
├── backend/
│   ├── app.py
│   ├── routes/
│   ├── services/
│   └── websocket/
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── state_manager/
│   ├── state_manager.py
│   ├── snapshot.py
│   ├── history.py
│   └── storage.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── scripts/