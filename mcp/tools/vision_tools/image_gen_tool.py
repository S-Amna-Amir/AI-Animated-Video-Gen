"""
mcp/tools/vision_tools/image_gen_tool.py
------------------------------------------
MCP tool: generate_image

Synthesizes a character reference image. Tries backends in order:
  1. Stable Diffusion 3 (local via diffusers - from Hugging Face)
  2. Placeholder PNG (Pillow — always works)
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.base_tool import BaseTool
from mcp.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_CLIP_WORD_LIMIT = 60   # SD CLIP encoder ≈ 77 tokens


class GenerateImageTool(BaseTool):
    name = "generate_image"
    description = (
        "Synthesizes a character reference image from a text prompt. "
        "Saves the PNG to output_path and returns the absolute path."
    )
    owner_agent = "story_agent"
    input_schema = {
        "prompt":          {"type": "string", "required": True},
        "output_path":     {"type": "string", "required": True},
        "negative_prompt": {"type": "string", "required": False,
                            "default": "blurry, low quality, distorted"},
        "steps":           {"type": "integer", "required": False, "default": 30},
        "character":       {"type": "object",  "required": False, "default": None},
    }

    def execute(
        self,
        prompt: str,
        output_path: str,
        negative_prompt: str = "blurry, low quality, distorted",
        steps: int = 30,
        character: Optional[Dict] = None,
        **_,
    ) -> str:
        # Build final prompt
        if character is not None:
            prompt = self._compress_prompt(character)
        else:
            words = prompt.split()
            if len(words) > _CLIP_WORD_LIMIT:
                prompt = " ".join(words[:_CLIP_WORD_LIMIT])
                logger.warning("[ImageGen] Prompt truncated to 60 words.")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if self._try_stable_diffusion(prompt, output_path, negative_prompt, steps):
            return str(Path(output_path).resolve())
        
        self._placeholder(prompt, output_path)
        return str(Path(output_path).resolve())

    # ── Prompt compression ──────────────────────────────────────────────────

    @staticmethod
    def _compress_prompt(character: Dict) -> str:
        name = character.get("name", "person")
        appearance = character.get("appearance", "")
        sentences = appearance.replace("\n", " ").split(".")
        parts = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if s.lower().startswith(name.lower()):
                idx = s.find(",")
                s = s[idx + 1:].strip() if idx != -1 else ""
            if s:
                parts.append(s)
        short = " ".join(" ".join(parts).split()[:55])
        return (
            f"portrait of {name}, {short}, "
            "cinematic lighting, sharp focus, photorealistic, 8k, detailed face"
        )

    # ── Backend 1: Stable Diffusion ─────────────────────────────────────────

    @staticmethod
    def _try_stable_diffusion(
        prompt: str, output_path: str, negative_prompt: str, steps: int
    ) -> bool:
        try:
            from diffusers import StableDiffusionPipeline
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype  = torch.float16 if device == "cuda" else torch.float32
            
            # Load Stable Diffusion v1.5 from Hugging Face
            pipe   = StableDiffusionPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5", 
                torch_dtype=dtype,
                safety_checker=None  # Disable safety checker for faster generation
            ).to(device)
            
            # Enable memory optimizations
            if device == "cuda":
                pipe.enable_attention_slicing()
            
            image = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                guidance_scale=7.5,
            ).images[0]
            image.save(output_path)
            logger.info(f"[ImageGen] Stable Diffusion image saved → {output_path}")
            return True
        except Exception as e:
            logger.warning(f"[ImageGen] Stable Diffusion unavailable: {e}")
            return False



    # ── Backend 2: Placeholder PNG ───────────────────────────────────────────

    @staticmethod
    def _placeholder(prompt: str, output_path: str) -> None:
        try:
            from PIL import Image, ImageDraw

            w, h = 512, 512
            img  = Image.new("RGB", (w, h), color=(30, 30, 40))
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, w - 10, h - 10], outline=(100, 100, 160), width=3)
            draw.text((w // 2, 80),  "CHARACTER REFERENCE",   fill=(180, 180, 220), anchor="mm")
            draw.text((w // 2, 130), "[PLACEHOLDER IMAGE]",   fill=(120, 120, 160), anchor="mm")
            excerpt = " ".join(prompt.split()[:12])
            draw.text((w // 2, h // 2), excerpt, fill=(200, 200, 200), anchor="mm")
            draw.text((w // 2, h - 60),
                      "Install diffusers & torch for Stable Diffusion",
                      fill=(80, 80, 100), anchor="mm")
            img.save(output_path)
            logger.info(f"[ImageGen] Placeholder PNG saved → {output_path}")
        except ImportError:
            # Absolute fallback: minimal 1×1 black PNG
            _minimal = (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
                b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
                b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
            )
            with open(output_path, "wb") as f:
                f.write(_minimal)
            logger.warning(f"[ImageGen] Minimal PNG fallback saved → {output_path}")


# ── Stock footage reference tool ───────────────────────────────────────────────

class QueryStockFootageTool(BaseTool):
    name = "query_stock_footage"
    description = "Returns a style reference string for a character."
    owner_agent = "story_agent"
    input_schema = {
        "character_name": {"type": "string", "required": True},
        "style":          {"type": "string", "required": False, "default": "cinematic"},
        "traits":         {"type": "array",  "required": False, "default": []},
    }

    def execute(
        self,
        character_name: str,
        style: str = "cinematic",
        traits: list = None,
        **_,
    ) -> str:
        traits = traits or []
        trait_str = ", ".join(traits) if traits else "neutral expression"
        return (
            f"Cinematic {style} portrait reference for '{character_name}': "
            f"{trait_str}, professional lighting, sharp focus, photorealistic."
        )


# Self-register
ToolRegistry.register(GenerateImageTool())
ToolRegistry.register(QueryStockFootageTool())
