"""
agents/edit_agent/executor.py
-------------------------------
Executes edit plans produced by EditPlanner.
Each action delegates to the correct phase agent.

Actions:
    rerun_phase1        → run_phase1() with modified prompt
    rerun_audio         → EnhancedAudioAgent.process()
    rerun_images        → VideoAgent.run() images-only step
    rerun_video_compose → VideoAgent.run() composition-only step
    rerun_video_full    → VideoAgent.run() full pipeline
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


def _latest_phase2_run() -> str:
    base = Path("data/outputs/Phase2")
    if not base.exists():
        return ""
    dirs = [p for p in base.iterdir() if p.is_dir()]
    return str(max(dirs, key=lambda p: p.stat().st_mtime)) if dirs else ""


class EditExecutor:
    """
    Executes a plan's steps sequentially.
    Each step is a dict: {"phase": N, "action": str, "params": dict}
    """

    def __init__(self, log_callback: Callable[[str], None] = None):
        """
        log_callback: optional function(str) called for each log line.
        Used by the API route to push live log updates over WebSocket.
        """
        self._log = log_callback or logger.info

    async def execute(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run all steps in the plan. Returns a results dict.
        """
        steps   = plan.get("steps", [])
        results = []
        success = True

        for i, step in enumerate(steps):
            self._log(f"[Executor] Step {i+1}/{len(steps)}: {step['action']} (phase {step['phase']})")
            try:
                result = await self._run_step(step)
                results.append({"step": step["action"], "result": result, "ok": True})
                self._log(f"[Executor] ✓ {step['action']} complete")
            except Exception as e:
                logger.error("[Executor] Step failed: %s — %s", step["action"], e)
                self._log(f"[Executor] ✗ {step['action']} FAILED: {e}")
                results.append({"step": step["action"], "error": str(e), "ok": False})
                success = False
                break   # stop pipeline on failure

        return {"success": success, "steps": results}

    async def _run_step(self, step: Dict[str, Any]) -> Any:
        action = step["action"]
        params = step.get("params", {})

        dispatch = {
            "rerun_phase1":        self._rerun_phase1,
            "rerun_audio":         self._rerun_audio,
            "rerun_images":        self._rerun_images,
            "rerun_video_compose": self._rerun_video_compose,
            "rerun_video_full":    self._rerun_video_full,
        }
        handler = dispatch.get(action)
        if not handler:
            raise NotImplementedError(f"Unknown action: {action}")
        return await handler(params)

    # ── Step handlers ─────────────────────────────────────────────────────────

    async def _rerun_phase1(self, params: Dict) -> Dict:
        from agents.orchestrator.workflow import run_phase1
        prompt   = params.get("prompt") or params.get("original_query", "")
        mode     = params.get("mode", "auto")
        if not prompt:
            # Re-read existing prompt from scene manifest
            import json
            for name in ("scene_manifest.json","scene_manifest_auto.json","scene_manifest_manual.json"):
                p = Path("data/outputs") / name
                if p.exists():
                    data   = json.loads(p.read_text())
                    prompt = data.get("title", "a cinematic story")
                    break
        self._log(f"[Executor] Re-running Phase 1 | mode={mode} prompt={prompt[:60]}…")
        state = await asyncio.get_event_loop().run_in_executor(
            None, run_phase1, mode, prompt
        )
        return {"status": state.get("status"), "title": state.get("script", {}).get("title")}

    async def _rerun_audio(self, params: Dict) -> Dict:
        from agents.audio_agent.enhanced_agent import EnhancedAudioAgent
        agent  = EnhancedAudioAgent(
            phase1_data_dir=params.get("phase1_dir", "data/outputs"),
            phase2_output_dir=params.get("phase2_dir", "data/outputs/Phase2"),
        )
        self._log(f"[Executor] Re-running Phase 2 | run={agent.run_manager.current_run_id}")
        result = await agent.process()
        return {"status": result.get("status"), "run_id": result.get("run_id")}

    async def _rerun_images(self, params: Dict) -> Dict:
        """Re-run image generation only (no animation/composition)."""
        from agents.video_agent.agent import VideoAgent
        from mcp.tools.video_tools import image_generator

        agent = VideoAgent()
        self._log(f"[Executor] Re-running Phase 3 images only | run={agent.run_id}")

        phase1_data = agent.load_phase1_output(params.get("phase1_dir", "data/outputs"))
        scenes      = phase1_data["scenes"]
        characters  = phase1_data["characters"]

        p2_run   = _latest_phase2_run()
        manifest = agent.load_phase2_manifest(p2_run)
        if not manifest:
            manifest = agent._fallback_manifest(scenes)

        # Apply scene filter if present
        scene_filter = params.get("scene_filter")
        if scene_filter:
            manifest = [e for e in manifest if str(e.get("scene_id")) == str(scene_filter)]

        # Aesthetic modifier: update prompt_builder style if needed
        aesthetic = params.get("aesthetic")
        if aesthetic:
            _patch_aesthetic(aesthetic)

        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: image_generator.generate_images_for_dialogue(
                manifest_entries=manifest,
                scenes=scenes,
                characters=characters,
                run_dir=str(agent.run_dir),
            ),
        )
        ok = sum(1 for r in results if r.get("status") == "success")
        return {"images_generated": ok, "run_id": agent.run_id}

    async def _rerun_video_compose(self, params: Dict) -> Dict:
        """Re-run composition step only using existing clips."""
        from agents.video_agent.agent import VideoAgent
        from mcp.tools.video_tools import video_compositor, animator
        import json

        p2_run  = _latest_phase2_run()
        agent   = VideoAgent()
        self._log(f"[Executor] Re-composing video | run={agent.run_id}")

        phase1_data    = agent.load_phase1_output(params.get("phase1_dir","data/outputs"))
        timing_manifest = agent.load_phase2_manifest(p2_run) if p2_run else []
        if not timing_manifest:
            timing_manifest = agent._fallback_manifest(phase1_data["scenes"])

        # Re-animate all (needed for speed changes)
        speed = params.get("speed_factor", 1.0)
        scene_clips = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: animator.animate_all_scenes(
                dialogue_results=_build_dialogue_results(timing_manifest, agent.run_dir),
                scenes=phase1_data["scenes"],
                run_dir=str(agent.run_dir),
            ),
        )

        final_video = video_compositor.compose_final_video(
            scene_clips_map=scene_clips,
            dialogue_results=_build_dialogue_results(timing_manifest, agent.run_dir),
            output_path=str(agent.run_dir / "final_output.mp4"),
            use_transitions=True,
            use_subtitles=params.get("use_subtitles", False),
        )
        return {"final_video": final_video, "run_id": agent.run_id}

    async def _rerun_video_full(self, params: Dict) -> Dict:
        from agents.video_agent.agent import VideoAgent
        p2_run = _latest_phase2_run()
        agent  = VideoAgent()
        self._log(f"[Executor] Full Phase 3 re-run | run={agent.run_id}")
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: agent.run(
                phase1_dir=params.get("phase1_dir", "data/outputs"),
                phase2_run_dir=p2_run,
                mock=params.get("mock", False),
                use_subtitles=params.get("use_subtitles", False),
            ),
        )
        return {"status": result.get("status"), "final_video": result.get("final_video"), "run_id": result.get("run_id")}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_aesthetic(aesthetic: str) -> None:
    """
    Temporarily patch prompt_builder TONE_STYLE_MAP to inject aesthetic modifier.
    This is applied globally for the current process — reset on next server restart.
    """
    try:
        from mcp.tools.video_tools import prompt_builder
        if aesthetic == "dark":
            prompt_builder.GLOBAL_STYLE = (
                "cinematic photography, dark moody aesthetic, low-key lighting, "
                "deep shadows, film noir, 35mm"
            )
        elif aesthetic == "bright":
            prompt_builder.GLOBAL_STYLE = (
                "cinematic photography, bright vivid colours, high-key lighting, "
                "optimistic tone, 35mm"
            )
        logger.info("[Executor] Aesthetic patched → %s", aesthetic)
    except Exception as e:
        logger.warning("[Executor] Aesthetic patch failed: %s", e)


def _build_dialogue_results(timing_manifest, run_dir: Path):
    """Build minimal dialogue_results list from a timing manifest for re-composition."""
    results = []
    images_dir = run_dir / "images"
    for entry in timing_manifest:
        sid   = str(entry.get("scene_id", ""))
        idx   = int(entry.get("line_index", 0))
        img   = str(images_dir / f"scene_{sid}_line_{idx}.png")
        results.append({
            "scene_id":   sid,
            "line_index": idx,
            "speaker":    entry.get("speaker", ""),
            "text":       entry.get("text", ""),
            "image_path": img if Path(img).exists() else "",
            "audio_file": entry.get("audio_file", ""),
            "start_ms":   int(entry.get("start_ms", 0)),
            "duration_ms": float(entry.get("duration_ms", 5000)),
            "status":     "success" if Path(img).exists() else "skipped",
        })
    return results
