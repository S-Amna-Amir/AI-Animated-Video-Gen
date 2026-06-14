"""
mcp/tools/video_tools/__init__.py
-----------------------------------
Exposes animator, image_generator, video_compositor as the public API
for VideoAgent. All imports are lazy-safe (no heavy deps at import time).
"""
from . import animator
from . import image_generator
from . import video_compositor

__all__ = ["animator", "image_generator", "video_compositor"]
