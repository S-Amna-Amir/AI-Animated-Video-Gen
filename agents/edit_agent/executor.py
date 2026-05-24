import logging
from typing import Dict, Any
from .intent_classifier import EditIntent
from state_manager.state_manager import StateManager

logger = logging.getLogger(__name__)

class EditExecutor:
    def __init__(self):
        self.state_manager = StateManager()

    async def execute(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the edit based on the classified intent."""
        
        if intent.target == "audio":
            return await self._execute_audio_edit(intent, run_id, current_state)
        elif intent.target == "video_frame":
            return await self._execute_video_frame_edit(intent, run_id, current_state)
        elif intent.target == "video":
            return await self._execute_video_edit(intent, run_id, current_state)
        elif intent.target == "script":
            return await self._execute_script_edit(intent, run_id, current_state)
        elif intent.target == "system":
            return await self._execute_system_edit(intent, run_id, current_state)
        else:
            raise ValueError(f"Unknown target: {intent.target}")

    async def _execute_audio_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute audio-related edits."""
        try:
            from backend.services.phase2_service import run_phase2
            
            # Update current_state with intent parameters
            updated_state = current_state.copy()
            if intent.scope.startswith("character:"):
                char = intent.scope.split(":")[1]
                if char in updated_state:
                    updated_state[char] = intent.parameters.get("tone", updated_state[char])
            
            # Run phase 2 with updated parameters
            result = await run_phase2(run_id)
            
            if result.get("status") == "success":
                logger.info(f"Audio edit executed: {intent}")
                return {
                    "status": "success",
                    "message": f"Audio regenerated: {intent.intent} on {intent.scope}",
                    "updated_state": updated_state
                }
            else:
                logger.warning(f"Audio edit failed: {result.get('error')}")
                return {
                    "status": "partial_success",
                    "message": f"Audio edit attempted but failed: {result.get('error')}",
                    "updated_state": updated_state
                }
        except Exception as e:
            logger.warning(f"Audio service not available: {e}")
            # Fallback to mock
            updated_state = current_state.copy()
            return {
                "status": "partial_success",
                "message": f"Audio edit simulated: {intent.intent} on {intent.scope} (service unavailable)",
                "updated_state": updated_state
            }

    async def _execute_video_frame_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute video frame/image generation edits."""
        try:
            from backend.services.phase3_service import run_phase3
            
            # Update current_state with intent parameters
            updated_state = current_state.copy()
            if intent.scope.startswith("scene:"):
                scene = intent.scope.split(":")[1]
                if "scenes" not in updated_state:
                    updated_state["scenes"] = {}
                updated_state["scenes"][scene] = intent.parameters
            
            # Run phase 3 to regenerate images
            result = await run_phase3(run_id)
            
            if result.get("status") == "success":
                logger.info(f"Video frame edit executed: {intent}")
                return {
                    "status": "success",
                    "message": f"Scene images regenerated: {intent.intent} on {intent.scope}",
                    "updated_state": updated_state
                }
            else:
                logger.warning(f"Video frame edit failed: {result.get('error')}")
                return {
                    "status": "partial_success",
                    "message": f"Video frame edit attempted but failed: {result.get('error')}",
                    "updated_state": updated_state
                }
        except Exception as e:
            logger.warning(f"Video service not available: {e}")
            # Fallback to mock
            updated_state = current_state.copy()
            return {
                "status": "partial_success",
                "message": f"Video frame edit simulated: {intent.intent} on {intent.scope} (service unavailable)",
                "updated_state": updated_state
            }

    async def _execute_video_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute video composition edits (FFmpeg only)."""
        try:
            from backend.services.phase3_service import run_phase3
            
            # For video edits, assume FFmpeg recomposition is part of phase 3
            # TODO: Add flag to skip image generation if possible
            result = await run_phase3(run_id)
            
            if result.get("status") == "success":
                logger.info(f"Video edit executed: {intent}")
                return {
                    "status": "success",
                    "message": f"Video recomposed: {intent.intent} on {intent.scope}",
                    "updated_state": current_state
                }
            else:
                logger.warning(f"Video edit failed: {result.get('error')}")
                return {
                    "status": "partial_success",
                    "message": f"Video edit attempted but failed: {result.get('error')}",
                    "updated_state": current_state
                }
        except Exception as e:
            logger.warning(f"Video service not available: {e}")
            # Fallback to mock
            return {
                "status": "partial_success",
                "message": f"Video edit simulated: {intent.intent} on {intent.scope} (service unavailable)",
                "updated_state": current_state
            }

    async def _execute_script_edit(self, intent: EditIntent, run_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute script regeneration edits."""
        try:
            # TODO: Integrate with story agent when available
            # For now, fallback
            logger.warning("Story agent not yet integrated")
            return {
                "status": "partial_success",
                "message": f"Script edit simulated: {intent.intent} on {intent.scope} (story agent unavailable)",
                "updated_state": current_state
            }
        except Exception as e:
            logger.warning(f"Script service error: {e}")
            return {
                "status": "partial_success",
                "message": f"Script edit failed: {e}",
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