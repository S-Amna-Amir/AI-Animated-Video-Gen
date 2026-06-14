"""
mcp/tools/video_tools/subtitle_generator.py
---------------------------------------------
Generates SRT from timing manifest and burns subtitles via FFmpeg.
"""
import json
import logging
import os
import subprocess
from pathlib import Path

import imageio_ffmpeg

logger = logging.getLogger(__name__)


def ms_to_srt(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s  = divmod(s, 60)
    h, m  = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _video_duration_ms(video_path: str) -> int:
    try:
        from moviepy import VideoFileClip
        with VideoFileClip(video_path) as c:
            return int(c.duration * 1000)
    except Exception:
        return 999_999_999


def generate_srt(manifest_path: str, video_duration_ms: int, output_srt: str) -> str:
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    entries = []
    for e in manifest:
        text = e.get("text", "").strip()
        if not text:
            continue
        start = int(e.get("start_ms", 0))
        end   = int(e.get("end_ms", start + int(e.get("duration_ms", 0))))
        if start >= video_duration_ms or end <= start:
            continue
        end = min(end, video_duration_ms - 50)
        entries.append({"start_ms": start, "end_ms": end, "text": text, "speaker": e.get("speaker", "")})

    entries.sort(key=lambda x: x["start_ms"])
    for i in range(len(entries) - 1):
        if entries[i]["end_ms"] > entries[i + 1]["start_ms"]:
            entries[i]["end_ms"] = entries[i + 1]["start_ms"] - 1

    lines = []
    for i, e in enumerate(entries, 1):
        lines += [str(i), f"{ms_to_srt(e['start_ms'])} --> {ms_to_srt(e['end_ms'])}", e["text"], ""]

    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_srt


def burn_captions(manifest_path: str, video_path: str) -> str:
    vp  = Path(video_path)
    out = vp.parent / f"{vp.stem}_captioned{vp.suffix}"
    dur = _video_duration_ms(video_path)
    srt = vp.parent / "temp_captions.srt"
    generate_srt(manifest_path, dur, str(srt))

    esc  = str(srt).replace("\\", "/").replace(":", "\\:")
    style = "FontSize=20,Alignment=2,MarginV=30,Outline=2,Shadow=1,FontName=Arial"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg, "-y", "-i", video_path,
        "-vf", f"subtitles='{esc}':force_style='{style}'",
        "-c:a", "copy", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    srt.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle burn failed: {r.stderr[-300:]}")
    return str(out)
