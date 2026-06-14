"""
mcp/base_tool.py
----------------
Abstract base class for every MCP tool.

All tools registered in the registry must inherit from BaseTool and
implement the `execute` method. This guarantees a uniform interface for
the tool_executor and agents.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """Abstract base for all MCP tools."""

    # Subclasses MUST set these class-level attributes
    name: str = ""
    description: str = ""
    owner_agent: str = "all"

    # JSON-schema-style dict describing required/optional inputs
    input_schema: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """
        Run the tool with the provided keyword arguments.

        Args:
            **kwargs: Tool-specific inputs validated against input_schema.

        Returns:
            Tool-specific output (type documented per tool).
        """

    def validate_inputs(self, inputs: Dict[str, Any]) -> None:
        """
        Raise ValueError if any required input is missing.
        Called automatically by ToolExecutor before execute().
        """
        for field, spec in self.input_schema.items():
            if isinstance(spec, dict) and spec.get("required", False):
                if field not in inputs:
                    raise ValueError(
                        f"[MCP:{self.name}] Missing required input '{field}'."
                    )
