"""
mcp/__init__.py
---------------
Importing this package registers all MCP tools for the current phase.
Agents only need to `import mcp` (or import from mcp.tool_executor)
to have the full tool registry available.
"""
# ── Phase 1 tools ──────────────────────────────────────────────────────────────
import mcp.tools.llm_tools.text_generator      # generate_script_segment
import mcp.tools.llm_tools.json_structurer     # validate_script_structure
import mcp.tools.system_tools.state_tool       # commit_memory, query_memory
import mcp.tools.system_tools.file_tool        # save_json_file
import mcp.tools.vision_tools.image_gen_tool   # generate_image, query_stock_footage

from mcp.tool_executor import invoke_tool
from mcp.tool_registry import ToolRegistry

__all__ = ["invoke_tool", "ToolRegistry"]
