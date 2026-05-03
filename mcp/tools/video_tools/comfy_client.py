"""Hugging Face Inference API client helpers for Phase 3 video tools."""

import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
if not HF_API_TOKEN:
    raise EnvironmentError("HF_API_TOKEN not found in environment. Please add it to your .env file.")

PRIMARY_MODEL = "black-forest-labs/FLUX.1-schnell"
FALLBACK_MODEL = "runwayml/stable-diffusion-v1-5"
BASE_API_URL = "https://router.huggingface.co/hf-inference/models/"


def generate_image(positive_prompt: str, negative_prompt: str, scene_id: str) -> bytes:
    """
    Generate an image using the Hugging Face Inference API.
    Handles rate limits (429) and model loading (503).
    """
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": positive_prompt,
        "parameters": {
            "negative_prompt": negative_prompt,
            "num_inference_steps": 20,
            "guidance_scale": 7.5,
            "width": 512,
            "height": 512
        }
    }

    url = f"{BASE_API_URL}{PRIMARY_MODEL}"
    
    # Retry states
    loading_retries = 3
    rate_limit_retries = 1

    while True:
        logger.info("Requesting image generation for scene_id=%s via Hugging Face API", scene_id)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as exc:
            logger.exception("Connection failure while calling Hugging Face API")
            raise ConnectionError(f"Failed to connect to Hugging Face API: {exc}") from exc

        if response.status_code == 200:
            logger.info("Image generated successfully for scene_id=%s", scene_id)
            return response.content
            
        elif response.status_code == 503:
            if loading_retries > 0:
                logger.warning("Model is loading (503). Waiting 20 seconds. Retries left: %d", loading_retries)
                time.sleep(20)
                loading_retries -= 1
                continue
            else:
                raise RuntimeError("Hugging Face API model loading timeout (503) exceeded retries.")
                
        elif response.status_code == 429:
            if rate_limit_retries > 0:
                logger.warning("Rate limited (429). Waiting 60 seconds. Retries left: %d", rate_limit_retries)
                time.sleep(60)
                rate_limit_retries -= 1
                continue
            else:
                raise RuntimeError("Hugging Face API rate limit (429) exceeded retries.")
                
        else:
            raise RuntimeError(
                f"Hugging Face API failed ({response.status_code}) for scene_id={scene_id}: "
                f"{response.text[:500]}"
            )


def save_image(image_bytes: bytes, save_path: str) -> str:
    """
    Save image bytes to disk and return saved path.
    """
    path = Path(save_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
    except OSError as exc:
        logger.exception("Failed to save image to %s", save_path)
        raise OSError(f"Failed to save image to '{save_path}': {exc}") from exc

    logger.info("Image saved to %s", path)
    return str(path)


def check_api_connection() -> bool:
    """
    Simple GET to https://huggingface.co to verify internet connection.
    """
    try:
        response = requests.get("https://huggingface.co", timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

def queue_prompt(workflow_json: dict) -> str:
    """Stub retained for test compatibility. Use generate_image() instead."""
    raise NotImplementedError(
        "queue_prompt is deprecated. Use generate_image() for HF API."
    )
