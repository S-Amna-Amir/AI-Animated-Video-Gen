import logging
from typing import Dict, Any
from .intent_classifier import EditIntent
from state_manager.state_manager import StateManager

logger = logging.getLogger(__name__)

class EditExecutor:
    def __init__(self):
        self.state_manager = StateManager()

    def execute(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the edit based on the classified intent."""
        
        if intent.target == "audio":
            return self._execute_audio_edit(intent, run_id, current_state)
        elif intent.target == "video_frame":
            return self._execute_video_frame_edit(intent, run_id, current_state)
        elif intent.target == "video":
            return self._execute_video_edit(intent, run_id, current_state)
        elif intent.target == "script":
            return self._execute_script_edit(intent, run_id, current_state)
        elif intent.target == "system":
            return self._execute_system_edit(intent, run_id, current_state)
        else:
            raise ValueError(f"Unknown target: {intent.target}")

    def _execute_audio_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute audio-related edits."""
        # TODO: Integrate with existing audio phase service/agent
        # For now, return mock success
        logger.info(f"Mock executing audio edit: {intent}")
        return {
            "status": "success",
            "message": f"Audio edit applied: {intent.intent} on {intent.scope}",
            "updated_state": current_state  # In real impl, this would be updated
        }

    def _execute_video_frame_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute video frame/image generation edits."""
        # TODO: Integrate with existing video/image generation service
        # For now, return mock success
        logger.info(f"Mock executing video frame edit: {intent}")
        return {
            "status": "success",
            "message": f"Video frame edit applied: {intent.intent} on {intent.scope}",
            "updated_state": current_state
        }

    def _execute_video_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute video composition edits (FFmpeg only)."""
        # TODO: Integrate with FFmpeg composition step
        # For now, return mock success
        logger.info(f"Mock executing video edit: {intent}")
        return {
            "status": "success",
            "message": f"Video composition updated: {intent.intent} on {intent.scope}",
            "updated_state": current_state
        }

    def _execute_script_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute script regeneration edits."""
        # TODO: Re-invoke the story agent
        # For now, return mock success
        logger.info(f"Mock executing script edit: {intent}")
        return {
            "status": "success",
            "message": f"Script regenerated: {intent.intent} on {intent.scope}",
            "updated_state": current_state
        }

    def _execute_system_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute system-level edits (like undo)."""
        if intent.intent == "undo":
            # Find the previous version
            history = self.state_manager.history(run_id)
            if len(history) < 2:
                return {
                    "status": "error",
                    "message": "No previous version to revert to",
                    "updated_state": current_state
                }
            
            previous_version = history[-2].version  # Second to last
            reverted_snapshot = self.state_manager.revert(run_id, previous_version)
            
            logger.info(f"Reverted to version {previous_version}")
            return {
                "status": "success",
                "message": f"Reverted to version {previous_version}",
                "updated_state": reverted_snapshot.state_json,
                "new_version": reverted_snapshot.version
            }
        else:
            # Other system commands
            return {
                "status": "error",
                "message": f"Unknown system intent: {intent.intent}",
                "updated_state": current_state
            }