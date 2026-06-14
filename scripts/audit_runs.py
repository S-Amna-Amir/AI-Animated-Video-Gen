"""
scripts/audit_runs.py
----------------------
Read-only audit of all pipeline run directories.
Prints a report of old-style and new-style runs.
Does NOT delete or modify anything.

Usage:
    python scripts/audit_runs.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def human_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def is_complete(run_dir: Path) -> bool:
    """A Phase 3 run is 'complete' if it has a final_output.mp4."""
    return any(run_dir.rglob("final_output.mp4"))


SEP = "=" * 70

print(SEP)
print("  PROJECT MONTAGE — RUN STORAGE AUDIT")
print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

# ── OLD-STYLE: data/outputs/Phase2/ ──────────────────────────────────────────
p2_base = DATA / "outputs" / "Phase2"
print(f"\n{'─'*70}")
print(f"  OLD-STYLE  data/outputs/Phase2/")
print(f"{'─'*70}")
p2_runs = sorted(p2_base.iterdir()) if p2_base.exists() else []
if not p2_runs:
    print("  (empty)")
else:
    total_p2 = 0
    for r in p2_runs:
        sz = dir_size(r)
        total_p2 += sz
        has_manifest = (r / "timing_manifest.json").exists()
        has_summary  = (r / "phase2_summary.json").exists()
        status = "complete" if (has_manifest and has_summary) else "incomplete/orphaned"
        ts = ""
        if has_summary:
            try:
                d = json.loads((r / "phase2_summary.json").read_text())
                ts = d.get("timestamp", "")[:19]
            except Exception:
                pass
        print(f"  {r.name:<12}  {status:<22}  {human_size(sz):>10}  {ts}")
    print(f"\n  Total: {len(p2_runs)} runs  |  {human_size(total_p2)}")

# ── OLD-STYLE: data/outputs/Phase3/ ──────────────────────────────────────────
p3_base = DATA / "outputs" / "Phase3"
print(f"\n{'─'*70}")
print(f"  OLD-STYLE  data/outputs/Phase3/")
print(f"{'─'*70}")
p3_runs = sorted(p3_base.iterdir()) if p3_base.exists() else []
if not p3_runs:
    print("  (empty)")
else:
    total_p3 = 0
    complete_count = 0
    orphaned_count = 0
    for r in p3_runs:
        sz  = dir_size(r)
        total_p3 += sz
        ok  = is_complete(r)
        complete_count  += int(ok)
        orphaned_count  += int(not ok)
        has_vm = (r / "version_manifest.json").exists()
        ts = ""
        try:
            p3out = r / "phase3_output.json"
            if p3out.exists():
                d = json.loads(p3out.read_text())
                ts = d.get("timestamp", "")[:19]
        except Exception:
            pass
        flags = []
        if ok:     flags.append("final_output.mp4")
        if has_vm: flags.append("version_manifest")
        status = "complete" if ok else "incomplete/orphaned"
        print(f"  {r.name:<12}  {status:<22}  {human_size(sz):>10}  {ts}  [{', '.join(flags)}]")
    print(f"\n  Total: {len(p3_runs)} runs  |  "
          f"{complete_count} complete  |  {orphaned_count} incomplete/orphaned  |  {human_size(total_p3)}")

# ── NEW-STYLE: data/runs/ ─────────────────────────────────────────────────────
runs_base = DATA / "runs"
print(f"\n{'─'*70}")
print(f"  NEW-STYLE  data/runs/")
print(f"{'─'*70}")
new_runs = sorted(runs_base.iterdir()) if runs_base.exists() else []
if not new_runs:
    print("  (empty — no projects created yet)")
else:
    total_new = 0
    for r in new_runs:
        if not r.is_dir():
            continue
        sz = dir_size(r)
        total_new += sz
        mf = r / "manifest.json"
        if mf.exists():
            m = json.loads(mf.read_text())
            title    = m.get("title", "?")
            created  = m.get("created_at", "")[:19]
            phases   = m.get("phases", {})
            p_status = " | ".join(f"p{k[-1]}:{v.get('status','?')}" for k, v in phases.items())
            edits    = len(m.get("edits", []))
            print(f"  {r.name}")
            print(f"    title={title!r}  created={created}  {p_status}  edits={edits}  size={human_size(sz)}")
        else:
            print(f"  {r.name:<50}  {human_size(sz):>10}  (no manifest.json)")
    print(f"\n  Total: {len(new_runs)} projects  |  {human_size(total_new)}")

# ── Cache ─────────────────────────────────────────────────────────────────────
cache_dir = DATA / "cache"
print(f"\n{'─'*70}")
print(f"  CACHE  data/cache/  (shared, not per-run)")
print(f"{'─'*70}")
if cache_dir.exists():
    for sub in sorted(cache_dir.iterdir()):
        if sub.is_dir():
            files = list(sub.rglob("*"))
            sz = sum(f.stat().st_size for f in files if f.is_file())
            print(f"  {sub.name:<20}  {len([f for f in files if f.is_file()]):>4} files  {human_size(sz):>10}")
else:
    print("  (does not exist)")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  SUMMARY")
print(SEP)
print(f"  Old Phase2 runs  : {len(p2_runs)}")
print(f"  Old Phase3 runs  : {len(p3_runs)}"
      + (f"  ({complete_count} complete, {orphaned_count} orphaned)" if p3_runs else ""))
print(f"  New-style runs   : {len([r for r in new_runs if r.is_dir()] if runs_base.exists() else [])}")
print()
print("  RECOMMENDATION:")
if p3_runs:
    print(f"  → {orphaned_count} orphaned Phase3 runs can be deleted manually once you confirm")
    print(f"    none are needed. They are listed above as 'incomplete/orphaned'.")
print(f"  → New runs will be created under data/runs/ going forward.")
print(f"  → data/outputs/ should NOT be committed to git (add to .gitignore).")
print(f"  → data/cache/   should NOT be committed to git (already listed).")
print(SEP)
