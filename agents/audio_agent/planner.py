"""
agents/audio_agent/planner.py
-------------------------------
Workflow step tracker and dialogue extractor for Phase 2.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AudioPhasePlanner:
    STEP_LOAD_DATA         = "load_phase1_data"
    STEP_MAP_VOICES        = "map_character_voices"
    STEP_EXTRACT_DIALOGUES = "extract_dialogues"
    STEP_SYNTHESIZE_AUDIO  = "synthesize_audio"
    STEP_BUILD_MANIFEST    = "build_timing_manifest"
    STEP_SAVE_OUTPUTS      = "save_outputs"

    def __init__(self):
        self.workflow_steps = [
            self.STEP_LOAD_DATA, self.STEP_MAP_VOICES,
            self.STEP_EXTRACT_DIALOGUES, self.STEP_SYNTHESIZE_AUDIO,
            self.STEP_BUILD_MANIFEST, self.STEP_SAVE_OUTPUTS,
        ]
        self.completed_steps: List[str] = []
        self.failed_steps: List[str] = []
        self.step_results: Dict[str, Any] = {}

    def mark_step_complete(self, step: str, result: Any = None) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if result:
            self.step_results[step] = result
        logger.info(f"✓ {step}")

    def mark_step_failed(self, step: str, error: str) -> None:
        if step not in self.failed_steps:
            self.failed_steps.append(step)
        self.step_results[step] = {"error": error}
        logger.error(f"✗ {step}: {error}")

    def get_progress(self) -> Dict:
        return {
            "total_steps": len(self.workflow_steps),
            "completed_steps": len(self.completed_steps),
            "failed_steps": len(self.failed_steps),
            "completed": self.completed_steps,
            "failed": self.failed_steps,
            "status": "complete" if (
                len(self.completed_steps) == len(self.workflow_steps)
                and not self.failed_steps
            ) else "in_progress",
        }


class DialogueExtractor:
    @staticmethod
    def extract_from_manifest(scene_manifest: Dict) -> List[Dict]:
        dialogues = []
        for scene in scene_manifest.get("scenes", []):
            scene_id = scene.get("scene_id")
            for idx, item in enumerate(scene.get("dialogue", []), start=1):
                speaker = item.get("speaker", "UNKNOWN")
                text = item.get("line", "").strip()
                if not text:
                    continue
                dialogues.append({
                    "speaker": speaker,
                    "text": text,
                    "scene_id": scene_id,
                    "line_index": idx,
                })
        logger.info(f"Extracted {len(dialogues)} dialogues from {len(scene_manifest.get('scenes', []))} scenes")
        return dialogues

    @staticmethod
    def validate_dialogues(dialogues: List[Dict]) -> Dict:
        report = {"total_dialogues": len(dialogues), "valid": 0,
                  "missing_speaker": 0, "missing_text": 0, "issues": []}
        for i, d in enumerate(dialogues):
            ok = True
            if not d.get("speaker"):
                report["missing_speaker"] += 1; ok = False
            if not d.get("text"):
                report["missing_text"] += 1; ok = False
            if ok:
                report["valid"] += 1
        return report
