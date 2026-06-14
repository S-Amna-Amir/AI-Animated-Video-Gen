"""
agents/edit_agent/planner.py
------------------------------
Translates a classified intent into an execution plan:
which phases need to re-run, with what parameters, in what order.

Plan format:
{
    "steps": [
        {"phase": 2, "action": "rerun_audio", "params": {...}},
        {"phase": 3, "action": "rerun_video",  "params": {...}},
    ],
    "requires_snapshot_before": True,
    "description": "human-readable summary",
}
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _latest_phase2_run() -> str:
    base = Path("data/outputs/Phase2")
    if not base.exists():
        return ""
    dirs = [p for p in base.iterdir() if p.is_dir()]
    return str(max(dirs, key=lambda p: p.stat().st_mtime)) if dirs else ""


def _latest_phase3_run_id() -> str:
    base = Path("data/outputs/Phase3")
    if not base.exists():
        return ""
    dirs = [p for p in base.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime).name if dirs else ""


class EditPlanner:
    """
    Converts a structured intent into a concrete re-run plan.
    Each step maps to an action the executor knows how to run.
    """

    def plan(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        target = intent.get("target", "script")
        params = intent.get("parameters", {})
        scope  = intent.get("scope", "all_scenes")

        if target == "script":
            return self._plan_script(intent, params)
        elif target == "audio":
            return self._plan_audio(intent, params, scope)
        elif target == "video_frame":
            return self._plan_video_frame(intent, params, scope)
        elif target == "video":
            return self._plan_video(intent, params, scope)
        else:
            return self._plan_script(intent, params)

    # ── Target: script ────────────────────────────────────────────────────────

    def _plan_script(self, intent, params):
        return {
            "steps": [
                {"phase": 1, "action": "rerun_phase1",    "params": params},
                {"phase": 2, "action": "rerun_audio",     "params": {}},
                {"phase": 3, "action": "rerun_video_full","params": {"mock": False}},
            ],
            "requires_snapshot_before": True,
            "description": f"Regenerate script + full pipeline ({intent['intent']})",
        }

    # ── Target: audio ─────────────────────────────────────────────────────────

    def _plan_audio(self, intent, params, scope):
        p2_run = _latest_phase2_run()
        return {
            "steps": [
                {
                    "phase": 2,
                    "action": "rerun_audio",
                    "params": {
                        "phase1_dir": "data/outputs",
                        "phase2_dir": "data/outputs/Phase2",
                        "scope": scope,
                        **params,
                    },
                },
                {
                    "phase": 3,
                    "action": "rerun_video_full",
                    "params": {"mock": False, "use_subtitles": False},
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Re-synthesise audio ({intent['intent']}, scope={scope}), recompose video",
        }

    # ── Target: video_frame ───────────────────────────────────────────────────

    def _plan_video_frame(self, intent, params, scope):
        # Parse scene filter from scope
        scene_filter = None
        if scope.startswith("scene:"):
            scene_filter = scope.split(":")[1]

        return {
            "steps": [
                {
                    "phase": 3,
                    "action": "rerun_images",
                    "params": {
                        "phase1_dir":    "data/outputs",
                        "mock":          False,
                        "scene_filter":  scene_filter,
                        "aesthetic":     params.get("aesthetic"),
                        **params,
                    },
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Regenerate scene images ({intent['intent']}, scope={scope})",
        }

    # ── Target: video ─────────────────────────────────────────────────────────

    def _plan_video(self, intent, params, scope):
        use_subtitles = "subtitle" in intent.get("intent", "").lower()
        # "remove_subtitle" → use_subtitles=False; "add_subtitle" → True
        if intent.get("intent") == "add_subtitle":
            use_subtitles = True
        elif intent.get("intent") == "remove_subtitle":
            use_subtitles = False

        return {
            "steps": [
                {
                    "phase": 3,
                    "action": "rerun_video_compose",
                    "params": {
                        "phase1_dir":    "data/outputs",
                        "use_subtitles": use_subtitles,
                        "speed_factor":  params.get("speed_factor", 1.0),
                        **params,
                    },
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Recompose video ({intent['intent']})",
        }
