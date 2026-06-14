"""
agents/edit_agent/run_context.py
---------------------------------
RunContext carries the explicit source-run IDs for a Phase 5 edit session.

Instead of calling _latest_phase2_run() / _latest_phase3_run_id() at
random points during execution (which races against filesystem mtimes),
we resolve ONCE at the start of EditExecutor.execute() and pass the result
everywhere through this object.

This is the single source of truth for:
  - which Phase 2 run produced the audio used in this edit
  - which Phase 3 run is the parent (the video being edited)
  - which new Phase 3 run this edit will produce
"""
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PHASE2_BASE = Path("data/outputs/Phase2")
PHASE3_BASE = Path("data/outputs/Phase3")


@dataclass
class RunContext:
    # ── Resolved at start of execute() ───────────────────────────────────────
    source_phase2_run_id:  str = ""   # Phase 2 run whose audio will be used
    source_phase2_run_dir: str = ""
    source_phase3_run_id:  str = ""   # Phase 3 run being edited (the parent video)
    source_phase3_run_dir: str = ""

    # ── Filled in after new Phase 3 run dir is created ───────────────────────
    new_phase3_run_id:     str = ""
    new_phase3_run_dir:    str = ""

    # ── Edit provenance ───────────────────────────────────────────────────────
    edit_query:            str = ""
    intent_label:          str = ""   # e.g. "change_voice_tone"
    intent_target:         str = ""   # e.g. "audio"
    edit_timestamp:        str = field(default_factory=lambda: datetime.now().isoformat())

    # ── Snapshot versions bracketing this edit ────────────────────────────────
    snapshot_before:       int = 0
    snapshot_after:        int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_source_runs(
    preferred_phase2_run_id: Optional[str] = None,
    preferred_phase3_run_id: Optional[str] = None,
) -> RunContext:
    """
    Build a RunContext by resolving the current 'best' source runs.

    Priority:
      1. Explicit IDs passed in (e.g. from the API request)
      2. The Phase 3 run that has a version_manifest.json with a linked Phase 2 run
      3. Latest by run number (not mtime — avoids partial/in-progress runs)

    Returns a populated RunContext (source fields only; new_* fields empty until
    the executor creates the new run dir).
    """
    ctx = RunContext()

    # ── Resolve Phase 3 source ────────────────────────────────────────────────
    if preferred_phase3_run_id:
        p3_dir = PHASE3_BASE / preferred_phase3_run_id
        if p3_dir.exists():
            ctx.source_phase3_run_id  = preferred_phase3_run_id
            ctx.source_phase3_run_dir = str(p3_dir)
    
    if not ctx.source_phase3_run_id:
        ctx.source_phase3_run_id, ctx.source_phase3_run_dir = _latest_successful_run(
            PHASE3_BASE, summary_file="phase3_output.json"
        )

    # ── Resolve Phase 2 source ────────────────────────────────────────────────
    # First try: read from the Phase 3 run's version_manifest.json
    if ctx.source_phase3_run_dir:
        p3_dir = Path(ctx.source_phase3_run_dir)
        vm = _read_version_manifest(p3_dir)
        if vm:
            linked_p2 = vm.get("source_phase2_run_id", "")
            linked_p2_dir = vm.get("source_phase2_run_dir", "")
            if linked_p2 and Path(linked_p2_dir).exists():
                ctx.source_phase2_run_id  = linked_p2
                ctx.source_phase2_run_dir = linked_p2_dir
                logger.info(
                    "[RunContext] Resolved Phase 2 run from version_manifest: %s", linked_p2
                )

        # Second try: read from phase3_output.json input.phase2_run_dir
        if not ctx.source_phase2_run_id:
            p3_out = p3_dir / "phase3_output.json"
            if p3_out.exists():
                try:
                    data = json.loads(p3_out.read_text(encoding="utf-8"))
                    p2_dir_str = data.get("input", {}).get("phase2_run_dir", "")
                    if p2_dir_str and Path(p2_dir_str).exists():
                        ctx.source_phase2_run_id  = Path(p2_dir_str).name
                        ctx.source_phase2_run_dir = p2_dir_str
                        logger.info(
                            "[RunContext] Resolved Phase 2 run from phase3_output: %s",
                            ctx.source_phase2_run_id
                        )
                except Exception as e:
                    logger.warning("[RunContext] Could not read phase3_output.json: %s", e)

    # Third try: explicit preference or latest by number
    if not ctx.source_phase2_run_id:
        if preferred_phase2_run_id:
            p2_dir = PHASE2_BASE / preferred_phase2_run_id
            if p2_dir.exists():
                ctx.source_phase2_run_id  = preferred_phase2_run_id
                ctx.source_phase2_run_dir = str(p2_dir)

    if not ctx.source_phase2_run_id:
        ctx.source_phase2_run_id, ctx.source_phase2_run_dir = _latest_successful_run(
            PHASE2_BASE, summary_file="phase2_summary.json"
        )

    logger.info(
        "[RunContext] Resolved — source_p2=%s  source_p3=%s",
        ctx.source_phase2_run_id, ctx.source_phase3_run_id,
    )
    return ctx


def write_version_manifest(run_dir: Path, ctx: RunContext) -> Path:
    """
    Write version_manifest.json into a Phase 3 run directory.
    This is the authoritative provenance record for that video version.
    """
    manifest = {
        # ── New run identity ──────────────────────────────────────────────────
        "run_id":              ctx.new_phase3_run_id or Path(run_dir).name,
        "run_dir":             str(run_dir),
        # ── Parent chain ──────────────────────────────────────────────────────
        "source_phase2_run_id":  ctx.source_phase2_run_id,
        "source_phase2_run_dir": ctx.source_phase2_run_dir,
        "source_phase3_run_id":  ctx.source_phase3_run_id,
        "source_phase3_run_dir": ctx.source_phase3_run_dir,
        # ── Edit provenance ───────────────────────────────────────────────────
        "edit_query":          ctx.edit_query,
        "intent_label":        ctx.intent_label,
        "intent_target":       ctx.intent_target,
        "edit_timestamp":      ctx.edit_timestamp,
        # ── Snapshot bracketing ───────────────────────────────────────────────
        "snapshot_before":     ctx.snapshot_before,
        "snapshot_after":      ctx.snapshot_after,
    }
    out = run_dir / "version_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("[RunContext] version_manifest.json written → %s", out)
    return out


def read_version_manifest(run_dir: Path) -> Optional[dict]:
    """Read version_manifest.json from a Phase 3 run dir. Returns None if missing."""
    return _read_version_manifest(run_dir)


def _read_version_manifest(run_dir: Path) -> Optional[dict]:
    p = run_dir / "version_manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[RunContext] Could not read version_manifest: %s", e)
        return None


def _latest_successful_run(base: Path, summary_file: str) -> tuple[str, str]:
    """
    Return (run_id, run_dir_str) for the latest run by run number that has
    a summary file (indicating it completed).  Falls back to mtime if needed.
    """
    if not base.exists():
        return "", ""

    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return "", ""

    # Filter to runs that have a summary file (completed runs only)
    complete = [d for d in dirs if (d / summary_file).exists()]
    pool = complete if complete else dirs

    # Sort by run number extracted from name (run_01, run_02, …)
    def _run_num(p: Path) -> int:
        parts = p.name.rsplit("_", 1)
        return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

    latest = max(pool, key=_run_num)
    return latest.name, str(latest)
