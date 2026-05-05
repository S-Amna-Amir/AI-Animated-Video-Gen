"""
Story Agent — Phase 1 Main Entry Point

Usage:
    from agents.story_agent.agent import StoryAgent

    agent = StoryAgent()
    result = agent.run("A young astronaut discovers a hidden ocean on Mars")
    print(result.story.title)
"""

from __future__ import annotations
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Resolve project root ──────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.story_agent.planner import build_graph, Phase1State
from mcp.tools.system_tools.file_tool import FileTool
from mcp.tools.system_tools.logger_tool import LoggerTool
from shared.schemas.phase1_schema import (
    Phase1Output, Story, Character, Scene,
)


class StoryAgent:
    """
    Phase 1 agent: Story, Script & Character Design.

    Wraps the LangGraph pipeline and handles:
    - Input validation
    - Graph execution
    - Output serialisation to Phase1Output Pydantic model
    - Artefact persistence (story.json, characters.json, script.json,
      phase2_audio_handoff.json, phase3_video_handoff.json, summary.json)
    """

    OUTPUT_DIR = Path("data/outputs/Phase1")

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else self.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._graph = build_graph()
        self._file_tool = FileTool()
        self._logger = LoggerTool()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        user_prompt: str,
        num_scenes: int = 4,
        workflow_id: Optional[str] = None,
    ) -> Phase1Output:
        """
        Execute the full Phase 1 pipeline.

        Args:
            user_prompt: Free-form story idea from the user.
            num_scenes:  How many scenes to generate (default 4).
            workflow_id: Optional ID; auto-generated if not provided.

        Returns:
            Phase1Output: Fully validated Pydantic model containing story,
                          characters, scenes, and downstream handoff data.
        """
        if not user_prompt or not user_prompt.strip():
            raise ValueError("user_prompt must not be empty.")
        if not (2 <= num_scenes <= 8):
            raise ValueError("num_scenes must be between 2 and 8.")

        wid = workflow_id or f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._logger.run("info", "StoryAgent.run: starting", workflow_id=wid)

        # ── Execute LangGraph ─────────────────────────────────────────────────
        initial_state: Phase1State = {
            "user_prompt": user_prompt.strip(),
            "num_scenes": num_scenes,
            "story": None,
            "characters": None,
            "scenes": None,
            "validation_result": None,
            "retry_count": 0,
            "errors": [],
            "tool_log": [],
            "status": "running",
        }

        config = {"configurable": {"thread_id": wid}}
        final_state = self._graph.invoke(initial_state, config=config)

        # ── Handle failures ───────────────────────────────────────────────────
        # Only hard-fail if core outputs are actually missing
        if not final_state.get("story") or not final_state.get("characters") or not final_state.get("scenes"):
            errors = final_state.get("errors", [])
            raise RuntimeError(
                f"Phase 1 pipeline failed — missing core outputs. Errors: {errors}"
            )

        # ── Build validated Phase1Output ──────────────────────────────────────
        output = self._build_output(
            wid=wid,
            user_prompt=user_prompt,
            state=final_state,
        )

        # ── Persist artefacts ─────────────────────────────────────────────────
        self._save_artifacts(wid, output, final_state)

        self._logger.run("info", "StoryAgent.run: complete", workflow_id=wid)
        return output

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _build_output(
        self,
        wid: str,
        user_prompt: str,
        state: Phase1State,
    ) -> Phase1Output:
        """Assemble and validate the final Phase1Output from graph state."""
        story = Story(**state["story"])
        characters = [Character(**c) for c in state["characters"]]
        scenes = [Scene(**s) for s in state["scenes"]]

        output = Phase1Output(
            workflow_id=wid,
            timestamp=datetime.now().isoformat(),
            user_prompt=user_prompt,
            story=story,
            characters=characters,
            scenes=scenes,
            summary={
                "status": state.get("status", "success"),
                "errors": state.get("errors", []),
                "tool_log": state.get("tool_log", []),
                "validation": state.get("validation_result", {}),
                "total_scenes": len(scenes),
                "total_characters": len(characters),
                "estimated_total_seconds": sum(s.duration_seconds for s in scenes),
            },
        )

        # Attach handoff payloads
        output.phase2_audio_handoff = output.to_phase2_handoff()
        output.phase3_video_handoff = output.to_phase3_handoff()

        return output

    def _save_artifacts(self, wid: str, output: Phase1Output, state: Phase1State):
        """Write all artefacts to data/outputs/Phase1/ matching the expected folder structure."""
        base = self.output_dir  # data/outputs/Phase1

        # ── Phase1 original-format files (core of the expected output) ────────
        self._save_phase1_format_artifacts(wid, output)

        # ── character_db.json — minimal stub (id + name + traits) ─────────────
        char_db_stub = {
            "characters": [
                {
                    "id": f"char_{i+1}",
                    "name": c.name,
                    "traits": [w for w in c.personality.split()[:2]],
                    "appearance": c.appearance,
                    "reference_style": c.style_reference,
                    "visual_refs": [f"data\\image_assets\\{c.name}.svg"],
                }
                for i, c in enumerate(output.characters)
            ]
        }
        self._file_tool.run("write_json", str(base / "character_db.json"), char_db_stub)

        # ── character_db_manual.json — same schema, first 2 chars as sample ───
        char_db_manual = {
            "workflow_id": wid,
            "timestamp": output.timestamp,
            "characters": [
                {
                    "name": c.name,
                    "personality": c.personality,
                    "appearance": c.appearance,
                    "style_reference": c.style_reference,
                    "first_appearance": c.first_appearance,
                    "dialogue_samples": [
                        ds.get("line", "") if isinstance(ds, dict) else str(ds)
                        for ds in (c.dialogue_samples or [])
                    ],
                }
                for c in output.characters[:2]
            ],
            "total_characters": min(2, len(output.characters)),
        }
        self._file_tool.run("write_json", str(base / "character_db_manual.json"), char_db_manual)

        # ── scene_manifest_manual.json — first 2 scenes in simplified format ──
        scene_manifest_manual = {
            "workflow_id": wid,
            "timestamp": output.timestamp,
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "location": s.location,
                    "dialogue": [
                        {
                            "speaker": dl.speaker,
                            "line": dl.line,
                            "visual_cue": dl.visual_cue,
                        }
                        for dl in s.dialogue
                    ],
                    "characters": s.characters,
                    "duration": s.duration_seconds,
                }
                for s in output.scenes[:2]
            ],
            "total_scenes": min(2, len(output.scenes)),
        }
        self._file_tool.run("write_json", str(base / "scene_manifest_manual.json"), scene_manifest_manual)

        # ── mcp_registry.json — tool registry stub ────────────────────────────
        mcp_registry = {
            "tools": [
                {
                    "name": "groq_generate_script_segment",
                    "capability": "generate_script_segment",
                    "type": "groq_llm",
                    "config": {"model": "llama-3.3-70b-versatile", "temperature": 0.7},
                },
                {"name": "memory_commit", "capability": "commit_memory", "type": "memory_commit"},
                {"name": "query_stock_footage", "capability": "query_stock_footage", "type": "local_stub"},
                {
                    "name": "generate_character_image",
                    "capability": "generate_character_image",
                    "type": "stability_image",
                    "config": {
                        "engine_id": "stable-diffusion-xl-1024-v1-0",
                        "width": 1024, "height": 1024, "steps": 30, "cfg_scale": 7,
                    },
                },
            ]
        }
        self._file_tool.run("write_json", str(base / "mcp_registry.json"), mcp_registry)

        # ── run_counter.json — increment run count each execution ─────────────
        counter_path = base / "run_counter.json"
        try:
            counter_data = self._file_tool.run("read_json", str(counter_path))
            last_run = counter_data.get("last_run", 0) + 1
        except Exception:
            last_run = 1
        self._file_tool.run("write_json", str(counter_path), {"last_run": last_run})

        # ── Script text files ─────────────────────────────────────────────────
        script_text = self._build_script_text(output)
        self._file_tool.run("write_text", str(base / "last_script_auto.txt"), script_text)
        self._file_tool.run("write_text", str(base / "last_script.txt"), script_text)

        # Manual script = first 2 scenes only
        manual_script_text = self._build_script_text(output, scenes=output.scenes[:2])
        self._file_tool.run("write_text", str(base / "last_script_manual.txt"), manual_script_text)
        self._file_tool.run("write_text", str(base / "sample_script.txt"), manual_script_text)

        self._logger.run("info", "Artefacts saved", path=str(base))

    def _build_script_text(self, output: Phase1Output, scenes=None) -> str:
        """Render scenes as a human-readable screenplay-style text."""
        lines = [f"TITLE: {output.story.title}", f"GENRE: {output.story.genre}", ""]
        for scene in (scenes or output.scenes):
            lines.append(f"SCENE {scene.scene_id} — {scene.location.upper()}")
            lines.append(f"[{scene.mood.upper()} | {scene.tone.upper()}]")
            lines.append("")
            for dl in scene.dialogue:
                lines.append(f"{dl.speaker.upper()}:")
                lines.append(f'  "{dl.line}"')
                if dl.visual_cue:
                    lines.append(f"  ({dl.visual_cue})")
                lines.append("")
            lines.append("-" * 60)
            lines.append("")
        return "\n".join(lines)

    def _save_phase1_format_artifacts(self, wid: str, output: Phase1Output):
        """
        Write artefacts in the original Phase 1 format so that downstream
        consumers (Phase 2 audio agent, Phase 3 video agent) can read them
        exactly as they expect.

        Files produced:
          - story_manifest_auto.json    — story metadata (matches story_manifest_auto.json)
          - character_db_auto.json      — character roster (matches character_db_auto.json)
          - scene_manifest_auto.json    — scene list with dialogue (matches scene_manifest_auto.json)
          - timing_manifest.json        — per-line audio timing stub (matches timing_manifest.json)
        """
        base = self.output_dir
        timestamp = output.timestamp

        # ── story_manifest_auto.json ──────────────────────────────────────────
        # Fix 3: Derive protagonist/antagonist names from the canonical character
        # roster (character_db) rather than from story.protagonist/antagonist,
        # which may have been generated with a different name (e.g. "Harris" vs
        # "Taylor").  This guarantees story_manifest_auto.json, character_db_auto.json
        # and scene_manifest_auto.json all reference the same character names.
        _role_map: dict[str, str] = {c.role: c.name for c in output.characters}
        canonical_protagonist = _role_map.get("protagonist", output.story.protagonist)
        canonical_antagonist = _role_map.get("antagonist", output.story.antagonist)

        story_manifest = {
            "workflow_id": wid,
            "timestamp": timestamp,
            "story": {
                "title": output.story.title,
                "logline": output.story.logline,
                "genre": output.story.genre,
                "tone": output.story.tone,
                "setting": output.story.setting,
                "time_period": output.story.time_period,
                "themes": output.story.themes,
                "acts": [a.model_dump() for a in output.story.acts],
                "protagonist": canonical_protagonist,
                "antagonist": canonical_antagonist,
                "world": output.story.world,
            },
        }
        self._file_tool.run("write_json", str(base / "story_manifest_auto.json"), story_manifest)

        # ── character_db_auto.json ────────────────────────────────────────────
        characters_out = []
        for c in output.characters:
            # Flatten dialogue_samples to the simpler {line, visual_cue} format
            dialogue_samples = []
            for ds in (c.dialogue_samples or []):
                if isinstance(ds, dict):
                    dialogue_samples.append({
                        "line": ds.get("line", ""),
                        "visual_cue": ds.get("visual_cue", ""),
                    })
                else:
                    dialogue_samples.append({"line": str(ds), "visual_cue": ""})

            characters_out.append({
                "name": c.name,
                "personality": c.personality,
                "appearance": c.appearance,
                "role": c.role,
                "style_reference": c.style_reference,
                "first_appearance": c.first_appearance,
                "dialogue_samples": dialogue_samples,
                # Fix 4: include voice_config so Phase 2 can read character_db_auto.json
                # directly without needing to fall back to the phase2_audio_handoff blob.
                "voice_config": c.voice_config.model_dump(),
            })

        character_db = {
            "workflow_id": wid,
            "timestamp": timestamp,
            "characters": characters_out,
            "total_characters": len(characters_out),
        }
        self._file_tool.run("write_json", str(base / "character_db_auto.json"), character_db)

        # ── scene_manifest_auto.json ──────────────────────────────────────────
        scenes_out = []
        total_duration = 0
        for scene in output.scenes:
            dialogue_out = []
            for dl in scene.dialogue:
                dialogue_out.append({
                    "speaker": dl.speaker,
                    "line": dl.line,
                    "visual_cue": dl.visual_cue,
                })
            scenes_out.append({
                "scene_id": scene.scene_id,
                "location": scene.location,
                # Fix 5: include mood (Phase 2 BGM selection) and visual (Phase 3
                # image generation prompt) — previously stripped by this serialiser.
                "mood": scene.mood,
                "visual": scene.visual.model_dump(),
                "dialogue": dialogue_out,
                "characters": scene.characters,
                "duration": scene.duration_seconds,
            })
            total_duration += scene.duration_seconds

        scene_manifest = {
            "workflow_id": wid,
            "timestamp": timestamp,
            "scenes": scenes_out,
            "total_scenes": len(scenes_out),
            "total_duration_seconds": total_duration,
        }
        self._file_tool.run("write_json", str(base / "scene_manifest_auto.json"), scene_manifest)

        # ── timing_manifest.json ──────────────────────────────────────────────
        # Fix 1: Each entry carries a `tts_duration_ms` field (initially None) that
        # Phase 2 MUST overwrite with the real audio length after TTS synthesis.
        # Phase 3 must not consume timing_manifest.json until all tts_duration_ms
        # values are non-null (i.e., Phase 2 has completed its update pass).
        # The `start_ms` / `end_ms` values below are placeholder estimates
        # (MS_PER_LINE ms per line) that Phase 2 replaces with cumulative real timings.
        timing_entries = []
        MS_PER_LINE = 3000  # placeholder: 3 s per dialogue line — Phase 2 overwrites
        for scene in output.scenes:
            t = 0
            for idx, dl in enumerate(scene.dialogue, start=1):
                safe_speaker = dl.speaker.replace(" ", "_")
                audio_file = (
                    f"data/audio/scene{scene.scene_id}/"
                    f"{safe_speaker}_line{idx}.mp3"
                )
                timing_entries.append({
                    "scene_id": scene.scene_id,
                    "audio_file": audio_file,
                    "speaker": dl.speaker,
                    "start_ms": t,
                    "end_ms": t + MS_PER_LINE,
                    # Phase 2 must set this to the real TTS audio length in ms.
                    "tts_duration_ms": None,
                    "_phase1_placeholder": True,
                })
                t += MS_PER_LINE

        self._file_tool.run("write_json", str(base / "timing_manifest.json"), timing_entries)

        self._logger.run("info", "Phase1-format artefacts saved", path=str(base))
