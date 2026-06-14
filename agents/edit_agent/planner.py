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

Source-run resolution uses version_manifest.json (written by the executor)
rather than filesystem mtime scans, so the plan carries the correct Phase 2
audio source even if multiple runs exist.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _latest_run_by_number(base: Path) -> Optional[Path]:
    """Return the latest run dir by numeric suffix, not mtime."""
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return None

    def _num(p: Path) -> int:
        parts = p.name.rsplit("_", 1)
        return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

    return max(dirs, key=_num)


def _latest_phase2_run() -> str:
    """Return the latest Phase 2 run dir path as a string."""
    d = _latest_run_by_number(Path("data/outputs/Phase2"))
    return str(d) if d else ""


def _latest_phase3_run_id() -> str:
    d = _latest_run_by_number(Path("data/outputs/Phase3"))
    return d.name if d else ""


def _latest_phase3_use_subtitles() -> bool:
    """Read subtitle setting from the latest Phase 3 run's version_manifest or phase3_output."""
    d = _latest_run_by_number(Path("data/outputs/Phase3"))
    if not d:
        return False
    # Try version_manifest first (more reliable)
    for fname in ("version_manifest.json", "phase3_output.json"):
        fp = d / fname
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                return bool(data.get("use_subtitles", False))
            except Exception:
                pass
    return False


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
        elif target == "video_effect":
            return self._plan_video_effect(intent, params, scope)
        elif target == "video_frame":
            return self._plan_video_frame(intent, params, scope)
        elif target == "video_composition":
            return self._plan_video_composition(intent, params, scope)
        elif target == "video":
            # Legacy target name — route to composition recompose
            return self._plan_video_composition(intent, params, scope)
        elif target == "system":
            return self._plan_system(intent, params)
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
        return {
            "steps": [
                {
                    "phase": 2,
                    "action": "rerun_audio",
                    "params": {
                        "phase1_dir": "data/outputs",
                        "phase2_dir": "data/outputs/Phase2",
                        "scope":      scope,
                        "intent":     intent.get("intent"),
                        **params,
                    },
                },
                {
                    "phase": 3,
                    "action": "rerun_video_compose",
                    "params": {
                        "phase1_dir": "data/outputs",
                        "use_subtitles": False,
                    },
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Re-synthesise audio ({intent['intent']}, scope={scope}), and recompose video",
        }

    # ── Target: video_frame ───────────────────────────────────────────────────

    def _plan_video_frame(self, intent, params, scope):
        # Parse scene filter from scope
        scene_filter = None
        if scope.startswith("scene:"):
            scene_filter = scope.split(":")[1]

        use_subtitles = _latest_phase3_use_subtitles()

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
                {
                    "phase": 3,
                    "action": "rerun_video_compose",
                    "params": {
                        "phase1_dir":    "data/outputs",
                        "use_subtitles": use_subtitles,
                    },
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Regenerate scene images ({intent['intent']}, scope={scope}) and recompose video",
        }

    # ── Target: video_effect ─────────────────────────────────────────────────
    # Apply color grading / filters WITHOUT regenerating images.
    # Single lightweight FFmpeg step — no HF API calls involved.

    def _plan_video_effect(self, intent, params, scope):
        use_subtitles = _latest_phase3_use_subtitles()
        return {
            "steps": [
                {
                    "phase": 3,
                    "action": "apply_color_grade",
                    "params": {
                        "phase1_dir":    "data/outputs",
                        "use_subtitles": use_subtitles,
                        "scope":         scope,
                        **params,
                    },
                },
            ],
            "requires_snapshot_before": True,
            "description": f"Apply video effect ({intent['intent']}, scope={scope}) — no image regeneration",
        }

    # ── Target: video_composition ─────────────────────────────────────────────
    # Re-compose with FFmpeg only (subtitles, speed, transitions).

    def _plan_video_composition(self, intent, params, scope):
        use_subtitles = "subtitle" in intent.get("intent", "").lower()
        if intent.get("intent") == "add_subtitle":
            use_subtitles = True
        elif intent.get("intent") in ("toggle_subtitles", "remove_subtitle"):
            use_subtitles = params.get("subtitles_enabled", False)

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

    # ── Target: system ────────────────────────────────────────────────────────

    def _plan_system(self, intent, params):
        return {
            "steps": [
                {
                    "phase": 0,
                    "action": "system_action",
                    "params": {
                        "intent": intent.get("intent"),
                        **params,
                    },
                },
            ],
            "requires_snapshot_before": False,
            "description": f"System action: {intent['intent']}",
        }

    # ── Target: video (legacy alias) ──────────────────────────────────────────

    def _plan_video(self, intent, params, scope):
        """Kept for backward-compat — routes to composition planner."""
        return self._plan_video_composition(intent, params, scope)
