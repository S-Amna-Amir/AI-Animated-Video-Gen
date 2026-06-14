"""
mcp/tools/llm_tools/json_structurer.py
----------------------------------------
MCP tool: validate_script_structure

Validates raw screenplay text for correct structural formatting.
Returns a list of validation error strings (empty = passed).
"""
import re
from typing import Any, List

from mcp.base_tool import BaseTool
from mcp.tool_registry import ToolRegistry


class ValidateScriptStructureTool(BaseTool):
    name = "validate_script_structure"
    description = (
        "Validates raw screenplay text for correct structure. "
        "Returns a list of error strings; empty list means validation passed."
    )
    owner_agent = "story_agent"
    input_schema = {
        "script_text": {"type": "string",  "required": True},
        "strict_mode": {"type": "boolean", "required": False, "default": False},
    }

    def execute(
        self,
        script_text: str,
        strict_mode: bool = False,
        **_,
    ) -> List[str]:
        errors: List[str] = []
        lines = script_text.strip().splitlines()

        if not script_text.strip():
            return ["Script is empty."]

        # Check 1: Scene headings
        has_headings = any(
            re.match(r"^(INT\.|EXT\.)\s+.+", l.strip(), re.IGNORECASE)
            for l in lines
        )
        if not has_headings:
            errors.append(
                "No scene headings found. Each scene must start with INT. or EXT. "
                "(e.g. 'INT. OFFICE - DAY')"
            )

        # Check 2: Dialogue speaker labels (ALL CAPS line)
        has_labels = any(
            re.match(r"^[A-Z][A-Z\s]{1,30}$", l.strip())
            for l in lines
            if l.strip()
        )
        if not has_labels:
            errors.append(
                "No dialogue speaker labels found. Speakers must appear as ALL CAPS "
                "on their own line (e.g. 'JOHN')."
            )

        # Check 3: Action descriptions
        non_heading = [
            l for l in lines
            if l.strip()
            and not re.match(r"^(INT\.|EXT\.)\s+", l.strip(), re.IGNORECASE)
            and not re.match(r"^[A-Z][A-Z\s]{1,30}$", l.strip())
        ]
        if not non_heading:
            errors.append(
                "No action descriptions found. Add narrative lines between "
                "scene headings and dialogue."
            )

        if strict_mode:
            heading_count = sum(
                1 for l in lines
                if re.match(r"^(INT\.|EXT\.)\s+", l.strip(), re.IGNORECASE)
            )
            if heading_count < 2:
                errors.append(
                    f"Strict mode: only {heading_count} scene(s) found. "
                    "Minimum 2 required."
                )

        return errors


# Self-register
ToolRegistry.register(ValidateScriptStructureTool())
