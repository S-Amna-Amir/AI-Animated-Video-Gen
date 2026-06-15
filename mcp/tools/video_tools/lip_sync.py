"""
mcp/tools/video_tools/lip_sync.py
------------------------------------
Wav2Lip neural lip sync with OpenCV + FFmpeg fallbacks.

Setup for real Wav2Lip (optional):
  1. git clone https://github.com/Rudrabha/Wav2Lip
  2. Download wav2lip_gan.pth -> project/checkpoints/
  3. pip install librosa==0.10.2 opencv-python torch
  4. In .env:
       WAV2LIP_CHECKPOINT=checkpoints/wav2lip_gan.pth
       WAV2LIP_REPO_PATH=Wav2Lip

Without setup, falls back to OpenCV mux (frames + audio, no mouth movement).
"""
import logging
import os
import struct
import subprocess
import wave
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

WAV2LIP_IMG_SIZE = 96
MEL_STEP_SIZE    = 16
DEFAULT_FPS      = 25.0

_wav2lip_model = None
_wav2lip_device = None

def _get_wav2lip_model():
    """Load Wav2Lip once and cache it for the process lifetime."""
    global _wav2lip_model, _wav2lip_device
    if _wav2lip_model is not None:
        return _wav2lip_model, _wav2lip_device

    ckpt = os.getenv("WAV2LIP_CHECKPOINT", "checkpoints/wav2lip_gan.pth")
    if not Path(ckpt).exists():
        return None, None

    try:
        import torch, importlib.util, sys
        repo = os.getenv("WAV2LIP_REPO_PATH", "Wav2Lip")
        if repo not in sys.path:
            sys.path.insert(0, str(Path(repo).resolve()))
        from models import Wav2Lip as W2L

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model  = W2L()
        ckpt_data = torch.load(ckpt, map_location=device)
        model.load_state_dict(ckpt_data["state_dict"])
        model = model.to(device).eval()
        logger.info("[LipSync] Wav2Lip loaded on %s (cached for session)", device)

        _wav2lip_model  = model
        _wav2lip_device = device
        return model, device
    except Exception as e:
        logger.warning("[LipSync] Wav2Lip model load failed: %s", e)
        return None, None

def align_lip_sync(
    scene_id: int,
    audio_path: str,
    frame_dir: str,
    output_video_path: str,
    fps: float = DEFAULT_FPS,
) -> Dict:
    """
    Try backends in order: Wav2Lip -> OpenCV mux -> FFmpeg mux -> placeholder.
    Returns a LipSyncResult dict.
    """
    Path(output_video_path).parent.mkdir(parents=True, exist_ok=True)

    for backend in (_try_wav2lip, _try_opencv_mux, _try_ffmpeg_mux):
        result = backend(scene_id, audio_path, frame_dir, output_video_path, fps)
        if result:
            return result

    logger.error("[LipSync] All backends failed for scene %02d", scene_id)
    return {
        "scene_id": scene_id, "output_video_path": output_video_path,
        "audio_path": audio_path, "frame_count": 0,
        "duration_seconds": 0.0, "sync_confidence": 0.0, "backend": "placeholder",
    }


# ── Backend 1: Wav2Lip ────────────────────────────────────────────────────────

def _try_wav2lip(scene_id, audio_path, frame_dir, output_video_path, fps):
    model, device = _get_wav2lip_model()
    if model is None:
        if not getattr(_try_wav2lip, "_warned", False):
            logger.info(
                "[LipSync] Wav2Lip not available. "
                "Falling back to OpenCV mux. See lip_sync.py docstring to enable."
            )
            _try_wav2lip._warned = True
        return None

    try:
        import cv2, numpy as np, torch, librosa, importlib.util, sys

        repo = os.getenv("WAV2LIP_REPO_PATH", "Wav2Lip")
        spec = importlib.util.spec_from_file_location(
            "wav2lip_audio", str(Path(repo) / "audio.py")
        )
        wa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wa)

        frame_paths = sorted(Path(frame_dir).glob("frame_*.png"))
        if not frame_paths:
            return None

        wav, _ = librosa.load(audio_path, sr=16000, mono=True)

        # Compute mel — handle API differences across Wav2Lip versions
        try:
            mel = wa.melspectrogram(wav)
        except TypeError:
            try:
                mel = wa.melspectrogram(wav, getattr(wa, 'num_mels', 80))
            except Exception:
                mel = librosa.feature.melspectrogram(
                    y=wav, sr=16000, n_fft=800, hop_length=200,
                    win_length=800, n_mels=80, fmax=7600
                )
                mel = librosa.power_to_db(mel, ref=np.max).astype(np.float32)

        mel_chunks = _align_mel(mel, len(frame_paths), fps)
        actual_n   = min(len(frame_paths), len(mel_chunks))

        detector   = _load_face_detector()
        out_frames = []
        batch_size = 8

        for bs in range(0, actual_n, batch_size):
            be = min(bs + batch_size, actual_n)
            imgs, mels_batch, origs, rects = [], [], [], []
            for idx in range(bs, be):
                bgr = cv2.imread(str(frame_paths[idx]))
                if bgr is None:
                    continue
                rect = _detect_face(bgr, detector) or (
                    bgr.shape[1]//4, bgr.shape[0]//4,
                    bgr.shape[1]*3//4, bgr.shape[0]*3//4
                )
                x1, y1, x2, y2 = rect
                face   = cv2.resize(bgr[y1:y2, x1:x2], (WAV2LIP_IMG_SIZE, WAV2LIP_IMG_SIZE))
                masked = face.copy()
                masked[WAV2LIP_IMG_SIZE//2:] = 0
                imgs.append(np.concatenate([masked, face], axis=2))
                mels_batch.append(mel_chunks[idx])
                origs.append(bgr)
                rects.append(rect)

            if not imgs:
                continue

            it = torch.FloatTensor(np.array(imgs)).permute(0,3,1,2).to(device) / 255.0
            mt = torch.FloatTensor(np.array(mels_batch)).unsqueeze(1).to(device)
            with torch.no_grad():
                pred = model(mt, it)   # reuse cached model — no reload
            pred_np = (pred.permute(0,2,3,1).cpu().numpy() * 255).astype(np.uint8)

            for orig, (x1,y1,x2,y2), synth in zip(origs, rects, pred_np):
                fh, fw = y2-y1, x2-x1
                rf = orig.copy()
                rf[y1:y2, x1:x2] = cv2.resize(synth, (fw, fh))
                out_frames.append(rf)

            logger.info(
                "[LipSync] Wav2Lip scene %s: batch %d-%d done", scene_id, bs, be-1
            )

        if not out_frames:
            return None

        dur = _write_video_with_audio(out_frames, audio_path, output_video_path, fps)
        return {
            "scene_id": scene_id,
            "output_video_path": os.path.abspath(output_video_path),
            "audio_path": audio_path,
            "frame_count": len(out_frames),
            "duration_seconds": round(dur, 3),
            "sync_confidence": 0.92,
            "backend": "wav2lip",
        }

    except Exception as e:
        logger.warning("[LipSync] Wav2Lip failed scene %s: %s", scene_id, e)
        return None


def _align_mel(mel, n_frames, fps):
    import numpy as np
    T, cs = mel.shape[1], MEL_STEP_SIZE
    chunks = []
    for i in range(n_frames):
        start = max(0, min(int((i/n_frames)*(T-cs)), T-cs))
        chunks.append(mel[:, start:start+cs])
    return chunks


def _load_face_detector():
    try:
        import cv2
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        return None if det.empty() else det
    except Exception:
        return None


def _detect_face(frame_bgr, detector) -> Optional[tuple]:
    if not detector:
        return None
    try:
        import cv2
        gray  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.1, 4, minSize=(40,40))
        if len(faces) == 0:
            return None
        x,y,w,h = max(faces, key=lambda f: f[2]*f[3])
        return (x,y,x+w,y+h)
    except Exception:
        return None


