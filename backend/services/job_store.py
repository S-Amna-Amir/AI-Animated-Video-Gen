"""
backend/services/job_store.py
-------------------------------
In-process job registry. Stores job state + log lines.
Replaced by Redis/DB for multi-worker deployments — fine for single-process.
"""
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, phase: int, params: Dict) -> Dict:
        job = {
            "job_id":     job_id,
            "phase":      phase,
            "params":     params,
            "status":     "queued",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "logs":       [],
            "result":     None,
            "error":      None,
        }
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Dict]:
        return self._jobs.get(job_id)

    def list_by_phase(self, phase: int) -> List[Dict]:
        return [j for j in self._jobs.values() if j["phase"] == phase]

    def log(self, job_id: str, message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["logs"].append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
                )
                self._jobs[job_id]["updated_at"] = datetime.now().isoformat()

    def set_running(self, job_id: str) -> None:
        self._update(job_id, status="running")

    def set_complete(self, job_id: str, result: Any = None) -> None:
        self._update(job_id, status="complete", result=result)

    def set_failed(self, job_id: str, error: str) -> None:
        self._update(job_id, status="failed", error=error)

    def _update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)
                self._jobs[job_id]["updated_at"] = datetime.now().isoformat()
    
    def set_pending_hitl(self, job_id: str, state: dict, script: dict):
        with self._lock:
            self._jobs[job_id]["status"] = "pending_hitl"
            self._jobs[job_id]["script"] = script          # exposed to frontend
            self._jobs[job_id]["_parked_state"] = state    # internal, not JSON-serialised to client

    def get_parked_state(self, job_id: str) -> dict | None:
        with self._lock:
            return self._jobs.get(job_id, {}).get("_parked_state")
