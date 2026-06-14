"""
agents/pipeline_run_manager.py
--------------------------------
PipelineRunManager  —  one folder per story pipeline run.

Layout
------
data/runs/<run_id>/
    manifest.json          ← single source of truth for this run
    phase1/
        scene_manifest.json
        character_db.json
        memory_log.json
        images/
    phase2/
        timing_manifest.json
        master_audio_track.mp3
        phase2_summary.json
        phase2_config.json
        bgm_metadata.json
        audio/
    phase3/
        images/
        clips/
        final_output.mp4
        phase3_output.json
        version_manifest.json
    phase5/
        edit_001/
            edit_manifest.json   ← what changed + intent
            final_output.mp4     ← copy of the new video
        edit_002/
            ...

<run_id> format: YYYYMMDD_HHMMSS_<slug>
  e.g.  20260615_143022_pirate-adventure
  Sorts chronologically by filename — no metadata read needed.

Rules
-----
- Every phase writes ONLY into its phaseN/ subfolder here.
- No writes to data/outputs/Phase2/ or data/outputs/Phase3/.
- data/outputs/ keeps Phase 1 JSONs as a shared "current-run pointer"
  so legacy paths (VideoAgent, AudioAgent defaults) can find them.
- data/cache/ stays shared across runs (TTS/BGM caching).
- manifest.json is updated by each phase on completion/failure.
"""
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUNS_BASE = Path("data/runs")


# ── Slug helpers ──────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50] or "untitled"


def _make_run_id(title: str) -> str:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(title)
    return f"{ts}_{slug}"


# ── PipelineRunManager ────────────────────────────────────────────────────────

