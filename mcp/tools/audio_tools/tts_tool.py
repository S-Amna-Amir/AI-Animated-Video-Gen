"""
mcp/tools/audio_tools/tts_tool.py
-----------------------------------
Edge-TTS wrapper for dialogue synthesis.
"""
import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import edge_tts

logger = logging.getLogger(__name__)


class TTSTool:
    def __init__(self, output_base_path: str = "data/outputs/Phase2"):
        self.output_base_path = Path(output_base_path)
        self.output_base_path.mkdir(parents=True, exist_ok=True)

    async def synthesize_dialogue(
        self, text: str, character_name: str, voice: str,
        scene_id: int, line_index: int, output_dir: Path,
    ) -> Dict:
        scene_dir = output_dir / f"scene{scene_id:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)
        safe_name = character_name.replace(" ", "_").upper()
        filepath = scene_dir / f"{safe_name}_line{line_index:03d}.mp3"
        clean_text = text.strip().strip('"').strip("'")
        logger.info(f"[TTS] {character_name} | scene {scene_id} line {line_index} | {voice}")
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(filepath))
        duration_ms = self._get_duration_ms(str(filepath))
        logger.info(f"[TTS] Saved {filepath.name} ({duration_ms}ms)")
        return {
            "speaker": character_name, "scene_id": scene_id,
            "line_index": line_index, "audio_file": str(filepath),
            "duration_ms": duration_ms, "text": clean_text,
            "voice": voice, "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def _get_duration_ms(filepath: str) -> int:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", filepath],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return int(float(result.stdout.strip()) * 1000)
        except Exception:
            pass
        try:
            size_kb = os.path.getsize(filepath) / 1024
            return max(1000, int((size_kb / 16) * 1000))
        except Exception:
            return 1000

    async def synthesize_batch(self, dialogues: List[Dict], output_dir: Path) -> List[Dict]:
        results = []
        for d in dialogues:
            try:
                result = await self.synthesize_dialogue(
                    text=d["text"], character_name=d["speaker"], voice=d["voice"],
                    scene_id=d["scene_id"], line_index=d["line_index"], output_dir=output_dir,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"[TTS] Failed {d.get('speaker')} line {d.get('line_index')}: {e}")
        return results
