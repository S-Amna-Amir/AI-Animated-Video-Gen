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
    apply_color_grade   → FFmpeg color-grade of existing final_output.mp4
    system_action       → undo/redo delegation

Run provenance is tracked via RunContext and written as
version_manifest.json into every new Phase 3 run directory so the
edit history can be reconstructed end-to-end.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agents.edit_agent.run_context import (
    RunContext,
    resolve_source_runs,
    write_version_manifest,
)

logger = logging.getLogger(__name__)


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
        self._log_cb = log_callback or logger.info
        self.phase3_run_id: Optional[str] = None
        self._ctx: Optional[RunContext] = None   # set in execute()

    def _log(self, msg: str) -> None:
        if callable(self._log_cb):
            self._log_cb(msg)
        else:
            logger.info(msg)

    async def execute(
        self,
        plan: Dict[str, Any],
        ctx: Optional[RunContext] = None,
    ) -> Dict[str, Any]:
        """
        Run all steps in the plan. Returns a results dict.

        ctx: optional pre-built RunContext.  If not supplied one is resolved
             automatically from the current filesystem state.
        """
        steps   = plan.get("steps", [])
        results = []
        success = True

        # ── 1. Resolve provenance context ONCE ───────────────────────────────
        if ctx is None:
            ctx = resolve_source_runs()
        self._ctx = ctx
        self._log(
            f"[Executor] Source context — p2={ctx.source_phase2_run_id}  "
            f"p3={ctx.source_phase3_run_id}"
        )

        # ── 2. Create new Phase 3 run dir & copy forward assets ───────────────
        has_phase3 = any(step.get("phase") == 3 for step in steps)
        if has_phase3:
            from agents.video_agent.run_manager import VideoRunManager
            import shutil

            manager = VideoRunManager()
            self.phase3_run_id, run_dir_str = manager.create_run_dir()
            new_run_dir = Path(run_dir_str)
            ctx.new_phase3_run_id  = self.phase3_run_id
            ctx.new_phase3_run_dir = run_dir_str
            self._log(f"[Executor] Created Phase 3 run: {self.phase3_run_id}")
            self._log(
                f"[Executor] Provenance: parent_p3={ctx.source_phase3_run_id} "
                f"audio_p2={ctx.source_phase2_run_id}"
            )

            # Copy images/clips from parent Phase 3 run for continuity
            if ctx.source_phase3_run_dir:
                parent_dir = Path(ctx.source_phase3_run_dir)
                if parent_dir.exists() and parent_dir != new_run_dir:
                    self._log(
                        f"[Executor] Copying assets from parent "
                        f"{parent_dir.name} → {new_run_dir.name}"
                    )
                    for sub in ("images", "clips"):
                        src = parent_dir / sub
                        if src.exists():
                            for f in src.glob("*"):
                                if f.is_file():
                                    shutil.copy2(f, new_run_dir / sub)

        # ── 3. Execute steps ──────────────────────────────────────────────────
        for i, step in enumerate(steps):
            self._log(f"[Executor] Step {i+1}/{len(steps)}: {step['action']} (phase {step['phase']})")
            try:
                result = await self._run_step(step)
                results.append({"step": step["action"], "result": result, "ok": True})
                self._log(f"[Executor] SUCCESS: {step['action']} complete")
            except Exception as e:
                logger.error("[Executor] Step failed: %s — %s", step["action"], e)
                self._log(f"[Executor] FAILED: {step['action']} failed: {e}")
                results.append({"step": step["action"], "error": str(e), "ok": False})
                success = False
                break   # stop pipeline on failure

        # ── 4. Write version_manifest.json into the new Phase 3 run ──────────
        if has_phase3 and ctx.new_phase3_run_dir:
            try:
                write_version_manifest(Path(ctx.new_phase3_run_dir), ctx)
            except Exception as e:
                logger.warning("[Executor] Could not write version_manifest: %s", e)

        return {"success": success, "steps": results, "run_context": ctx.to_dict()}

    async def _run_step(self, step: Dict[str, Any]) -> Any:
        action = step["action"]
        params = step.get("params", {})

        dispatch = {
            "rerun_phase1":        self._rerun_phase1,
            "rerun_audio":         self._rerun_audio,
            "rerun_images":        self._rerun_images,
            "rerun_video_compose": self._rerun_video_compose,
            "rerun_video_full":    self._rerun_video_full,
            "apply_color_grade":   self._apply_color_grade,
            "system_action":       self._system_action,
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
        bgm_vol = params.get("volume_factor")
        bgm_q = params.get("mood_query") or params.get("mood")
        agent  = EnhancedAudioAgent(
            phase1_data_dir=params.get("phase1_dir", "data/outputs"),
            phase2_output_dir=params.get("phase2_dir", "data/outputs/Phase2"),
            custom_bgm_volume=bgm_vol,
            custom_bgm_query=bgm_q,
            edit_intent=params.get("intent"),
            edit_scope=params.get("scope"),
        )
        self._log(f"[Executor] Re-running Phase 2 | run={agent.run_manager.current_run_id}")
        result = await agent.process()
        # Update context so subsequent Phase 3 steps use this new audio run
        if result.get("status") == "success" and self._ctx:
            new_p2_id = result.get("run_id", "")
            if new_p2_id:
                self._ctx.source_phase2_run_id  = new_p2_id
                self._ctx.source_phase2_run_dir = str(
                    Path("data/outputs/Phase2") / new_p2_id
                )
                self._log(f"[Executor] Phase 2 run updated in context: {new_p2_id}")
        return {"status": result.get("status"), "run_id": result.get("run_id")}

    async def _rerun_images(self, params: Dict) -> Dict:
        """Re-run image generation only (no animation/composition)."""
        from agents.video_agent.agent import VideoAgent
        from mcp.tools.video_tools import image_generator

        agent = VideoAgent(run_id=self.phase3_run_id)
        self._log(f"[Executor] Re-running Phase 3 images only | run={agent.run_id}")

        phase1_data = agent.load_phase1_output(params.get("phase1_dir", "data/outputs"))
        scenes      = phase1_data["scenes"]
        characters  = phase1_data["characters"]

        # Use explicit context source instead of mtime scan
        p2_run = (self._ctx.source_phase2_run_dir if self._ctx else "") or \
                 str(Path("data/outputs/Phase2") / _latest_run_id_by_number(Path("data/outputs/Phase2")))
        manifest = agent.load_phase2_manifest(p2_run)
        if not manifest:
            manifest = agent._fallback_manifest(scenes)

        # Apply scene filter if present
        scene_filter = params.get("scene_filter")
        if scene_filter:
            manifest = [e for e in manifest if str(e.get("scene_id")) == str(scene_filter)]

        # Delete existing images we plan to regenerate, renaming to .bak so they
        # can be restored if the HF API call fails.
        for entry in manifest:
            sid = str(entry.get("scene_id", ""))
            idx = int(entry.get("line_index", 0))
            existing_file = agent.run_dir / "images" / f"scene_{sid}_line_{idx}.png"
            if existing_file.exists():
                bak_file = existing_file.with_suffix(".png.bak")
                if bak_file.exists():
                    bak_file.unlink()
                existing_file.rename(bak_file)

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

        # Use explicit context source instead of mtime scan
        p2_run = (self._ctx.source_phase2_run_dir if self._ctx else "") or \
                 str(Path("data/outputs/Phase2") / _latest_run_id_by_number(Path("data/outputs/Phase2")))
        agent   = VideoAgent(run_id=self.phase3_run_id)
        self._log(f"[Executor] Re-composing video | run={agent.run_id} | audio={Path(p2_run).name if p2_run else '?'}")

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
        # Use explicit context source instead of mtime scan
        p2_run = (self._ctx.source_phase2_run_dir if self._ctx else "") or \
                 str(Path("data/outputs/Phase2") / _latest_run_id_by_number(Path("data/outputs/Phase2")))
        agent  = VideoAgent(run_id=self.phase3_run_id)
        self._log(f"[Executor] Full Phase 3 re-run | run={agent.run_id} | audio={Path(p2_run).name if p2_run else '?'}")
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

    async def _apply_color_grade(self, params: Dict) -> Dict:
        """
        Apply color grading / visual filters to the existing final video using
        FFmpeg only.  No image regeneration — this is the fast path for requests
        like "make the scene darker" or "add more contrast".

        Supported parameters (all optional, combined in one FFmpeg pass):
            brightness    float  –1.0 … +1.0   (default 0)
            contrast      float  0.5 … 2.0     (default 1)
            saturation    float  0.0 … 3.0     (default 1)
            tint          str    colour name   (e.g. "blue")
            intensity     float  0.0 … 1.0     tint intensity (default 0.5)
            vignette      float  0.0 … 1.0     vignette strength (default 0)
            temperature   str    "warm"|"cool"
        """
        import subprocess
        from pathlib import Path

        p2_run = (self._ctx.source_phase2_run_dir if self._ctx else "") or \
                 str(Path("data/outputs/Phase2") / _latest_run_id_by_number(Path("data/outputs/Phase2")))
        agent  = _get_or_create_video_agent(self.phase3_run_id)
        self.phase3_run_id = agent.run_id
        self._log(f"[Executor] Applying color grade | run={agent.run_id}")

        # Locate the most recent final_output.mp4 to use as source
        source_video = _latest_final_video(agent.run_dir)
        if not source_video:
            raise FileNotFoundError(
                "No existing final_output.mp4 found to color-grade. "
                "Run the full pipeline first."
            )

        output_path = agent.run_dir / "final_output.mp4"
        # Write to a temp file so we don't clobber the source if it's the same path
        temp_output = agent.run_dir / "final_output_graded_tmp.mp4"

        # Build FFmpeg eq + colorchannelmixer filters
        filters = _build_ffmpeg_color_filters(params)
        if not filters:
            self._log("[Executor] No color parameters supplied — skipping FFmpeg pass")
            return {"final_video": str(source_video), "run_id": agent.run_id, "skipped": True}

        import imageio_ffmpeg as _iio
        ffmpeg_exe = _iio.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(source_video),
            "-vf", filters,
            "-c:a", "copy",
            str(temp_output),
        ]
        self._log(f"[Executor] FFmpeg color grade: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg color grade failed: {stderr.decode()[-500:]}")

        # Replace output
        if output_path.exists():
            output_path.unlink()
        temp_output.rename(output_path)

        self._log(f"[Executor] Color grade applied → {output_path}")
        return {"final_video": str(output_path), "run_id": agent.run_id}

    async def _system_action(self, params: Dict) -> Dict:
        """Handle system intents (undo/redo) surfaced via the planner."""
        intent_name = params.get("intent", "unknown")
        self._log(f"[Executor] System action: {intent_name} — delegate to StateManager")
        # Actual undo/redo is handled by EditAgent.undo(); just return info here.
        return {"action": intent_name, "note": "Use EditAgent.undo(version) to revert."}



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


