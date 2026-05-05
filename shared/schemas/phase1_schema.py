"""
Phase 1 Shared Pydantic Schema
Defines the validated JSON contract consumed by all downstream phases.
"""

from __future__ import annotations
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
import re


# ─────────────────────────────────────────────
# Character Models
# ─────────────────────────────────────────────

class VoiceConfig(BaseModel):
    """Voice parameters consumed directly by Phase 2 TTS."""
    tone: str = Field(..., description="e.g. 'warm', 'authoritative', 'nervous'")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: str = Field(default="medium", description="low / medium / high")
    emotion: str = Field(default="neutral", description="dominant emotional register")


class Character(BaseModel):
    name: str
    role: str = Field(..., description="protagonist / antagonist / supporting / narrator")
    personality: str
    appearance: str = Field(..., description="Visual description for image generation")
    style_reference: str = Field(..., description="Artistic/visual style cue for image gen")
    voice_config: VoiceConfig
    first_appearance: int = Field(..., description="Scene number where character first appears")
    dialogue_samples: Optional[List[Any]] = []

    @field_validator("dialogue_samples", mode="before")
    @classmethod
    def normalize_dialogue_samples(cls, v):
        """Accept both plain strings and dicts — normalize everything to dicts."""
        if not v:
            return []
        result = []
        for item in v:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                result.append({"line": item, "visual_cue": ""})
            else:
                result.append({"line": str(item), "visual_cue": ""})
        return result


# ─────────────────────────────────────────────
# Scene Models
# ─────────────────────────────────────────────

class DialogueLine(BaseModel):
    speaker: str
    line: str
    visual_cue: str = Field(default="medium shot", description="Camera angle / expression instruction for video gen")
    emotion: Optional[str] = "neutral"


class SceneVisual(BaseModel):
    """Visual prompt data consumed by Phase 3 image generation."""
    image_prompt: str = Field(..., description="Full Stable Diffusion / DALL-E prompt")
    camera_angle: str = Field(default="medium shot")
    lighting: str = Field(default="natural")
    color_palette: str = Field(default="neutral")
    transition_in: str = Field(default="cut")
    transition_out: str = Field(default="cut")


class Scene(BaseModel):
    scene_id: int
    location: str
    setting_description: str
    mood: str = Field(..., description="Used by Phase 2 for BGM selection")
    tone: str
    dialogue: List[DialogueLine]
    characters: List[str]
    duration_seconds: int = Field(..., ge=5, description="Estimated scene length in seconds")
    visual: SceneVisual


# ─────────────────────────────────────────────
# Story / Narrative Models
# ─────────────────────────────────────────────

class Act(BaseModel):
    act: int
    label: str
    description: str


class Story(BaseModel):
    title: str
    logline: str
    genre: str
    tone: str
    setting: str
    time_period: str
    themes: List[str]
    acts: List[Act]
    protagonist: str
    antagonist: Optional[str] = None
    world: str


# ─────────────────────────────────────────────
# Root Pipeline State Schema
# ─────────────────────────────────────────────

class Phase1Output(BaseModel):
    """
    Top-level validated JSON object output by Phase 1.
    All downstream phases (2, 3, 4, 5) consume this schema.
    """
    workflow_id: str
    timestamp: str
    user_prompt: str
    story: Story
    characters: List[Character]
    scenes: List[Scene]

    # ── Handoff contracts ──────────────────────────────
    phase2_audio_handoff: Optional[dict] = Field(
        default=None,
        description="Pre-built voice config map keyed by character name for Phase 2"
    )
    phase3_video_handoff: Optional[dict] = Field(
        default=None,
        description="Visual prompt list and camera instructions for Phase 3"
    )
    summary: Optional[dict] = Field(
        default=None,
        description="Run metadata: status, errors, tool log, artifact paths"
    )

    @field_validator("scenes")
    @classmethod
    def at_least_one_scene(cls, v):
        if not v:
            raise ValueError("Phase 1 must produce at least one scene.")
        return v

    @field_validator("characters")
    @classmethod
    def at_least_one_character(cls, v):
        if not v:
            raise ValueError("Phase 1 must produce at least one character.")
        return v

    def to_phase2_handoff(self) -> dict:
        """Build the voice-config map consumed by Phase 2 audio agent."""
        return {
            char.name: {
                "voice_config": char.voice_config.model_dump(),
                "personality": char.personality,
                "appearance": char.appearance,
            }
            for char in self.characters
        }

    def to_phase3_handoff(self) -> dict:
        """Build the visual prompts list consumed by Phase 3 video agent."""
        return {
            "scenes": [
                {
                    "scene_id": scene.scene_id,
                    "location": scene.location,
                    "mood": scene.mood,
                    "visual": scene.visual.model_dump(),
                    "characters": scene.characters,
                    "duration_seconds": scene.duration_seconds,
                }
                for scene in self.scenes
            ]
        }
