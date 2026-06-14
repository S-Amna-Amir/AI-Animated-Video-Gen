"""
shared/schemas/state.py
-----------------------
Central state schema for the entire Project Montage pipeline.
All agents and LangGraph nodes read from and write to this TypedDict.
"""
from typing import TypedDict, List, Optional, Any, Dict


class CharacterProfile(TypedDict):
    name: str
    personality: str
    appearance: str
    style_reference: str
    image_path: Optional[str]


class DialogueLine(TypedDict):
    speaker: str
    line: str
    visual_cue: str


class Scene(TypedDict):
    scene_id: int
    location: str
    characters: List[str]
    dialogue: List[DialogueLine]
    action_description: str


class SceneManifest(TypedDict):
    title: str
    genre: str
    total_scenes: int
    scenes: List[Scene]


class MemoryLogEntry(TypedDict):
    timestamp: str
    collection: str
    doc_id: str
    summary: str


class ProjectState(TypedDict):
    """
    Master pipeline state. Populated progressively as each phase executes.
    Phases 1-5 all extend this same object.
    """
    # ── Input ──────────────────────────────────────────────────────────────
    input_mode: str          # 'manual' | 'auto'
    raw_input: str

    # ── Phase 1 outputs ────────────────────────────────────────────────────
    script: SceneManifest
    characters: List[CharacterProfile]
    images: List[str]        # file paths to generated character images

    # ── Control flow ───────────────────────────────────────────────────────
    validation_errors: List[str]
    hitl_approved: bool
    status: str              # 'processing' | 'complete' | 'failed'
    error_message: Optional[str]

    # ── Audit / memory ─────────────────────────────────────────────────────
    memory_log: List[MemoryLogEntry]
