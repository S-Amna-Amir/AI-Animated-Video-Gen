"""
agents/audio_agent/agent.py
-----------------------------
Phase 2 Audio Agent — TTS synthesis + timing manifest.
Reads Phase 1 outputs, synthesises dialogue with Edge-TTS,
layers BGM via MoviePy, builds timing manifest for Phase 3.
"""
import asyncio
import importlib
import json
import logging
import math
import os
import subprocess
import shutil
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import imageio_ffmpeg
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from mcp.tools.audio_tools.voice_mapper import VoiceMapper
from mcp.tools.audio_tools.tts_tool import TTSTool
from mcp.tools.audio_tools.bgm_tool import search_and_download_bgm, BGMLocator
from mcp.tools.audio_tools.scene_mood_analyzer import SceneMoodAnalyzer
from agents.audio_agent.run_manager import AudioRunManager
from agents.audio_agent.planner import AudioPhasePlanner, DialogueExtractor

logger = logging.getLogger(__name__)


def _ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _decode_audio_to_segment(source_path: Path, source_format: str = "mp3") -> AudioSegment:
    ffmpeg_exe = _ffmpeg_path()
    command = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(source_path),
        "-f", "wav",
        "-",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or f"ffmpeg decode failed for {source_path}")
    return AudioSegment.from_file(BytesIO(result.stdout), format="wav")


def _export_segment_as_mp3(segment: AudioSegment, output_path: Path, bitrate: str = "192k") -> None:
    temp_wav = output_path.with_suffix(".tmp.wav")
    segment.export(str(temp_wav), format="wav")
    try:
        ffmpeg_exe = _ffmpeg_path()
        command = [
            ffmpeg_exe,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(temp_wav),
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            str(output_path),
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or f"ffmpeg encode failed for {output_path}")
    finally:
        try:
            if temp_wav.exists():
                temp_wav.unlink()
        except Exception:
            pass


def _load_moviepy():
    """Lazy MoviePy import so the module stays importable without it installed."""
    afc = importlib.import_module("moviepy.audio.io.AudioFileClip")
    ac  = importlib.import_module("moviepy.audio.AudioClip")
    afx = importlib.import_module("moviepy.audio.fx")

    class _MP:
        AudioFileClip         = afc.AudioFileClip
        CompositeAudioClip    = ac.CompositeAudioClip
        concatenate_audioclips = ac.concatenate_audioclips

    return _MP, afx


def _trim_leading_silence(audio: AudioSegment, silence_threshold: int = -45, chunk_size: int = 20) -> AudioSegment:
    leading_ms = detect_leading_silence(audio, silence_threshold=silence_threshold, chunk_size=chunk_size)
    if leading_ms <= 0:
        return audio
    if leading_ms >= len(audio):
        return audio
    return audio[leading_ms:]


# ── Timing manifest builder ────────────────────────────────────────────────────

class TimingManifestBuilder:
    @staticmethod
    def build_manifest(audio_metadata_list: List[Dict]) -> List[Dict]:
        entries = []
        scene_cursor: Dict[int, int] = {}
        for audio in sorted(audio_metadata_list, key=lambda x: (x["scene_id"], x["line_index"])):
            sid = audio["scene_id"]
            start = scene_cursor.get(sid, 0)
            end   = start + audio["duration_ms"]
            entries.append({
                "scene_id":   sid,
                "speaker":    audio["speaker"],
                "audio_file": audio["audio_file"],
                "start_ms":   start,
                "end_ms":     end,
                "duration_ms": audio["duration_ms"],
                "line_index": audio["line_index"],
                "text":       audio["text"],
            })
            scene_cursor[sid] = end
        return entries


# ── Enhanced Audio Agent ───────────────────────────────────────────────────────

