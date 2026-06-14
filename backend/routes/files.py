"""
backend/routes/files.py
------------------------
File serving endpoints — lets the frontend stream/download pipeline outputs.

GET /api/files/video/{phase3_run_id}      — stream final MP4
GET /api/files/audio/{phase2_run_id}      — stream master audio MP3
GET /api/files/image/{phase1_rel_path}    — serve character image
GET /api/files/manifest/{phase2_run_id}   — download timing_manifest.json
"""
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

PHASE1_IMAGES = Path("data/outputs/images")
PHASE2_DIR    = Path("data/outputs/Phase2")
PHASE3_DIR    = Path("data/outputs/Phase3")


def _safe(path: Path) -> Path:
    """Raise 404 if path doesn't exist."""
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return path


@router.get("/video/{run_id}")
async def get_video(run_id: str):
    video = _safe(PHASE3_DIR / run_id / "final_output.mp4")
    return FileResponse(str(video), media_type="video/mp4",
                        filename="final_output.mp4")


@router.get("/video/{run_id}/captioned")
async def get_captioned_video(run_id: str):
    # Try captioned first, fall back to plain
    captioned = PHASE3_DIR / run_id / "final_output_captioned.mp4"
    plain     = PHASE3_DIR / run_id / "final_output.mp4"
    path      = captioned if captioned.exists() else plain
    _safe(path)
    return FileResponse(str(path), media_type="video/mp4", filename=path.name)


@router.get("/audio/{run_id}")
async def get_audio(run_id: str):
    audio = _safe(PHASE2_DIR / run_id / "master_audio_track.mp3")
    return FileResponse(str(audio), media_type="audio/mpeg",
                        filename="master_audio_track.mp3")


@router.get("/image/{filename:path}")
async def get_image(filename: str):
    # filename is relative, e.g. "alex.png" or "images/alex.png"
    decoded = urllib.parse.unquote(filename)
    # Try Phase 1 images dir, then absolute path as fallback
    candidates = [
        PHASE1_IMAGES / decoded,
        Path("data/outputs") / decoded,
        Path(decoded),
    ]
    for p in candidates:
        if p.exists():
            suffix = p.suffix.lower()
            media  = {"png": "image/png", "jpg": "image/jpeg",
                      "jpeg": "image/jpeg", "gif": "image/gif"}.get(suffix.lstrip("."), "image/png")
            return FileResponse(str(p), media_type=media)
    raise HTTPException(status_code=404, detail=f"Image not found: {filename}")


@router.get("/manifest/{run_id}")
async def get_manifest(run_id: str):
    manifest = _safe(PHASE2_DIR / run_id / "timing_manifest.json")
    return FileResponse(str(manifest), media_type="application/json",
                        filename="timing_manifest.json")


@router.get("/scene-manifest")
async def get_scene_manifest():
    """Return Phase 1 scene_manifest.json for the frontend."""
    candidates = [
        Path("data/outputs/scene_manifest.json"),
        Path("data/outputs/scene_manifest_auto.json"),
        Path("data/outputs/scene_manifest_manual.json"),
    ]
    for p in candidates:
        if p.exists():
            return FileResponse(str(p), media_type="application/json")
    raise HTTPException(status_code=404, detail="No scene manifest found. Run Phase 1 first.")


@router.get("/character-db")
async def get_character_db():
    """Return Phase 1 character_db.json for the frontend."""
    candidates = [
        Path("data/outputs/character_db.json"),
        Path("data/outputs/character_db_auto.json"),
        Path("data/outputs/character_db_manual.json"),
    ]
    for p in candidates:
        if p.exists():
            return FileResponse(str(p), media_type="application/json")
    raise HTTPException(status_code=404, detail="No character DB found. Run Phase 1 first.")
