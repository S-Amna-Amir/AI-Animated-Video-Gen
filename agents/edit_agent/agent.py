"""
agents/edit_agent/agent.py
----------------------------
Edit Agent — orchestrates the full Phase 5 edit + undo pipeline.

Flow:
  1. Take a "before" snapshot (StateManager)
  2. Classify the edit query (IntentClassifier)
  3. Plan the re-runs (EditPlanner)
  4. Execute the plan (EditExecutor)
  5. Take an "after" snapshot
  6. Return structured result
"""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from agents.edit_agent.intent_classifier import IntentClassifier
from agents.edit_agent.planner import EditPlanner
from agents.edit_agent.executor import EditExecutor
from state_manager.state_manager import StateManager

logger = logging.getLogger(__name__)


class EditAgent:
    """
    Entry point for Phase 5.  Call agent.edit(query) to apply a free-text edit.
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.classifier = IntentClassifier()
        self.planner    = EditPlanner()
        self.sm         = StateManager()
        self._log_cb    = log_callback

    def _log(self, msg: str) -> None:
        logger.info(msg)
        if self._log_cb:
            self._log_cb(msg)

    async def edit(self, query: str) -> Dict[str, Any]:
        """
        Apply a free-text edit command to the current pipeline outputs.

        Returns:
        {
            "success":      bool,
            "intent":       dict,
            "plan":         dict,
            "execution":    dict,
            "snapshot_before": int,   # version number
            "snapshot_after":  int,
            "error":        str | None
        }
        """
        self._log(f"[EditAgent] Query: {query}")

        # ── 1. Snapshot before ────────────────────────────────────────────────
        snap_before = self.sm.snapshot(
            description="Pre-edit snapshot",
            edit_query=query,
        )
        self._log(f"[EditAgent] Snapshot before: v{snap_before['version']:03d}")

        # ── 2. Classify ───────────────────────────────────────────────────────
        intent = self.classifier.classify(query)
        self._log(f"[EditAgent] Intent: {intent['intent']} | target: {intent['target']} | scope: {intent['scope']}")

        # ── 3. Plan ───────────────────────────────────────────────────────────
        plan = self.planner.plan(intent)
        self._log(f"[EditAgent] Plan: {plan['description']} ({len(plan['steps'])} steps)")

        # ── 4. Execute ────────────────────────────────────────────────────────
        executor = EditExecutor(log_callback=self._log_cb)
        execution = await executor.execute(plan)

        # ── 5. Snapshot after ─────────────────────────────────────────────────
        snap_after = self.sm.snapshot(
            description=f"After edit: {intent['intent']}",
            edit_query=query,
            intent=intent,
        )
        self._log(f"[EditAgent] Snapshot after: v{snap_after['version']:03d}")

        result = {
            "success":         execution["success"],
            "intent":          intent,
            "plan":            plan,
            "execution":       execution,
            "snapshot_before": snap_before["version"],
            "snapshot_after":  snap_after["version"],
            "error":           None if execution["success"] else "One or more steps failed",
        }

        if execution["success"]:
            self._log(f"[EditAgent] ✓ Edit complete (v{snap_before['version']} → v{snap_after['version']})")
        else:
            self._log(f"[EditAgent] ✗ Edit failed — reverted snapshot available at v{snap_before['version']}")

        return result

    def undo(self, version: int) -> Dict[str, Any]:
        """Revert pipeline state to a specific snapshot version."""
        self._log(f"[EditAgent] Reverting to version v{version:03d}")
        result = self.sm.revert(version)
        self._log(f"[EditAgent] Revert {'complete' if result['success'] else 'failed'}")
        return result

    def history(self):
        return self.sm.history()
