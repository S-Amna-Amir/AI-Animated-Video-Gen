"""
Audio Phase Planner - Orchestrates Phase 2 audio generation workflow.
Coordinates dialogue extraction, TTS synthesis, and manifest creation.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class AudioPhasePlanner:
    """
    Plans and orchestrates the Phase 2 audio generation workflow.
    Breaks down the audio generation process into logical steps.
    """
    
    # Workflow steps
    STEP_LOAD_DATA = "load_phase1_data"
    STEP_MAP_VOICES = "map_character_voices"
    STEP_EXTRACT_DIALOGUES = "extract_dialogues"
    STEP_SYNTHESIZE_AUDIO = "synthesize_audio"
    STEP_BUILD_MANIFEST = "build_timing_manifest"
    STEP_SAVE_OUTPUTS = "save_outputs"
    
    def __init__(self):
        """Initialize the planner."""
        self.workflow_steps = [
            self.STEP_LOAD_DATA,
            self.STEP_MAP_VOICES,
            self.STEP_EXTRACT_DIALOGUES,
            self.STEP_SYNTHESIZE_AUDIO,
            self.STEP_BUILD_MANIFEST,
            self.STEP_SAVE_OUTPUTS
        ]
        self.completed_steps: List[str] = []
        self.failed_steps: List[str] = []
        self.step_results: Dict[str, Any] = {}
    
    def get_workflow(self) -> List[str]:
        """
        Get the ordered list of workflow steps.
        
        Returns:
            List of step identifiers
        """
        return self.workflow_steps.copy()
    
    def mark_step_complete(self, step: str, result: Any = None) -> None:
        """
        Mark a workflow step as completed.
        
        Args:
            step: Step identifier
            result: Optional result data from the step
        """
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        
        if result:
            self.step_results[step] = result
        
        logger.info(f"✓ Completed: {step}")
    
    def mark_step_failed(self, step: str, error: str) -> None:
        """
        Mark a workflow step as failed.
        
        Args:
            step: Step identifier
            error: Error message
        """
        if step not in self.failed_steps:
            self.failed_steps.append(step)
        
        self.step_results[step] = {"error": error}
        
        logger.error(f"✗ Failed: {step} - {error}")
    
    def is_step_complete(self, step: str) -> bool:
        """Check if a step is completed."""
        return step in self.completed_steps
    
    def is_workflow_complete(self) -> bool:
        """Check if entire workflow is completed."""
        return len(self.completed_steps) == len(self.workflow_steps) and not self.failed_steps
    
    def get_next_step(self) -> str:
        """
        Get the next unexecuted step.
        
        Returns:
            Next step identifier or None if workflow is complete
        """
        for step in self.workflow_steps:
            if step not in self.completed_steps and step not in self.failed_steps:
                return step
        return None
    
    def get_progress(self) -> Dict:
        """
        Get current workflow progress.
        
        Returns:
            Progress dictionary with statistics
        """
        return {
            "total_steps": len(self.workflow_steps),
            "completed_steps": len(self.completed_steps),
            "failed_steps": len(self.failed_steps),
            "completed": self.completed_steps,
            "failed": self.failed_steps,
            "status": "complete" if self.is_workflow_complete() else "in_progress"
        }
    
    def plan_dialogue_synthesis(
        self,
        dialogues: List[Dict]
    ) -> Dict:
        """
        Plan the dialogue synthesis process.
        
        Args:
            dialogues: List of dialogue dicts to synthesize
            
        Returns:
            Plan dictionary with synthesis details
        """
        plan = {
            "total_dialogues": len(dialogues),
            "dialogue_by_scene": {},
            "dialogue_by_character": {}
        }
        
        # Group by scene
        for dialogue in dialogues:
            scene_id = dialogue.get("scene_id")
            if scene_id not in plan["dialogue_by_scene"]:
                plan["dialogue_by_scene"][scene_id] = []
            plan["dialogue_by_scene"][scene_id].append(dialogue)
        
        # Group by character
        for dialogue in dialogues:
            speaker = dialogue.get("speaker")
            if speaker not in plan["dialogue_by_character"]:
                plan["dialogue_by_character"][speaker] = []
            plan["dialogue_by_character"][speaker].append(dialogue)
        
        plan["total_scenes"] = len(plan["dialogue_by_scene"])
        plan["total_characters"] = len(plan["dialogue_by_character"])
        
        return plan
    
    def save_plan(self, output_path: Path) -> None:
        """
        Save the workflow plan to a file.
        
        Args:
            output_path: Path to save the plan JSON
        """
        plan_data = {
            "workflow": self.workflow_steps,
            "progress": self.get_progress(),
            "results": self.step_results
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(plan_data, f, indent=2)
        
        logger.info(f"Saved workflow plan to {output_path}")


class DialogueExtractor:
    """
    Extracts and prepares dialogues from Phase 1 scene manifest.
    """
    
    @staticmethod
    def extract_from_manifest(scene_manifest: Dict) -> List[Dict]:
        """
        Extract all dialogues from Phase 1 scene manifest.
        
        Args:
            scene_manifest: Scene manifest from Phase 1
            
        Returns:
            List of dialogue dicts with structure:
            {
                "speaker": character_name,
                "text": dialogue_text,
                "scene_id": scene_id,
                "line_index": line_number
            }
        """
        dialogues = []
        
        scenes = scene_manifest.get("scenes", [])
        
        for scene in scenes:
            scene_id = scene.get("scene_id")
            dialogue_list = scene.get("dialogue", [])
            
            for line_idx, dialogue_item in enumerate(dialogue_list, start=1):
                speaker = dialogue_item.get("speaker", "UNKNOWN")
                text = dialogue_item.get("line", "")
                
                if not text or text.strip() == "":
                    continue
                
                dialogues.append({
                    "speaker": speaker,
                    "text": text,
                    "scene_id": scene_id,
                    "line_index": line_idx
                })
        
        logger.info(f"Extracted {len(dialogues)} dialogues from {len(scenes)} scenes")
        
        return dialogues
    
    @staticmethod
    def validate_dialogues(dialogues: List[Dict]) -> Dict:
        """
        Validate extracted dialogues for completeness.
        
        Args:
            dialogues: List of dialogues to validate
            
        Returns:
            Validation report dictionary
        """
        report = {
            "total_dialogues": len(dialogues),
            "valid": 0,
            "missing_speaker": 0,
            "missing_text": 0,
            "missing_scene_id": 0,
            "issues": []
        }
        
        for idx, dialogue in enumerate(dialogues):
            is_valid = True
            
            if not dialogue.get("speaker"):
                report["missing_speaker"] += 1
                is_valid = False
                report["issues"].append(f"Dialogue {idx}: missing speaker")
            
            if not dialogue.get("text"):
                report["missing_text"] += 1
                is_valid = False
                report["issues"].append(f"Dialogue {idx}: missing text")
            
            if dialogue.get("scene_id") is None:
                report["missing_scene_id"] += 1
                is_valid = False
                report["issues"].append(f"Dialogue {idx}: missing scene_id")
            
            if is_valid:
                report["valid"] += 1
        
        return report