# ── Backend 2: OpenCV mux ─────────────────────────────────────────────────────

def _try_opencv_mux(scene_id, audio_path, frame_dir, output_video_path, fps):
    try:
        import cv2
        frames = sorted(Path(frame_dir).glob("frame_*.png"))
        if not frames:
            return None

        audio_dur = _wav_duration(audio_path)
        req_frames = max(len(frames), int(audio_dur * fps) + 1)
        sample = cv2.imread(str(frames[0]))
        h, w   = sample.shape[:2]

        tmp    = output_video_path.replace(".mp4", "_noaudio.mp4")
        writer = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w,h))
        for fp in frames:
            f = cv2.imread(str(fp))
            if f is not None:
                writer.write(f)
        if req_frames > len(frames):
            last = cv2.imread(str(frames[-1]))
            for _ in range(len(frames), req_frames):
                if last is not None: writer.write(last)
        writer.release()

        import imageio_ffmpeg as _iio_ffmpeg
        subprocess.run(
            [_iio_ffmpeg.get_ffmpeg_exe(),"-y","-i",tmp,"-i",audio_path,"-c:v","copy","-c:a","aac",output_video_path],
            capture_output=True, timeout=120,
        )
        Path(tmp).unlink(missing_ok=True)
        return {
            "scene_id": scene_id, "output_video_path": os.path.abspath(output_video_path),
            "audio_path": audio_path, "frame_count": req_frames,
            "duration_seconds": round(max(audio_dur, req_frames/fps), 3),
            "sync_confidence": 0.78, "backend": "opencv_mux",
        }
    except Exception as e:
        logger.debug("[LipSync] OpenCV mux failed: %s", e)
        return None


# ── Backend 3: FFmpeg mux ─────────────────────────────────────────────────────

def _try_ffmpeg_mux(scene_id, audio_path, frame_dir, output_video_path, fps):
    try:
        import imageio_ffmpeg as _iio_ffmpeg
        pattern = str(Path(frame_dir) / "frame_%04d.png")
        r = subprocess.run(
            [_iio_ffmpeg.get_ffmpeg_exe(),"-y","-framerate",str(fps),"-i",pattern,"-i",audio_path,
             "-c:v","libx264","-c:a","aac","-pix_fmt","yuv420p",output_video_path],
            capture_output=True, timeout=300,
        )
        if r.returncode != 0:
            return None
        frames  = list(Path(frame_dir).glob("frame_*.png"))
        return {
            "scene_id": scene_id, "output_video_path": os.path.abspath(output_video_path),
            "audio_path": audio_path, "frame_count": len(frames),
            "duration_seconds": round(len(frames)/fps, 3),
            "sync_confidence": 0.75, "backend": "ffmpeg",
        }
    except Exception as e:
        logger.debug("[LipSync] FFmpeg mux failed: %s", e)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "r") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _write_video_with_audio(frames, audio_path, output_path, fps) -> float:
    import cv2
    h, w = frames[0].shape[:2]
    tmp  = output_path.replace(".mp4", "_raw.mp4")
    wr   = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w,h))
    for f in frames: wr.write(f)
    wr.release()
    import imageio_ffmpeg as _iio_ffmpeg
    subprocess.run(
        [_iio_ffmpeg.get_ffmpeg_exe(),"-y","-i",tmp,"-i",audio_path,"-c:v","copy","-c:a","aac","-shortest",output_path],
        capture_output=True, timeout=120,
    )
    Path(tmp).unlink(missing_ok=True)
    return len(frames)/fps