class PipelineRunManager:
    """Manages a single data/runs/<run_id>/ project folder."""

    def __init__(self, run_dir: Path):
        self.run_dir    = run_dir
        self.phase1_dir = run_dir / "phase1"
        self.phase2_dir = run_dir / "phase2"
        self.phase3_dir = run_dir / "phase3"
        self.phase5_dir = run_dir / "phase5"
        self._manifest: Dict[str, Any] = {}

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, title: str) -> "PipelineRunManager":
        """Create a new run folder for *title*. Always creates a fresh folder."""
        RUNS_BASE.mkdir(parents=True, exist_ok=True)
        run_id  = _make_run_id(title)
        run_dir = RUNS_BASE / run_id
        # In the (very unlikely) case of a collision within the same second:
        suffix = 0
        while run_dir.exists():
            suffix += 1
            run_dir = RUNS_BASE / f"{run_id}_{suffix}"

        pm = cls(run_dir)
        pm._init_dirs()
        pm._manifest = {
            "run_id":     run_dir.name,
            "title":      title,
            "slug":       _slugify(title),
            "created_at": datetime.now().isoformat(),
            "phases": {
                "phase1": {"status": "pending"},
                "phase2": {"status": "pending"},
                "phase3": {"status": "pending"},
            },
            "edits": [],
        }
        pm._save()
        logger.info("[PipelineRunManager] Created: %s", run_dir)
        return pm

    @classmethod
    def load(cls, run_id_or_dir: str) -> Optional["PipelineRunManager"]:
        """Load by run_id (folder name) or full path."""
        RUNS_BASE.mkdir(parents=True, exist_ok=True)
        candidate = RUNS_BASE / run_id_or_dir
        if not candidate.exists():
            candidate = Path(run_id_or_dir)
        if not candidate.exists() or not (candidate / "manifest.json").exists():
            return None
        pm = cls(candidate)
        pm._manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        return pm

    @classmethod
    def latest(cls) -> Optional["PipelineRunManager"]:
        """Return the most recently created project with a manifest.json."""
        RUNS_BASE.mkdir(parents=True, exist_ok=True)
        dirs = sorted(
            [p for p in RUNS_BASE.iterdir()
             if p.is_dir() and (p / "manifest.json").exists()],
            reverse=True,   # lexicographic = chronological because of YYYYMMDD_HHMMSS_ prefix
        )
        return cls.load(dirs[0].name) if dirs else None

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        """List all runs, newest first, as lightweight dicts."""
        RUNS_BASE.mkdir(parents=True, exist_ok=True)
        results = []
        for p in sorted(
            [d for d in RUNS_BASE.iterdir()
             if d.is_dir() and (d / "manifest.json").exists()],
            reverse=True,
        ):
            try:
                m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
                results.append({
                    "run_id":     m.get("run_id", p.name),
                    "title":      m.get("title", p.name),
                    "slug":       m.get("slug", ""),
                    "created_at": m.get("created_at", ""),
                    "phases":     m.get("phases", {}),
                    "edit_count": len(m.get("edits", [])),
                    "run_dir":    str(p),
                })
            except Exception:
                pass
        return results

    # ── Directory setup ───────────────────────────────────────────────────────

    def _init_dirs(self):
        for d in (
            self.phase1_dir,
            self.phase1_dir / "images",
            self.phase2_dir,
            self.phase2_dir / "audio",
            self.phase3_dir,
            self.phase3_dir / "images",
            self.phase3_dir / "clips",
            self.phase5_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ── Phase lifecycle ───────────────────────────────────────────────────────

    def mark_phase_complete(self, phase: int) -> None:
        self._manifest.setdefault("phases", {})[f"phase{phase}"] = {
            "status":       "complete",
            "completed_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info("[PipelineRunManager] Phase %d complete  run=%s", phase, self.run_id)

    def mark_phase_failed(self, phase: int, error: str = "") -> None:
        self._manifest.setdefault("phases", {})[f"phase{phase}"] = {
            "status":    "failed",
            "error":     error,
            "failed_at": datetime.now().isoformat(),
        }
        self._save()
        logger.warning("[PipelineRunManager] Phase %d FAILED  run=%s  %s",
                       phase, self.run_id, error[:120])

    # ── Edit management ───────────────────────────────────────────────────────

    def next_edit_dir(self, edit_query: str = "") -> Path:
        """Create edit_NNN/ under phase5/ and write a skeleton edit_manifest.json."""
        existing = (
            [p for p in self.phase5_dir.iterdir()
             if p.is_dir() and p.name.startswith("edit_")]
            if self.phase5_dir.exists() else []
        )
        n = len(existing) + 1
        edit_dir = self.phase5_dir / f"edit_{n:03d}"
        edit_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "edit_index":  n,
            "edit_query":  edit_query,
            "timestamp":   datetime.now().isoformat(),
            "output_file": None,
            "intent":      {},
            "completed_at": None,
        }
        (edit_dir / "edit_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        logger.info("[PipelineRunManager] Created edit dir: %s", edit_dir)
        return edit_dir

    def finalize_edit(
        self,
        edit_dir: Path,
        output_video: Optional[Path],
        intent: Dict[str, Any] = None,
    ) -> None:
        """Copy output video into edit_dir and update both manifests."""
        dest = None
        if output_video and output_video.exists():
            dest = edit_dir / output_video.name
            if output_video != dest:
                shutil.copy2(output_video, dest)
            logger.info("[PipelineRunManager] Edit video → %s", dest)

        # Update edit_manifest.json
        em_path = edit_dir / "edit_manifest.json"
        em: Dict = {}
        if em_path.exists():
            em = json.loads(em_path.read_text(encoding="utf-8"))
        em["output_file"]  = str(dest) if dest else None
        em["intent"]       = intent or {}
        em["completed_at"] = datetime.now().isoformat()
        em_path.write_text(json.dumps(em, indent=2), encoding="utf-8")

        # Update run manifest edits list
        self._manifest.setdefault("edits", []).append({
            "edit_index":  em.get("edit_index"),
            "edit_query":  em.get("edit_query"),
            "output_file": em.get("output_file"),
            "timestamp":   em.get("completed_at"),
            "intent":      em.get("intent", {}),
        })
        self._save()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self._manifest, indent=2), encoding="utf-8"
        )

    def get_manifest(self) -> Dict[str, Any]:
        return dict(self._manifest)

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def run_id(self) -> str:
        return self._manifest.get("run_id", self.run_dir.name)

    @property
    def title(self) -> str:
        return self._manifest.get("title", self.run_dir.name)

    @property
    def slug(self) -> str:
        return self._manifest.get("slug", "")

    def __repr__(self) -> str:
        return f"<PipelineRunManager run_id={self.run_id!r}>"
