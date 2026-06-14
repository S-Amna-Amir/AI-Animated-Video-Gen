"""
mcp/tool_registry.py
--------------------
Central registry for all MCP tools.

Tools self-register by calling ToolRegistry.register() (done at import
time inside each tool module). Agents discover tools at runtime via
ToolRegistry.get(), satisfying the requirement that no tool is hardcoded.
"""
import logging
from typing import Dict, Type

from mcp.base_tool import BaseTool

logger = logging.getLogger(__name__)

_registry: Dict[str, BaseTool] = {}


class ToolRegistry:
    """Singleton-style registry accessed via class methods."""

    @classmethod
    def register(cls, tool_instance: BaseTool) -> None:
        """Register a tool instance. Called at module import time."""
        if not tool_instance.name:
            raise ValueError(f"Tool {type(tool_instance)} has no 'name' set.")
        _registry[tool_instance.name] = tool_instance
        logger.debug(f"[Registry] Registered tool: '{tool_instance.name}'")

    @classmethod
    def get(cls, name: str) -> BaseTool:
        """
        Discover a tool by name.

        Raises:
            ValueError: If the tool is not registered.
        """
        if name not in _registry:
            available = list(_registry.keys())
            raise ValueError(
                f"[Registry] Tool '{name}' not found.\n"
                f"Available tools: {available}"
            )
        logger.info(f"[Registry] Tool discovered: '{name}'")
        return _registry[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        return list(_registry.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in _registry
