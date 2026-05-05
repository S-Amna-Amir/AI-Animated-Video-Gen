"""
WebSocket connection manager.
Maintains per-run_id subscriber lists and broadcasts log lines to all connected clients.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections keyed by run_id."""

    def __init__(self) -> None:
        # run_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        # run_id -> buffered log lines (so late-joiners can replay recent history)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._MAX_HISTORY = 200

    # ── connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[run_id].append(ws)
        # replay buffered history so the UI catches up immediately
        for entry in self._history[run_id]:
            try:
                await ws.send_text(json.dumps(entry))
            except Exception:
                break

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        subs = self._connections.get(run_id, [])
        if ws in subs:
            subs.remove(ws)

    # ── broadcasting ─────────────────────────────────────────────────────────

    async def broadcast(
        self,
        run_id: str,
        message: str,
        log_type: str = "info",
    ) -> None:
        """Send a log line to every subscriber of run_id."""
        entry: dict[str, Any] = {
            "type": log_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        }
        # buffer for late-joiners
        buf = self._history[run_id]
        buf.append(entry)
        if len(buf) > self._MAX_HISTORY:
            buf.pop(0)

        payload = json.dumps(entry)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(run_id, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)

    # convenience wrappers ────────────────────────────────────────────────────

    async def info(self, run_id: str, message: str) -> None:
        await self.broadcast(run_id, message, "info")

    async def success(self, run_id: str, message: str) -> None:
        await self.broadcast(run_id, message, "success")

    async def warn(self, run_id: str, message: str) -> None:
        await self.broadcast(run_id, message, "warn")

    async def error(self, run_id: str, message: str) -> None:
        await self.broadcast(run_id, message, "error")

    def clear_history(self, run_id: str) -> None:
        self._history.pop(run_id, None)


# singleton used across the entire app
ws_manager = ConnectionManager()