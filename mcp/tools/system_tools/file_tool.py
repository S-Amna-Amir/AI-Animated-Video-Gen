"""
mcp/tools/system_tools/file_tool.py
-------------------------------------
MCP tool: save_json_file

Saves a JSON-serializable object to disk.
Used by orchestrator nodes to persist final outputs.
"""
import json
from pathlib import Path
from typing import Any, Dict

from mcp.base_tool import BaseTool
from mcp.tool_registry import ToolRegistry


class SaveJsonFileTool(BaseTool):
    name = "save_json_file"
    description = "Saves a Python object as a JSON file at the given path."
    owner_agent = "all"
    input_schema = {
        "data":     {"type": "object", "required": True},
        "filepath": {"type": "string", "required": True},
    }

    def execute(self, data: Any, filepath: str, **_) -> str:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(path.resolve())


ToolRegistry.register(SaveJsonFileTool())
