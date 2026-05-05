"""
File Tool — MCP system utility for reading and writing JSON / text artefacts.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from mcp.base_tool import BaseTool


class FileTool(BaseTool):
    name = "file_tool"
    description = "Reads and writes JSON and plain-text files to the data directory."

    def run(self, action: str, path: str, data: Any = None) -> Any:
        """
        Args:
            action: 'read_json' | 'write_json' | 'read_text' | 'write_text'
            path:   File path (relative or absolute).
            data:   Data to write (for write actions).
        """
        if action == "read_json":
            return self._read_json(path)
        elif action == "write_json":
            return self._write_json(path, data)
        elif action == "read_text":
            return Path(path).read_text(encoding="utf-8")
        elif action == "write_text":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(data, encoding="utf-8")
            return path
        else:
            raise ValueError(f"Unknown FileTool action: {action}")

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, data: Any) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if hasattr(data, "dict"):
                json.dump(data.dict(), f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return path
