"""
File download routes.
GET /files/{run_id}                       — list all output files
GET /files/{run_id}/download/{filename}   — download any output file
GET /files/{run_id}/video                 — stream final_output.mp4 with Range support
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from backend.services import state_service

router = APIRouter(tags=["files"])

_CHUNK = 1024 * 1024  # 1 MiB streaming chunks


# ── helpers ───────────────────────────────────────────────────────────────────

def _guess_media_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _iter_file(path: Path, start: int, end: int):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/files/{run_id}")
async def list_files(run_id: str) -> list[dict[str, Any]]:
    return state_service.list_files(run_id)


@router.get("/files/{run_id}/download/{filename:path}")
async def download_file(run_id: str, filename: str) -> FileResponse:
    path = state_service.resolve_file(run_id, filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found for run_id={run_id}",
        )
    return FileResponse(
        path=str(path),
        media_type=_guess_media_type(path),
        filename=path.name,
    )


@router.get("/files/{run_id}/video", response_model=None)
async def stream_video(run_id: str, request: Request) -> StreamingResponse | FileResponse:
    video_path = state_service.get_video_path(run_id)
    if video_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Video not found for run_id={run_id}",
        )

    total = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            range_val = range_header.strip().replace("bytes=", "")
            parts = range_val.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else total - 1
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="Invalid Range header")

        # Clamp to file bounds
        start = max(0, start)
        end = min(end, total - 1)

        if start > end or start >= total:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")

        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(
            _iter_file(video_path, start, end),
            status_code=206,
            headers=headers,
            media_type="video/mp4",
        )

    # Full file (no Range header)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(total),
        "Content-Type": "video/mp4",
    }
    return StreamingResponse(
        _iter_file(video_path, 0, total - 1),
        status_code=200,
        headers=headers,
        media_type="video/mp4",
    )