class EnhancedAudioAgent:
    """
    Full Phase 2 pipeline:
      - Edge-TTS per dialogue line
            - One shared Freesound BGM track per run, looped to full length
            - MoviePy: voice-only scene concatenation
      - Master track concatenation
      - Cumulative timing manifest
    """

    def __init__(
        self,
        phase1_data_dir: str = "data/outputs/Phase1",
        phase2_output_dir: str = "data/outputs/Phase2",
        custom_voice_mappings: Optional[Dict[str, str]] = None,
        freesound_api_key: Optional[str] = None,
        run_id: Optional[str] = None,
        reverse_voice_preference: bool = True,
    ):
        self.phase1_data_dir = Path(phase1_data_dir)
        self.voice_mapper    = VoiceMapper(custom_voice_mappings, reverse_preference=reverse_voice_preference)
        self.run_manager     = AudioRunManager(phase2_output_dir)
        self.planner         = AudioPhasePlanner()
        self.freesound_api_key = freesound_api_key or os.getenv("FREESOUND_API_KEY")
        self.groq_api_key    = os.getenv("GROQ_API_KEY")

        groq_client = None
        if self.groq_api_key:
            try:
                from groq import Groq
                groq_client = Groq(api_key=self.groq_api_key)
            except Exception as e:
                logger.warning(f"[Audio] Groq unavailable: {e}")
        self.mood_analyzer = SceneMoodAnalyzer(groq_client=groq_client)

        self.run_manager.create_run_directory(run_id)
        self.tts_tool = TTSTool(str(self.run_manager.get_audio_output_dir()))

        self.bgm_volume = 0.2
        self.scene_manifest: Dict = {}
        self.bgm_metadata: Dict[str, Any] = {}
        self.global_bgm_source: Optional[Path] = None
        self.global_bgm_query: str = ""
        self.cumulative_timing: List[Dict] = []

        logger.info(f"[Audio] EnhancedAudioAgent ready | run={self.run_manager.current_run_id}")
        logger.info(f"[Audio] Freesound={bool(self.freesound_api_key)} | Groq={bool(self.groq_api_key)}")

    # ── Data loading ───────────────────────────────────────────────────────────

    def load_phase1_data(self) -> bool:
        candidates = [
            self.phase1_data_dir / "scene_manifest_auto.json",
            self.phase1_data_dir / "scene_manifest_manual.json",
            self.phase1_data_dir / "scene_manifest.json",
        ]
        found = next((f for f in candidates if f.exists()), None)
        if not found:
            logger.error(f"[Audio] No scene manifest in {self.phase1_data_dir}")
            return False
        with open(found) as f:
            self.scene_manifest = json.load(f)
        logger.info(f"[Audio] Loaded {found.name}")
        return True

    def _extract_dialogues(self) -> List[Dict]:
        dialogues = DialogueExtractor.extract_from_manifest(self.scene_manifest)
        for d in dialogues:
            d["voice"] = self.voice_mapper.get_voice_for_character(d["speaker"])
        return dialogues

    # ── TTS per scene ──────────────────────────────────────────────────────────

    async def _synthesize_scene(
        self, scene_dialogues: List[Dict], scene_id: int
    ):
        """Returns (scene_voice_path | None, enriched_dialogues)."""
        scene_audio_dir = self.run_manager.get_audio_scene_dir(scene_id)
        MP, _ = _load_moviepy()

        dialogue_files: List[Path] = []
        enriched: List[Dict] = []

        for d in scene_dialogues:
            try:
                result = await self.tts_tool.synthesize_dialogue(
                    text=d["text"], character_name=d["speaker"], voice=d["voice"],
                    scene_id=scene_id, line_index=d["line_index"],
                    output_dir=scene_audio_dir,
                )
                fp = Path(result["audio_file"])
                if fp.exists():
                    dialogue_files.append(fp)
                    dc = d.copy()
                    dc["duration_ms"] = result["duration_ms"]
                    dc["audio_file"]  = str(fp)
                    enriched.append(dc)
            except Exception as e:
                logger.warning(f"[Audio] TTS failed {d['speaker']}: {e}")

        if not dialogue_files:
            return None, []

        voice_file = scene_audio_dir / f"scene{scene_id:02d}_voice.mp3"
        clips = []
        try:
            for i, fp in enumerate(dialogue_files):
                try:
                    clip = MP.AudioFileClip(str(fp))
                    if i < len(enriched):
                        enriched[i]["duration_ms"] = int(clip.duration * 1000)
                    clips.append(clip)
                except Exception as e:
                    logger.warning(f"[Audio] Cannot load {fp}: {e}")
            if not clips:
                return None, []
            scene_audio = MP.concatenate_audioclips(clips)
            scene_audio.write_audiofile(str(voice_file), logger=None)
            scene_audio.close()
            return voice_file, enriched
        finally:
            for c in clips:
                try: c.close()
                except Exception: pass

    # ── BGM ────────────────────────────────────────────────────────────────────

    def _get_mood_query(self, scene: Dict) -> str:
        text = " ".join(
            d.get("line", "") for d in scene.get("dialogue", []) if isinstance(d, dict)
        )
        return self.mood_analyzer.generate_bgm_query(
            scene_description=text,
            location=scene.get("location", ""),
            duration=max(20, len(scene.get("dialogue", [])) * 4),
        )

    def _get_global_bgm_query(self, scenes: List[Dict]) -> str:
        if not scenes:
            return "ambient background music"

        snippets: List[str] = []
        for scene in scenes[:3]:
            scene_text = " ".join(
                d.get("line", "") for d in scene.get("dialogue", []) if isinstance(d, dict)
            ).strip()
            if scene_text:
                snippets.append(scene_text)

        if snippets:
            return self.mood_analyzer.generate_bgm_query(
                scene_description=" ".join(snippets),
                location=", ".join(
                    str(scene.get("location", "")) for scene in scenes[:3] if scene.get("location")
                ),
                duration=max(30, len(scenes) * 6),
            )
        return "ambient background music"

    def _resolve_global_bgm_source(self, bgm_query: str) -> Optional[Path]:
        bgm_out = self.run_manager.get_audio_output_dir() / "bgm_source.mp3"
        cached_bgm = self.run_manager.get_cached_bgm(bgm_query, scope="global")
        if cached_bgm and cached_bgm.exists():
            self.bgm_metadata = {
                "source": "cache",
                "query": bgm_query,
                "query_used": bgm_query,
                "name": cached_bgm.name,
                "path": str(cached_bgm),
            }
            logger.info(f"[Audio] Cache Hit for global BGM query '{bgm_query}' -> {cached_bgm.name}")
            return cached_bgm

        path, meta = search_and_download_bgm(
            mood_query=bgm_query,
            output_path=bgm_out,
            api_key=self.freesound_api_key,
            use_fallback=True,
        )
        if path and path.exists():
            self.bgm_metadata = meta or {"source": "fallback", "query": bgm_query}
            self.bgm_metadata.setdefault("query", bgm_query)
            self.bgm_metadata.setdefault("query_used", bgm_query)
            if meta and meta.get("source") == "freesound":
                self.run_manager.save_bgm_to_cache(bgm_query, path, scope="global")
            return path

        fallback = BGMLocator.get_fallback_bgm()
        if fallback:
            self.bgm_metadata = {
                "source": "local_fallback",
                "query": bgm_query,
                "query_used": "local_fallback",
                "name": fallback.name,
                "path": str(fallback),
            }
            logger.warning(f"[Audio] Using local fallback BGM: {fallback.name}")
            return fallback

        self.bgm_metadata = {
            "source": "silence",
            "query": bgm_query,
            "query_used": "none",
        }
        logger.warning("[Audio] No BGM source available; continuing without BGM")
        return None

    def _render_global_bgm(self, bgm_source: Optional[Path], total_duration_ms: int) -> Optional[Path]:
        if not bgm_source or not bgm_source.exists() or total_duration_ms <= 0:
            return None

        try:
            source = _decode_audio_to_segment(bgm_source)
            source = _trim_leading_silence(source)
            if len(source) <= 0:
                logger.warning("[Audio] BGM source is empty after trimming silence")
                return None

            target_ms = max(1, int(total_duration_ms))
            looped = AudioSegment.empty()
            while len(looped) < target_ms:
                looped += source
            looped = looped[:target_ms]
            if len(looped) > 1500:
                looped = looped.fade_out(1500)
            if self.bgm_volume and self.bgm_volume != 1.0:
                gain_db = 20.0 * math.log10(max(self.bgm_volume, 0.001))
                looped = looped.apply_gain(gain_db)

            bgm_out = self.run_manager.get_audio_output_dir() / "bgm_final.mp3"
            _export_segment_as_mp3(looped, bgm_out)
            logger.info(f"[Audio] Global BGM rendered for {target_ms / 1000:.1f}s -> {bgm_out.name}")
            return bgm_out
        except Exception as e:
            logger.warning(f"[Audio] Failed to render global BGM: {e}")
            return None

    def _mix_master_with_bgm(self, voice_master: Optional[Path], bgm_track: Optional[Path]) -> Optional[Path]:
        if not voice_master or not Path(voice_master).exists():
            return bgm_track if bgm_track and bgm_track.exists() else None
        if not bgm_track or not bgm_track.exists():
            return voice_master

        try:
            voice = _decode_audio_to_segment(voice_master)
            bgm = _decode_audio_to_segment(bgm_track)
            if len(bgm) < len(voice):
                repeats = (len(voice) // max(1, len(bgm))) + 1
                bgm = bgm * repeats
            bgm = bgm[: len(voice)]
            if len(bgm) > 1500:
                bgm = bgm.fade_out(1500)
            mixed = voice.overlay(bgm)
            _export_segment_as_mp3(mixed, voice_master)
            logger.info(f"[Audio] Master track mixed with shared BGM: {Path(voice_master).name}")
            return voice_master
        except Exception as e:
            logger.warning(f"[Audio] Failed to mix master with BGM: {e}; using voice master only")
            return voice_master

    # ── Layer ─────────────────────────────────────────────────────────────────

    def _layer(self, voice_file: Path, bgm_file: Path, scene_id: int) -> Path:
        out = self.run_manager.get_audio_scene_dir(scene_id) / f"scene{scene_id:02d}_composed.mp3"
        MP, afx = _load_moviepy()
        voice = bgm = None
        try:
            voice = MP.AudioFileClip(str(voice_file))
            bgm   = MP.AudioFileClip(str(bgm_file))
            bgm_looped = bgm.with_effects([afx.AudioLoop(duration=voice.duration)])
            bgm_quiet  = bgm_looped.with_effects([afx.MultiplyVolume(0.2)])
            combined   = MP.CompositeAudioClip([bgm_quiet, voice])
            combined.write_audiofile(str(out), logger=None)
            logger.info(f"[Audio] Composed scene {scene_id}: {out.name}")
            return out
        except Exception as e:
            logger.error(f"[Audio] Layer failed scene {scene_id}: {e} — voice only")
            return voice_file
        finally:
            for c in [voice, bgm]:
                try:
                    if c: c.close()
                except Exception: pass

    # ── Master track ──────────────────────────────────────────────────────────

    def _master_track(self, scene_files: List[Path]) -> Optional[Path]:
        if not scene_files:
            return None
        MP, _ = _load_moviepy()
        clips = []
        try:
            for f in scene_files:
                try:
                    clips.append(MP.AudioFileClip(str(f)))
                except Exception as e:
                    logger.warning(f"[Audio] Cannot load {f}: {e}")
            if not clips:
                return None
            master_file = self.run_manager.get_master_audio_path()
            master = MP.concatenate_audioclips(clips)
            master.write_audiofile(str(master_file), logger=None)
            logger.info(f"[Audio] Master track: {master.duration:.1f}s -> {master_file.name}")
            return master_file
        finally:
            for c in clips:
                try: c.close()
                except Exception: pass

    # ── Main process ──────────────────────────────────────────────────────────

    async def process(self) -> Dict[str, Any]:
        if not self.load_phase1_data():
            return {"status": "failure", "error": "Failed to load Phase 1 data"}

        dialogues = self._extract_dialogues()
        if not dialogues:
            return {"status": "failure", "error": "No dialogues found"}

        scenes = self.scene_manifest.get("scenes", [])
        scene_files: List[Path] = []
        cumulative_ms = 0
        MP, _ = _load_moviepy()
        self.global_bgm_query = self._get_global_bgm_query(scenes)
        self.global_bgm_source = self._resolve_global_bgm_source(self.global_bgm_query)

        for scene in scenes:
            scene_id = scene.get("scene_id")
            location = scene.get("location", "Unknown")
            logger.info(f"\n{'─'*60}\nSCENE {scene_id}: {location}\n{'─'*60}")

            scene_dialogues = [d for d in dialogues if d["scene_id"] == scene_id]
            if not scene_dialogues:
                continue

            voice_file, enriched = await self._synthesize_scene(scene_dialogues, scene_id)
            if not voice_file or not voice_file.exists():
                logger.warning(f"[Audio] Skipping scene {scene_id} — no voice audio")
                continue

            composed = voice_file

            if composed and composed.exists():
                scene_files.append(composed)
                try:
                    clip = MP.AudioFileClip(str(composed))
                    scene_dur_ms = int(clip.duration * 1000)
                    clip.close()
                    line_cursor = cumulative_ms
                    for d in enriched:
                        dur = d.get("duration_ms", 1000)
                        self.cumulative_timing.append({
                            "scene_id":    scene_id,
                            "speaker":     d["speaker"],
                            "text":        d["text"],
                            "voice":       d["voice"],
                            "start_ms":    line_cursor,
                            "end_ms":      line_cursor + dur,
                            "duration_ms": dur,
                            "cumulative_start_ms": cumulative_ms,
                            "scene_duration_ms":   scene_dur_ms,
                            "bgm_used":    bool(self.global_bgm_source),
                            "audio_file":  str(composed),
                            "individual_audio_file": d.get("audio_file", ""),
                        })
                        line_cursor += dur
                    cumulative_ms += scene_dur_ms
                except Exception as e:
                    logger.warning(f"[Audio] Duration read failed scene {scene_id}: {e}")

        if not scene_files:
            return {"status": "failure", "error": "No scene audio generated"}

        voice_master = self._master_track(scene_files)
        bgm_track = self._render_global_bgm(self.global_bgm_source, cumulative_ms)
        master = self._mix_master_with_bgm(voice_master, bgm_track)
        manifest_path = self.run_manager.save_timing_manifest(self.cumulative_timing)
        bgm_meta_path = self.run_manager.save_bgm_metadata(
            {
                "mode": "single_global_track",
                "query": self.global_bgm_query,
                "source": self.bgm_metadata,
                "global_bgm_source": str(self.global_bgm_source) if self.global_bgm_source else None,
                "final_bgm_track": str(bgm_track) if bgm_track else None,
                "total_video_duration_ms": cumulative_ms,
            }
        )
        summary = {
            "timestamp":        datetime.now().isoformat(),
            "run_id":           self.run_manager.current_run_id,
            "total_scenes":     len(scenes),
            "scenes_processed": len(scene_files),
            "scenes_with_bgm":  1 if bgm_track else 0,
            "master_audio":     str(master) if master else None,
            "character_voices": self.voice_mapper.get_all_character_voices(),
        }
        self.run_manager.save_phase2_summary(summary)
        self.run_manager.save_phase2_config({
            "phase1_data_dir": str(self.phase1_data_dir),
            "freesound_available": bool(self.freesound_api_key),
            "audio_engine": "moviepy+edge-tts",
            "voice_mappings": self.voice_mapper.get_all_character_voices(),
            "bgm_mode": "single_global_track",
            "global_bgm_query": self.global_bgm_query,
            "global_bgm_source": str(self.global_bgm_source) if self.global_bgm_source else None,
            "final_bgm_track": str(bgm_track) if bgm_track else None,
            "total_video_duration_ms": cumulative_ms,
        })

        logger.info("\n✨ PHASE 2 COMPLETE")
        return {
            "status":               "success",
            "run_id":               self.run_manager.current_run_id,
            "total_scenes":         len(scenes),
            "scenes_processed":     len(scene_files),
            "scenes_with_bgm":      1 if bgm_track else 0,
            "total_duration_ms":    cumulative_ms,
            "master_audio_track":   str(master) if master else None,
            "output_directory":     str(self.run_manager.current_run_dir),
            "timing_manifest_path": str(manifest_path),
            "character_voices_used": self.voice_mapper.get_all_character_voices(),
            "bgm_metadata":         {
                "mode": "single_global_track",
                "query": self.global_bgm_query,
                "source": self.bgm_metadata,
                "global_bgm_source": str(self.global_bgm_source) if self.global_bgm_source else None,
                "final_bgm_track": str(bgm_track) if bgm_track else None,
                "total_video_duration_ms": cumulative_ms,
            },
        }


# ── Backward-compat alias ──────────────────────────────────────────────────────
AudioAgent = EnhancedAudioAgent


async def run_audio_agent(
    phase1_dir: str = "data/outputs/Phase1",
    phase2_dir: str = "data/outputs/Phase2",
    custom_voices: Optional[Dict[str, str]] = None,
    freesound_api_key: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict:
    agent = EnhancedAudioAgent(phase1_dir, phase2_dir, custom_voices, freesound_api_key, run_id)
    return await agent.process()


if __name__ == "__main__":
    import sys
    result = asyncio.run(run_audio_agent())
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("status") == "success" else 1)
