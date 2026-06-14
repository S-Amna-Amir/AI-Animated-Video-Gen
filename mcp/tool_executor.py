"""
mcp/tool_executor.py
--------------------
Single entry point for all agent tool calls.

Agents call:
    invoke_tool("tool_name", {"param": value, ...})

The executor discovers the tool, validates inputs, delegates to the tool's
execute() method, and returns the result. This is the MCP dispatch layer.
"""
import logging
from typing import Any, Dict

from mcp.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def invoke_tool(tool_name: str, inputs: Dict[str, Any]) -> Any:
    """
    Discover and invoke a registered MCP tool.

    Args:
        tool_name: Registered name of the tool.
        inputs:    Dict of input parameters.

    Returns:
        Tool output (type varies per tool).

    Raises:
        ValueError: Tool not found or required input missing.
        RuntimeError: Tool execution failed.
    """
    # Step 1: Discover (runtime resolution — never hardcoded)
    tool = ToolRegistry.get(tool_name)

    # Step 2: Validate required inputs
    tool.validate_inputs(inputs)

    # Step 3: Execute
    logger.info(f"[Executor] Invoking '{tool_name}' | inputs: {list(inputs.keys())}")
    try:
        result = tool.execute(**inputs)
        logger.info(f"[Executor] '{tool_name}' completed successfully.")
        return result
    except Exception as e:
        logger.error(f"[Executor] '{tool_name}' failed: {e}")
        raise RuntimeError(f"Tool '{tool_name}' raised an error: {e}") from e
