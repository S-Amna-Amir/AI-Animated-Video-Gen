"""
Base MCP Tool Interface
All tools in the MCP layer must inherit from BaseTool.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    name: str = "base_tool"
    description: str = "Abstract base tool"

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        ...

    def __repr__(self):
        return f"<Tool: {self.name}>"