def _get_or_create_video_agent(run_id: str):
    """Return a VideoAgent, reusing run_id if given, or creating a new run."""
    from agents.video_agent.agent import VideoAgent
    return VideoAgent(run_id=run_id)


def _latest_run_id_by_number(base: Path) -> str:
    """
    Return the name of the latest run directory by numeric suffix (not mtime).
    Falls back to empty string if no runs exist.
    """
    if not base.exists():
        return ""
    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return ""

    def _num(p: Path) -> int:
        parts = p.name.rsplit("_", 1)
        return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

    return max(dirs, key=_num).name


def _latest_final_video(run_dir: Path) -> Optional[Path]:
    """
    Return the path to final_output.mp4 in run_dir, or search previous Phase 3
    runs if run_dir doesn't have one yet.
    """
    candidate = run_dir / "final_output.mp4"
    if candidate.exists():
        return candidate

    base = Path("data/outputs/Phase3")
    if not base.exists():
        return None
    dirs = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in dirs:
        f = d / "final_output.mp4"
        if f.exists():
            return f
    return None


# Colour-name → approximate RGB shift (R, G, B  each –1.0 … +1.0)
_TINT_COLOURS: Dict[str, tuple] = {
    "red":    (0.3,  -0.1, -0.1),
    "green":  (-0.1,  0.3, -0.1),
    "blue":   (-0.1, -0.1,  0.3),
    "orange": (0.3,   0.1, -0.2),
    "yellow": (0.2,   0.2, -0.2),
    "purple": (0.2,  -0.1,  0.2),
    "pink":   (0.3,  -0.1,  0.1),
    "cyan":   (-0.2,  0.2,  0.2),
}

