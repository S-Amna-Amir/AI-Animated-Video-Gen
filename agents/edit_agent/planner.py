from typing import List, Dict, Any
from pydantic import BaseModel
from .intent_classifier import EditIntent

class ExecutionPlan(BaseModel):
    steps: List[str] = []
    affected_assets: List[str] = []
    estimated_impact: str = ""

class EditPlanner:
    def plan(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Create an execution plan for the edit intent."""
        
        if intent.target == "audio":
            return self._plan_audio_edit(intent, current_state)
        elif intent.target == "video_frame":
            return self._plan_video_frame_edit(intent, current_state)
        elif intent.target == "video":
            return self._plan_video_edit(intent, current_state)
        elif intent.target == "script":
            return self._plan_script_edit(intent, current_state)
        elif intent.target == "system":
            return self._plan_system_edit(intent, current_state)
        else:
            return ExecutionPlan(
                steps=["Unknown edit type"],
                affected_assets=[],
                estimated_impact="Unknown"
            )

    def _plan_audio_edit(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Plan audio edits."""
        steps = ["Update audio parameters", "Regenerate audio files"]
        affected_assets = [f"audio_{intent.scope}.mp3"]  # Mock
        impact = f"Regenerates audio for {intent.scope}"
        
        return ExecutionPlan(
            steps=steps,
            affected_assets=affected_assets,
            estimated_impact=impact
        )

    def _plan_video_frame_edit(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Plan video frame edits."""
        if "scene:" in intent.scope:
            scene_num = intent.scope.split(":")[1]
            steps = [f"Update scene {scene_num} prompt", f"Regenerate scene {scene_num} image"]
            affected_assets = [f"scene_{scene_num}.png"]
            impact = f"Regenerates 1 scene image"
        else:
            steps = ["Update all scene prompts", "Regenerate all scene images"]
            affected_assets = ["all_scene_images"]
            impact = "Regenerates all scene images"
        
        return ExecutionPlan(
            steps=steps,
            affected_assets=affected_assets,
            estimated_impact=impact
        )

    def _plan_video_edit(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Plan video composition edits."""
        steps = ["Update video composition parameters", "Re-run FFmpeg composition"]
        affected_assets = ["final_video.mp4"]
        impact = "Re-composes final video without regenerating assets"
        
        return ExecutionPlan(
            steps=steps,
            affected_assets=affected_assets,
            estimated_impact=impact
        )

    def _plan_script_edit(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Plan script edits."""
        steps = ["Regenerate story script", "Re-run full pipeline"]
        affected_assets = ["script.txt", "all_assets"]
        impact = "Regenerates entire video from new script"
        
        return ExecutionPlan(
            steps=steps,
            affected_assets=affected_assets,
            estimated_impact=impact
        )

    def _plan_system_edit(self, intent: EditIntent, current_state: Dict[str, Any]) -> ExecutionPlan:
        """Plan system edits."""
        if intent.intent == "undo":
            steps = ["Revert to previous state"]
            affected_assets = ["state_and_assets"]
            impact = "Restores previous version"
        else:
            steps = ["Unknown system operation"]
            affected_assets = []
            impact = "Unknown"
        
        return ExecutionPlan(
            steps=steps,
            affected_assets=affected_assets,
            estimated_impact=impact
        )