"""
mcp/tools/video_tools/comfy_client.py
----------------------------------------
Hugging Face Inference API client for image generation.
Primary model: FLUX.1-schnell | Fallback: stable-diffusion-v1-5
"""
import hashlib
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

HF_API_TOKEN    = os.getenv("HF_API_TOKEN")
PRIMARY_MODEL   = "black-forest-labs/FLUX.1-schnell"
FALLBACK_MODEL  = "runwayml/stable-diffusion-v1-5"
BASE_URL        = "https://router.huggingface.co/hf-inference/models/"

CHARACTER_SEEDS = {"JACK": 42, "RACHEL": 137, "VLADIMIR": 256}


def generate_image(
    positive_prompt: str,
    negative_prompt: str,
    scene_id: str,
    character_name: str = "",
) -> bytes:
    if not HF_API_TOKEN:
        raise EnvironmentError("HF_API_TOKEN not set in .env")

    seed = CHARACTER_SEEDS.get(
        character_name,
        int(hashlib.md5(character_name.encode()).hexdigest(), 16) % (2**32 - 1)
        if character_name else 42,
    )
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": positive_prompt,
        "parameters": {
            "negative_prompt": negative_prompt,
            "num_inference_steps": 20,
            "guidance_scale": 7.5,
            "width": 512, "height": 512,
            "seed": seed,
        },
    }

    url = f"{BASE_URL}{PRIMARY_MODEL}"
    loading_retries = 3
    rate_retries    = 1

    while True:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            raise ConnectionError(f"HF API connection failed: {e}") from e

        if resp.status_code == 200:
            return resp.content
        elif resp.status_code == 503:
            if loading_retries > 0:
                logger.warning("HF model loading (503), waiting 20s … retries=%d", loading_retries)
                time.sleep(20)
                loading_retries -= 1
            else:
                raise RuntimeError("HF API 503 timeout exceeded")
        elif resp.status_code == 429:
            if rate_retries > 0:
                logger.warning("HF rate limited (429), waiting 60s … retries=%d", rate_retries)
                time.sleep(60)
                rate_retries -= 1
            else:
                raise RuntimeError("HF API 429 rate limit exceeded")
        else:
            raise RuntimeError(f"HF API {resp.status_code} for scene {scene_id}: {resp.text[:300]}")


def save_image(image_bytes: bytes, save_path: str) -> str:
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    logger.info("Image saved → %s", path)
    return str(path)


def check_api_connection() -> bool:
    try:
        return requests.get("https://huggingface.co", timeout=10).status_code == 200
    except Exception:
        return False