_TEMPERATURE_PRESETS: Dict[str, Dict] = {
    "warm": {"brightness": 0.05, "tint": "orange", "intensity": 0.25},
    "cool": {"brightness": 0.0,  "tint": "blue",   "intensity": 0.25},
}


def _build_ffmpeg_color_filters(params: Dict) -> str:
    """
    Translate color-grade parameters into an FFmpeg -vf filter string.

    Handles:
        brightness  float  –1.0 … +1.0
        contrast    float   0.5 … 2.0
        saturation  float   0.0 … 3.0
        tint        str     colour name
        intensity   float   0.0 … 1.0
        vignette    float   0.0 … 1.0
        temperature str     "warm" | "cool"

    Returns an empty string if no relevant params are found.
    """
    # Expand temperature preset into individual params
    temperature = params.get("temperature")
    if temperature and temperature in _TEMPERATURE_PRESETS:
        preset = _TEMPERATURE_PRESETS[temperature]
        params = {**preset, **params}
        del params["temperature"]

    parts: List[str] = []

    # ── eq filter (brightness / contrast / saturation) ────────────────────────
    brightness = float(params.get("brightness", 0.0))
    contrast   = float(params.get("contrast",   1.0))
    saturation = float(params.get("saturation", 1.0))

    # FFmpeg eq brightness range is –1 … 1; contrast 0 … 2
    has_eq = brightness != 0.0 or contrast != 1.0 or saturation != 1.0
    if has_eq:
        # Clamp to safe ranges
        brightness = max(-1.0, min(1.0, brightness))
        contrast   = max(0.0,  min(2.0, contrast))
        saturation = max(0.0,  min(3.0, saturation))
        parts.append(
            f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}"
        )

    # ── colorchannelmixer (tint) ───────────────────────────────────────────────
    tint_name = params.get("tint", "").lower()
    intensity  = float(params.get("intensity", 0.5))
    if tint_name in _TINT_COLOURS:
        dr, dg, db = _TINT_COLOURS[tint_name]
        # Scale by intensity
        rr = 1.0 + dr * intensity
        gg = 1.0 + dg * intensity
        bb = 1.0 + db * intensity
        # colorchannelmixer: rr=X:gg=Y:bb=Z keeps other channels at 0
        parts.append(
            f"colorchannelmixer=rr={rr:.3f}:gg={gg:.3f}:bb={bb:.3f}"
        )

    # ── vignette ──────────────────────────────────────────────────────────────
    vignette_str = params.get("vignette")
    if vignette_str is not None:
        v = float(vignette_str)
        if v > 0:
            # FFmpeg vignette angle: 0 = no vignette, PI/2 ≈ 1.57 = full
            angle = v * 1.57
            parts.append(f"vignette=angle={angle:.3f}:mode=forward")

    return ",".join(parts)
