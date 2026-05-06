"""
WebSocket routes.
Exposes GET /ws/logs/{run_id} for real-time log streaming.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.websocket.manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/logs/{run_id}")
async def websocket_logs(run_id: str, ws: WebSocket) -> None:
    """
    WebSocket endpoint that streams log lines for a given run_id.
    Replays buffered history on connect, then forwards any new broadcasts.
    Handles ping/pong keepalive by echoing messages sent by the client.
    """
    await ws_manager.connect(run_id, ws)
    try:
        while True:
            # Block waiting for client messages (ping frames / close).
            # Any text message is treated as a ping and echoed back.
            data = await ws.receive_text()
            if data.strip().lower() in ("ping", ""):
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(run_id, ws)